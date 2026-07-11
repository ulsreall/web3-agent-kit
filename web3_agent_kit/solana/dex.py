"""Solana DEX — Jupiter aggregator for quotes and swap execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


@dataclass
class JupiterDEXConfig:
    """Configuration for Jupiter DEX aggregator."""

    api_url: str = "https://quote-api.jup.ag/v6"
    slippage_bps: int = 50  # 0.5% default slippage
    timeout: int = 30
    max_retries: int = 3


class JupiterDEX:
    """Jupiter DEX aggregator — the top Solana liquidity aggregator.

    Provides best-route quotes and swap execution across all Solana DEXes.

    Usage:
        jup = JupiterDEX()
        quote = await jup.get_quote("So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 1_000_000_000)
        route = await jup.get_swap_route(wallet_address, quote)
    """

    def __init__(self, config: Optional[JupiterDEXConfig] = None):
        self.config = config or JupiterDEXConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _api_get(self, endpoint: str, params: dict) -> dict:
        """Make GET request to Jupiter API."""
        client = await self._get_client()
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(
                    f"{self.config.api_url}/{endpoint}",
                    params=params,
                )
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.config.max_retries - 1:
                    raise JupiterAPIError(f"Jupiter API '{endpoint}' failed: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
        return {}

    async def _api_post(self, endpoint: str, body: dict) -> dict:
        """Make POST request to Jupiter API."""
        client = await self._get_client()
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post(
                    f"{self.config.api_url}/{endpoint}",
                    json=body,
                )
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.config.max_retries - 1:
                    raise JupiterAPIError(f"Jupiter API '{endpoint}' failed: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
        return {}

    # ── Quote ────────────────────────────────────────

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: Optional[int] = None,
    ) -> dict:
        """Get swap quote for token pair.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Input amount in token's smallest unit (lamports for SOL)
            slippage_bps: Slippage in basis points (default 50 = 0.5%)

        Returns:
            {
                "input_mint": str,
                "output_mint": str,
                "in_amount": int,
                "out_amount": int,
                "price_impact_pct": float,
                "route_plan": list[dict],
                "other_amount_threshold": int,
                "swap_mode": str,
            }
        """
        slippage = slippage_bps or self.config.slippage_bps
        return await self._api_get(
            "quote",
            {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": slippage,
            },
        )

    async def get_quote_price(
        self,
        input_mint: str,
        output_mint: str,
        amount_sol: float = 1.0,
    ) -> float:
        """Get output token price for given input amount.

        Returns output amount in UI units (e.g., USDC for SOL).
        """
        amount_lamports = int(amount_sol * 1_000_000_000)
        quote = await self.get_quote(input_mint, output_mint, amount_lamports)
        out_amount = int(quote.get("outAmount", 0))
        if not out_amount:
            return 0.0
        # Most tokens on Solana use 6 decimals
        return out_amount / 1_000_000

    # ── Swap ─────────────────────────────────────────

    async def get_swap_route(
        self,
        wallet_address: str,
        quote_response: dict,
        wrap_unwrap_sol: bool = True,
    ) -> dict:
        """Get the serialized swap transaction from a quote.

        Args:
            wallet_address: User's wallet address
            quote_response: Full quote response from get_quote()
            wrap_unwrap_sol: Auto-wrap/unwrap SOL (recommended)

        Returns:
            {
                "swap_transaction": str,  # base64-encoded transaction
                "last_valid_block_height": int,
                "prioritization_fee_lamports": int,
            }
        """
        return await self._api_post(
            "swap",
            {
                "quoteResponse": quote_response,
                "userPublicKey": wallet_address,
                "wrapAndUnwrapSol": wrap_unwrap_sol,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto",
            },
        )

    async def swap(
        self,
        wallet_address: str,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: Optional[int] = None,
    ) -> dict:
        """Full swap flow: get quote → build transaction.

        Returns swap route ready for signing and sending.
        """
        quote = await self.get_quote(input_mint, output_mint, amount, slippage_bps)

        if "error" in quote:
            return {"error": quote["error"]}

        route = await self.get_swap_route(wallet_address, quote)

        return {
            "quote": {
                "in_amount": int(quote.get("inAmount", 0)),
                "out_amount": int(quote.get("outAmount", 0)),
                "price_impact_pct": float(quote.get("priceImpactPct", 0)),
                "route_plan": quote.get("routePlan", []),
            },
            "swap_transaction": route.get("swapTransaction", ""),
            "last_valid_block_height": route.get("lastValidBlockHeight", 0),
        }

    # ── Token List ───────────────────────────────────

    async def get_tokens(self) -> list[dict]:
        """Get all supported tokens from Jupiter."""
        result = await self._api_get("tokens", {})
        return result if isinstance(result, list) else []

    async def get_token_by_symbol(self, symbol: str) -> Optional[dict]:
        """Find a token by symbol (e.g., 'USDC', 'SOL')."""
        tokens = await self.get_tokens()
        s = symbol.upper()
        for token in tokens:
            if token.get("symbol", "").upper() == s:
                return token
        return None

    async def get_token_by_mint(self, mint: str) -> Optional[dict]:
        """Find a token by mint address."""
        tokens = await self.get_tokens()
        for token in tokens:
            if token.get("address", "") == mint:
                return token
        return None

    # ── Price ────────────────────────────────────────

    async def get_price(self, token_ids: list[str]) -> dict:
        """Get token prices by mint address.

        Args:
            token_ids: List of token mint addresses

        Returns:
            {mint: {"price": float, "price_ui": float, "confidence": float}}
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                "https://api.jup.ag/price/v2",
                params={"ids": ",".join(token_ids)},
            )
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception:
            return {}

    # ── Cleanup ──────────────────────────────────────

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class JupiterAPIError(Exception):
    """Raised when Jupiter API call fails."""
    pass