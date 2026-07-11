"""DEX Aggregator — unified interface for multi-chain DEX quotes and swaps.

Supports EVM (1inch, Paraswap, 0x) and Solana (Jupiter) through a single API.
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


@dataclass
class AggregatorConfig:
    """Configuration for DEX aggregator."""

    slippage: float = 0.5  # percentage
    timeout: int = 30
    max_retries: int = 3

    # EVM aggregator API keys (optional but recommended)
    oneinch_api_key: Optional[str] = None
    paraswap_partner: Optional[str] = None

    # Solana (Jupiter)
    jupiter_api_url: str = "https://quote-api.jup.ag/v6"


class DEXAggregator:
    """Multi-chain DEX aggregator — get best quotes across all major DEXes.

    Usage:
        agg = DEXAggregator()
        quote = await agg.get_best_quote(Chain.ETHEREUM, "0x...", "0x...", 10**18)
        swap = await agg.get_swap(Chain.ETHEREUM, "0x...", "0x...", 10**18, "0x_wallet")
    """

    def __init__(self, config: Optional[AggregatorConfig] = None):
        self.config = config or AggregatorConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _api_get(self, url: str, params: dict, headers: dict | None = None) -> dict:
        client = await self._get_client()
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.config.max_retries - 1:
                    raise AggregatorError(f"API call failed: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
        return {}

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
        return await self._api_get(url, params, headers)

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
        return await self._api_get(url, params, headers)

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
        return await self._api_get(url, params)

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
        resp = await client.post(url, json=params)
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
        url = f"https://api.0x.org/swap/allowance-holder/quote"
        params = {
            "chainId": CHAIN_IDS[chain],
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": sell_amount,
            "taker": taker_address,
        }
        headers = {"0x-api-key": self.config.oneinch_api_key or ""}
        return await self._api_get(url, params, headers)

    # ── Best Quote ──────────────────────────────────

    async def get_best_quote(
        self,
        chain: Chain,
        token_in: str,
        token_out: str,
        amount: int,
        from_address: str = "0x0000000000000000000000000000000000000000",
    ) -> dict:
        """Get the best quote across all aggregators for the chain.

        Returns:
            {
                "best_provider": str,
                "token_in": str,
                "token_out": str,
                "amount_in": str,
                "amount_out": str,
                "quotes": {"1inch": ..., "paraswap": ..., "0x": ..., "jupiter": ...},
            }
        """
        amount_str = str(amount)

        if chain == Chain.SOLANA:
            # Use Jupiter for Solana
            try:
                from src.solana.dex import JupiterDEX

                jup = JupiterDEX()
                quote = await jup.get_quote(token_in, token_out, amount)
                out_amount = int(quote.get("outAmount", 0))
                await jup.close()
                return {
                    "best_provider": "jupiter",
                    "token_in": token_in,
                    "token_out": token_out,
                    "amount_in": amount_str,
                    "amount_out": str(out_amount),
                    "quotes": {"jupiter": quote},
                }
            except Exception as e:
                return {"error": str(e), "quotes": {}}

        # EVM: query all aggregators in parallel
        tasks = {}

        tasks["1inch"] = self.oneinch_quote(chain, token_in, token_out, amount_str)
        tasks["paraswap"] = self.paraswap_quote(chain, token_in, token_out, amount_str, from_address)
        tasks["0x"] = self.zeroex_quote(chain, token_in, token_out, amount_str, from_address)

        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception:
                results[name] = {"error": "failed"}

        # Find best output amount
        best_provider = None
        best_amount = 0

        for name, quote in results.items():
            if "error" in quote:
                continue

            out = self._extract_output_amount(name, quote)
            if out > best_amount:
                best_amount = out
                best_provider = name

        return {
            "best_provider": best_provider,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_str,
            "amount_out": str(best_amount),
            "quotes": results,
        }

    def _extract_output_amount(self, provider: str, quote: dict) -> int:
        """Extract output amount from a provider's quote response."""
        if provider == "1inch":
            return int(quote.get("toAmount", 0))
        elif provider == "paraswap":
            route = quote.get("priceRoute", {})
            return int(route.get("destAmount", 0))
        elif provider == "0x":
            return int(quote.get("buyAmount", 0))
        return 0

    # ── Cleanup ─────────────────────────────────────

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class AggregatorError(Exception):
    """Raised when DEX aggregator API fails."""
    pass