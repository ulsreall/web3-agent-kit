"""Replay protection must survive a second gate, a restart and a broken store."""

from __future__ import annotations

import time

import pytest
from eth_account import Account

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationEvidence,
    CallableAuthorizationProvider,
    EnforcementDenied,
    ExecutionPolicy,
    PreSignInterceptor,
)
from web3_agent_kit.execution.replay import (
    InMemoryReplayStore,
    SqliteReplayStore,
    default_store,
    reset_default_store,
)

SENDER_KEY = "0x" + "11" * 32
SENDER = Account.from_key(SENDER_KEY).address
TARGET = "0x" + "22" * 20


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE}),
        allowed_actions=frozenset({ActionType.SWAP}),
        allowed_contracts=frozenset({TARGET}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )


def _evidence(context) -> AuthorizationEvidence:
    now = int(time.time())
    return AuthorizationEvidence(
        authorization_id="auth-replay",
        envelope_digest=context.envelope_digest,
        executor=context.envelope.executor,
        authorizer=context.envelope.executor,
        valid_from=now - 5,
        valid_until=now + 300,
        nonce="nonce-1",
        policy_commitment_digest=context.policy_commitment.digest(),
    )


def _gate(store) -> PreSignInterceptor:
    return PreSignInterceptor(
        policy=_policy(),
        signer=lambda tx: Account.sign_transaction(tx, SENDER_KEY).raw_transaction,
        authorization_provider=CallableAuthorizationProvider(_evidence),
        replay_store=store,
    )


def _request():
    from web3_agent_kit.execution import AuthorizationRequest

    tx = {
        "from": SENDER,
        "to": TARGET,
        "value": 0,
        "data": "0x",
        "nonce": 1,
        "chainId": 8453,
        "gas": 100_000,
        "maxFeePerGas": 10**9,
        "maxPriorityFeePerGas": 10**9,
    }
    return AuthorizationRequest(Chain.BASE, ActionType.SWAP, tx)


# -- stores ---------------------------------------------------------------


def test_memory_store_consumes_once():
    store = InMemoryReplayStore()
    assert store.consume("k", int(time.time()) + 60) is True
    assert store.consume("k", int(time.time()) + 60) is False


def test_memory_store_prunes_expired_keys():
    store = InMemoryReplayStore()
    store.consume("old", int(time.time()) - 1)
    store.consume("live", int(time.time()) + 60)
    assert store.consume("old", int(time.time()) + 60) is True
    assert len(store) == 2
    assert store.prune() == 0  # nothing expired yet
    store.consume("stale", int(time.time()) - 1)
    assert store.prune() == 1
    assert len(store) == 2


def test_memory_store_stays_bounded():
    store = InMemoryReplayStore(max_entries=2)
    now = int(time.time())
    store.consume("a", now + 10)
    store.consume("b", now + 20)
    store.consume("c", now + 30)
    assert len(store) == 2


def test_sqlite_store_survives_a_new_instance(tmp_path):
    path = str(tmp_path / "replay.db")
    first = SqliteReplayStore(path)
    assert first.consume("k", int(time.time()) + 60) is True

    second = SqliteReplayStore(path)
    assert second.consume("k", int(time.time()) + 60) is False


def test_sqlite_store_prunes(tmp_path):
    store = SqliteReplayStore(str(tmp_path / "replay.db"))
    store.consume("old", int(time.time()) - 1)
    assert store.prune() == 1
    assert len(store) == 0


# -- gate integration -----------------------------------------------------


def test_second_gate_sharing_a_store_denies_the_replay():
    store = InMemoryReplayStore()
    _gate(store).sign(_request())

    with pytest.raises(EnforcementDenied, match="single-use"):
        _gate(store).sign(_request())


def test_replay_survives_a_restart_via_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB3_REPLAY_DB", str(tmp_path / "replay.db"))
    reset_default_store()
    _gate(default_store()).sign(_request())

    reset_default_store()  # simulate a fresh process
    with pytest.raises(EnforcementDenied, match="single-use"):
        _gate(default_store()).sign(_request())


def test_broken_store_fails_closed():
    class Broken:
        def consume(self, key, expires_at):
            raise RuntimeError("db is gone")

        def prune(self, now=None):
            return 0

        def __len__(self):
            return 0

    with pytest.raises(EnforcementDenied, match="replay store unavailable"):
        _gate(Broken()).sign(_request())
