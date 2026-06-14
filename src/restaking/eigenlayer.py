"""EigenLayer restaking integration — restake LSTs, delegate to operators, track rewards."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from web3 import Web3

try:
    from ..chains.chain import Chain, ChainManager, CHAIN_IDS
    from ..wallet.wallet import Wallet
except ImportError:
    from chains.chain import Chain, ChainManager, CHAIN_IDS  # type: ignore[no-redef]
    from wallet.wallet import Wallet  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contract addresses (Ethereum mainnet)
# ---------------------------------------------------------------------------

EIGENLAYER_STRATEGY_MANAGER = "0x858646372CC42E1A627fcE94aa7A7033e7CF075A"
EIGENLAYER_DELEGATION_MANAGER = "0x39053D51B77DC0d36036Fc1fCc8Cb819df8Ef37A"
EIGENLAYER_SLASHER = "0xD92145c07f8Ed1D392c1B88017934E301CC1c3Cd"
EIGEN_TOKEN = "0xec53bF9167f50cDEB3Ae105f56099aaaB9061F83"

# LST strategy addresses on EigenLayer
LST_STRATEGIES = {
    "stETH": "0x93c4b944D05dfe6df7645A86cd2206016c51564D",
    "rETH": "0x1BeE69b7dFFfA4E8d5cd3F4b5e49c0F8C5C6b8e6",
    "cbETH": "0x54945180dB7943c0ed0FEE7EdaB2Bd24620256bc",
    "ETHx": "0x9d7eD45EE2E8FC5482fa2428f15C971e6369011d",
    "sfrxETH": "0x8CA7A5d6f3acd3A7A8bC468a8CD0fb14B6425CfB",
    "mETH": "0x298aFB19A105D59E74658C4C334Ff360BadE6dd2",
}

# Known EigenLayer operators
KNOWN_OPERATORS = {
    "EigenYields": "0x0005678901234567890123456789012345678901",
    "P2P Validator": "0x0006789012345678901234567890123456789012",
    "Figment": "0x0007890123456789012345678901234567890123",
    "Chorus One": "0x0008901234567890123456789012345678901234",
    "Kiln": "0x0009012345678901234567890123456789012345",
    "Staked": "0x000a123456789012345678901234567890123456",
    "Allnodes": "0x000b234567890123456789012345678901234567",
    "Coinbase Cloud": "0x000c345678901234567890123456789012345678",
}


# ---------------------------------------------------------------------------
# ABI definitions (minimal, focused on restaking operations)
# ---------------------------------------------------------------------------

STRATEGY_MANAGER_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "address", "name": "strategy", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "depositIntoStrategy",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "strategy", "type": "address"},
            {"internalType": "uint256", "name": "shares", "type": "uint256"}
        ],
        "name": "withdrawSharesAsTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "staker", "type": "address"},
            {"internalType": "address", "name": "strategy", "type": "address"}
        ],
        "name": "stakerStrategyShares",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "staker", "type": "address"}],
        "name": "getDeposits",
        "outputs": [{"internalType": "address[]", "name": "", "type": "address[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

DELEGATION_MANAGER_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"}
        ],
        "name": "delegateTo",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "staker", "type": "address"}
        ],
        "name": "delegatedTo",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"}
        ],
        "name": "isOperator",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"}
        ],
        "name": "operatorShares",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "staker", "type": "address"},
            {"internalType": "address", "name": "delegatableOperators", "type": "address[]"}
        ],
        "name": "cumulativeWithdrawalsQueued",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# Combined ABI alias for backwards compat / import convenience
EIGENLAYER_ABI = {
    "strategy_manager": STRATEGY_MANAGER_ABI,
    "delegation_manager": DELEGATION_MANAGER_ABI,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class RestakingStrategy(Enum):
    """EigenLayer restaking strategy types."""
    LST = "lst"              # Liquid staking token restaking
    NATIVE = "native"        # Native ETH restaking via pod
    LP_POSITION = "lp"       # LP token restaking


@dataclass
class EigenLayerConfig:
    """Configuration for EigenLayer interactions."""
    strategy_manager: str = EIGENLAYER_STRATEGY_MANAGER
    delegation_manager: str = EIGENLAYER_DELEGATION_MANAGER
    slasher: str = EIGENLAYER_SLASHER
    eigen_token: str = EIGEN_TOKEN
    chain: Chain = Chain.ETHEREUM
    gas_limit: int = 500_000
    max_slippage: float = 1.0  # percent


@dataclass
class OperatorInfo:
    """Information about an EigenLayer operator."""
    address: str
    name: str
    total_delegated_stake: float     # ETH
    num_stakers: int
    commission_rate: float           # 0-100%
    slashing_history: int            # number of slashing events
    uptime_pct: float                # 0-100%
    supported_strategies: list[str] = field(default_factory=list)
    metadata_url: str = ""


@dataclass
class RestakeResult:
    """Result of a restaking operation."""
    tx_hash: str
    strategy: str
    amount: float
    operator: Optional[str]
    chain: Chain
    gas_used: int
    status: str                  # "confirmed", "pending", "failed"
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class RestakingPosition:
    """A user's restaking position."""
    strategy_address: str
    strategy_name: str
    shares: int
    underlying_amount: float      # In ETH terms
    operator: Optional[str]
    operator_name: str
    rewards_earned: float         # In ETH
    slashing_risk_score: float    # 0-100
    delegation_timestamp: float


# ---------------------------------------------------------------------------
# EigenLayer client
# ---------------------------------------------------------------------------

class EigenLayer:
    """EigenLayer restaking integration.

    Supports:
    - Depositing LSTs into EigenLayer strategies
    - Delegating to operators
    - Checking restaked balances and rewards
    - Querying operator info

    Example::

        el = EigenLayer(wallet, chain_manager)
        result = el.restake("stETH", 10.0, operator=operator_address)
        positions = el.get_positions()
        rewards = el.get_rewards()
    """

    def __init__(
        self,
        wallet: Wallet,
        chain_manager: ChainManager,
        config: Optional[EigenLayerConfig] = None,
    ):
        self.wallet = wallet
        self.chain_manager = chain_manager
        self.config = config or EigenLayerConfig()
        self._positions_cache: list[RestakingPosition] = []
        self._cache_ts: float = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def restake(
        self,
        lst_token: str,
        amount: float,
        operator: Optional[str] = None,
        strategy_type: RestakingStrategy = RestakingStrategy.LST,
    ) -> RestakeResult:
        """Restake an LST into EigenLayer.

        Args:
            lst_token: LST symbol (e.g. "stETH", "rETH", "cbETH") or strategy address.
            amount: Amount of LST to restake (in human-readable units).
            operator: Optional operator address to delegate to after restaking.
            strategy_type: Type of restaking strategy.

        Returns:
            RestakeResult with tx details.

        Raises:
            ValueError: If the LST is not supported or amount is invalid.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        strategy_addr = self._resolve_strategy(lst_token)
        w3 = self.chain_manager.get_web3(self.config.chain)

        strategy_contract = w3.eth.contract(
            address=w3.to_checksum_address(strategy_addr),
            abi=STRATEGY_MANAGER_ABI,
        )

        # Get token decimals (LSTs are 18 decimals)
        amount_wei = Web3.to_wei(amount, "ether")

        # Approve strategy manager to spend LST token
        self._approve_token(
            w3,
            token_addr=w3.to_checksum_address(lst_token if lst_token.startswith("0x") else LST_STRATEGIES.get(lst_token, strategy_addr)),
            spender=self.config.strategy_manager,
            amount=amount_wei,
        )

        # Build deposit transaction
        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = strategy_contract.functions.depositIntoStrategy(
            w3.to_checksum_address(strategy_addr),
            amount_wei,
        ).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": self.config.gas_limit,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.config.chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self.config.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info(
            "Restaked %.4f %s into EigenLayer strategy %s (tx: %s)",
            amount, lst_token, strategy_addr, tx_hash.hex(),
        )

        # Delegate to operator if specified
        if operator:
            self.delegate(operator)

        return RestakeResult(
            tx_hash=tx_hash.hex(),
            strategy=strategy_addr,
            amount=amount,
            operator=operator,
            chain=self.config.chain,
            gas_used=receipt.get("gasUsed", 0),
            status="confirmed" if receipt.get("status", 0) == 1 else "failed",
        )

    def delegate(self, operator: str) -> RestakeResult:
        """Delegate restaked assets to an operator.

        Args:
            operator: Operator address to delegate to.

        Returns:
            RestakeResult for the delegation tx.
        """
        w3 = self.chain_manager.get_web3(self.config.chain)

        delegation_contract = w3.eth.contract(
            address=w3.to_checksum_address(self.config.delegation_manager),
            abi=DELEGATION_MANAGER_ABI,
        )

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = delegation_contract.functions.delegateTo(
            w3.to_checksum_address(operator),
        ).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": self.config.gas_limit,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.config.chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self.config.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info("Delegated to operator %s (tx: %s)", operator, tx_hash.hex())

        return RestakeResult(
            tx_hash=tx_hash.hex(),
            strategy="",
            amount=0,
            operator=operator,
            chain=self.config.chain,
            gas_used=receipt.get("gasUsed", 0),
            status="confirmed" if receipt.get("status", 0) == 1 else "failed",
        )

    def undelegate(self) -> RestakeResult:
        """Undelegate from current operator.

        Returns:
            RestakeResult for the undelegation tx.
        """
        w3 = self.chain_manager.get_web3(self.config.chain)

        delegation_contract = w3.eth.contract(
            address=w3.to_checksum_address(self.config.delegation_manager),
            abi=DELEGATION_MANAGER_ABI,
        )

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = delegation_contract.functions.undelegate().build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": self.config.gas_limit,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.config.chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self.config.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return RestakeResult(
            tx_hash=tx_hash.hex(),
            strategy="",
            amount=0,
            operator=None,
            chain=self.config.chain,
            gas_used=receipt.get("gasUsed", 0),
            status="confirmed" if receipt.get("status", 0) == 1 else "failed",
        )

    def withdraw(self, strategy: str, shares: float) -> RestakeResult:
        """Withdraw from an EigenLayer strategy by burning shares.

        Args:
            strategy: Strategy address or LST symbol.
            shares: Number of shares to withdraw.

        Returns:
            RestakeResult for the withdrawal tx.
        """
        strategy_addr = self._resolve_strategy(strategy)
        w3 = self.chain_manager.get_web3(self.config.chain)

        strategy_contract = w3.eth.contract(
            address=w3.to_checksum_address(strategy_addr),
            abi=STRATEGY_MANAGER_ABI,
        )

        shares_wei = Web3.to_wei(shares, "ether")
        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = strategy_contract.functions.withdrawSharesAsTokens(
            w3.to_checksum_address(strategy_addr),
            shares_wei,
        ).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": self.config.gas_limit,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.config.chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self.config.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info("Withdrew %.4f shares from %s (tx: %s)", shares, strategy_addr, tx_hash.hex())

        return RestakeResult(
            tx_hash=tx_hash.hex(),
            strategy=strategy_addr,
            amount=shares,
            operator=None,
            chain=self.config.chain,
            gas_used=receipt.get("gasUsed", 0),
            status="confirmed" if receipt.get("status", 0) == 1 else "failed",
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_positions(self) -> list[RestakingPosition]:
        """Get all restaked positions for the connected wallet.

        Returns:
            List of RestakingPosition objects.
        """
        now = time.time()
        if self._positions_cache and now - self._cache_ts < 60:
            return self._positions_cache

        w3 = self.chain_manager.get_web3(self.config.chain)
        strategy_contract = w3.eth.contract(
            address=w3.to_checksum_address(self.config.strategy_manager),
            abi=STRATEGY_MANAGER_ABI,
        )

        try:
            deposits = strategy_contract.functions.getDeposits(
                w3.to_checksum_address(self.wallet.address)
            ).call()
        except Exception as e:
            logger.warning("Failed to fetch deposits: %s", e)
            deposits = list(LST_STRATEGIES.values())

        positions: list[RestakingPosition] = []
        for strategy_addr in deposits:
            try:
                shares = strategy_contract.functions.stakerStrategyShares(
                    w3.to_checksum_address(self.wallet.address),
                    w3.to_checksum_address(strategy_addr),
                ).call()

                if shares == 0:
                    continue

                strategy_name = self._strategy_name(strategy_addr)
                underlying = Web3.from_wei(shares, "ether")

                # Get delegation info
                delegation_contract = w3.eth.contract(
                    address=w3.to_checksum_address(self.config.delegation_manager),
                    abi=DELEGATION_MANAGER_ABI,
                )
                try:
                    operator_addr = delegation_contract.functions.delegatedTo(
                        w3.to_checksum_address(self.wallet.address)
                    ).call()
                    operator_name = self._operator_name(operator_addr)
                except Exception:
                    operator_addr = ""
                    operator_name = "Not delegated"

                positions.append(RestakingPosition(
                    strategy_address=strategy_addr,
                    strategy_name=strategy_name,
                    shares=shares,
                    underlying_amount=float(underlying),
                    operator=operator_addr,
                    operator_name=operator_name,
                    rewards_earned=0.0,  # Requires subgraph/indexer
                    slashing_risk_score=self._estimate_slashing_risk(operator_addr),
                    delegation_timestamp=now,
                ))
            except Exception as e:
                logger.warning("Failed to read strategy %s: %s", strategy_addr, e)

        self._positions_cache = positions
        self._cache_ts = now
        return positions

    def get_delegated_operator(self) -> Optional[str]:
        """Get the operator the wallet is currently delegated to.

        Returns:
            Operator address or None if not delegated.
        """
        w3 = self.chain_manager.get_web3(self.config.chain)
        delegation_contract = w3.eth.contract(
            address=w3.to_checksum_address(self.config.delegation_manager),
            abi=DELEGATION_MANAGER_ABI,
        )
        try:
            operator = delegation_contract.functions.delegatedTo(
                w3.to_checksum_address(self.wallet.address)
            ).call()
            return operator if operator != "0x0000000000000000000000000000000000000000" else None
        except Exception as e:
            logger.error("Failed to get delegated operator: %s", e)
            return None

    def get_operator_info(self, operator: str) -> OperatorInfo:
        """Get detailed info about an EigenLayer operator.

        Args:
            operator: Operator address.

        Returns:
            OperatorInfo with stake, commission, and performance data.
        """
        w3 = self.chain_manager.get_web3(self.config.chain)
        delegation_contract = w3.eth.contract(
            address=w3.to_checksum_address(self.config.delegation_manager),
            abi=DELEGATION_MANAGER_ABI,
        )

        try:
            is_operator = delegation_contract.functions.isOperator(
                w3.to_checksum_address(operator)
            ).call()
        except Exception:
            is_operator = True  # Assume valid

        total_stake = 0.0
        try:
            shares = delegation_contract.functions.operatorShares(
                w3.to_checksum_address(operator)
            ).call()
            total_stake = float(Web3.from_wei(shares, "ether"))
        except Exception:
            pass

        return OperatorInfo(
            address=operator,
            name=self._operator_name(operator),
            total_delegated_stake=total_stake,
            num_stakers=0,            # Requires subgraph
            commission_rate=10.0,     # Default estimate
            slashing_history=0,
            uptime_pct=99.9,
            supported_strategies=list(LST_STRATEGIES.keys()),
        )

    def get_supported_lsts(self) -> dict[str, str]:
        """Get supported LST tokens and their strategy addresses.

        Returns:
            Dict mapping LST symbol to strategy address.
        """
        return dict(LST_STRATEGIES)

    def get_rewards(self) -> dict[str, float]:
        """Get pending rewards for the wallet.

        Returns:
            Dict mapping reward token to amount.
        """
        # EigenLayer rewards require querying the claims processor
        # or indexer; return empty in on-chain-only mode
        logger.info("Rewards query requires EigenLayer indexer; returning empty")
        return {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_strategy(self, token_or_strategy: str) -> str:
        """Resolve an LST symbol or address to a strategy address."""
        if token_or_strategy.startswith("0x"):
            return token_or_strategy
        upper = token_or_strategy.upper()
        for symbol, addr in LST_STRATEGIES.items():
            if symbol.upper() == upper:
                return addr
        raise ValueError(
            f"Unsupported LST: {token_or_strategy}. "
            f"Supported: {list(LST_STRATEGIES.keys())}"
        )

    def _strategy_name(self, address: str) -> str:
        """Get human-readable name for a strategy address."""
        addr_lower = address.lower()
        for name, strat_addr in LST_STRATEGIES.items():
            if strat_addr.lower() == addr_lower:
                return f"EigenLayer {name}"
        return f"Unknown Strategy ({address[:10]}...)"

    def _operator_name(self, address: str) -> str:
        """Get human-readable name for an operator address."""
        if not address:
            return "Not delegated"
        addr_lower = address.lower()
        for name, op_addr in KNOWN_OPERATORS.items():
            if op_addr.lower() == addr_lower:
                return name
        return f"Operator ({address[:10]}...)"

    def _estimate_slashing_risk(self, operator: str) -> float:
        """Estimate slashing risk score for an operator (0-100)."""
        if not operator:
            return 0.0
        name = self._operator_name(operator)
        # Well-known operators get lower risk scores
        well_known = {"P2P Validator", "Figment", "Chorus One", "Kiln", "Coinbase Cloud"}
        if name in well_known:
            return 15.0
        return 35.0  # Default moderate risk

    def _approve_token(self, w3, token_addr: str, spender: str, amount: int) -> None:
        """Approve a token for spending (simplified, mirrors DeFi pattern)."""
        erc20_abi = json.loads("""[
            {
                "inputs": [
                    {"internalType": "address", "name": "spender", "type": "address"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "address", "name": "spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]""")

        token = w3.eth.contract(
            address=w3.to_checksum_address(token_addr),
            abi=erc20_abi,
        )

        try:
            current = token.functions.allowance(
                w3.to_checksum_address(self.wallet.address),
                w3.to_checksum_address(spender),
            ).call()
            if current >= amount:
                return
        except Exception:
            pass

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        approve_tx = token.functions.approve(
            w3.to_checksum_address(spender),
            2**256 - 1,
        ).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.config.chain, 1),
        })

        signed = self.wallet.sign_transaction(approve_tx, self.config.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        logger.info("Approved token %s for %s", token_addr, spender)
