"""Price fetching utilities with caching for crypto assets."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Cache: {coin_id: (price_usd, timestamp)}
_price_cache: dict[str, tuple[float, float]] = {}
CACHE_TTL = 60  # seconds

# Common asset name → CoinGecko coin ID mapping
ASSET_TO_COINGECKO: dict[str, str] = {
    "ETH": "ethereum",
    "WETH": "ethereum",
    "stETH": "ethereum",
    "rETH": "ethereum",
    "WBTC": "bitcoin",
    "BTC": "bitcoin",
    "DAI": "dai",
    "USDC": "usd-coin",
    "USDT": "tether",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "COMP": "compound-governance-token",
    "LDO": "lido-dao",
    "MKR": "maker",
    "CRV": "curve-dao-token",
    "SNX": "havven",
    "1INCH": "1inch",
    "ENS": "ethereum-name-service",
}

# Stablecoins that are pegged to ~$1
STABLECOINS = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "GUSD", "BUSD", "TUSD"}


def get_price_usd(asset: str, fallback: Optional[float] = None) -> float:
    """
    Get the current USD price for a crypto asset.

    Uses CoinGecko free API with a 60-second in-memory cache.

    Args:
        asset: Asset symbol (e.g. "ETH", "WETH", "USDC")
        fallback: Fallback price if fetch fails. Defaults to None (returns 0).

    Returns:
        Current price in USD, or fallback value if the fetch fails.
    """
    asset_upper = asset.upper().strip()

    # Stablecoins: return 1.0 directly
    if asset_upper in STABLECOINS:
        return 1.0

    coin_id = ASSET_TO_COINGECKO.get(asset_upper)
    if not coin_id:
        logger.warning("Unknown asset '%s' for price lookup, using fallback", asset)
        return fallback if fallback is not None else 0.0

    # Check cache
    if coin_id in _price_cache:
        cached_price, cached_time = _price_cache[coin_id]
        if time.time() - cached_time < CACHE_TTL:
            return cached_price

    # Fetch from CoinGecko
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        price = float(data[coin_id]["usd"])
        _price_cache[coin_id] = (price, time.time())
        return price
    except Exception as e:
        logger.warning(
            "Failed to fetch price for %s (coin_id=%s): %s. Using fallback.",
            asset, coin_id, e,
        )
        if fallback is not None:
            return fallback
        return 0.0


def get_eth_price_usd() -> float:
    """Convenience: get ETH price in USD with a fallback of 3500."""
    return get_price_usd("ETH", fallback=3500.0)
