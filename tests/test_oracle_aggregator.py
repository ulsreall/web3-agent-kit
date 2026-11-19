"""Oracle aggregation: source fan-in, median, deviation and staleness.

The aggregator's whole job is to survive one bad source, so the arithmetic that
decides the price matters more than the fetches do.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from web3_agent_kit.oracle import AggregatedPrice, OracleAggregator, OracleSource, PricePoint


def _pt(price, age=0.0, source=OracleSource.COINGECKO):
    return PricePoint(source=source, price=price, timestamp=int(time.time() - age), confidence=0.5)


def _bare() -> OracleAggregator:
    """An aggregator with the real fetchers left in place."""
    return OracleAggregator(rpc_url="http://rpc")


def _agg(points, sources=None, **kw) -> OracleAggregator:
    aggregator = OracleAggregator(
        rpc_url="http://rpc", sources=sources or [OracleSource.COINGECKO], **kw
    )
    mapping = {s: p for s, p in zip(sources or [OracleSource.COINGECKO], points)}
    aggregator._fetch_coingecko = lambda b, q: mapping.get(OracleSource.COINGECKO)  # type: ignore[method-assign]
    aggregator._fetch_dexscreener = lambda b, q: mapping.get(OracleSource.DEX_SCREENER)  # type: ignore[method-assign]
    aggregator._fetch_chainlink = lambda b, q: mapping.get(OracleSource.CHAINLINK)  # type: ignore[method-assign]
    return aggregator


class TestMedian:
    def test_a_single_source_is_its_price(self):
        price = _agg([_pt(100.0)]).get_price("eth")
        assert price.price == 100.0 and price.num_sources == 1

    def test_three_sources_take_the_middle(self):
        aggregator = _agg(
            [_pt(90.0), _pt(100.0), _pt(130.0)],
            [OracleSource.COINGECKO, OracleSource.DEX_SCREENER, OracleSource.CHAINLINK],
        )
        assert aggregator.get_price("eth").price == 100.0

    def test_two_sources_average_the_middle(self):
        # Taking only the upper of the two let one high outlier set the price.
        aggregator = _agg(
            [_pt(100.0), _pt(300.0)],
            [OracleSource.COINGECKO, OracleSource.DEX_SCREENER],
        )
        assert aggregator.get_price("eth").price == 200.0

    def test_deviation_is_relative_to_the_median(self):
        aggregator = _agg(
            [_pt(90.0), _pt(100.0), _pt(110.0)],
            [OracleSource.COINGECKO, OracleSource.DEX_SCREENER, OracleSource.CHAINLINK],
        )
        assert aggregator.get_price("eth").deviation == pytest.approx(0.2)


class TestSources:
    def test_a_zero_price_is_not_a_source(self):
        aggregator = _agg(
            [_pt(0.0), _pt(50.0)],
            [OracleSource.COINGECKO, OracleSource.DEX_SCREENER],
        )
        result = aggregator.get_price("eth")
        assert result.num_sources == 1 and result.price == 50.0

    def test_a_throwing_source_is_skipped(self):
        aggregator = _agg([_pt(50.0)])

        def boom(*a):
            raise RuntimeError("down")

        aggregator._fetch_dexscreener = boom  # type: ignore[method-assign]
        aggregator.sources = [OracleSource.DEX_SCREENER, OracleSource.COINGECKO]
        assert aggregator.get_price("eth").price == 50.0

    def test_no_source_at_all_raises(self):
        with pytest.raises(ValueError, match="No oracle sources returned"):
            _agg([]).get_price("eth")

    def test_the_pair_is_normalised(self):
        assert _agg([_pt(1.0)]).get_price("eth", "usd").pair == "ETH/USD"

    def test_an_old_point_marks_the_result_stale(self):
        result = _agg([_pt(10.0, age=99999)], max_age=10).get_price("eth")
        assert result.stale is True

    def test_a_fresh_point_is_not_stale(self):
        assert _agg([_pt(10.0)]).get_price("eth").stale is False


class TestCache:
    def test_a_second_call_is_served_from_the_cache(self):
        aggregator = _agg([_pt(10.0)])
        calls = []
        aggregator._fetch_coingecko = lambda b, q: calls.append(b) or _pt(10.0)  # type: ignore[method-assign]
        aggregator.get_price("eth")
        aggregator.get_price("eth")
        assert len(calls) == 1

    def test_clearing_the_cache_forces_a_fetch(self):
        aggregator = _agg([_pt(10.0)])
        calls = []
        aggregator._fetch_coingecko = lambda b, q: calls.append(b) or _pt(10.0)  # type: ignore[method-assign]
        aggregator.get_price("eth")
        aggregator.clear_cache()
        aggregator.get_price("eth")
        assert len(calls) == 2

    def test_an_expired_entry_is_refetched(self):
        aggregator = _agg([_pt(10.0)], cache_ttl=0)
        calls = []
        aggregator._fetch_coingecko = lambda b, q: calls.append(b) or _pt(10.0)  # type: ignore[method-assign]
        aggregator.get_price("eth")
        aggregator.get_price("eth")
        assert len(calls) == 2


class TestBatch:
    def test_every_token_is_returned(self):
        agg = _agg([_pt(10.0)])
        assert set(agg.get_prices_batch(["ETH", "BTC"])) == {"ETH", "BTC"}

    def test_a_missing_token_is_left_out(self):
        agg = _agg([_pt(10.0)])

        def _get(token, quote="USD"):
            if token == "NOPE":
                raise ValueError("no sources")
            return SimpleNamespace(price=1.0)

        agg.get_price = _get  # type: ignore[method-assign]
        assert set(agg.get_prices_batch(["ETH", "NOPE"])) == {"ETH"}


class TestPointShape:
    def test_to_dict_keeps_the_price_and_rounds_the_deviation(self):
        point = AggregatedPrice(
            pair="ETH/USD", price=1.23456, sources=[], num_sources=0, deviation=0.123456
        )
        payload = point.to_dict()
        assert payload["price"] == 1.23456
        assert payload["deviation_pct"] == 12.35


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        return self._p


@pytest.fixture
def http(monkeypatch):
    import requests

    state = {"payload": {}, "status": 200, "urls": []}

    def _get(url, **kw):
        state["urls"].append(url)
        return _Resp(state["payload"], state["status"])

    monkeypatch.setattr(requests, "get", _get)
    return state


class TestFetchers:
    def test_coingecko_maps_the_symbol(self, http):
        http["payload"] = {"ethereum": {"usd": 2000.0}}
        point = _bare()._fetch_coingecko("ETH", "USD")
        assert point.price == 2000.0
        assert "ids=ethereum" in http["urls"][0]

    def test_coingecko_skips_a_non_200(self, http):
        http["status"] = 429
        assert _bare()._fetch_coingecko("ETH", "USD") is None

    def test_coingecko_skips_a_zero_price(self, http):
        http["payload"] = {"ethereum": {"usd": 0}}
        assert _bare()._fetch_coingecko("ETH", "USD") is None

    def test_dexscreener_refuses_a_non_usd_quote(self, http):
        assert _bare()._fetch_dexscreener("ETH", "EUR") is None
        assert http["urls"] == []

    def test_dexscreener_picks_the_deepest_pair(self, http):
        http["payload"] = {
            "pairs": [
                {"baseToken": {"symbol": "ETH"}, "priceUsd": "1", "liquidity": {"usd": 5}},
                {"baseToken": {"symbol": "ETH"}, "priceUsd": "2000", "liquidity": {"usd": 900}},
            ]
        }
        point = _bare()._fetch_dexscreener("ETH", "USD")
        assert point.price == 2000.0

    def test_dexscreener_ignores_other_symbols(self, http):
        http["payload"] = {"pairs": [{"baseToken": {"symbol": "BTC"}, "priceUsd": "1"}]}
        assert _bare()._fetch_dexscreener("ETH", "USD") is None

    def test_dexscreener_stops_on_a_bad_status(self, http):
        http["status"] = 500
        assert _bare()._fetch_dexscreener("ETH", "USD") is None

    def test_chainlink_needs_a_registered_feed(self):
        assert _bare()._fetch_chainlink("NOPE", "USD") is None

    def test_chainlink_reads_the_feed(self, monkeypatch):
        import sys
        import types as _types

        class _Fn:
            def __init__(self, value):
                self._value = value

            def call(self):
                return self._value

        class _Contract:
            @property
            def functions(self):
                return _types.SimpleNamespace(
                    latestRoundData=lambda: _Fn((1, 2000 * 10**8, 0, 1_700_000_000, 1)),
                    decimals=lambda: _Fn(8),
                )

        class _Eth:
            @staticmethod
            def contract(**kw):
                return _Contract()

        class _W3:
            HTTPProvider = staticmethod(lambda url: url)

            def __init__(self, provider=None):
                self.eth = _Eth()

            @staticmethod
            def to_checksum_address(addr):
                return addr

        monkeypatch.setitem(sys.modules, "web3", _types.SimpleNamespace(Web3=_W3))
        point = _bare()._fetch_chainlink("ETH", "USD")
        assert point.price == 2000.0
        assert point.confidence == 0.95

    def test_chainlink_swallows_a_revert(self, monkeypatch):
        import sys
        import types as _types

        class _Eth:
            @staticmethod
            def contract(**kw):
                raise RuntimeError("no code")

        class _W3:
            def __init__(self, provider=None):
                self.eth = _Eth()

        monkeypatch.setitem(sys.modules, "web3", _types.SimpleNamespace(Web3=_W3))
        assert _bare()._fetch_chainlink("ETH", "USD") is None
