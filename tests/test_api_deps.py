"""The API dependency layer: chain/token resolution and gate assembly.

Every route goes through these, so a wrong answer here reaches the signer.
"""

from __future__ import annotations

import time

import pytest

from web3_agent_kit.api import deps
from web3_agent_kit.chains import Chain


class TestChains:
    def test_a_known_chain_resolves(self):
        assert deps.resolve_chain("base") is Chain.BASE

    def test_case_does_not_matter(self):
        assert deps.resolve_chain("BASE") is Chain.BASE

    def test_an_unknown_chain_is_rejected(self):
        with pytest.raises(ValueError, match="unsupported chain"):
            deps.resolve_chain("dogechain")

    def test_an_allowlist_narrows_the_choices(self, monkeypatch):
        monkeypatch.setenv("WEB3_ALLOWED_CHAINS", "base, arbitrum")
        assert deps.resolve_chain("arbitrum") is Chain.ARBITRUM

    def test_a_chain_outside_the_allowlist_is_rejected(self, monkeypatch):
        monkeypatch.setenv("WEB3_ALLOWED_CHAINS", "base")
        with pytest.raises(ValueError, match="WEB3_ALLOWED_CHAINS"):
            deps.resolve_chain("ethereum")

    def test_the_manager_is_scoped_to_one_chain(self):
        assert set(deps.chain_manager(Chain.BASE).configs) == {Chain.BASE}


class TestTokens:
    def test_native_passes_through_uppercased(self):
        assert deps.resolve_token(Chain.BASE, "native") == "NATIVE"

    def test_eth_passes_through(self):
        assert deps.resolve_token(Chain.BASE, "eth") == "ETH"

    def test_a_known_symbol_resolves(self):
        assert deps.resolve_token(Chain.BASE, "usdc").startswith("0x")

    def test_an_address_passes_through_untouched(self):
        address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        assert deps.resolve_token(Chain.BASE, address) == address

    def test_an_uppercase_x_address_passes(self):
        address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913".replace("0x", "0X")
        assert deps.resolve_token(Chain.BASE, address) == address

    def test_an_address_shaped_non_hex_string_is_rejected(self):
        with pytest.raises(ValueError, match="not a 20-byte hex address"):
            deps.resolve_token(Chain.BASE, "0x" + "z" * 40)

    def test_a_short_address_is_rejected(self):
        with pytest.raises(ValueError, match="not a 20-byte hex address"):
            deps.resolve_token(Chain.BASE, "0x1234")

    def test_an_unknown_symbol_lists_the_known_ones(self):
        with pytest.raises(ValueError, match="unknown token"):
            deps.resolve_token(Chain.BASE, "NOTACOIN")


class TestGate:
    def test_the_gate_is_off_by_default(self, monkeypatch):
        monkeypatch.delenv("WEB3_AUTO_AUTHORIZE", raising=False)
        assert deps.build_gate(Chain.BASE, signer=lambda tx: tx) is None

    def test_the_gate_turns_on(self, monkeypatch):
        monkeypatch.setenv("WEB3_AUTO_AUTHORIZE", "true")
        monkeypatch.setenv("WEB3_ALLOWED_CONTRACTS", "0x1111111111111111111111111111111111111111")
        gate = deps.build_gate(Chain.BASE, signer=lambda tx: tx)
        assert gate is not None

    def test_a_bad_native_limit_is_reported(self, monkeypatch):
        monkeypatch.setenv("WEB3_AUTO_AUTHORIZE", "1")
        monkeypatch.setenv("WEB3_MAX_NATIVE_WEI", "lots")
        with pytest.raises(ValueError, match="must be an integer"):
            deps.build_gate(Chain.BASE, signer=lambda tx: tx)

    def test_the_route_target_seeds_the_allowlist(self, monkeypatch):
        monkeypatch.setenv("WEB3_AUTO_AUTHORIZE", "1")
        monkeypatch.delenv("WEB3_ALLOWED_CONTRACTS", raising=False)
        gate = deps.build_gate(
            Chain.BASE, signer=lambda tx: tx, targets={"0x1111111111111111111111111111111111111111"}
        )
        assert gate.policy.allowed_contracts == frozenset(
            {"0x1111111111111111111111111111111111111111"}
        )

    def test_an_operator_allowlist_wins_over_the_route(self, monkeypatch):
        monkeypatch.setenv("WEB3_AUTO_AUTHORIZE", "1")
        monkeypatch.setenv("WEB3_ALLOWED_CONTRACTS", "0x2222222222222222222222222222222222222222")
        gate = deps.build_gate(
            Chain.BASE, signer=lambda tx: tx, targets={"0x1111111111111111111111111111111111111111"}
        )
        assert gate.policy.allowed_contracts == frozenset(
            {"0x2222222222222222222222222222222222222222"}
        )

    def test_the_default_native_limit_is_small(self, monkeypatch):
        monkeypatch.setenv("WEB3_AUTO_AUTHORIZE", "1")
        monkeypatch.delenv("WEB3_MAX_NATIVE_WEI", raising=False)
        gate = deps.build_gate(Chain.BASE, signer=lambda tx: tx)
        assert gate.policy.max_native_value_wei == deps.DEFAULT_MAX_NATIVE_WEI


class TestAutoAuthorization:
    def test_it_binds_the_evidence_to_the_envelope(self):
        provider = deps.AutoAuthorizationProvider()
        evidence = provider.authorize(_Context())
        assert evidence.envelope_digest == DIGEST
        assert evidence.executor == "exec"
        assert evidence.policy_commitment_digest == DIGEST

    def test_the_window_matches_the_ttl(self):
        evidence = deps.AutoAuthorizationProvider().authorize(_Context())
        assert evidence.valid_until - evidence.valid_from == deps.AUTHORIZATION_TTL_SECONDS

    def test_each_call_gets_a_fresh_nonce(self):
        provider = deps.AutoAuthorizationProvider()
        assert provider.authorize(_Context()).nonce != provider.authorize(_Context()).nonce

    def test_the_policy_id_names_the_provider(self):
        assert deps.AutoAuthorizationProvider().policy_id == "api-auto-authorization"


DIGEST = "0x" + "ab" * 32


class _Commitment:
    def digest(self) -> str:
        return DIGEST


class _Context:
    envelope_digest = DIGEST

    class envelope:  # noqa: N801 - mirrors the real context shape
        executor = "exec"

    policy_commitment = _Commitment()


def _now() -> int:
    return int(time.time())


class TestWallet:
    def test_the_wallet_is_bound_to_the_gate(self, monkeypatch):
        monkeypatch.setenv("WEB3_AUTO_AUTHORIZE", "1")
        monkeypatch.setenv("PRIVATE_KEY", "0x" + "11" * 32)
        wallet = deps.build_wallet(Chain.BASE, targets={"0x" + "11" * 20})
        assert wallet.enforcement is not None

    def test_without_authorization_the_wallet_is_unbound(self, monkeypatch):
        monkeypatch.delenv("WEB3_AUTO_AUTHORIZE", raising=False)
        monkeypatch.setenv("PRIVATE_KEY", "0x" + "11" * 32)
        assert deps.build_wallet(Chain.BASE).enforcement is None
