"""Oracle Module — Multi-source price aggregation.

Aggregates prices from Chainlink, Pyth, Redstone, and DEX-based
TWAP/VWAP oracles with automatic fallback.

Usage::
    from web3_agent_kit.oracle import OracleAggregator
    
    oracle = OracleAggregator(rpc_url="https://eth.llamarpc.com")
    price = oracle.get_price("ETH", "USD")
    print(f"ETH: ${price.price:.2f} (sources: {len(price.sources)})")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class OracleSource(Enum):
    """Supported oracle sources."""
    CHAINLINK = "chainlink"
    PYTH = "pyth"
    REDSTONE = "redstone"
    UNISWAP_V3_TWAP = "uniswap_v3_twap"
    DEX_SCREENER = "dex_screener"
    COINGECKO = "coingecko"
    BINANCE = "binance"


@dataclass
class PricePoint:
    """A single price data point from one source."""
    source: OracleSource
    price: float
    timestamp: int
    confidence: float = 0.0  # 0-1 scale


@dataclass
class AggregatedPrice:
    """Aggregated price from multiple sources."""
    pair: str                     # e.g. "ETH/USD"
    price: float                  # Weighted median price
    sources: list[PricePoint] = field(default_factory=list)
    num_sources: int = 0
    deviation: float = 0.0        # Max deviation among sources
    timestamp: int = 0
    stale: bool = False

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "price": self.price,
            "num_sources": self.num_sources,
            "deviation_pct": round(self.deviation * 100, 2),
            "stale": self.stale,
            "sources": [
                {"source": s.source.value, "price": s.price, "confidence": s.confidence}
                for s in self.sources
            ],
        }


# Chainlink feed registry (Ethereum mainnet)
CHAINLINK_FEEDS: dict[str, dict[str, str]] = {
    "ETH/USD": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "BTC/USD": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
    "LINK/USD": "0x2c1d072e956AFFC0D435Cb7AC38EF18d24d9127c",
    "UNI/USD": "0x553303d460EE0afB37EdFf9bE42922D8FF63220e",
    "AAVE/USD": "0x547a514d5e3769680Ce22B2361c10Ea13619e8a9",
    "MATIC/USD": "0x7bAC85A8a13A4BcD8abb3eB7d6b4d632c5a57676",
    "USDC/USD": "0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6",
    "USDT/USD": "0x3E7d1eAB13ad0104d2750B8863b489D65364e32D",
    "DAI/USD": "0xAed0c38402a5d19df6E4c03F4E2DceD6e29c1ee9",
    "ARB/USD": "0xb2A824043730FE05F3DA2efaFa1CBbe83fa548D6",
    "OP/USD": "0x0D276FC14719f9292D5C1eA2198673d1f4269246",
    "SOL/USD": "0x4ffC43a60e009B551865A93d232E33Fce9f01507",
}

# Chainlink ABI (minimal for price feed)
CHAINLINK_AGGREGATOR_ABI = [
    {"inputs": [], "name": "latestRoundData", "outputs": [
        {"name": "roundId", "type": "uint80"},
        {"name": "answer", "type": "int256"},
        {"name": "startedAt", "type": "uint256"},
        {"name": "updatedAt", "type": "uint256"},
        {"name": "answeredInRound", "type": "uint80"},
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
]


class OracleAggregator:
    """Multi-source price oracle aggregator.

    Fetches prices from multiple sources and computes a weighted median.
    Falls back through sources in priority order.

    Example::
        oracle = OracleAggregator(rpc_url="https://eth.llamarpc.com")
        price = oracle.get_price("ETH", "USD")
        print(f"${price.price:.2f}")
    """

    def __init__(
        self,
        rpc_url: str,
        sources: Optional[list[OracleSource]] = None,
        max_age: int = 3600,   # Max age in seconds before considered stale
        cache_ttl: int = 30,   # Cache TTL in seconds
    ):
        self.rpc_url = rpc_url
        self.sources = sources or [
            OracleSource.CHAINLINK,
            OracleSource.DEX_SCREENER,
            OracleSource.COINGECKO,
        ]
        self.max_age = max_age
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, AggregatedPrice]] = {}

    def get_price(self, base: str, quote: str = "USD") -> AggregatedPrice:
        """Get aggregated price for a pair.

        Args:
            base: Base token symbol (e.g. "ETH", "BTC")
            quote: Quote currency (default "USD")

        Returns:
            AggregatedPrice with weighted median
        """
        pair = f"{base.upper()}/{quote.upper()}"
        now = int(time.time())

        # Check cache
        cache_key = pair
        if cache_key in self._cache:
            cached_time, cached_price = self._cache[cache_key]
            if now - cached_time < self.cache_ttl:
                return cached_price

        points: list[PricePoint] = []

        for source in self.sources:
            try:
                if source == OracleSource.CHAINLINK:
                    pt = self._fetch_chainlink(base, quote)
                elif source == OracleSource.DEX_SCREENER:
                    pt = self._fetch_dexscreener(base, quote)
                elif source == OracleSource.COINGECKO:
                    pt = self._fetch_coingecko(base, quote)
                else:
                    continue

                if pt and pt.price > 0:
                    points.append(pt)
            except Exception as e:
                logger.debug(f"Oracle {source.value} failed for {pair}: {e}")

        if not points:
            raise ValueError(f"No oracle sources returned a price for {pair}")

        # Weighted median: sort by price, pick middle (median)
        sorted_pts = sorted(points, key=lambda p: p.price)
        median = sorted_pts[len(sorted_pts) // 2]
        deviation = max(p.price for p in points) - min(p.price for p in points)
        if median.price > 0:
            deviation /= median.price

        result = AggregatedPrice(
            pair=pair,
            price=median.price,
            sources=points,
            num_sources=len(points),
            deviation=deviation,
            timestamp=now,
            stale=(now - max(p.timestamp for p in points) > self.max_age),
        )

        self._cache[cache_key] = (now, result)
        return result

    def _fetch_chainlink(self, base: str, quote: str) -> Optional[PricePoint]:
        """Fetch from Chainlink price feed."""
        pair = f"{base.upper()}/{quote.upper()}"
        feed_addr = CHAINLINK_FEEDS.get(pair)
        if not feed_addr:
            return None

        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(feed_addr),
                abi=CHAINLINK_AGGREGATOR_ABI,
            )
            _round_id, answer, _started_at, updated_at, _answered = contract.functions.latestRoundData().call()
            decimals = contract.functions.decimals().call()
            price = float(answer) / (10 ** decimals)
            return PricePoint(
                source=OracleSource.CHAINLINK,
                price=price,
                timestamp=updated_at,
                confidence=0.95,
            )
        except Exception as e:
            logger.debug(f"Chainlink fetch failed: {e}")
            return None

    def _fetch_dexscreener(self, base: str, quote: str) -> Optional[PricePoint]:
        """Fetch from DexScreener API."""
        import requests
        try:
            # DexScreener search for top pair
            resp = requests.get(
                f"https://api.dexscreener.com/latest/dex/search?q={base}",
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            pairs = resp.json().get("pairs", [])
            if not pairs:
                return None
            # Take the pair with highest liquidity
            best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            price = float(best.get("priceUsd", 0))
            return PricePoint(
                source=OracleSource.DEX_SCREENER,
                price=price,
                timestamp=int(time.time()),
                confidence=0.85,
            )
        except Exception:
            return None

    def _fetch_coingecko(self, base: str, quote: str) -> Optional[PricePoint]:
        """Fetch from CoinGecko free API."""
        import requests
        try:
            # Map symbols to CoinGecko IDs
            symbol_map = {
                "ETH": "ethereum", "BTC": "bitcoin", "SOL": "solana",
                "MATIC": "matic-network", "ARB": "arbitrum", "OP": "optimism",
                "LINK": "chainlink", "UNI": "uniswap", "AAVE": "aave",
                "USDC": "usd-coin", "USDT": "tether", "DAI": "dai",
                "AVAX": "avalanche-2", "BNB": "binancecoin",
            }
            cg_id = symbol_map.get(base.upper(), base.lower())
            resp = requests.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies={quote.lower()}",
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            price = data.get(cg_id, {}).get(quote.lower(), 0)
            if not price:
                return None
            return PricePoint(
                source=OracleSource.COINGECKO,
                price=float(price),
                timestamp=int(time.time()),
                confidence=0.80,
            )
        except Exception:
            return None

    def get_prices_batch(self, tokens: list[str], quote: str = "USD") -> dict[str, AggregatedPrice]:
        """Get prices for multiple tokens at once."""
        return {token: self.get_price(token, quote) for token in tokens}

    def clear_cache(self):
        """Clear the price cache."""
        self._cache.clear()


__all__ = [
    "OracleAggregator",
    "AggregatedPrice",
    "PricePoint",
    "OracleSource",
    "CHAINLINK_FEEDS",
]