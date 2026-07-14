"""DEX Aggregator — unified interface for multi-chain DEX quotes and swaps.

Supports EVM (1inch, Paraswap, 0x) and Solana (Jupiter) through a single API.
Includes fallback routing, per-provider timeout, and health tracking.

Usage:
    agg = DEXAggregator()
    quote = await agg.get_best_quote(Chain.ETHEREUM, "0x...", "0x...", 10**18)
    swap = await agg.get_swap(Chain.ETHEREUM, "0x...", "0x...", 10**18, "0x_wallet")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx


class Chain(Enum):
    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BASE = "base"
    AVALANCHE = "avalanche"
    SOLANA = "solana"


# Chain IDs for 1inch and Paraswap
CHAIN_IDS = {
    Chain.ETHEREUM: 1,
    Chain.BSC: 56,
    Chain.POLYGON: 137,
    Chain.ARBITRUM: 42161,
    Chain.OPTIMISM: 10,
    Chain.BASE: 8453,
    Chain.AVALANCHE: 43114,
}

# Provider priority chains per chain type
# Each entry is a list of (provider_name, method) tuples
# Fallback happens in order if a provider fails
EVM_PROVIDERS = [
    ("1inch", "oneinch_quote"),
    ("paraswap", "paraswap_quote"),
    ("0x", "zeroex_quote"),
]

SOLANA_PROVIDERS = [
    ("jupiter", "jupiter_quote"),
]


@dataclass
class AggregatorConfig:
    """Configuration for DEX aggregator."""

    slippage: float = 0.5  # percentage
    timeout: int = 30  # global timeout per provider call
    max_retries: int = 3
    fallback_enabled: bool = True  # enable fallback chain
    per_provider_timeout: int = 15  # individual provider timeout (shorter than global)

    # EVM aggregator API keys (optional but recommended)
    oneinch_api_key: Optional[str] = None
    paraswap_partner: Optional[str] = None

    # Solana (Jupiter)
    jupiter_api_url: str = "https://quote-api.jup.ag/v6"


class ProviderHealth:
    """Tracks health status of each DEX provider.

    Providers get marked as degraded after consecutive failures,
    and fallback routing skips degraded providers.
    """

    def __init__(self, max_failures: int = 3, cooldown: int = 60):
        self.max_failures = max_failures
        self.cooldown = cooldown
        self._failures: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}
        self._disabled: set[str] = set()

    def record_success(self, provider: str):
        self._failures[provider] = 0
        self._disabled.discard(provider)

    def record_failure(self, provider: str):
        import time

        self._failures[provider] = self._failures.get(provider, 0) + 1
        self._last_failure[provider] = time.time()
        if self._failures[provider] >= self.max_failures:
            self._disabled.add(provider)

    def is_available(self, provider: str) -> bool:
        import time

        if provider not in self._disabled:
            return True
        # Check cooldown
        last_fail = self._last_failure.get(provider, 0)
        if time.time() - last_fail > self.cooldown:
            self._disabled.discard(provider)
            self._failures[provider] = max(0, self._failures.get(provider, 0) - 1)
            return True
        return False

    def reset(self, provider: Optional[str] = None):
        if provider:
            self._failures[provider] = 0
            self._disabled.discard(provider)
            self._last_failure.pop(provider, None)
        else:
            self._failures.clear()
            self._disabled.clear()
            self._last_failure.clear()

    @property
    def active_providers(self) -> list[str]:
        return [p for p in self._failures if p not in self._disabled]

    @property
    def status(self) -> dict[str, str]:
        return {
            p: "disabled" if p in self._disabled else "active"
            for p in self._failures
        }


class DEXAggregator:
    """Multi-chain DEX aggregator — get best quotes across all major DEXes.

    Features:
    - Multi-provider support (1inch, Paraswap, 0x, Jupiter)
    - Fallback routing (auto-failover to next provider)
    - Provider health tracking (degraded providers are skipped)
    - Per-provider timeout
    - Parallel quote fetching with graceful degradation

    Usage:
        agg = DEXAggregator()
        quote = await agg.get_best_quote(Chain.ETHEREUM, "0x...", "0x...", 10**18)
        swap = await agg.get_swap(Chain.ETHEREUM, "0x...", "0x...", 10**18, "0x_wallet")
    """

    def __init__(self, config: Optional[AggregatorConfig] = None):
        self.config = config or AggregatorConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._health = ProviderHealth()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _api_get(
        self,
        url: str,
        params: dict,
        headers: dict | None = None,
        timeout: int | None = None,
    ) -> dict:
        client = await self._get_client()
        t = timeout or self.config.timeout
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, params=params, headers=headers, timeout=t)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.config.max_retries - 1:
                    raise AggregatorError(f"API call failed: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
        return {}

    async def _safe_api_call(
        self,
        provider: str,
        method,  # callable
        *args,
        **kwargs,
    ) -> dict:
        """Make an API call with timeout and health tracking.

        Returns the response on success, or an error dict on failure.
        Health tracking records failures for fallback routing.
        """
        if not self._health.is_available(provider):
            return {"error": f"provider {provider} is degraded (skipped)"}

        try:
            result = await asyncio.wait_for(
                method(*args, **kwargs),
                timeout=self.config.per_provider_timeout,
            )
            self._health.record_success(provider)
            return result
        except (asyncio.TimeoutError, AggregatorError, Exception) as e:
            self._health.record_failure(provider)
            return {"error": f"{provider}: {e}"}

    # ── 1inch ───────────────────────────────────────

    def _oneinch_url(self, chain: Chain, version: int = 6) -> str:
        return f"https://api.1inch.dev/swap/v{version}.0/{CHAIN_IDS[chain]}"

    async def oneinch_quote(
        self,
        chain: Chain,
        src: str,
        dst: str,
        amount: str,
    ) -> dict:
        """Get quote from 1inch."""
        url = f"{self._oneinch_url(chain)}/quote"
        params = {"src": src, "dst": dst, "amount": amount}
        headers = {}
        if self.config.oneinch_api_key:
            headers["Authorization"] = f"Bearer {self.config.oneinch_api_key}"
        return await self._api_get(url, params, headers, timeout=self.config.per_provider_timeout)

    async def oneinch_swap(
        self,
        chain: Chain,
        src: str,
        dst: str,
        amount: str,
        from_address: str,
        slippage: Optional[float] = None,
    ) -> dict:
        """Get swap transaction from 1inch."""
        slp = slippage if slippage is not None else self.config.slippage
        url = f"{self._oneinch_url(chain)}/swap"
        params = {
            "src": src,
            "dst": dst,
            "amount": amount,
            "from": from_address,
            "slippage": slp,
        }
        headers = {}
        if self.config.oneinch_api_key:
            headers["Authorization"] = f"Bearer {self.config.oneinch_api_key}"
        return await self._api_get(url, params, headers, timeout=self.config.per_provider_timeout)

    # ── Paraswap ────────────────────────────────────

    async def paraswap_quote(
        self,
        chain: Chain,
        src: str,
        dst: str,
        amount: str,
        user_address: str,
    ) -> dict:
        """Get quote from Paraswap."""
        url = "https://apiv5.paraswap.io/prices"
        params = {
            "srcToken": src,
            "destToken": dst,
            "amount": amount,
            "srcDecimals": "18",
            "destDecimals": "18",
            "side": "SELL",
            "network": str(CHAIN_IDS[chain]),
            "userAddress": user_address,
        }
        if self.config.paraswap_partner:
            params["partner"] = self.config.paraswap_partner
        return await self._api_get(url, params, timeout=self.config.per_provider_timeout)

    async def paraswap_swap(
        self,
        chain: Chain,
        src: str,
        dst: str,
        amount: str,
        user_address: str,
        slippage: Optional[float] = None,
    ) -> dict:
        """Get swap transaction from Paraswap."""
        slp = slippage if slippage is not None else self.config.slippage

        # First get the price route
        price_resp = await self.paraswap_quote(chain, src, dst, amount, user_address)
        price_route = price_resp.get("priceRoute")

        if not price_route:
            return {"error": "No price route from Paraswap"}

        # Build swap transaction
        url = f"https://apiv5.paraswap.io/transactions/{str(CHAIN_IDS[chain])}"
        params = {
            "srcToken": src,
            "destToken": dst,
            "srcAmount": amount,
            "destAmount": price_route.get("destAmount", "0"),
            "priceRoute": price_route,
            "userAddress": user_address,
            "slippage": int(slp * 100),  # Paraswap uses bps
            "srcDecimals": 18,
            "destDecimals": 18,
        }
        client = await self._get_client()
        resp = await client.post(url, json=params, timeout=self.config.per_provider_timeout)
        resp.raise_for_status()
        return resp.json()

    # ── 0x / Matcha ─────────────────────────────────

    async def zeroex_quote(
        self,
        chain: Chain,
        sell_token: str,
        buy_token: str,
        sell_amount: str,
        taker_address: str,
    ) -> dict:
        """Get quote from 0x Protocol."""
        url = "https://api.0x.org/swap/allowance-holder/quote"
        params = {
            "chainId": CHAIN_IDS[chain],
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": sell_amount,
            "taker": taker_address,
        }
        headers = {"0x-api-key": self.config.oneinch_api_key or ""}
        return await self._api_get(url, params, headers, timeout=self.config.per_provider_timeout)

    # ── Jupiter (Solana) ────────────────────────────

    async def jupiter_quote(
        self,
        token_in: str,
        token_out: str,
        amount: int,
    ) -> dict:
        """Get quote from Jupiter for Solana."""
        from web3_agent_kit.solana.dex import JupiterDEX, JupiterDEXConfig

        jup = JupiterDEX(
            JupiterDEXConfig(
                api_url=self.config.jupiter_api_url,
                slippage_bps=int(self.config.slippage * 100),
                timeout=self.config.per_provider_timeout,
            )
        )
        try:
            quote = await jup.get_quote(token_in, token_out, amount)
            return quote
        finally:
            await jup.close()

    # ── Best Quote with Fallback ────────────────────

    async def get_best_quote(
        self,
        chain: Chain,
        token_in: str,
        token_out: str,
        amount: int,
        from_address: str = "0x0000000000000000000000000000000000000000",
    ) -> dict:
        """Get the best quote across all aggregators for the chain.

        Features:
        - Parallel quote fetching from all available providers
        - Fallback routing: if a provider fails, it's skipped
        - Provider health tracking: degraded providers are automatically avoided
        - Graceful degradation: returns best available quote even if some providers fail

        Args:
            chain: Target blockchain
            token_in: Input token address
            token_out: Output token address
            amount: Input amount in smallest unit
            from_address: User wallet address (required for Paraswap and 0x)

        Returns:
            {
                "best_provider": str | None,
                "token_in": str,
                "token_out": str,
                "amount_in": str,
                "amount_out": str,
                "quotes": {...},
                "provider_status": {...},
                "fallback_used": bool,
            }
        """
        amount_str = str(amount)

        if chain == Chain.SOLANA:
            return await self._get_best_quote_solana(token_in, token_out, amount, amount_str)

        return await self._get_best_quote_evm(
            chain, token_in, token_out, amount_str, from_address
        )

    async def _get_best_quote_solana(
        self,
        token_in: str,
        token_out: str,
        amount: int,
        amount_str: str,
    ) -> dict:
        """Get best quote for Solana via Jupiter."""
        result = await self._safe_api_call("jupiter", self.jupiter_quote, token_in, token_out, amount)
        if "error" in result:
            return {
                "best_provider": None,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": amount_str,
                "amount_out": "0",
                "quotes": {"jupiter": result},
                "provider_status": self._health.status,
                "error": result["error"],
            }
        out_amount = int(result.get("outAmount", 0))
        return {
            "best_provider": "jupiter",
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_str,
            "amount_out": str(out_amount),
            "quotes": {"jupiter": result},
            "provider_status": self._health.status,
            "fallback_used": False,
        }

    async def _get_best_quote_evm(
        self,
        chain: Chain,
        token_in: str,
        token_out: str,
        amount_str: str,
        from_address: str,
    ) -> dict:
        """Get best quote for EVM chains with fallback routing."""
        # Determine which providers to call based on health
        available_providers = [
            (name, method)
            for name, method in EVM_PROVIDERS
            if self._health.is_available(name)
        ]

        if not available_providers:
            # All providers degraded — try resetting and force a call
            self._health.reset()
            available_providers = EVM_PROVIDERS

        # Build provider call map
        provider_calls = {}
        for name, method in available_providers:
            if name == "1inch":
                provider_calls[name] = self._safe_api_call(
                    name, self.oneinch_quote, chain, token_in, token_out, amount_str
                )
            elif name == "paraswap":
                provider_calls[name] = self._safe_api_call(
                    name, self.paraswap_quote, chain, token_in, token_out, amount_str, from_address
                )
            elif name == "0x":
                provider_calls[name] = self._safe_api_call(
                    name, self.zeroex_quote, chain, token_in, token_out, amount_str, from_address
                )

        # Gather all quotes in parallel
        results = {}
        for name, call in provider_calls.items():
            try:
                results[name] = await call
            except Exception as e:
                results[name] = {"error": f"unexpected error: {e}"}

        # Find best output amount
        best_provider = None
        best_amount = 0
        fallback_used = False

        for name, quote in results.items():
            if "error" in quote:
                fallback_used = True
                continue
            out = self._extract_output_amount(name, quote)
            if out >= best_amount:
                best_amount = out
                best_provider = name

        # If no provider succeeded, attempt fallback chain
        if best_provider is None and self.config.fallback_enabled:
            fallback_used = True
            best_provider, best_amount, results = await self._fallback_chain(
                chain, token_in, token_out, amount_str, from_address, available_providers, results
            )

        return {
            "best_provider": best_provider,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_str,
            "amount_out": str(best_amount),
            "quotes": results,
            "provider_status": self._health.status,
            "fallback_used": fallback_used,
        }

    async def _fallback_chain(
        self,
        chain: Chain,
        token_in: str,
        token_out: str,
        amount_str: str,
        from_address: str,
        attempted: list[tuple[str, str]],
        results: dict,
    ) -> tuple[Optional[str], int, dict]:
        """Fallback chain: try each provider sequentially until one succeeds.

        Used when all providers failed in parallel mode.
        """
        # Reset health for a fresh attempt
        self._health.reset()

        # Try providers one by one with longer timeout
        for name, method in EVM_PROVIDERS:
            if name in attempted:
                continue

            try:
                if name == "1inch":
                    quote = await asyncio.wait_for(
                        self.oneinch_quote(chain, token_in, token_out, amount_str),
                        timeout=self.config.timeout,
                    )
                elif name == "paraswap":
                    quote = await asyncio.wait_for(
                        self.paraswap_quote(chain, token_in, token_out, amount_str, from_address),
                        timeout=self.config.timeout,
                    )
                elif name == "0x":
                    quote = await asyncio.wait_for(
                        self.zeroex_quote(chain, token_in, token_out, amount_str, from_address),
                        timeout=self.config.timeout,
                    )
                else:
                    continue

                if "error" not in quote:
                    out = self._extract_output_amount(name, quote)
                    results[name] = quote
                    return name, out, results
            except Exception:
                continue

        return None, 0, results

    def _extract_output_amount(self, provider: str, quote: dict) -> int:
        """Extract output amount from a provider's quote response."""
        if provider == "1inch":
            return int(quote.get("toAmount", 0))
        elif provider == "paraswap":
            route = quote.get("priceRoute", {})
            return int(route.get("destAmount", 0))
        elif provider == "0x":
            return int(quote.get("buyAmount", 0))
        elif provider == "jupiter":
            return int(quote.get("outAmount", 0))
        return 0

    # ── Swap ─────────────────────────────────────────

    async def get_swap(
        self,
        chain: Chain,
        token_in: str,
        token_out: str,
        amount: int,
        from_address: str,
        preferred_provider: Optional[str] = None,
        slippage: Optional[float] = None,
    ) -> dict:
        """Get a swap transaction from the best provider.

        Args:
            chain: Target blockchain
            token_in: Input token address
            token_out: Output token address
            amount: Input amount in smallest unit
            from_address: User wallet address
            preferred_provider: Force a specific provider (e.g., "1inch", "jupiter")
            slippage: Override slippage tolerance

        Returns:
            Swap transaction data from the provider
        """
        amount_str = str(amount)

        if chain == Chain.SOLANA:
            return await self._get_solana_swap(token_in, token_out, amount, from_address)

        # For EVM, get best quote first, then swap
        if preferred_provider:
            # Use the preferred provider directly
            return await self._direct_swap(
                preferred_provider, chain, token_in, token_out, amount_str, from_address, slippage
            )

        # Get best quote first
        best = await self.get_best_quote(chain, token_in, token_out, amount, from_address)
        provider = best.get("best_provider")
        if not provider or provider == "jupiter":
            return {"error": "No viable provider found"}

        return await self._direct_swap(
            provider, chain, token_in, token_out, amount_str, from_address, slippage
        )

    async def _direct_swap(
        self,
        provider: str,
        chain: Chain,
        token_in: str,
        token_out: str,
        amount_str: str,
        from_address: str,
        slippage: Optional[float] = None,
    ) -> dict:
        """Execute a swap through a specific provider."""
        try:
            if provider == "1inch":
                return await self.oneinch_swap(chain, token_in, token_out, amount_str, from_address, slippage)
            elif provider == "paraswap":
                return await self.paraswap_swap(chain, token_in, token_out, amount_str, from_address, slippage)
            elif provider == "0x":
                return await self.zeroex_quote(chain, token_in, token_out, amount_str, from_address)
            else:
                return {"error": f"Unknown provider: {provider}"}
        except Exception as e:
            return {"error": f"Swap failed: {e}"}

    async def _get_solana_swap(
        self,
        token_in: str,
        token_out: str,
        amount: int,
        from_address: str,
    ) -> dict:
        """Get a Solana swap via Jupiter."""
        try:
            from web3_agent_kit.solana.dex import JupiterDEX

            jup = JupiterDEX()
            result = await jup.swap(from_address, token_in, token_out, amount)
            await jup.close()
            return result
        except Exception as e:
            return {"error": f"Solana swap failed: {e}"}

    # ── Health & Status ─────────────────────────────

    def get_provider_health(self) -> dict[str, str]:
        """Get current health status of all providers."""
        return self._health.status

    def reset_health(self, provider: Optional[str] = None):
        """Reset health tracking for a provider (or all)."""
        self._health.reset(provider)

    # ── Cleanup ─────────────────────────────────────

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class AggregatorError(Exception):
    """Raised when DEX aggregator API fails."""
    pass