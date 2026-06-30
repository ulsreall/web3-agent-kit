"""On-chain Airdrop Module — automate DeFi interactions for airdrop farming.

Automates on-chain activities that qualify for airdrops:
- DEX swaps (Uniswap, Jupiter, Aerodrome)
- Bridge usage (Stargate, Across, Hop, LayerZero)
- Lending (Aave, Compound, Morpho)
- Staking/Restaking (EigenLayer, Ether.fi, Renzo)
- L2 activity (Base, Arbitrum, Optimism, zkSync, Scroll, Linea)

Usage::

    from web3_agent_kit.airdrop.onchain import OnChainAirdropFarmer, OnChainConfig

    config = OnChainConfig(
        private_key="0x...",
        chain="base",
        rpc_url="https://mainnet.base.org",
    )
    farmer = OnChainAirdropFarmer(config)
    farmer.farm_all()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Chain(Enum):
    """Supported chains."""
    ETHEREUM = "ethereum"
    BASE = "base"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    POLYGON = "polygon"
    BNB = "bnb"
    AVALANCHE = "avalanche"
    ZKSYNC = "zksync"
    SCROLL = "scroll"
    LINEA = "linea"
    BLAST = "blast"
    SOLANA = "solana"


class DeFiProtocol(Enum):
    """Supported DeFi protocols."""
    # DEX
    UNISWAP_V3 = "uniswap_v3"
    AERODROME = "aerodrome"
    JUPITER = "jupiter"
    PANCAKESWAP = "pancakeswap"
    CAMELOT = "camelot"
    SYNCSWAP = "syncswap"
    SKYDROME = "skydrome"
    VELodrome = "velodrome"

    # Bridge
    STARGATE = "stargate"
    ACROSS = "across"
    HOP = "hop"
    LAYERZERO = "layerzero"
    DEBRIDGE = "debridge"
    WORMHOLE = "wormhole"

    # Lending
    AAVE_V3 = "aave_v3"
    COMPOUND_V3 = "compound_v3"
    MORPHO = "morpho"
    RADIANT = "radiant"
    SPARK = "spark"

    # Staking/Restaking
    EIGENLAYER = "eigenlayer"
    ETHERFI = "etherfi"
    RENZO = "renzo"
    PUFFER = "puffer"
    KELP = "kelp"
    SWELL = "swell"

    # LRT
    MELLOW = "mellow"


@dataclass
class OnChainConfig:
    """Configuration for on-chain airdrop farming."""
    private_key: str = ""
    chain: str = "base"
    rpc_url: str = ""
    # Transaction settings
    gas_limit: int = 500000
    max_gas_price_gwei: int = 50
    slippage_bps: int = 50  # 0.5%
    # Amount settings
    swap_amount_eth: float = 0.001
    bridge_amount_eth: float = 0.001
    lend_amount_eth: float = 0.01
    stake_amount_eth: float = 0.01
    # Timing
    delay_between_txs: float = 10.0
    randomize_delay: bool = True
    # Safety
    dry_run: bool = True  # Default: simulate only
    max_daily_txs: int = 50
    # Proxy
    proxy: Optional[str] = None


@dataclass
class TransactionResult:
    """Result of an on-chain transaction."""
    protocol: str
    action: str
    chain: str
    tx_hash: str = ""
    success: bool = False
    gas_used: int = 0
    gas_cost_eth: float = 0.0
    amount: str = ""
    error: str = ""
    block_number: int = 0
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "action": self.action,
            "chain": self.chain,
            "tx_hash": self.tx_hash,
            "success": self.success,
            "gas_used": self.gas_used,
            "gas_cost_eth": self.gas_cost_eth,
            "amount": self.amount,
            "error": self.error,
            "block_number": self.block_number,
        }


@dataclass
class FarmingPlan:
    """A farming plan with specific actions."""
    name: str
    description: str
    chain: Chain = Chain.BASE
    protocols: list[DeFiProtocol] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    estimated_gas_eth: float = 0.0
    estimated_points: int = 0
    priority: int = 0  # Higher = more important


# Pre-defined farming plans for known airdrops
FARMING_PLANS: dict[str, FarmingPlan] = {
    "base_activity": FarmingPlan(
        name="Base Activity",
        description="Daily swaps + NFT mints on Base for Base airdrop",
        chain=Chain.BASE,
        protocols=[DeFiProtocol.AERODROME, DeFiProtocol.UNISWAP_V3],
        actions=[
            {"protocol": "aerodrome", "action": "swap", "tokens": ["ETH", "USDC"]},
            {"protocol": "uniswap_v3", "action": "swap", "tokens": ["ETH", "USDbC"]},
            {"protocol": "aerodrome", "action": "add_liquidity"},
        ],
        estimated_gas_eth=0.0005,
        estimated_points=50,
        priority=10,
    ),
    "eigenlayer_restake": FarmingPlan(
        name="EigenLayer Restake",
        description="Restake ETH/LSTs on EigenLayer for EIGEN airdrop",
        chain=Chain.ETHEREUM,
        protocols=[DeFiProtocol.EIGENLAYER],
        actions=[
            {"protocol": "eigenlayer", "action": "deposit", "asset": "stETH"},
            {"protocol": "eigenlayer", "action": "delegate_operator"},
        ],
        estimated_gas_eth=0.005,
        estimated_points=200,
        priority=9,
    ),
    "arbitrum_defi": FarmingPlan(
        name="Arbitrum DeFi",
        description="Use GMX, Radiant, Uniswap on Arbitrum",
        chain=Chain.ARBITRUM,
        protocols=[DeFiProtocol.AAVE_V3, DeFiProtocol.UNISWAP_V3],
        actions=[
            {"protocol": "uniswap_v3", "action": "swap", "tokens": ["ETH", "USDC"]},
            {"protocol": "aave_v3", "action": "supply", "asset": "USDC"},
            {"protocol": "aave_v3", "action": "borrow", "asset": "ETH"},
        ],
        estimated_gas_eth=0.0003,
        estimated_points=80,
        priority=8,
    ),
    "optimism_rpgf": FarmingPlan(
        name="Optimism RPGF",
        description="Velodrome swaps + OP delegation for OP airdrop",
        chain=Chain.OPTIMISM,
        protocols=[DeFiProtocol.VELodrome],
        actions=[
            {"protocol": "velodrome", "action": "swap", "tokens": ["ETH", "USDC"]},
            {"protocol": "velodrome", "action": "add_liquidity"},
        ],
        estimated_gas_eth=0.0002,
        estimated_points=60,
        priority=7,
    ),
    "scroll_activity": FarmingPlan(
        name="Scroll Activity",
        description="Skydrome + bridge activity on Scroll",
        chain=Chain.SCROLL,
        protocols=[DeFiProtocol.SKYDROME],
        actions=[
            {"protocol": "skydrome", "action": "swap", "tokens": ["ETH", "USDC"]},
        ],
        estimated_gas_eth=0.0002,
        estimated_points=40,
        priority=6,
    ),
    "linea_voyage": FarmingPlan(
        name="Linea DeFi Voyage",
        description="SyncSwap + NILE on Linea",
        chain=Chain.LINEA,
        protocols=[DeFiProtocol.SYNCSWAP],
        actions=[
            {"protocol": "syncswap", "action": "swap", "tokens": ["ETH", "USDC"]},
        ],
        estimated_gas_eth=0.0002,
        estimated_points=40,
        priority=6,
    ),
    "zksync_era": FarmingPlan(
        name="zkSync Era",
        description="SyncSwap + Mute.io on zkSync",
        chain=Chain.ZKSYNC,
        protocols=[DeFiProtocol.SYNCSWAP],
        actions=[
            {"protocol": "syncswap", "action": "swap", "tokens": ["ETH", "USDC"]},
        ],
        estimated_gas_eth=0.0003,
        estimated_points=50,
        priority=6,
    ),
}


class OnChainAirdropFarmer:
    """Automate on-chain DeFi interactions for airdrop farming.

    Supports multiple chains and protocols. Executes swap, bridge, lend,
    stake, and restake transactions to accumulate on-chain activity
    that qualifies for airdrops.

    Example::

        config = OnChainConfig(
            private_key="0x...",
            chain="base",
            rpc_url="https://mainnet.base.org",
            dry_run=True,
        )
        farmer = OnChainAirdropFarmer(config)
        farmer.farm_all()
    """

    # Chain RPC URLs (defaults, can be overridden)
    DEFAULT_RPCS: dict[str, str] = {
        "ethereum": "https://eth.llamarpc.com",
        "base": "https://mainnet.base.org",
        "arbitrum": "https://arb1.arbitrum.io/rpc",
        "optimism": "https://mainnet.optimism.io",
        "polygon": "https://polygon-rpc.com",
        "bnb": "https://bsc-dataseed.binance.org",
        "avalanche": "https://api.avax.network/ext/bc/C/rpc",
        "zksync": "https://mainnet.era.zksync.io",
        "scroll": "https://rpc.scroll.io",
        "linea": "https://rpc.linea.build",
        "blast": "https://rpc.blast.io",
    }

    # Minimal ABIs for common operations
    ERC20_ABI = [
        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    ]

    # Known DEX router addresses
    ROUTERS: dict[str, dict[str, str]] = {
        "base": {
            "aerodrome": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
            "uniswap_v3": "0x2626664c2603336E57B271c5C0b26F421741e481",
        },
        "ethereum": {
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        },
        "arbitrum": {
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        },
        "optimism": {
            "velodrome": "0x9c12939390052919aF3155f41Bf42913ABfB8e51",
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        },
    }

    # Known token addresses (per chain)
    TOKENS: dict[str, dict[str, str]] = {
        "base": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0x4200000000000000000000000000000000000006",
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
            "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
        },
        "ethereum": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "stETH": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        },
        "arbitrum": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
            "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",
        },
        "optimism": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0x4200000000000000000000000000000000000006",
            "USDC": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
            "USDC.e": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",
            "OP": "0x4200000000000000000000000000000000000042",
        },
        "scroll": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0x5300000000000000000000000000000000000004",
            "USDC": "0x06eFdBFf2a14a7c8E15944D1F4A48F9F95F663A4",
        },
        "linea": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f",
            "USDC": "0x176211869cA2b568f2A7D4EE941E073a821EE1ff",
        },
        "zksync": {
            "ETH": "0x0000000000000000000000000000000000000000",
            "WETH": "0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91",
            "USDC": "0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4",
        },
    }

    def __init__(self, config: OnChainConfig):
        """Initialize on-chain farmer.

        Args:
            config: On-chain farming configuration.
        """
        self.config = config
        self._results: list[TransactionResult] = []
        self._tx_count = 0
        self._web3 = None
        self._account = None

        if config.private_key:
            self._init_web3()

        logger.info(
            f"OnChainAirdropFarmer initialized: chain={config.chain}, "
            f"dry_run={config.dry_run}"
        )

    def _init_web3(self) -> None:
        """Initialize Web3 connection."""
        try:
            from eth_account import Account
            from web3 import Web3

            rpc_url = self.config.rpc_url or self.DEFAULT_RPCS.get(
                self.config.chain, ""
            )
            if not rpc_url:
                raise ValueError(f"No RPC URL for chain {self.config.chain}")

            self._web3 = Web3(Web3.HTTPProvider(rpc_url))
            self._account = Account.from_key(self.config.private_key)

            if self._web3.is_connected():
                logger.info(f"Connected to {self.config.chain}: {rpc_url}")
                balance = self._web3.eth.get_balance(self._account.address)
                logger.info(
                    f"Wallet: {self._account.address[:10]}... "
                    f"Balance: {Web3.from_wei(balance, 'ether'):.4f} ETH"
                )
            else:
                logger.error(f"Failed to connect to {rpc_url}")

        except ImportError:
            logger.warning("web3 not installed. Run: pip install web3")
        except Exception as e:
            logger.error(f"Web3 init failed: {e}")

    def farm_all(self) -> list[TransactionResult]:
        """Execute all farming plans for the configured chain.

        Returns:
            List of transaction results.
        """
        plans = self.get_plans_for_chain(self.config.chain)
        logger.info(f"Found {len(plans)} farming plans for {self.config.chain}")

        for plan in plans:
            logger.info(f"Executing plan: {plan.name}")
            self._execute_plan(plan)
            time.sleep(self.config.delay_between_txs)  # TODO: convert to async

        return self._results

    async def async_farm_all(self) -> list[TransactionResult]:
        """Async version of farm_all — non-blocking sleep between plans.

        Returns:
            List of transaction results.
        """
        plans = self.get_plans_for_chain(self.config.chain)
        logger.info(f"Found {len(plans)} farming plans for {self.config.chain}")

        for plan in plans:
            logger.info(f"Executing plan: {plan.name}")
            self._execute_plan(plan)
            await asyncio.sleep(self.config.delay_between_txs)

        return self._results

    def farm_plan(self, plan_name: str) -> list[TransactionResult]:
        """Execute a specific farming plan.

        Args:
            plan_name: Name of the plan (e.g., 'base_activity').

        Returns:
            List of transaction results.
        """
        plan = FARMING_PLANS.get(plan_name)
        if not plan:
            logger.error(f"Unknown plan: {plan_name}")
            return []
        return self._execute_plan(plan)

    def get_plans_for_chain(self, chain: str) -> list[FarmingPlan]:
        """Get all farming plans for a specific chain.

        Args:
            chain: Chain name.

        Returns:
            List of farming plans.
        """
        chain_enum = Chain(chain.lower())
        return sorted(
            [p for p in FARMING_PLANS.values() if p.chain == chain_enum],
            key=lambda p: p.priority,
            reverse=True,
        )

    def get_all_plans(self) -> dict[str, FarmingPlan]:
        """Get all available farming plans.

        Returns:
            Dict of plan name to FarmingPlan.
        """
        return FARMING_PLANS.copy()

    def execute_swap(
        self,
        chain: str,
        protocol: str,
        token_in: str,
        token_out: str,
        amount_in: float,
    ) -> TransactionResult:
        """Execute a swap on a DEX.

        Args:
            chain: Chain name.
            protocol: DEX protocol name.
            token_in: Input token symbol.
            token_out: Output token symbol.
            amount_in: Amount to swap (in token units).

        Returns:
            Transaction result.
        """
        result = TransactionResult(
            protocol=protocol,
            action="swap",
            chain=chain,
            amount=f"{amount_in} {token_in} -> {token_out}",
        )

        if self.config.dry_run:
            logger.info(
                f"[DRY RUN] Swap {amount_in} {token_in} -> {token_out} "
                f"on {protocol} ({chain})"
            )
            result.success = True
            result.tx_hash = "0xDRY_RUN"
            self._results.append(result)
            return result

        # Real execution would go here
        logger.warning("Real swap execution not yet implemented")
        result.error = "Not implemented"
        self._results.append(result)
        return result

    def execute_bridge(
        self,
        from_chain: str,
        to_chain: str,
        amount_eth: float,
        protocol: str = "across",
    ) -> TransactionResult:
        """Execute a bridge transaction.

        Args:
            from_chain: Source chain.
            to_chain: Destination chain.
            amount_eth: Amount to bridge in ETH.
            protocol: Bridge protocol.

        Returns:
            Transaction result.
        """
        result = TransactionResult(
            protocol=protocol,
            action="bridge",
            chain=from_chain,
            amount=f"{amount_eth} ETH: {from_chain} -> {to_chain}",
        )

        if self.config.dry_run:
            logger.info(
                f"[DRY RUN] Bridge {amount_eth} ETH from {from_chain} "
                f"to {to_chain} via {protocol}"
            )
            result.success = True
            result.tx_hash = "0xDRY_RUN"
            self._results.append(result)
            return result

        logger.warning("Real bridge execution not yet implemented")
        result.error = "Not implemented"
        self._results.append(result)
        return result

    def execute_lend(
        self,
        chain: str,
        protocol: str,
        asset: str,
        amount: float,
        action: str = "supply",
    ) -> TransactionResult:
        """Execute a lending protocol interaction.

        Args:
            chain: Chain name.
            protocol: Lending protocol.
            asset: Asset symbol.
            amount: Amount to lend/borrow.
            action: 'supply' or 'borrow'.

        Returns:
            Transaction result.
        """
        result = TransactionResult(
            protocol=protocol,
            action=f"lend_{action}",
            chain=chain,
            amount=f"{amount} {asset}",
        )

        if self.config.dry_run:
            logger.info(
                f"[DRY RUN] {action} {amount} {asset} on {protocol} ({chain})"
            )
            result.success = True
            result.tx_hash = "0xDRY_RUN"
            self._results.append(result)
            return result

        logger.warning("Real lend execution not yet implemented")
        result.error = "Not implemented"
        self._results.append(result)
        return result

    def execute_stake(
        self,
        chain: str,
        protocol: str,
        amount_eth: float,
    ) -> TransactionResult:
        """Execute a staking/restaking transaction.

        Args:
            chain: Chain name.
            protocol: Staking protocol.
            amount_eth: Amount to stake in ETH.

        Returns:
            Transaction result.
        """
        result = TransactionResult(
            protocol=protocol,
            action="stake",
            chain=chain,
            amount=f"{amount_eth} ETH",
        )

        if self.config.dry_run:
            logger.info(
                f"[DRY RUN] Stake {amount_eth} ETH on {protocol} ({chain})"
            )
            result.success = True
            result.tx_hash = "0xDRY_RUN"
            self._results.append(result)
            return result

        logger.warning("Real stake execution not yet implemented")
        result.error = "Not implemented"
        self._results.append(result)
        return result

    def get_results(self) -> list[TransactionResult]:
        """Get all transaction results.

        Returns:
            List of transaction results.
        """
        return self._results

    def get_summary(self) -> dict:
        """Get a summary of all farming results.

        Returns:
            Summary dict.
        """
        total = len(self._results)
        success = sum(1 for r in self._results if r.success)
        failed = total - success
        total_gas = sum(r.gas_cost_eth for r in self._results)

        return {
            "total_transactions": total,
            "successful": success,
            "failed": failed,
            "success_rate": success / total if total > 0 else 0.0,
            "total_gas_eth": total_gas,
            "chains": list(set(r.chain for r in self._results)),
            "protocols": list(set(r.protocol for r in self._results)),
        }

    # ─── Private Methods ─────────────────────────────────────────

    def _execute_plan(self, plan: FarmingPlan) -> list[TransactionResult]:
        """Execute a farming plan."""
        results = []
        for action in plan.actions:
            protocol = action.get("protocol", "")
            action_type = action.get("action", "")

            if action_type == "swap":
                tokens = action.get("tokens", ["ETH", "USDC"])
                result = self.execute_swap(
                    chain=plan.chain.value,
                    protocol=protocol,
                    token_in=tokens[0] if len(tokens) > 0 else "ETH",
                    token_out=tokens[1] if len(tokens) > 1 else "USDC",
                    amount_in=self.config.swap_amount_eth,
                )
            elif action_type == "bridge":
                result = self.execute_bridge(
                    from_chain=plan.chain.value,
                    to_chain=action.get("to_chain", "ethereum"),
                    amount_eth=self.config.bridge_amount_eth,
                    protocol=protocol,
                )
            elif action_type in ("supply", "borrow"):
                result = self.execute_lend(
                    chain=plan.chain.value,
                    protocol=protocol,
                    asset=action.get("asset", "USDC"),
                    amount=self.config.lend_amount_eth,
                    action=action_type,
                )
            elif action_type in ("deposit", "delegate_operator"):
                result = self.execute_stake(
                    chain=plan.chain.value,
                    protocol=protocol,
                    amount_eth=self.config.stake_amount_eth,
                )
            else:
                logger.warning(f"Unknown action type: {action_type}")
                continue

            results.append(result)
            time.sleep(self.config.delay_between_txs)  # TODO: convert to async

        return results

    async def _async_execute_plan(self, plan: FarmingPlan) -> list[TransactionResult]:
        """Async version of _execute_plan — non-blocking sleep between txs."""
        results = []
        for action in plan.actions:
            protocol = action.get("protocol", "")
            action_type = action.get("action", "")

            if action_type == "swap":
                tokens = action.get("tokens", ["ETH", "USDC"])
                result = self.execute_swap(
                    chain=plan.chain.value,
                    protocol=protocol,
                    token_in=tokens[0] if len(tokens) > 0 else "ETH",
                    token_out=tokens[1] if len(tokens) > 1 else "USDC",
                    amount_in=self.config.swap_amount_eth,
                )
            elif action_type == "bridge":
                result = self.execute_bridge(
                    from_chain=plan.chain.value,
                    to_chain=action.get("to_chain", "ethereum"),
                    amount_eth=self.config.bridge_amount_eth,
                    protocol=protocol,
                )
            elif action_type in ("supply", "borrow"):
                result = self.execute_lend(
                    chain=plan.chain.value,
                    protocol=protocol,
                    asset=action.get("asset", "USDC"),
                    amount=self.config.lend_amount_eth,
                    action=action_type,
                )
            elif action_type in ("deposit", "delegate_operator"):
                result = self.execute_stake(
                    chain=plan.chain.value,
                    protocol=protocol,
                    amount_eth=self.config.stake_amount_eth,
                )
            else:
                logger.warning(f"Unknown action type: {action_type}")
                continue

            results.append(result)
            await asyncio.sleep(self.config.delay_between_txs)

        return results

    def _check_daily_limit(self) -> bool:
        """Check if daily transaction limit is reached."""
        return self._tx_count < self.config.max_daily_txs

    def _send_transaction(self, tx: dict) -> Optional[str]:
        """Send a transaction (placeholder for real implementation)."""
        if not self._web3 or not self._account:
            logger.error("Web3 not initialized")
            return None

        try:
            signed = self._account.sign_transaction(tx)
            tx_hash = self._web3.eth.send_raw_transaction(
                signed.raw_transaction
            )
            receipt = self._web3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=120
            )
            return receipt.transactionHash.hex()
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            return None
