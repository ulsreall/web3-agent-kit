"""Wallet management — secure key handling and transaction signing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .chain import Chain, ChainManager


@dataclass
class WalletConfig:
    """Wallet configuration."""

    private_key: Optional[str] = None
    seed_phrase: Optional[str] = None
    keystore_path: Optional[str] = None
    password: Optional[str] = None


class Wallet:
    """
    Secure wallet management for multi-chain operations.

    Supports:
    - Private key import
    - Seed phrase import
    - Keystore file
    - Environment variable

    Example:
        wallet = Wallet.from_env("PRIVATE_KEY")
        wallet = Wallet.from_key("0x...")
        wallet = Wallet.from_seed("word1 word2 ... word12")
    """

    def __init__(self, config: WalletConfig, chain_manager: Optional[ChainManager] = None):
        self.config = config
        self.chain_manager = chain_manager
        self._account = None

    @classmethod
    def from_key(cls, private_key: str, **kwargs) -> "Wallet":
        """Create wallet from private key."""
        config = WalletConfig(private_key=private_key)
        return cls(config, **kwargs)

    @classmethod
    def from_env(cls, env_var: str = "PRIVATE_KEY", **kwargs) -> "Wallet":
        """Create wallet from environment variable."""
        key = os.environ.get(env_var)
        if not key:
            raise ValueError(f"Environment variable {env_var} not set")
        return cls.from_key(key, **kwargs)

    @classmethod
    def from_seed(cls, seed_phrase: str, index: int = 0, **kwargs) -> "Wallet":
        """Create wallet from seed phrase (BIP-39/BIP-44)."""
        config = WalletConfig(seed_phrase=seed_phrase)
        wallet = cls(config, **kwargs)
        wallet._derive_account(index)
        return wallet

    def _get_account(self):
        """Get or create web3 Account from private key."""
        if self._account is None:
            if not self.config.private_key:
                raise ValueError("No private key configured")
            from eth_account import Account
            self._account = Account.from_key(self.config.private_key)
        return self._account

    def _derive_account(self, index: int):
        """Derive account from seed phrase."""
        if not self.config.seed_phrase:
            raise ValueError("No seed phrase configured")
        from eth_account import Account
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(self.config.seed_phrase, account_path=f"m/44'/60'/0'/0/{index}")
        self.config.private_key = acct.key.hex()
        self._account = acct

    @property
    def address(self) -> str:
        """Get wallet address."""
        return self._get_account().address

    @property
    def private_key(self) -> str:
        """Get private key (use with caution)."""
        return self.config.private_key or ""

    def get_balance(self, chain: Chain) -> float:
        """Get native token balance on a chain."""
        if not self.chain_manager:
            raise ValueError("ChainManager not configured")

        if chain == Chain.SOLANA:
            sol = self.chain_manager.get_solana()
            resp = sol.get_balance(self.address)
            return resp.value / 1e9

        w3 = self.chain_manager.get_web3(chain)
        balance_wei = w3.eth.get_balance(self.address)
        return w3.from_wei(balance_wei, "ether")

    def sign_transaction(self, tx: dict, chain: Chain) -> bytes:
        """Sign a transaction for a specific chain."""
        if not self.config.private_key:
            raise ValueError("No private key configured")

        from eth_account import Account
        signed = Account.sign_transaction(tx, self.config.private_key)
        return signed.rawTransaction

    def send_transaction(self, tx: dict, chain: Chain) -> str:
        """Sign and send a transaction."""
        if not self.chain_manager:
            raise ValueError("ChainManager not configured")

        w3 = self.chain_manager.get_web3(chain)
        signed = self.sign_transaction(tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        return tx_hash.hex()

    def __repr__(self) -> str:
        return f"Wallet(address={self.address[:10]}...)"
