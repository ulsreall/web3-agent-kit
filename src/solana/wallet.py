"""Solana wallet — keypair management, signing, and transaction sending."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from solders.keypair import Keypair

from .client import SolanaClient, SolanaClientConfig


@dataclass
class SolanaWalletConfig:
    """Configuration for Solana wallet."""

    keypair_path: Optional[str] = None  # Path to keypair JSON file
    private_key: Optional[str] = None  # Base58 or base64 private key
    client_config: SolanaClientConfig = field(default_factory=SolanaClientConfig)


class SolanaWallet:
    """Solana wallet for keypair management and transaction operations.

    Usage:
        wallet = SolanaWallet(private_key="your_base58_key")
        wallet = SolanaWallet(keypair_path="/path/to/keypair.json")
        wallet = SolanaWallet()  # Creates new keypair

        address = wallet.address
        balance = await wallet.get_balance()
        sig = await wallet.send_sol("RecipientPubkey", 0.01)
    """

    def __init__(self, config: Optional[SolanaWalletConfig] = None):
        self.config = config or SolanaWalletConfig()
        self._keypair: Keypair  # set in _load_keypair
        self._client = SolanaClient(self.config.client_config)
        self._load_keypair()

    def _load_keypair(self):
        """Load or create keypair."""
        if self.config.private_key:
            pk_bytes = self._decode_private_key(self.config.private_key)
            self._keypair = Keypair.from_bytes(pk_bytes)
        elif self.config.keypair_path:
            path = Path(os.path.expanduser(self.config.keypair_path))
            if not path.exists():
                raise FileNotFoundError(f"Keypair file not found: {path}")
            keypair_data = json.loads(path.read_text())
            pk_bytes = bytes(keypair_data) if isinstance(keypair_data, list) else bytes(keypair_data["secret_key"])
            self._keypair = Keypair.from_bytes(pk_bytes)
        else:
            self._keypair = Keypair()

    def _decode_private_key(self, key: str) -> bytes:
        """Decode base58 or base64 private key to bytes."""
        if len(key) <= 88:
            try:
                import base58
                return base58.b58decode(key)
            except ImportError:
                pass

        try:
            return base64.b64decode(key)
        except Exception:
            raise ValueError(
                "Unable to decode private key. Provide a valid base58 or base64 private key."
            )

    # ── Properties ───────────────────────────────────

    @property
    def address(self) -> str:
        return str(self._keypair.pubkey())

    @property
    def pubkey(self):
        """Raw solders Pubkey object."""
        return self._keypair.pubkey()

    # ── Balance ──────────────────────────────────────

    async def get_balance(self) -> float:
        return await self._client.get_sol_balance(self.address)

    async def get_token_balance(self, mint: str) -> dict:
        return await self._client.get_token_balance(self.address, mint)

    # ── Send SOL ─────────────────────────────────────

    async def send_sol(
        self,
        to_address: str,
        amount_sol: float,
    ) -> dict:
        """Send SOL to another address.

        Returns:
            dict with 'signature', 'status', 'explorer_url'
        """
        from solders.pubkey import Pubkey
        from solders.system_program import TransferParams, transfer
        from solders.message import Message
        from solders.transaction import Transaction
        from solders.hash import Hash

        to_pubkey = Pubkey.from_string(to_address)
        from_pubkey = self._keypair.pubkey()
        lamports = int(amount_sol * 1_000_000_000)

        blockhash_resp = await self._client.get_latest_blockhash()
        blockhash_str = blockhash_resp.get("blockhash", "")
        if not blockhash_str:
            raise ValueError("Failed to get blockhash")

        ix = transfer(
            TransferParams(
                from_pubkey=from_pubkey,
                to_pubkey=to_pubkey,
                lamports=lamports,
            )
        )

        recent_blockhash = Hash.from_string(blockhash_str)
        msg = Message.new_with_blockhash([ix], from_pubkey, recent_blockhash)
        tx = Transaction.new_unsigned(msg)
        tx.sign([self._keypair], recent_blockhash)

        raw_tx = base64.b64encode(bytes(tx)).decode("utf-8")
        signature = await self._client.send_transaction(raw_tx)

        return {
            "signature": signature,
            "status": "sent",
            "explorer_url": f"https://solscan.io/tx/{signature}",
            "from": self.address,
            "to": to_address,
            "amount_sol": amount_sol,
        }

    # ── Send SPL Token ──────────��────────────────────

    async def send_token(
        self,
        to_address: str,
        mint: str,
        amount: float,
        decimals: int = 6,
    ) -> dict:
        """Send SPL tokens to another address.

        Creates the associated token account if needed.
        """
        from solders.pubkey import Pubkey
        from solders.message import Message
        from solders.transaction import Transaction
        from solders.hash import Hash
        from solders.instruction import Instruction
        from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID
        from spl.token.instructions import (
            get_associated_token_address,
            create_associated_token_account,
            transfer_checked,
            TransferCheckedParams,
        )

        from_pubkey = self._keypair.pubkey()
        to_pubkey = Pubkey.from_string(to_address)
        mint_pubkey = Pubkey.from_string(mint)
        amount_raw = int(amount * 10**decimals)

        from_ata = get_associated_token_address(from_pubkey, mint_pubkey)
        to_ata = get_associated_token_address(to_pubkey, mint_pubkey)

        blockhash_resp = await self._client.get_latest_blockhash()
        blockhash_str = blockhash_resp.get("blockhash", "")
        if not blockhash_str:
            raise ValueError("Failed to get blockhash")

        recent_blockhash = Hash.from_string(blockhash_str)

        instructions: list[Instruction] = [
            create_associated_token_account(from_pubkey, to_pubkey, mint_pubkey),
            transfer_checked(
                TransferCheckedParams(
                    amount=amount_raw,
                    decimals=decimals,
                    source=from_ata,
                    mint=mint_pubkey,
                    dest=to_ata,
                    owner=from_pubkey,
                    program_id=TOKEN_PROGRAM_ID,
                )
            ),
        ]

        msg = Message.new_with_blockhash(instructions, from_pubkey, recent_blockhash)
        tx = Transaction.new_unsigned(msg)
        tx.sign([self._keypair], recent_blockhash)

        raw_tx = base64.b64encode(bytes(tx)).decode("utf-8")
        signature = await self._client.send_transaction(raw_tx)

        return {
            "signature": signature,
            "status": "sent",
            "explorer_url": f"https://solscan.io/tx/{signature}",
            "from": self.address,
            "to": to_address,
            "mint": mint,
            "amount": amount,
        }

    # ── Sign Message ─────────────────────────────────

    def sign_message(self, message: bytes) -> bytes:
        """Sign an arbitrary message. Returns signature bytes."""
        sig = self._keypair.sign_message(message)
        return bytes(sig)

    def sign_message_base58(self, message: str) -> str:
        """Sign a message and return base58-encoded signature."""
        import base58
        sig_bytes = self.sign_message(message.encode("utf-8"))
        return base58.b58encode(sig_bytes).decode("utf-8")

    # ── Export ───────────────────────────────────────

    def export_private_key_base58(self) -> str:
        """Export private key as base58 string."""
        import base58
        return base58.b58encode(bytes(self._keypair)).decode("utf-8")

    def export_keypair_bytes(self) -> bytes:
        """Export keypair as raw bytes."""
        return bytes(self._keypair)

    # ── Cleanup ──────────────────────────────────────

    async def close(self):
        await self._client.close()