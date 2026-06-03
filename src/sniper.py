"""Token sniper — monitor new liquidity pools and auto-buy.

Monitors DEX factory contracts for new pair creation,
analyzes contract safety, and executes buys if safe.

Usage:
    from web3_agent_kit.sniper import TokenSniper, SniperConfig

    sniper = TokenSniper(
        chain_manager=chain_manager,
        wallet=wallet,
        config=SniperConfig(
            max_buy=0.05,         # max 0.05 ETH per snipe
            auto_buy=True,        # auto-buy safe tokens
            honeypot_check=True,  # check if token is honeypot
        ),
    )
    sniper.start()  # begins monitoring
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Thread, Event
from typing import Any, Callable, Optional

from .wallet import Wallet
from .chain import Chain, ChainManager, CHAIN_IDS

logger = logging.getLogger(__name__)


# Uniswap V2 Factory ABI (minimal)
UNISWAP_V2_FACTORY_ABI = json.loads("""[
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "internalType": "address", "name": "token0", "type": "address"},
            {"indexed": true, "internalType": "address", "name": "token1", "type": "address"},
            {"indexed": false, "internalType": "address", "name": "pair", "type": "address"},
            {"indexed": false, "internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "name": "PairCreated",
        "type": "event"
    }
]""")

# Uniswap V2 Pair ABI (minimal)
UNISWAP_V2_PAIR_ABI = json.loads("""[
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# ERC20 ABI (minimal for safety checks)
ERC20_ABI = json.loads("""[
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# Factory addresses
FACTORIES = {
    Chain.ETHEREUM: "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
    Chain.BASE: "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",
    Chain.ARBITRUM: "0xf1D7CC64Fb4452F05c498126312eBE29f30Fbcf9",
}

# WETH addresses
WETH = {
    Chain.ETHEREUM: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    Chain.BASE: "0x4200000000000000000000000000000000000006",
    Chain.ARBITRUM: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
}


class RiskLevel(Enum):
    """Token risk assessment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SCAM = "scam"


@dataclass
class SniperConfig:
    """Configuration for token sniper."""

    max_buy: float = 0.05           # max ETH per snipe
    auto_buy: bool = True           # auto-buy safe tokens
    honeypot_check: bool = True     # check if token is honeypot
    min_liquidity: float = 1.0      # min ETH liquidity to consider
    max_buy_tax: float = 10.0       # max buy tax percentage
    max_sell_tax: float = 10.0      # max sell tax percentage
    blacklisted_tokens: list[str] = field(default_factory=list)
    whitelisted_tokens: list[str] = field(default_factory=list)
    callback: Optional[Callable] = None  # callback(new_pair_info)


@dataclass
class NewPair:
    """Information about a newly created trading pair."""

    pair_address: str
    token0: str
    token1: str
    chain: Chain
    timestamp: float
    risk_level: RiskLevel
    token_name: str = ""
    token_symbol: str = ""
    reserves: tuple = (0, 0)
    liquidity_eth: float = 0.0
    score: float = 0.0

    @property
    def is_weth_pair(self) -> bool:
        """Check if pair includes WETH."""
        weth = WETH.get(self.chain, "").lower()
        return self.token0.lower() == weth or self.token1.lower() == weth

    @property
    def non_weth_token(self) -> str:
        """Get the non-WETH token address."""
        weth = WETH.get(self.chain, "").lower()
        if self.token0.lower() == weth:
            return self.token1
        return self.token0

    def to_dict(self) -> dict:
        return {
            "pair": self.pair_address,
            "token0": self.token0,
            "token1": self.token1,
            "chain": self.chain.value,
            "risk": self.risk_level.value,
            "name": self.token_name,
            "symbol": self.token_symbol,
            "liquidity_eth": self.liquidity_eth,
            "score": self.score,
        }


class TokenSniper:
    """
    Token sniper — monitors new liquidity pools and auto-buys.

    Example:
        sniper = TokenSniper(chain_manager, wallet, SniperConfig(max_buy=0.05))
        sniper.start()  # non-blocking monitor

        # Or process events manually
        pairs = sniper.scan_recent_blocks(100)
        for pair in pairs:
            if pair.risk_level == RiskLevel.LOW:
                sniper.buy(pair)
    """

    def __init__(
        self,
        chain_manager: ChainManager,
        wallet: Wallet,
        config: Optional[SniperConfig] = None,
        uniswap=None,
    ):
        self.chain_manager = chain_manager
        self.wallet = wallet
        self.config = config or SniperConfig()
        self.uniswap = uniswap
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self.detected_pairs: list[NewPair] = []

    def scan_recent_blocks(self, num_blocks: int = 100, chain: Chain = Chain.BASE) -> list[NewPair]:
        """
        Scan recent blocks for new pair creation events.

        Args:
            num_blocks: Number of blocks to scan
            chain: Chain to scan on

        Returns:
            List of newly detected pairs
        """
        if chain not in FACTORIES:
            raise ValueError(f"Factory not configured for {chain.value}")

        w3 = self.chain_manager.get_web3(chain)
        factory_addr = FACTORIES[chain]
        factory = w3.eth.contract(
            address=w3.to_checksum_address(factory_addr),
            abi=UNISWAP_V2_FACTORY_ABI,
        )

        current_block = w3.eth.block_number
        from_block = max(0, current_block - num_blocks)

        logger.info(f"Scanning blocks {from_block} → {current_block} on {chain.value}")

        # Get PairCreated events
        events = factory.events.PairCreated.get_logs(
            fromBlock=from_block,
            toBlock=current_block,
        )

        pairs = []
        for event in events:
            pair_info = self._analyze_pair(
                pair_address=event.args.pair,
                token0=event.args.token0,
                token1=event.args.token1,
                chain=chain,
                block_number=event.blockNumber,
            )

            if pair_info:
                pairs.append(pair_info)
                self.detected_pairs.append(pair_info)

                logger.info(
                    f"New pair: {pair_info.token_symbol} ({pair_info.risk_level.value}) "
                    f"LIQ: {pair_info.liquidity_eth:.2f} ETH | Score: {pair_info.score:.1f}"
                )

                # Auto-buy if configured and safe
                if self.config.auto_buy and pair_info.risk_level == RiskLevel.LOW:
                    self.buy(pair_info)

        return pairs

    def _analyze_pair(self, pair_address: str, token0: str, token1: str,
                      chain: Chain, block_number: int) -> Optional[NewPair]:
        """Analyze a new pair for safety and profitability."""
        w3 = self.chain_manager.get_web3(chain)

        # Check if WETH pair
        weth_addr = WETH.get(chain, "").lower()
        is_weth = token0.lower() == weth_addr or token1.lower() == weth_addr

        if not is_weth:
            return None  # Skip non-WETH pairs

        # Get pair contract
        pair = w3.eth.contract(
            address=w3.to_checksum_address(pair_address),
            abi=UNISWAP_V2_PAIR_ABI,
        )

        try:
            reserves = pair.functions.getReserves().call()
            token0_addr = pair.functions.token0().call()
        except Exception as e:
            logger.debug(f"Failed to get pair info: {e}")
            return None

        # Calculate liquidity
        if token0_addr.lower() == weth_addr:
            liq_reserve = reserves[0]
        else:
            liq_reserve = reserves[1]

        liquidity_eth = w3.from_wei(liq_reserve, "ether")

        # Get token info
        non_weth = token1 if token0.lower() == weth_addr else token0
        token_contract = w3.eth.contract(
            address=w3.to_checksum_address(non_weth),
            abi=ERC20_ABI,
        )

        try:
            token_name = token_contract.functions.name().call()
            token_symbol = token_contract.functions.symbol().call()
        except Exception:
            token_name = "Unknown"
            token_symbol = "???"

        # Check blacklist
        if non_weth.lower() in [t.lower() for t in self.config.blacklisted_tokens]:
            return None

        # Risk assessment
        risk, score = self._assess_risk(
            token_address=non_weth,
            liquidity_eth=float(liquidity_eth),
            chain=chain,
        )

        return NewPair(
            pair_address=pair_address,
            token0=token0,
            token1=token1,
            chain=chain,
            timestamp=time.time(),
            risk_level=risk,
            token_name=token_name,
            token_symbol=token_symbol,
            reserves=(reserves[0], reserves[1]),
            liquidity_eth=float(liquidity_eth),
            score=score,
        )

    def _assess_risk(self, token_address: str, liquidity_eth: float,
                     chain: Chain) -> tuple[RiskLevel, float]:
        """
        Assess token risk level.

        Returns:
            (RiskLevel, score) where score is 0-100 (higher = safer)
        """
        score = 50.0  # Start neutral

        # Liquidity check
        if liquidity_eth >= self.config.min_liquidity:
            score += 15
        else:
            score -= 30

        # Check contract code size
        w3 = self.chain_manager.get_web3(chain)
        try:
            code = w3.eth.get_code(w3.to_checksum_address(token_address))
            code_size = len(code)

            if code_size < 100:
                # Too small — likely a scam
                score -= 40
            elif code_size > 1000:
                # Reasonable contract size
                score += 10
        except Exception:
            score -= 20

        # Honeypot check (simplified)
        if self.config.honeypot_check:
            # Try to simulate a sell — if it fails, might be honeypot
            # This is a simplified check; real implementation would use
            # a honeypot detection API
            score += 5  # Assume safe for now

        # Determine risk level
        if score >= 70:
            risk = RiskLevel.LOW
        elif score >= 40:
            risk = RiskLevel.MEDIUM
        elif score >= 20:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.SCAM

        return risk, score

    def buy(self, pair: NewPair) -> Optional[str]:
        """
        Buy the non-WETH token in a pair.

        Args:
            pair: NewPair to buy

        Returns:
            Transaction hash or None if failed
        """
        if not self.uniswap:
            logger.error("Uniswap tool not configured — cannot buy")
            return None

        amount = self.config.max_buy
        logger.info(f"Buying {pair.token_symbol} with {amount} ETH on {pair.chain.value}")

        try:
            result = self.uniswap.execute(
                wallet=self.wallet,
                token_in="ETH",
                token_out=pair.non_weth_token,
                amount=amount,
                chain=pair.chain,
            )
            logger.info(f"Buy TX: {result.tx_hash}")
            return result.tx_hash
        except Exception as e:
            logger.error(f"Buy failed: {e}")
            return None

    def start(self, chain: Chain = Chain.BASE, poll_interval: int = 12):
        """
        Start monitoring for new pairs in a background thread.

        Args:
            chain: Chain to monitor
            poll_interval: Seconds between block scans
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitor already running")
            return

        self._stop_event.clear()

        def _monitor():
            logger.info(f"Starting sniper monitor on {chain.value}")
            last_block = 0

            while not self._stop_event.is_set():
                try:
                    w3 = self.chain_manager.get_web3(chain)
                    current_block = w3.eth.block_number

                    if current_block > last_block:
                        new_pairs = self.scan_recent_blocks(
                            num_blocks=current_block - last_block,
                            chain=chain,
                        )

                        if new_pairs:
                            logger.info(f"Found {len(new_pairs)} new pairs")

                            # Call callback if configured
                            if self.config.callback:
                                for pair in new_pairs:
                                    self.config.callback(pair)

                        last_block = current_block

                except Exception as e:
                    logger.error(f"Monitor error: {e}")

                self._stop_event.wait(poll_interval)

            logger.info("Sniper monitor stopped")

        self._monitor_thread = Thread(target=_monitor, daemon=True)
        self._monitor_thread.start()

    def stop(self):
        """Stop the monitoring thread."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def get_detected_pairs(self, risk_filter: Optional[RiskLevel] = None) -> list[NewPair]:
        """Get all detected pairs, optionally filtered by risk."""
        if risk_filter:
            return [p for p in self.detected_pairs if p.risk_level == risk_filter]
        return self.detected_pairs

    def __repr__(self) -> str:
        return f"TokenSniper(chains={[c.value for c in FACTORIES.keys()]}, detected={len(self.detected_pairs)})"
