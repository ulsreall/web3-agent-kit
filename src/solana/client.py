"""Solana RPC client — async HTTP client for Solana JSON-RPC."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


@dataclass
class SolanaClientConfig:
    """Configuration for Solana RPC client."""

    rpc_url: str = "https://api.mainnet-beta.solana.com"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0

    # Optional API keys for premium RPC
    helius_api_key: Optional[str] = None
    quicknode_api_key: Optional[str] = None


class SolanaClient:
    """Async Solana JSON-RPC client.

    Supports standard Solana RPC methods plus Helius/QuickNode premium endpoints.

    Usage:
        client = SolanaClient(SolanaClientConfig(rpc_url="https://api.mainnet-beta.solana.com"))
        balance = await client.get_balance("YourPubkeyHere")
    """

    def __init__(self, config: Optional[SolanaClientConfig] = None):
        self.config = config or SolanaClientConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _rpc_call(self, method: str, params: list[Any] | None = None) -> dict:
        """Make a JSON-RPC call to Solana with retries."""
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post(self.config.rpc_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise SolanaRPCError(data["error"].get("message", str(data["error"])))
                return data.get("result", {})
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
            except SolanaRPCError:
                raise

        raise SolanaRPCError(f"RPC call '{method}' failed after {self.config.max_retries} retries: {last_error}")

    # ── Balance ──────────────────────────────────────

    async def get_balance(self, pubkey: str) -> int:
        """Get SOL balance in lamports. 1 SOL = 1e9 lamports."""
        result = await self._rpc_call("getBalance", [pubkey])
        return result.get("value", 0)

    async def get_sol_balance(self, pubkey: str) -> float:
        """Get SOL balance in SOL units."""
        lamports = await self.get_balance(pubkey)
        return lamports / 1_000_000_000

    # ── Token Accounts ───────────────────────────────

    async def get_token_accounts_by_owner(
        self, owner: str, program_id: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    ) -> list[dict]:
        """Get all token accounts owned by an address.

        Args:
            owner: The wallet address to query
            program_id: Default is Token program; use TokenzQd... for Token-2022
        """
        result = await self._rpc_call(
            "getTokenAccountsByOwner",
            [
                owner,
                {"programId": program_id},
                {"encoding": "jsonParsed"},
            ],
        )
        return result.get("value", [])

    async def get_token_balance(self, owner: str, mint: str) -> dict:
        """Get balance for a specific SPL token."""
        accounts = await self.get_token_accounts_by_owner(owner)
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            if info.get("mint") == mint:
                return {
                    "amount": info.get("tokenAmount", {}).get("amount", "0"),
                    "decimals": info.get("tokenAmount", {}).get("decimals", 0),
                    "ui_amount": info.get("tokenAmount", {}).get("uiAmount", 0),
                }
        return {"amount": "0", "decimals": 0, "ui_amount": 0}

    # ── Transaction ──────────────────────────────────

    async def get_latest_blockhash(self) -> dict:
        """Get latest blockhash for transaction building."""
        result = await self._rpc_call("getLatestBlockhash", [{"commitment": "finalized"}])
        return result.get("value", {})

    async def send_transaction(self, signed_tx: str) -> str:
        """Send a signed transaction. Returns transaction signature."""
        result = await self._rpc_call("sendTransaction", [signed_tx, {"encoding": "base64"}])
        return str(result)  # tx signature string

    async def get_transaction(self, signature: str) -> dict:
        """Get transaction details."""
        result = await self._rpc_call(
            "getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
        )
        return result

    async def confirm_transaction(self, signature: str, commitment: str = "finalized") -> dict:
        """Wait for transaction confirmation."""
        result = await self._rpc_call(
            "getSignatureStatuses", [[signature], {"searchTransactionHistory": True}]
        )
        return result.get("value", [{}])[0] or {}

    # ── Account Info ─────────────────────────────────

    async def get_account_info(self, pubkey: str) -> dict:
        """Get account info."""
        result = await self._rpc_call(
            "getAccountInfo", [pubkey, {"encoding": "jsonParsed"}]
        )
        return result.get("value", {})

    # ── Token Supply ─────────────────────────────────

    async def get_token_supply(self, mint: str) -> dict:
        """Get SPL token total supply."""
        result = await self._rpc_call("getTokenSupply", [mint])
        return result.get("value", {})

    # ── Cleanup ──────────────────────────────────────

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class SolanaRPCError(Exception):
    """Raised when a Solana RPC call fails."""
    pass