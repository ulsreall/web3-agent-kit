"""Wallet management — secure key handling and transaction signing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..chains.chain import Chain, ChainManager
from ..execution import ActionType


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
        wallet = Wallet.from_keystore("keystore.json", password="...")
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

    @classmethod
    def from_keystore(cls, keystore_path: str, password: str, **kwargs) -> "Wallet":
        """Create wallet from a standard Ethereum JSON keystore (UTC / V3) file.

        Args:
            keystore_path: path to the keystore JSON file.
            password: password used to decrypt the keystore.

        Raises:
            FileNotFoundError: if the keystore file doesn't exist.
            ValueError: if the password is wrong or the keystore is malformed
                (raised by ``eth_account`` as a ``ValueError``).
        """
        import json

        from eth_account import Account

        with open(keystore_path, "r", encoding="utf-8") as f:
            keystore_json = json.load(f)

        private_key = Account.decrypt(keystore_json, password)
        config = WalletConfig(
            private_key=private_key.hex(), keystore_path=keystore_path
        )
        return cls(config, **kwargs)

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

    def _raw_signer(self, tx: dict) -> bytes:
        """Low-level signing primitive. Do not call this directly.

        This is the single underlying signer the pre-sign gate wraps. Every
        other write path in the package must reach signing through
        :meth:`sign_transaction`, which enforces policy first.
        """
        if not self.config.private_key:
            raise ValueError("No private key configured")

        from eth_account import Account
        signed = Account.sign_transaction(tx, self.config.private_key)
        raw = getattr(signed, "raw_transaction", None)
        if raw is None:
            raw = signed.rawTransaction
        return raw

    def bind_enforcement(self, gate) -> "Wallet":
        """Attach an enforced pre-sign gate to this wallet.

        Once bound, :meth:`sign_transaction` routes every transaction through
        the gate. A wallet with no bound gate refuses to sign write-capable
        transactions rather than signing them unprotected.

        Returns self so it can be chained at construction time.
        """
        from ..execution import PreSignInterceptor

        if not isinstance(gate, PreSignInterceptor):
            raise ValueError("gate must be a PreSignInterceptor")
        self._gate = gate
        return self

    @property
    def enforcement(self):
        """Return the bound pre-sign gate, if any."""
        return getattr(self, "_gate", None)

    @property
    def is_enforced(self) -> bool:
        """Return whether an enforced pre-sign gate is bound."""
        return self.enforcement is not None

    def sign_transaction(
        self,
        tx: dict,
        chain: Chain,
        *,
        action: Optional[ActionType] = None,
        metadata: Optional[dict] = None,
    ) -> bytes:
        """Sign a transaction for a specific chain.

        When a pre-sign gate is bound, the transaction is evaluated against the
        execution policy before any signature is produced. A denial raises
        :class:`~web3_agent_kit.execution.EnforcementDenied` and no signature
        is created.

        When no gate is bound the call fails closed for transactions that
        carry a destination contract, because an unguarded signature of a
        write-capable call is indistinguishable from an authorized one.
        """
        gate = self.enforcement

        if gate is None:
            if tx.get("to") is not None:
                from ..execution import EnforcementDenied

                raise EnforcementDenied(
                    "wallet has no bound pre-sign gate; refusing to sign a "
                    "write-capable transaction. Call wallet.bind_enforcement(gate) "
                    "or route the call through an AuthorizedExecutor."
                )
            return self._raw_signer(tx)

        from ..execution import ActionType as _ActionType, AuthorizationRequest

        resolved_action = action or _ActionType.CONTRACT_CALL
        if not isinstance(resolved_action, _ActionType):
            raise ValueError("action must be an ActionType member")

        # Most builders omit "from"; the wallet owns the signer, so it supplies
        # the sender the intent requires. An explicit conflicting sender is an
        # error rather than a silent override.
        sender = tx.get("from")
        if sender is None:
            tx = {**tx, "from": self.address}
        elif str(sender).lower() != str(self.address).lower():
            from ..execution import EnforcementDenied

            raise EnforcementDenied(
                "transaction sender does not match the wallet address: "
                f"{sender} != {self.address}"
            )

        request = AuthorizationRequest(
            chain=chain,
            action=resolved_action,
            transaction=tx,
            metadata=metadata or {},
        )
        return gate.sign(request).raw_transaction

    def send_transaction(
        self,
        tx: dict,
        chain: Chain,
        *,
        action: Optional[ActionType] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Sign and send a transaction. Signing is policy-gated when bound."""
        if not self.chain_manager:
            raise ValueError("ChainManager not configured")

        w3 = self.chain_manager.get_web3(chain)
        signed = self.sign_transaction(
            tx, chain, action=action, metadata=metadata
        )
        tx_hash = w3.eth.send_raw_transaction(signed)
        return tx_hash.hex()

    def __repr__(self) -> str:
        return f"Wallet(address={self.address[:10]}...)"
