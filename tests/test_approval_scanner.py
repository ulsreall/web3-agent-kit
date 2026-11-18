"""Behaviour of the approval scanner's bulk paths.

`scan`, `revoke_all_unlimited` and `revoke_unknown` are the surface a user
actually runs when cleaning up allowances, and they were the untested part of
the module: the individual pieces were covered, the loops that combine them and
decide what to revoke were not.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.wallet.approval import ApprovalManager, ApprovalRisk, TokenApproval

TOKEN = "0x" + "aa" * 20
SPENDER = "0x" + "bb" * 20
WALLET = "0x" + "cc" * 20


def _approval(*, amount: float, label: str = "Uniswap V2", risk=ApprovalRisk.HIGH):
    return TokenApproval(
        token_address=TOKEN,
        token_symbol="TKN",
        spender=SPENDER,
        spender_label=label,
        amount=amount,
        amount_raw=int(amount) if amount != float("inf") else 2**256 - 1,
        risk=risk,
        chain=Chain.BASE,
    )


@pytest.fixture
def manager():
    return ApprovalManager(SimpleNamespace(address=WALLET), SimpleNamespace())


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("web3_agent_kit.wallet.approval.time.sleep", lambda _s: None)


class TestScan:
    def test_scan_aggregates_every_token(self, manager, monkeypatch):
        monkeypatch.setattr(
            ApprovalManager, "_get_common_tokens", lambda self, chain: [(TOKEN, "TKN")]
        )
        seen = []

        def fake_check(self, token_addr, symbol, chain):
            seen.append((token_addr, symbol))
            return [_approval(amount=1.0)]

        monkeypatch.setattr(ApprovalManager, "_check_token_approvals", fake_check)
        result = manager.scan(Chain.BASE)
        assert seen == [(TOKEN, "TKN")]
        assert len(result) == 1
        # The scan result is retained for the bulk revokers and for callers.
        assert manager.approvals is result

    def test_scan_resets_previous_results(self, manager, monkeypatch):
        manager.approvals = [_approval(amount=1.0)]
        monkeypatch.setattr(ApprovalManager, "_get_common_tokens", lambda self, chain: [])
        assert manager.scan(Chain.BASE) == []
        assert manager.approvals == []

    def test_scan_continues_over_many_tokens(self, manager, monkeypatch):
        tokens = [(TOKEN, "A"), ("0x" + "dd" * 20, "B")]
        monkeypatch.setattr(ApprovalManager, "_get_common_tokens", lambda self, chain: tokens)
        monkeypatch.setattr(
            ApprovalManager,
            "_check_token_approvals",
            lambda self, token_addr, symbol, chain: [_approval(amount=1.0)],
        )
        assert len(manager.scan(Chain.BASE)) == 2


class TestBulkRevoke:
    @pytest.fixture
    def recorded(self, manager, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ApprovalManager,
            "revoke",
            lambda self, token, spender, chain: calls.append((token, spender, chain)) or "ok",
        )
        return calls

    def test_revoke_all_unlimited_only_takes_unlimited(self, manager, recorded):
        manager.approvals = [_approval(amount=float("inf")), _approval(label="Finite", amount=5.0)]
        results = manager.revoke_all_unlimited(Chain.BASE)
        assert results == ["ok"]
        assert recorded == [(TOKEN, SPENDER, Chain.BASE)]

    def test_revoke_all_unlimited_with_nothing_to_do(self, manager, recorded):
        manager.approvals = [_approval(amount=1.0)]
        assert manager.revoke_all_unlimited(Chain.BASE) == []
        assert recorded == []

    def test_revoke_unknown_needs_both_unknown_and_unlimited(self, manager, recorded):
        manager.approvals = [
            _approval(amount=float("inf"), label="Unknown"),
            _approval(amount=float("inf"), label="Uniswap"),  # known: keep
            _approval(amount=1.0, label="Unknown"),  # bounded: keep
        ]
        assert manager.revoke_unknown(Chain.BASE) == ["ok"]
        assert len(recorded) == 1

    def test_revoke_unknown_with_nothing_to_do(self, manager, recorded):
        manager.approvals = []
        assert manager.revoke_unknown(Chain.BASE) == []


class TestBuildRevokeTx:
    def test_revoke_tx_approves_zero_and_carries_the_nonce_and_chain(self, manager):
        captured = {}

        class FakeFn:
            def approve(self, spender, amount):
                captured["spender"] = spender
                captured["amount"] = amount

                class B:
                    def build_transaction(self, tx):
                        captured["tx"] = tx
                        return {"raw": "tx"}

                return B()

        w3 = SimpleNamespace(
            eth=SimpleNamespace(
                contract=lambda address, abi: SimpleNamespace(functions=FakeFn()),
                get_transaction_count=lambda address: 9,
                chain_id=8453,
            ),
            to_checksum_address=lambda a: a,
        )
        manager.chain_manager = SimpleNamespace(get_web3=lambda chain: w3)

        assert manager._build_revoke_tx(TOKEN, SPENDER, Chain.BASE) == {"raw": "tx"}
        assert captured["amount"] == 0
        assert captured["tx"]["from"] == WALLET
        assert captured["tx"]["nonce"] == 9
        assert captured["tx"]["chainId"] == 8453
