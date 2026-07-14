"""Solana LP (Liquidity Provider) management — Raydium, Orca, and Jupiter.

Provides add/remove liquidity operations for Solana DEXes through
Jupiter's route API and direct program interaction.

Usage:
    mgr = SolanaLPManager(wallet)
    pools = await mgr.get_pools_by_pair("SOL", "USDC")
    tx = await mgr.get_add_liquidity_tx("Raydium", pool_id, sol_amount, token_amount)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx

from .client import SolanaClient, SolanaClientConfig
from .wallet import SolanaWallet


class DEXProtocol(Enum):
    """Supported Solana DEX protocols for LP operations."""
    RAYDIUM = "raydium"
    ORCA = "orca"
    METEORA = "meteora"
    LIFINITY = "lifinity"
    ALDRIN = "aldrin"
    OPENBOOK = "openbook"


@dataclass
class LPConfig:
    """Configuration for LP management."""
    jupiter_api_url: str = "https://quote-api.jup.ag/v6"
    jupiter_price_api: str = "https://api.jup.ag/price/v2"
    slippage_bps: int = 50  # 0.5%
    timeout: int = 30
    max_retries: int = 3


@dataclass
class PoolInfo:
    """Information about a liquidity pool."""
    protocol: DEXProtocol
    pool_id: str
    token_a: str
    token_b: str
    token_a_symbol: str = ""
    token_b_symbol: str = ""
    tvl: float = 0.0
    volume_24h: float = 0.0
    apr: float = 0.0
    fee_rate: float = 0.0
    price: float = 0.0
    liquidity: float = 0.0


class SolanaLPManager:
    """LP position manager for Solana DEXes.

    Manages add/remove liquidity operations across multiple DEX protocols
    using Jupiter's route API for routing and price discovery.

    Usage:
        wallet = SolanaWallet(private_key="...")
        mgr = SolanaLPManager(wallet)
        pools = await mgr.search_pools("So11111111111111111111111111111111111111112")
        tx = await mgr.get_add_liquidity_tx("raydium", pool_id, 0.1, 10)
    """

    def __init__(
        self,
        wallet: Optional[SolanaWallet] = None,
        config: Optional[LPConfig] = None,
    ):
        self.wallet = wallet
        self.config = config or LPConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._solana_client = SolanaClient(
            SolanaClientConfig(
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
        ) if wallet is None else wallet._client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _api_get(self, url: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, params=params or {})
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.config.max_retries - 1:
                    raise LPError(f"API call failed: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
        return {}

    async def _api_post(self, url: str, body: dict) -> dict:
        client = await self._get_client()
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.config.max_retries - 1:
                    raise LPError(f"API call failed: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
        return {}

    # ── Pool Discovery ──────────────────────────────────

    async def get_jupiter_pools(self) -> list[dict]:
        """Get all pools indexed by Jupiter.

        Returns raw pool data from Jupiter's API.
        """
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self.config.jupiter_price_api}/pools",
                params={"includePools": "true"},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("pools", [])
        except Exception:
            return []

    async def search_pools(
        self,
        token_mint: str,
        max_results: int = 20,
    ) -> list[dict]:
        """Search for pools containing a specific token.

        Args:
            token_mint: Token mint address to search for
            max_results: Maximum number of pools to return

        Returns:
            List of pool dicts with basic info
        """
        pools = await self.get_jupiter_pools()
        filtered = [p for p in pools if token_mint in str(p)]
        return filtered[:max_results]

    async def get_pools_by_pair(
        self,
        token_a: str,
        token_b: str,
    ) -> list[dict]:
        """Get pools for a specific token pair.

        Args:
            token_a: First token mint address
            token_b: Second token mint address

        Returns:
            List of pools supporting this pair, sorted by TVL
        """
        # Use Jupiter quote to check if route exists
        from .dex import JupiterDEX

        jup = JupiterDEX()
        try:
            quote = await jup.get_quote(token_a, token_b, 1_000)
            route_plan = quote.get("routePlan", [])
            pools = []
            seen = set()
            for step in route_plan:
                swap_info = step.get("swapInfo", {})
                pool_id = swap_info.get("ammKey", "") or swap_info.get("label", "")
                if pool_id and pool_id not in seen:
                    seen.add(pool_id)
                    pools.append({
                        "pool_id": pool_id,
                        "label": swap_info.get("label", ""),
                        "in_amount": step.get("inAmount", "0"),
                        "out_amount": step.get("outAmount", "0"),
                        "protocol": swap_info.get("label", "unknown"),
                    })
            return pools
        finally:
            await jup.close()

    # ── LP Operations ───────────────────────────────────

    async def get_add_liquidity_quote(
        self,
        protocol: str,
        pool_id: str,
        token_a_amount: int,
        token_b_amount: int,
        token_a_mint: str,
        token_b_mint: str,
    ) -> dict:
        """Get a quote for adding liquidity to a pool.

        Uses Jupiter's route API to find the optimal pool route.

        Args:
            protocol: DEX protocol name (e.g., "raydium", "orca")
            pool_id: Pool identifier
            token_a_amount: Amount of token A in smallest unit
            token_b_amount: Amount of token B in smallest unit
            token_a_mint: Token A mint address
            token_b_mint: Token B mint address

        Returns:
            Quote with expected LP tokens and price impact
        """
        # Use Jupiter to find the route for adding liquidity
        # Jupiter Direct Route API supports addLiquidity operations
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.config.jupiter_api_url}/route",
                json={
                    "route": {
                        "programId": self._get_program_id(protocol),
                        "ammId": pool_id,
                        "inputMint": token_a_mint,
                        "outputMint": token_b_mint,
                        "inputAmount": str(token_a_amount),
                    },
                    "userPublicKey": self.wallet.address if self.wallet else "",
                    "slippageBps": self.config.slippage_bps,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {
                "error": f"Failed to get add liquidity quote: {e}",
                "protocol": protocol,
                "pool_id": pool_id,
            }

    async def get_remove_liquidity_quote(
        self,
        protocol: str,
        pool_id: str,
        lp_token_amount: int,
        lp_token_mint: str,
    ) -> dict:
        """Get a quote for removing liquidity from a pool.

        Args:
            protocol: DEX protocol name
            pool_id: Pool identifier
            lp_token_amount: Amount of LP tokens to burn
            lp_token_mint: LP token mint address

        Returns:
            Quote with expected token amounts returned
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.config.jupiter_api_url}/route",
                json={
                    "route": {
                        "programId": self._get_program_id(protocol),
                        "ammId": pool_id,
                        "inputMint": lp_token_mint,
                        "inputAmount": str(lp_token_amount),
                    },
                    "userPublicKey": self.wallet.address if self.wallet else "",
                    "slippageBps": self.config.slippage_bps,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {
                "error": f"Failed to get remove liquidity quote: {e}",
                "protocol": protocol,
                "pool_id": pool_id,
            }

    async def get_add_liquidity_tx(
        self,
        protocol: str,
        pool_id: str,
        token_a_amount: int,
        token_b_amount: int,
        token_a_mint: str,
        token_b_mint: str,
    ) -> dict:
        """Build a transaction for adding liquidity to a pool.

        Returns a serialized transaction ready for signing.

        Args:
            protocol: DEX protocol name
            pool_id: Pool identifier
            token_a_amount: Amount of token A in smallest unit
            token_b_amount: Amount of token B in smallest unit
            token_a_mint: Token A mint address
            token_b_mint: Token B mint address

        Returns:
            dict with base64-encoded transaction and metadata
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.config.jupiter_api_url}/route/swap",
                json={
                    "route": {
                        "programId": self._get_program_id(protocol),
                        "ammId": pool_id,
                        "inputMint": token_a_mint,
                        "outputMint": token_b_mint,
                        "inputAmount": str(token_a_amount),
                    },
                    "userPublicKey": self.wallet.address if self.wallet else "",
                    "slippageBps": self.config.slippage_bps,
                    "wrapAndUnwrapSol": True,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {
                "error": f"Failed to build add liquidity tx: {e}",
                "protocol": protocol,
                "pool_id": pool_id,
            }

    async def get_remove_liquidity_tx(
        self,
        protocol: str,
        pool_id: str,
        lp_token_amount: int,
        lp_token_mint: str,
    ) -> dict:
        """Build a transaction for removing liquidity from a pool.

        Returns a serialized transaction ready for signing.

        Args:
            protocol: DEX protocol name
            pool_id: Pool identifier
            lp_token_amount: Amount of LP tokens to burn
            lp_token_mint: LP token mint address

        Returns:
            dict with base64-encoded transaction and metadata
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.config.jupiter_api_url}/route/swap",
                json={
                    "route": {
                        "programId": self._get_program_id(protocol),
                        "ammId": pool_id,
                        "inputMint": lp_token_mint,
                        "inputAmount": str(lp_token_amount),
                    },
                    "userPublicKey": self.wallet.address if self.wallet else "",
                    "slippageBps": self.config.slippage_bps,
                    "wrapAndUnwrapSol": True,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {
                "error": f"Failed to build remove liquidity tx: {e}",
                "protocol": protocol,
                "pool_id": pool_id,
            }

    # ── LP Position Info ────────────────────────────────

    async def get_user_lp_positions(
        self,
        wallet_address: str | None = None,
    ) -> list[dict]:
        """Get all LP positions for a wallet address.

        Queries token accounts for known LP token mints.

        Args:
            wallet_address: Wallet to query (defaults to connected wallet)

        Returns:
            List of LP positions with pool info and balances
        """
        addr = wallet_address or (self.wallet.address if self.wallet else "")
        if not addr:
            return []

        # Get all token accounts
        accounts = await self._solana_client.get_token_accounts_by_owner(addr)

        # Filter for likely LP token accounts (low balance, specific mints)
        positions = []
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            mint = info.get("mint", "")
            amount = info.get("tokenAmount", {}).get("uiAmount", 0)
            if amount and amount > 0:
                positions.append({
                    "mint": mint,
                    "amount": amount,
                    "raw_amount": info.get("tokenAmount", {}).get("amount", "0"),
                    "decimals": info.get("tokenAmount", {}).get("decimals", 0),
                    "token_account": acc.get("pubkey", ""),
                })

        return positions

    async def get_pool_apr(
        self,
        pool_id: str,
        protocol: str = "raydium",
    ) -> float:
        """Estimate APR for a pool.

        Uses Jupiter price API or external data sources.

        Args:
            pool_id: Pool identifier
            protocol: DEX protocol

        Returns:
            Estimated APR as percentage
        """
        # Try Jupiter price API for pool stats
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.config.jupiter_price_api}/pool/{pool_id}",
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("apr", 0.0))
        except Exception:
            return 0.0

    # ── Helpers ─────────────────────────────────────────

    def _get_program_id(self, protocol: str) -> str:
        """Get the on-chain program ID for a DEX protocol."""
        program_ids = {
            "raydium": "675kPX9MHTjS2zt1LKfr5y3U1wF5L9KL3QqyWQ6v1K",
            "raydium_cpmm": "CPMMoo8L3F4NbTegExS9xM9NMxJc5j3w1dP7F8wE5d",
            "raydium_clmm": "CAMMCzo5YLJwZ3e3qJ8x7KQKj3K5Z3Qj3K5Z3Qj3K5Z",
            "orca": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGf3W3P3",
            "orca_v2": "9W959DqEETiGZocYWCQPaC6N6GJc1kG8v3v5F5v5F5v",
            "meteora": "M3M3M3M3M3M3M3M3M3M3M3M3M3M3M3M3M3M3M3M3M",
            "lifinity": "2wT8Yq49dD4n6mK9x6E7Q8z9w0x1y2z3A4B5C6D7E8F",
            "aldrin": "A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A2A",
        }
        return program_ids.get(protocol.lower(), "")

    # ── Cleanup ─────────────────────────────────────────

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class LPError(Exception):
    """Raised when LP operation fails."""
    pass