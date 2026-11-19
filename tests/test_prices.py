"""Price lookups: cache, staleness and failure behaviour.

A price feed going down must not silently turn a portfolio into zeros, and a
cached observation must not be thrown away just because it aged out.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.utils import prices


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    prices._price_cache.clear()
    calls = []

    def _get(url, **kwargs):
        calls.append((url, kwargs))
        return _Resp({"ethereum": {"usd": 2500.0}})

    monkeypatch.setattr(prices.requests, "get", _get)
    yield calls
    prices._price_cache.clear()


class TestLookups:
    def test_a_stablecoin_is_one_without_a_request(self, clean_cache):
        assert prices.get_price_usd("USDC") == 1.0
        assert clean_cache == []

    def test_the_symbol_is_normalised(self, clean_cache):
        assert prices.get_price_usd(" eth ") == 2500.0

    def test_an_unknown_asset_uses_the_fallback(self, clean_cache):
        assert prices.get_price_usd("NOPE", fallback=7.0) == 7.0
        assert clean_cache == []

    def test_an_unknown_asset_without_a_fallback_is_zero(self):
        assert prices.get_price_usd("NOPE") == 0.0

    def test_a_fetched_price_is_cached(self, clean_cache):
        assert prices.get_price_usd("ETH") == 2500.0
        assert prices.get_price_usd("ETH") == 2500.0
        assert len(clean_cache) == 1

    def test_the_cache_key_is_the_coin_id(self, clean_cache):
        prices.get_price_usd("ETH")
        prices.get_price_usd("WETH")
        assert len(clean_cache) == 1

    def test_the_request_carries_a_timeout(self, clean_cache):
        prices.get_price_usd("ETH")
        assert clean_cache[0][1]["timeout"] == 5

    def test_eth_has_a_built_in_fallback(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(prices.requests, "get", boom)
        assert prices.get_eth_price_usd() == 3500.0


class TestFailures:
    def test_a_http_error_without_a_cache_uses_the_fallback(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(prices.requests, "get", boom)
        assert prices.get_price_usd("ETH", fallback=1000.0) == 1000.0

    def test_a_http_error_without_anything_is_zero(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(prices.requests, "get", boom)
        assert prices.get_price_usd("ETH") == 0.0

    def test_a_stale_price_beats_both(self, monkeypatch):
        prices._price_cache["ethereum"] = (2400.0, 0.0)  # ancient

        def boom(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(prices.requests, "get", boom)
        assert prices.get_price_usd("ETH", fallback=1000.0) == 2400.0

    def test_a_bad_payload_is_a_fetch_failure(self, monkeypatch):
        monkeypatch.setattr(prices.requests, "get", lambda *a, **k: _Resp({"other": {}}))
        assert prices.get_price_usd("ETH", fallback=5.0) == 5.0
