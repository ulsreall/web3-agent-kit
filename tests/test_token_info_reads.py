"""Reading token metadata from the chain.

`_get_token_info` decides ``is_verified`` and normalises ``total_supply`` by the
token's own decimals, and both feed the safety score. A silent failure here
either marks an unreadable token verified or divides by the wrong scale.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from web3_agent_kit.security import SecurityConfig, TokenAnalyzer, TokenInfo

ADDRESS = "0x" + "aa" * 20


class _Fn:
    def __init__(self, value=None, error=None):
        self._value = value
        self._error = error

    def call(self):
        if self._error:
            raise self._error
        return self._value


class _Functions:
    def __init__(self, **values):
        self._values = values

    def __getattr__(self, name):
        if name not in self._values:
            raise AttributeError(name)
        return lambda: _Fn(*self._values[name])


class _W3:
    def __init__(self, functions):
        self.eth = SimpleNamespace(contract=lambda address, abi: SimpleNamespace(functions=functions))

    @staticmethod
    def to_checksum_address(address):
        return address


class _Web3Proxy:
    """Stands in for the `web3.Web3` class the method imports."""

    def __init__(self, functions):
        self._functions = functions

    def __call__(self):  # pragma: no cover - not used
        return None

    ether = None


@pytest.fixture
def analyzer(monkeypatch) -> TokenAnalyzer:
    instance = TokenAnalyzer(SecurityConfig())

    def make(functions):
        class FakeWeb3:
            @staticmethod
            def to_checksum_address(address):
                return address

        monkeypatch.setattr("web3.Web3", FakeWeb3)
        return _W3(functions)

    instance._build = make  # type: ignore[attr-defined]
    return instance


def _full(**overrides):
    values = {
        "name": ("Token", None),
        "symbol": ("TKN", None),
        "decimals": (6, None),
        "totalSupply": (2_000_000_000, None),
        "owner": (ADDRESS, None),
    }
    values.update({k: v for k, v in overrides.items()})
    return _Functions(**values)


class TestTokenInfo:
    def test_reads_metadata_and_normalises_by_decimals(self, analyzer):
        analyzer._web3 = analyzer._build(_full())
        info = analyzer._get_token_info(ADDRESS)
        assert info.symbol == "TKN"
        assert info.decimals == 6
        assert info.total_supply == 2_000.0

    def test_owner_present_marks_the_token_verified(self, analyzer):
        analyzer._web3 = analyzer._build(_full())
        assert analyzer._get_token_info(ADDRESS).is_verified is True

    def test_missing_owner_leaves_it_unverified_but_keeps_the_metadata(self, analyzer):
        # No owner() (non-standard or unreadable) must not throw away the
        # name/symbol that were read fine.
        analyzer._web3 = analyzer._build(_full(owner=("", ValueError("no owner"))))
        info = analyzer._get_token_info(ADDRESS)
        assert info.is_verified is False
        assert info.owner == ""
        assert info.symbol == "TKN"

    def test_unreadable_contract_returns_the_bare_record(self, analyzer):
        analyzer._web3 = analyzer._build(_Functions())
        info = analyzer._get_token_info(ADDRESS)
        assert info == TokenInfo(address=ADDRESS, chain="ethereum")

    def test_no_web3_returns_the_bare_record(self, analyzer):
        info = analyzer._get_token_info(ADDRESS)
        assert info.address == ADDRESS
        assert info.symbol == ""

    def test_zero_decimals_does_not_divide_by_zero(self, analyzer):
        analyzer._web3 = analyzer._build(_full(decimals=(0, None)))
        assert analyzer._get_token_info(ADDRESS).total_supply == 2_000_000_000.0
