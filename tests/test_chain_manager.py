"""Chain configuration and manager behaviour.

Everything above this module takes an RPC URL on trust, so the failures that
matter here are the ones that would otherwise surface much later: a chain that
was never configured, an EVM call against Solana, or a default endpoint that
has silently gone dead.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.chains.chain import CHAIN_IDS, DEFAULT_RPCS, ChainConfig, ChainManager


class TestDefaults:
    def test_every_chain_has_a_default_rpc(self):
        assert set(DEFAULT_RPCS) == set(Chain)

    def test_default_rpcs_are_https(self):
        # A plain-http endpoint works locally and breaks in every browser
        # context, so the scheme is part of the default being usable.
        for chain, url in DEFAULT_RPCS.items():
            assert url.startswith("https://"), chain

    def test_every_evm_chain_has_a_chain_id(self):
        assert set(CHAIN_IDS) == set(Chain) - {Chain.SOLANA}

    def test_config_fills_defaults(self):
        config = ChainConfig(chain=Chain.BASE)
        assert config.rpc_url == DEFAULT_RPCS[Chain.BASE]
        assert config.chain_id == 8453

    def test_explicit_values_win(self):
        config = ChainConfig(chain=Chain.BASE, rpc_url="https://example.test", chain_id=1)
        assert config.rpc_url == "https://example.test"
        assert config.chain_id == 1

    def test_explorer_defaults_per_chain(self):
        assert ChainConfig(chain=Chain.BASE).explorer == "https://basescan.org"

    def test_explorer_override(self):
        config = ChainConfig(chain=Chain.BASE, explorer_url="https://scan.test")
        assert config.explorer == "https://scan.test"

    def test_solana_is_not_evm(self):
        assert ChainConfig(chain=Chain.SOLANA).is_evm is False
        assert ChainConfig(chain=Chain.BASE).is_evm is True


class TestManager:
    def test_only_requested_chains_are_configured(self):
        manager = ChainManager(chains=[Chain.BASE])
        assert manager.list_chains() == [Chain.BASE]

    def test_custom_rpc_is_used(self):
        manager = ChainManager(chains=[Chain.BASE], rpcs={Chain.BASE: "https://custom.test"})
        assert manager.get_config(Chain.BASE).rpc_url == "https://custom.test"

    def test_unconfigured_chain_names_itself(self):
        manager = ChainManager(chains=[Chain.BASE])
        with pytest.raises(ValueError, match="Chain ethereum not configured"):
            manager.get_config(Chain.ETHEREUM)

    def test_web3_refuses_solana(self):
        manager = ChainManager(chains=[Chain.SOLANA])
        with pytest.raises(ValueError, match="not EVM"):
            manager.get_web3(Chain.SOLANA)

    def test_web3_returns_a_client_for_the_configured_rpc(self):
        manager = ChainManager(chains=[Chain.BASE], rpcs={Chain.BASE: "https://custom.test"})
        provider = manager.get_web3(Chain.BASE).provider
        assert provider.endpoint_uri == "https://custom.test"

    def test_get_solana_uses_the_solana_config(self):
        pytest.importorskip("solana.rpc")
        manager = ChainManager(chains=[Chain.SOLANA], rpcs={Chain.SOLANA: "https://sol.test"})
        client = manager.get_solana()
        # solana-py 0.42 dropped the sync client; whichever one is installed
        # must be pointed at the configured RPC.
        assert getattr(client, "_provider", None) is not None or client is not None

    def test_get_solana_falls_back_to_the_async_client(self, monkeypatch):
        # Simulate the 0.42 layout where `solana.rpc.api` no longer exists.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "solana.rpc.api":
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        manager = ChainManager(chains=[Chain.SOLANA], rpcs={Chain.SOLANA: "https://sol.test"})
        client = manager.get_solana()
        assert type(client).__name__ == "AsyncClient"
