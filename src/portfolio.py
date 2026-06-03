"""Portfolio dashboard — real-time balance, P&L, positions across chains.

Tracks wallet balances, token holdings, and calculates total portfolio value.

Usage:
    from web3_agent_kit.portfolio import PortfolioTracker

    tracker = PortfolioTracker(chain_manager, wallet)
    summary = tracker.get_summary()
    print(summary)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .wallet import Wallet
from .chain import Chain, ChainManager

logger = logging.getLogger(__name__)


# ERC20 ABI (minimal)
ERC20_ABI = json.loads("""[
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
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
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# Common token addresses per chain
KNOWN_TOKENS = {
    Chain.ETHEREUM: {
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
    },
    Chain.BASE: {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
        "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
        "AERO": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
    },
    Chain.ARBITRUM: {
        "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",
        "GMX": "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a",
    },
}

# Approximate USD prices (would need oracle in production)
ETH_PRICE_USD = 3500.0


@dataclass
class TokenBalance:
    """Balance of a single token."""

    symbol: str
    address: str
    balance: float
    decimals: int
    chain: Chain
    price_usd: float = 0.0
    value_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "address": self.address,
            "balance": self.balance,
            "chain": self.chain.value,
            "price_usd": self.price_usd,
            "value_usd": self.value_usd,
        }


@dataclass
class ChainPortfolio:
    """Portfolio summary for a single chain."""

    chain: Chain
    native_balance: float
    native_value_usd: float
    tokens: list[TokenBalance]
    total_value_usd: float

    def to_dict(self) -> dict:
        return {
            "chain": self.chain.value,
            "native_balance": self.native_balance,
            "native_value_usd": self.native_value_usd,
            "tokens": [t.to_dict() for t in self.tokens],
            "total_value_usd": self.total_value_usd,
        }


@dataclass
class PortfolioSummary:
    """Full portfolio summary across all chains."""

    address: str
    timestamp: float
    chains: list[ChainPortfolio]
    total_value_usd: float
    total_native_balances: dict[str, float]  # chain -> ETH balance

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "timestamp": self.timestamp,
            "chains": [c.to_dict() for c in self.chains],
            "total_value_usd": self.total_value_usd,
            "total_native_balances": self.total_native_balances,
        }

    def __str__(self) -> str:
        lines = [
            f"📊 Portfolio: {self.address[:10]}...",
            f"💰 Total Value: ${self.total_value_usd:,.2f}",
            "",
        ]
        for cp in self.chains:
            lines.append(f"  🔗 {cp.chain.value.upper()}: ${cp.total_value_usd:,.2f}")
            lines.append(f"     Native: {cp.native_balance:.4f} ETH (${cp.native_value_usd:,.2f})")
            for token in cp.tokens:
                if token.balance > 0:
                    lines.append(f"     {token.symbol}: {token.balance:.4f} (${token.value_usd:,.2f})")
        return "\n".join(lines)


class PortfolioTracker:
    """
    Track wallet portfolio across multiple chains.

    Example:
        tracker = PortfolioTracker(chain_manager, wallet)
        summary = tracker.get_summary()
        print(summary)
    """

    def __init__(
        self,
        chain_manager: ChainManager,
        wallet: Wallet,
        eth_price: float = ETH_PRICE_USD,
    ):
        self.chain_manager = chain_manager
        self.wallet = wallet
        self.eth_price = eth_price
        self._history: list[PortfolioSummary] = []

    def get_summary(self, chains: Optional[list[Chain]] = None) -> PortfolioSummary:
        """
        Get full portfolio summary.

        Args:
            chains: Chains to check (defaults to all configured chains)

        Returns:
            PortfolioSummary with all balances and values
        """
        if chains is None:
            chains = self.chain_manager.list_chains()

        chain_portfolios = []
        total_value = 0.0
        native_balances = {}

        for chain in chains:
            try:
                cp = self._get_chain_portfolio(chain)
                chain_portfolios.append(cp)
                total_value += cp.total_value_usd
                native_balances[chain.value] = cp.native_balance
            except Exception as e:
                logger.warning(f"Failed to get portfolio for {chain.value}: {e}")

        summary = PortfolioSummary(
            address=self.wallet.address,
            timestamp=time.time(),
            chains=chain_portfolios,
            total_value_usd=total_value,
            total_native_balances=native_balances,
        )

        self._history.append(summary)
        return summary

    def _get_chain_portfolio(self, chain: Chain) -> ChainPortfolio:
        """Get portfolio for a single chain."""
        # Get native balance
        native_balance = self.wallet.get_balance(chain)
        native_value = native_balance * self.eth_price

        # Get token balances
        tokens = []
        tokens_value = 0.0

        known = KNOWN_TOKENS.get(chain, {})
        for symbol, address in known.items():
            try:
                token = self._get_token_balance(address, chain)
                if token and token.balance > 0:
                    # Estimate value (simplified — would need oracle in production)
                    if symbol in ("USDC", "USDT", "DAI", "USDbC"):
                        token.price_usd = 1.0
                        token.value_usd = token.balance
                    elif symbol == "WETH":
                        token.price_usd = self.eth_price
                        token.value_usd = token.balance * self.eth_price
                    elif symbol == "WBTC":
                        token.price_usd = 60000.0
                        token.value_usd = token.balance * 60000.0
                    else:
                        # Unknown price — would need oracle
                        token.price_usd = 0.0
                        token.value_usd = 0.0

                    tokens.append(token)
                    tokens_value += token.value_usd
            except Exception as e:
                logger.debug(f"Failed to get {symbol} balance: {e}")

        return ChainPortfolio(
            chain=chain,
            native_balance=native_balance,
            native_value_usd=native_value,
            tokens=tokens,
            total_value_usd=native_value + tokens_value,
        )

    def _get_token_balance(self, token_address: str, chain: Chain) -> Optional[TokenBalance]:
        """Get balance of a specific token."""
        w3 = self.chain_manager.get_web3(chain)
        token = w3.eth.contract(
            address=w3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )

        try:
            balance_raw = token.functions.balanceOf(
                w3.to_checksum_address(self.wallet.address)
            ).call()
            decimals = token.functions.decimals().call()
            symbol = token.functions.symbol().call()

            balance = balance_raw / (10 ** decimals)

            return TokenBalance(
                symbol=symbol,
                address=token_address,
                balance=balance,
                decimals=decimals,
                chain=chain,
            )
        except Exception as e:
            logger.debug(f"Failed to get token balance: {e}")
            return None

    def get_history(self) -> list[PortfolioSummary]:
        """Get portfolio history."""
        return self._history

    def get_pnl(self) -> dict:
        """
        Calculate P&L between first and last snapshot.

        Returns:
            Dict with pnl_absolute and pnl_percent
        """
        if len(self._history) < 2:
            return {"pnl_absolute": 0.0, "pnl_percent": 0.0}

        first = self._history[0]
        last = self._history[-1]

        pnl = last.total_value_usd - first.total_value_usd
        pnl_pct = (pnl / first.total_value_usd * 100) if first.total_value_usd > 0 else 0

        return {
            "initial_value": first.total_value_usd,
            "current_value": last.total_value_usd,
            "pnl_absolute": pnl,
            "pnl_percent": pnl_pct,
            "timestamp_start": first.timestamp,
            "timestamp_end": last.timestamp,
        }

    def __repr__(self) -> str:
        return f"PortfolioTracker(wallet={self.wallet.address[:10]}...)"
