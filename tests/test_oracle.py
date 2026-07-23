"""Tests for the Oracle module — price aggregation from multiple sources."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.oracle import (
    CHAINLINK_AGGREGATOR_ABI,
    CHAINLINK_FEEDS,
    AggregatedPrice,
    OracleAggregator,
    OracleSource,
    PricePoint,
)


class TestPricePoint:
    def test_default_confidence(self):
        pt = PricePoint(source=OracleSource.CHAINLINK, price=100.0, timestamp=1000)
        assert pt.confidence == 0.0

    def test_all_fields(self):
        pt = PricePoint(source=OracleSource.PYTH, price=50.0, timestamp=2000, confidence=0.9)
        assert pt.source == OracleSource.PYTH
        assert pt.price == 50.0
        assert pt.timestamp == 2000
        assert pt.confidence == 0.9


class TestAggregatedPrice:
    def test_defaults(self):
        ap = AggregatedPrice(pair="ETH/USD", price=2000.0)
        assert ap.sources == []
        assert ap.num_sources == 0
        assert ap.deviation == 0.0

    def test_to_dict_with_sources(self):
        pts = [PricePoint(OracleSource.CHAINLINK, 100.0, 1000, 0.95)]
        ap = AggregatedPrice(pair="ETH/USD", price=100.5, sources=pts, num_sources=1)
        d = ap.to_dict()
        assert d["sources"][0]["source"] == "chainlink"

    def test_to_dict_stale(self):
        ap = AggregatedPrice(pair="SOL/USD", price=150.0, stale=True)
        assert ap.to_dict()["stale"] is True


class TestOracleSource:
    def test_enum_values(self):
        assert OracleSource.CHAINLINK.value == "chainlink"
        assert len(OracleSource) == 7


class TestChainlinkFeeds:
    def test_major_feeds_exist(self):
        for pair in ["ETH/USD", "BTC/USD", "SOL/USD"]:
            assert pair in CHAINLINK_FEEDS

    def test_abi_structure(self):
        names = [a["name"] for a in CHAINLINK_AGGREGATOR_ABI if "name" in a]
        assert "latestRoundData" in names
        assert "decimals" in names


class TestOracleAggregatorInit:
    def test_default_sources(self):
        agg = OracleAggregator(rpc_url="https://eth.llamarpc.com")
        assert len(agg.sources) == 3
        assert OracleSource.CHAINLINK in agg.sources

    def test_custom_sources(self):
        agg = OracleAggregator(rpc_url="https://rpc.ankr.com/eth", sources=[OracleSource.PYTH])
        assert agg.sources == [OracleSource.PYTH]

    def test_empty_cache(self):
        agg = OracleAggregator(rpc_url="https://eth.llamarpc.com")
        assert agg._cache == {}


@patch("web3_agent_kit.oracle.OracleAggregator._fetch_chainlink")
@patch("web3_agent_kit.oracle.OracleAggregator._fetch_dexscreener")
@patch("web3_agent_kit.oracle.OracleAggregator._fetch_coingecko")
class TestGetPrice:
    def test_single_source(self, mock_cg, mock_ds, mock_cl):
        mock_cl.return_value = PricePoint(OracleSource.CHAINLINK, 2000.0, 1000000, 0.95)
        mock_ds.return_value = None
        mock_cg.return_value = None
        agg = OracleAggregator(rpc_url="https://eth.llamarpc.com")
        result = agg.get_price("ETH", "USD")
        assert result.price == 2000.0
        assert result.num_sources == 1

    def test_median_three(self, mock_cg, mock_ds, mock_cl):
        mock_cl.return_value = PricePoint(OracleSource.CHAINLINK, 1990.0, 1000000, 0.95)
        mock_ds.return_value = PricePoint(OracleSource.DEX_SCREENER, 2000.0, 1000000, 0.85)
        mock_cg.return_value = PricePoint(OracleSource.COINGECKO, 2010.0, 1000000, 0.80)
        agg = OracleAggregator(rpc_url="https://eth.llamarpc.com")
        result = agg.get_price("ETH", "USD")
        assert result.num_sources == 3
        assert result.price == 2000.0

    def test_all_fail_raises(self, mock_cg, mock_ds, mock_cl):
        for m in [mock_cl, mock_ds, mock_cg]:
            m.return_value = None
        agg = OracleAggregator(rpc_url="https://eth.llamarpc.com")
        with pytest.raises(ValueError, match="No oracle sources returned a price"):
            agg.get_price("UNKNOWN", "USD")

    def test_stale_check(self, mock_cg, mock_ds, mock_cl):
        mock_cl.return_value = None
        mock_ds.return_value = PricePoint(OracleSource.DEX_SCREENER, 100.0, 0, 0.85)
        mock_cg.return_value = None
        agg = OracleAggregator(rpc_url="https://rpc.test", max_age=1)
        result = agg.get_price("ETH", "USD")
        assert result.stale is True

    def test_cache_hit(self, mock_cg, mock_ds, mock_cl):
        mock_cl.return_value = PricePoint(OracleSource.CHAINLINK, 100.0, 9999999999, 0.95)
        agg = OracleAggregator(rpc_url="https://rpc.test", cache_ttl=300)
        agg.get_price("ETH", "USD")
        agg.get_price("ETH", "USD")
        assert mock_cl.call_count == 1


@patch("web3_agent_kit.oracle.OracleAggregator._fetch_chainlink")
@patch("web3_agent_kit.oracle.OracleAggregator._fetch_dexscreener")
@patch("web3_agent_kit.oracle.OracleAggregator._fetch_coingecko")
class TestGetPricesBatch:
    def test_multiple_tokens(self, mock_cg, mock_ds, mock_cl):
        mock_cl.return_value = PricePoint(OracleSource.CHAINLINK, 100.0, 9999999999, 0.95)
        mock_ds.return_value = None
        mock_cg.return_value = None
        agg = OracleAggregator(rpc_url="https://rpc.test")
        results = agg.get_prices_batch(["ETH", "BTC"])
        assert "ETH" in results
        assert "BTC" in results
        assert results["ETH"].price == 100.0


class TestClearCache:
    def test_clears_cache(self):
        agg = OracleAggregator(rpc_url="https://rpc.test")
        agg._cache["test"] = (0, None)
        assert len(agg._cache) == 1
        agg.clear_cache()
        assert agg._cache == {}


@patch("web3_agent_kit.oracle.OracleAggregator._fetch_chainlink")
class TestFetchChainlink:
    def test_unsupported_pair(self, mock_cl):
        agg = OracleAggregator(rpc_url="https://rpc.test", sources=[OracleSource.CHAINLINK])
        with pytest.raises(ValueError):
            agg.get_price("SHIBA_INU", "USD")

    def test_source_fail_logs(self, mock_cl):
        mock_cl.side_effect = Exception("RPC timeout")
        agg = OracleAggregator(rpc_url="https://rpc.test", sources=[OracleSource.CHAINLINK])
        with pytest.raises(ValueError):
            agg.get_price("ETH", "USD")


class TestPairFormatting:
    def test_uppercase_pair(self):
        ap = AggregatedPrice(pair="eth/usd", price=1.0)
        assert ap.pair == "eth/usd"

    def test_special_chars(self):
        ap = AggregatedPrice(pair="meme/usd", price=0.01)
        assert ap.pair == "meme/usd"