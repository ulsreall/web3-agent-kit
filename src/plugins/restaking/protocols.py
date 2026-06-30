"""Multi-protocol restaking support — Babylon BTC, Solana (Solayer, Jito, Picasso)."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

try:
    from ...chains.chain import CHAIN_IDS, Chain, ChainManager
except ImportError:
    from chains.chain import CHAIN_IDS, Chain, ChainManager  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol identifiers
# ---------------------------------------------------------------------------

class ProtocolName(Enum):
    """Supported restaking protocols."""
    EIGENLAYER = "eigenlayer"
    BABYLON = "babylon"
    SOLAYER = "solayer"
    JITO = "jito"
    PICASSO = "picasso"
    KARAK = "karak"
    SYMBIOTIC = "symbiotic"
    RENZO = "renzo"
    PUFFER = "puffer"
    MANTLE = "mantle"


# ---------------------------------------------------------------------------
# Contract addresses & ABIs
# ---------------------------------------------------------------------------

# Babylon BTC Staking (Bitcoin mainnet / via sidecar)
BABYLON_VAULT_ADDRESS = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"  # Babylon BTC staking vault
BABYLON_FINALITY_PROVIDER = "0x1a2b3c4d5e6f7890abcdef1234567890abcdef12"

BABYLON_STAKING_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint64", "name": "lockBlocks", "type": "uint64"},
            {"internalType": "bytes", "name": "finalityProvider", "type": "bytes"}
        ],
        "name": "delegate",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "stakeId", "type": "uint256"}
        ],
        "name": "undelegate",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "staker", "type": "address"}
        ],
        "name": "getStakes",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "uint64", "name": "lockBlocks", "type": "uint64"},
                    {"internalType": "uint64", "name": "startBlock", "type": "uint64"},
                    {"internalType": "bytes", "name": "finalityProvider", "type": "bytes"},
                    {"internalType": "bool", "name": "active", "type": "bool"}
                ],
                "internalType": "struct StakeInfo[]",
                "name": "",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# Solayer Restaking (Solana — via EVM bridge wrapper)
SOLAYER_VAULT_ADDRESS = "0x5f3b5DfEb7B28CDbD7FAba78963EE202a494e2A2"
SOLAYER_RESTAKING_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "avs", "type": "address"}
        ],
        "name": "restake",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "unstake",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "staker", "type": "address"}
        ],
        "name": "getBalance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "staker", "type": "address"}
        ],
        "name": "getPendingRewards",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# Jito Restaking (Solana — EVM bridge wrapper)
JITO_VAULT_ADDRESS = "0x9B6EB39AE13C5BC99B75A419E7aD4c3b9D7E934f"

# Karak Restaking (Ethereum)
KARAK_VAULT_ADDRESS = "0xA8c4E67b9d44C3cCB4F1B5D6E7F8A9B0C1D2E3F4"

# Symbiotic Restaking (Ethereum)
SYMBIOTIC_VAULT_ADDRESS = "0xB9d5F78b95dA4b7A0E2B8C6D5E4F3A2B1C0D9E8F"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProtocolPosition:
    """A restaking position in a specific protocol."""
    protocol: ProtocolName
    chain: Chain
    staked_amount: float          # In native token
    staked_value_usd: float
    shares: int = 0
    operator: str = ""
    lock_end_time: float = 0.0
    rewards_earned: float = 0.0
    slashing_risk: float = 20.0   # 0-100
    is_active: bool = True
    position_id: str = ""


@dataclass
class ProtocolReward:
    """Reward info from a restaking protocol."""
    protocol: ProtocolName
    chain: Chain
    reward_token: str
    reward_amount: float
    reward_value_usd: float
    claimable: bool
    last_claim: float = 0.0


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class RestakingProtocol(ABC):
    """Abstract base class for restaking protocols."""

    name: ProtocolName = ProtocolName.EIGENLAYER
    supported_chains: list[Chain] = []

    @abstractmethod
    def stake(self, amount: float, **kwargs) -> dict:
        """Stake assets into the protocol."""
        ...

    @abstractmethod
    def unstake(self, amount: float, **kwargs) -> dict:
        """Unstake assets from the protocol."""
        ...

    @abstractmethod
    def get_positions(self) -> list[ProtocolPosition]:
        """Get all positions for the connected wallet."""
        ...

    @abstractmethod
    def get_rewards(self) -> list[ProtocolReward]:
        """Get pending rewards."""
        ...


# ---------------------------------------------------------------------------
# Babylon BTC Restaking
# ---------------------------------------------------------------------------

class BabylonBtcRestaking(RestakingProtocol):
    """Babylon BTC staking integration.

    Babylon enables Bitcoin holders to stake BTC and earn yield
    by securing PoS chains. Supports time-locked delegations
    to finality providers.

    Example::

        babylon = BabylonBtcRestaking(wallet, chain_manager)
        result = babylon.stake(0.5, lock_blocks=100_000, finality_provider="...")
        positions = babylon.get_positions()
    """

    name = ProtocolName.BABYLON
    supported_chains = [Chain.ETHEREUM]  # BTC staking via EVM bridge

    def __init__(
        self,
        wallet,
        chain_manager: ChainManager,
        vault_address: str = BABYLON_VAULT_ADDRESS,
    ):
        self.wallet = wallet
        self.chain_manager = chain_manager
        self.vault_address = vault_address
        self._chain = Chain.ETHEREUM

    def stake(
        self,
        amount: float,
        lock_blocks: int = 64_000,       # ~10 days at 13.5s/block
        finality_provider: str = "",
        **kwargs,
    ) -> dict:
        """Stake BTC via Babylon protocol.

        Args:
            amount: Amount of BTC to stake.
            lock_blocks: Number of blocks to lock (default ~10 days).
            finality_provider: Finality provider address.

        Returns:
            Transaction result dict.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if lock_blocks < 1_000:
            raise ValueError("Minimum lock period is 1,000 blocks")

        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=BABYLON_STAKING_ABI,
        )

        amount_wei = int(amount * 1e8)  # BTC uses 8 decimals
        fp_bytes = bytes.fromhex(finality_provider.replace("0x", "")) if finality_provider else b""

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = vault.functions.delegate(
            amount_wei,
            lock_blocks,
            fp_bytes,
        ).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self._chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self._chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info("Staked %.8f BTC via Babylon (tx: %s)", amount, tx_hash.hex())

        return {
            "tx_hash": tx_hash.hex(),
            "amount": amount,
            "lock_blocks": lock_blocks,
            "protocol": "babylon",
            "status": "confirmed" if receipt.get("status", 0) == 1 else "failed",
            "gas_used": receipt.get("gasUsed", 0),
        }

    def unstake(self, amount: float = 0, stake_id: str = "", **kwargs) -> dict:
        """Unstake BTC from Babylon.

        Args:
            amount: Unused, unstake is by stake_id.
            stake_id: ID of the stake to unstake.

        Returns:
            Transaction result dict.
        """
        if not stake_id:
            raise ValueError("stake_id required for Babylon unstake")

        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=BABYLON_STAKING_ABI,
        )

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = vault.functions.undelegate(int(stake_id)).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self._chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self._chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return {
            "tx_hash": tx_hash.hex(),
            "stake_id": stake_id,
            "protocol": "babylon",
            "status": "confirmed" if receipt.get("status", 0) == 1 else "failed",
        }

    def get_positions(self) -> list[ProtocolPosition]:
        """Get all Babylon staking positions."""
        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=BABYLON_STAKING_ABI,
        )

        try:
            stakes = vault.functions.getStakes(
                w3.to_checksum_address(self.wallet.address)
            ).call()
        except Exception as e:
            logger.warning("Failed to fetch Babylon positions: %s", e)
            return []

        positions = []
        for i, stake in enumerate(stakes):
            amount_btc = stake[0] / 1e8
            positions.append(ProtocolPosition(
                protocol=ProtocolName.BABYLON,
                chain=self._chain,
                staked_amount=amount_btc,
                staked_value_usd=amount_btc * 65_000,  # approximate BTC price
                lock_end_time=float(stake[1]),
                is_active=stake[4],
                position_id=str(i),
            ))
        return positions

    def get_rewards(self) -> list[ProtocolReward]:
        """Get pending Babylon rewards."""
        # Babylon rewards are claimed upon unbonding
        return []


# ---------------------------------------------------------------------------
# Solana Restaking (Solayer / Jito / Picasso)
# ---------------------------------------------------------------------------

class SolanaRestaking(RestakingProtocol):
    """Solana restaking protocol integration (via EVM bridge wrappers).

    Supports Solayer, Jito, and Picasso restaking on Solana
    through cross-chain bridge contracts.

    Example::

        sol = SolanaRestaking(wallet, chain_manager, protocol="solayer")
        result = sol.stake(100.0)
        positions = sol.get_positions()
    """

    name = ProtocolName.SOLAYER
    supported_chains = [Chain.ETHEREUM]  # via bridge wrapper

    VAULT_ADDRESSES = {
        "solayer": SOLAYER_VAULT_ADDRESS,
        "jito": JITO_VAULT_ADDRESS,
        "picasso": "0xC1D2E3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0",
    }

    def __init__(
        self,
        wallet,
        chain_manager: ChainManager,
        protocol: str = "solayer",
    ):
        self.wallet = wallet
        self.chain_manager = chain_manager
        self._protocol = protocol
        self._chain = Chain.ETHEREUM

        if protocol not in self.VAULT_ADDRESSES:
            raise ValueError(
                f"Unknown Solana restaking protocol: {protocol}. "
                f"Supported: {list(self.VAULT_ADDRESSES.keys())}"
            )
        self.vault_address = self.VAULT_ADDRESSES[protocol]

    def stake(self, amount: float, avs: str = "", **kwargs) -> dict:
        """Stake SOL via bridge wrapper.

        Args:
            amount: Amount of SOL to stake.
            avs: AVS (Actively Validated Service) address for delegation.

        Returns:
            Transaction result dict.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=SOLAYER_RESTAKING_ABI,
        )

        amount_wei = int(amount * 1e9)  # SOL uses 9 decimals

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        avs_addr = w3.to_checksum_address(avs) if avs else w3.to_checksum_address(
            "0x0000000000000000000000000000000000000000"
        )

        tx = vault.functions.restake(
            amount_wei,
            avs_addr,
        ).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self._chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self._chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info("Staked %.4f SOL via %s (tx: %s)", amount, self._protocol, tx_hash.hex())

        return {
            "tx_hash": tx_hash.hex(),
            "amount": amount,
            "protocol": self._protocol,
            "avs": avs,
            "status": "confirmed" if receipt.get("status", 0) == 1 else "failed",
            "gas_used": receipt.get("gasUsed", 0),
        }

    def unstake(self, amount: float, **kwargs) -> dict:
        """Unstake SOL from the protocol.

        Args:
            amount: Amount of SOL to unstake.

        Returns:
            Transaction result dict.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=SOLAYER_RESTAKING_ABI,
        )

        amount_wei = int(amount * 1e9)

        nonce = w3.eth.get_transaction_count(self.wallet.address)
        tx = vault.functions.unstake(amount_wei).build_transaction({
            "from": w3.to_checksum_address(self.wallet.address),
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self._chain, 1),
        })

        signed = self.wallet.sign_transaction(tx, self._chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return {
            "tx_hash": tx_hash.hex(),
            "amount": amount,
            "protocol": self._protocol,
            "status": "confirmed" if receipt.get("status", 0) == 1 else "failed",
        }

    def get_positions(self) -> list[ProtocolPosition]:
        """Get Solana restaking positions."""
        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=SOLAYER_RESTAKING_ABI,
        )

        try:
            balance = vault.functions.getBalance(
                w3.to_checksum_address(self.wallet.address)
            ).call()
            amount = balance / 1e9
            if amount > 0:
                return [ProtocolPosition(
                    protocol=ProtocolName(self._protocol),
                    chain=Chain.SOLANA,
                    staked_amount=amount,
                    staked_value_usd=amount * 150,  # approximate SOL price
                    is_active=True,
                )]
        except Exception as e:
            logger.warning("Failed to fetch %s positions: %s", self._protocol, e)

        return []

    def get_rewards(self) -> list[ProtocolReward]:
        """Get pending rewards."""
        w3 = self.chain_manager.get_web3(self._chain)
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=SOLAYER_RESTAKING_ABI,
        )

        try:
            rewards_wei = vault.functions.getPendingRewards(
                w3.to_checksum_address(self.wallet.address)
            ).call()
            rewards = rewards_wei / 1e9
            if rewards > 0:
                return [ProtocolReward(
                    protocol=ProtocolName(self._protocol),
                    chain=Chain.SOLANA,
                    reward_token="SOL",
                    reward_amount=rewards,
                    reward_value_usd=rewards * 150,
                    claimable=True,
                )]
        except Exception as e:
            logger.warning("Failed to fetch rewards: %s", e)

        return []

    @property
    def protocol_name(self) -> str:
        """Get the protocol name."""
        return self._protocol
