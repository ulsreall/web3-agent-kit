"""Contract tests: the API must call the library with the library's own signature.

The route tests mock the collaborator outright, so a renamed parameter or a
rotated argument order passes CI. These tests bind every route call against the
real signature, which fails on exactly that drift.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from web3_agent_kit.api import app  # noqa: E402

AUTH = {"X-API-Key": "test-key-123"}
client = TestClient(app, headers=AUTH)


def _bind(func, *args, **kwargs):
    """Raise TypeError if the call does not fit the real signature."""
    inspect.signature(func).bind(*args, **kwargs)


class _UniswapStub:
    ROUTERS = None

    def __init__(self, *args, **kwargs):
        _bind(_REAL_UNISWAP_INIT, self, *args, **kwargs)

    def execute(self, *args, **kwargs):
        _bind(_REAL_UNISWAP_EXECUTE, self, *args, **kwargs)
        return {"tx_hash": "0xstub"}

    def get_quote(self, *args, **kwargs):
        _bind(_REAL_UNISWAP_QUOTE, self, *args, **kwargs)
        return {"token_in": "ETH"}


class _BridgeStub:
    def __init__(self, *args, **kwargs):
        _bind(_REAL_BRIDGE_INIT, self, *args, **kwargs)

    def get_routes(self, *args, **kwargs):
        _bind(_REAL_BRIDGE_ROUTES, self, *args, **kwargs)
        return []

    def transfer(self, *args, **kwargs):
        _bind(_REAL_BRIDGE_TRANSFER, self, *args, **kwargs)
        return {"tx_hash": "0xstub"}


class _DCAStub:
    def __init__(self, *args, **kwargs):
        _bind(_REAL_DCA_INIT, self, *args, **kwargs)

    def create_order(self, *args, **kwargs):
        _bind(_REAL_DCA_CREATE, self, *args, **kwargs)
        return {"order_id": "stub"}

    def list_orders(self, *args, **kwargs):
        _bind(_REAL_DCA_LIST, self, *args, **kwargs)
        return []


from web3_agent_kit.bridge.bridge import BridgeAgent as _Bridge  # noqa: E402
from web3_agent_kit.defi import Uniswap as _Uniswap  # noqa: E402
from web3_agent_kit.trading.dca import DCABot as _DCA  # noqa: E402

_REAL_UNISWAP_INIT = _Uniswap.__init__
_REAL_UNISWAP_EXECUTE = _Uniswap.execute
_REAL_UNISWAP_QUOTE = _Uniswap.get_quote
_REAL_BRIDGE_INIT = _Bridge.__init__
_REAL_BRIDGE_ROUTES = _Bridge.get_routes
_REAL_BRIDGE_TRANSFER = _Bridge.transfer
_REAL_DCA_INIT = _DCA.__init__
_REAL_DCA_CREATE = _DCA.create_order
_REAL_DCA_LIST = _DCA.list_orders


@pytest.fixture(autouse=True)
def _stub_routers():
    _UniswapStub.ROUTERS = {chain: "0x" + "22" * 20 for chain in _Uniswap.ROUTERS}


def test_swap_execute_matches_library_signature():
    with patch("web3_agent_kit.defi.Uniswap", _UniswapStub):
        resp = client.post("/swap/execute?chain=base&token_out=USDC")
    assert resp.status_code == 200, resp.text


def test_swap_quote_matches_library_signature():
    with patch("web3_agent_kit.defi.Uniswap", _UniswapStub):
        resp = client.get("/swap/quote?chain=base")
    assert resp.status_code == 200, resp.text


def test_bridge_execute_matches_library_signature():
    with patch("web3_agent_kit.bridge.bridge.BridgeAgent", _BridgeStub):
        resp = client.post("/bridge/execute?from_chain=base&to_chain=arbitrum")
    assert resp.status_code == 200, resp.text


def test_bridge_quote_matches_library_signature():
    with patch("web3_agent_kit.bridge.bridge.BridgeAgent", _BridgeStub):
        resp = client.get("/bridge/quote?from_chain=base&to_chain=arbitrum")
    assert resp.status_code == 200, resp.text


def test_dca_create_matches_library_signature():
    with patch("web3_agent_kit.trading.dca.DCABot", _DCAStub):
        resp = client.post("/dca/orders?amount_per_buy=10")
    assert resp.status_code == 200, resp.text


def test_dca_list_matches_library_signature():
    with patch("web3_agent_kit.trading.dca.DCABot", _DCAStub):
        resp = client.get("/dca/orders")
    assert resp.status_code == 200, resp.text
