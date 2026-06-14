"""Tests for src/mev/ — MEV protection, sandwich detection, frontrunning."""

import pytest
from unittest.mock import MagicMock, patch

from src.mev import (
    MEVProtector,
    check_sandwich_risk,
    detect_frontrun,
    MEVConfig,
    MEVStrategy,
    ProtectedTx,
    BundleResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    defaults = dict(chain="ethereum", strategy=MEVStrategy.FLASHBOTS)
    defaults.update(overrides)
    return MEVConfig(**defaults)


def _make_protector(**overrides):
    return MEVProtector(_make_config(**overrides))


def _simple_tx():
    return {"to": "0xRouter", "data": "0x", "value": "0x0", "gasPrice": "0x0"}


def _swap_tx():
    return {
        "to": "0xRouter",
        "data": "0x38ed1739" + "0" * 200,
        "value": hex(2 * 10**18),
        "gasPrice": hex(60 * 10**9),
    }


# ===========================================================================
# MEVStrategy enum
# ===========================================================================

class TestMEVStrategy:
    def test_flashbots_value(self):
        assert MEVStrategy.FLASHBOTS.value == "flashbots"

    def test_private_rpc_value(self):
        assert MEVStrategy.PRIVATE_RPC.value == "private_rpc"

    def test_bundle_value(self):
        assert MEVStrategy.BUNDLE.value == "bundle"

    def test_none_value(self):
        assert MEVStrategy.NONE.value == "none"


# ===========================================================================
# MEVConfig
# ===========================================================================

class TestMEVConfig:
    def test_defaults(self):
        config = MEVConfig()
        assert config.chain == "ethereum"
        assert config.strategy == MEVStrategy.FLASHBOTS
        assert config.timeout == 30
        assert config.retry_count == 3

    def test_custom(self):
        config = MEVConfig(chain="base", strategy=MEVStrategy.BUNDLE, timeout=60)
        assert config.chain == "base"
        assert config.strategy == MEVStrategy.BUNDLE
        assert config.timeout == 60

    def test_private_rpcs_default(self):
        config = MEVConfig()
        assert len(config.private_rpcs) >= 3


# ===========================================================================
# ProtectedTx
# ===========================================================================

class TestProtectedTx:
    def test_fields(self):
        tx = ProtectedTx(
            original_tx={"data": "0x1"},
            protected_tx={"data": "0x1"},
            strategy=MEVStrategy.FLASHBOTS,
        )
        assert tx.status == "pending"
        assert tx.error == ""
        assert tx.bundle_hash == ""

    def test_to_dict(self):
        tx = ProtectedTx(
            original_tx={}, protected_tx={},
            strategy=MEVStrategy.BUNDLE,
            target_block=100, bundle_hash="0xabc",
            status="bundled",
        )
        d = tx.to_dict()
        assert d["strategy"] == "bundle"
        assert d["target_block"] == 100
        assert d["status"] == "bundled"


# ===========================================================================
# BundleResult
# ===========================================================================

class TestBundleResult:
    def test_fields(self):
        br = BundleResult(bundle_hash="0xabc", block_number=100, success=True, tx_count=2)
        assert br.bundle_hash == "0xabc"
        assert br.success is True
        assert br.tx_count == 2

    def test_to_dict(self):
        br = BundleResult(bundle_hash="0x1", block_number=50, success=False, error="fail")
        d = br.to_dict()
        assert d["success"] is False
        assert d["block_number"] == 50


# ===========================================================================
# check_sandwich_risk
# ===========================================================================

class TestCheckSandwichRisk:
    def test_no_risk_simple_tx(self):
        result = check_sandwich_risk(_simple_tx())
        assert result["risk_score"] == 0
        assert len(result["risk_factors"]) == 0
        assert "Standard RPC" in result["recommendation"]

    def test_swap_high_risk(self):
        tx = _swap_tx()
        result = check_sandwich_risk(tx)
        assert result["risk_score"] >= 30
        assert any("Swap" in f for f in result["risk_factors"])
        assert "Flashbots" in result["recommendation"]

    def test_high_value_adds_risk(self):
        tx = {"data": "0x", "value": hex(5 * 10**18), "gasPrice": "0x0"}
        result = check_sandwich_risk(tx)
        assert result["risk_score"] >= 20
        assert any("High value" in f for f in result["risk_factors"])

    def test_high_gas_adds_risk(self):
        tx = {"data": "0x", "value": "0x0", "gasPrice": hex(100 * 10**9)}
        result = check_sandwich_risk(tx)
        assert result["risk_score"] >= 10
        assert any("gas" in f.lower() for f in result["risk_factors"])

    def test_long_calldata_adds_risk(self):
        tx = {"data": "0x" + "ab" * 200, "value": "0x0", "gasPrice": "0x0"}
        result = check_sandwich_risk(tx)
        assert result["risk_score"] >= 5
        assert any("slippage" in f.lower() for f in result["risk_factors"])

    def test_max_risk_capped_at_100(self):
        tx = _swap_tx()
        tx["gasPrice"] = hex(100 * 10**9)
        tx["data"] = "0x38ed1739" + "0" * 300
        result = check_sandwich_risk(tx)
        assert result["risk_score"] <= 100


# ===========================================================================
# detect_frontrun
# ===========================================================================

class TestDetectFrontrun:
    def test_no_pending(self):
        result = detect_frontrun(_simple_tx())
        assert result["at_risk"] is False
        assert result["risk_score"] == 0
        assert result["competing_txs"] == []

    def test_frontrun_detected(self):
        tx = {"to": "0xRouter", "gasPrice": 50}
        pending = [{"to": "0xRouter", "gasPrice": 100, "hash": "0xp1"}]
        result = detect_frontrun(tx, pending)
        assert result["at_risk"] is True
        assert len(result["competing_txs"]) == 1
        assert result["competing_txs"][0]["gas_ratio"] == 2.0

    def test_different_target_no_risk(self):
        tx = {"to": "0xA", "gasPrice": 50}
        pending = [{"to": "0xB", "gasPrice": 100, "hash": "0xp1"}]
        result = detect_frontrun(tx, pending)
        assert result["at_risk"] is False

    def test_lower_gas_no_risk(self):
        tx = {"to": "0xRouter", "gasPrice": 100}
        pending = [{"to": "0xRouter", "gasPrice": 50, "hash": "0xp1"}]
        result = detect_frontrun(tx, pending)
        assert result["at_risk"] is False

    def test_high_risk_recommendation(self):
        # Generate many competing txs to push risk_score > 50
        tx = {"to": "0xRouter", "gasPrice": 10}
        pending = [
            {"to": "0xRouter", "gasPrice": 500, "hash": f"0xp{i}"}
            for i in range(5)
        ]
        result = detect_frontrun(tx, pending)
        assert result["at_risk"] is True
        assert result["risk_score"] > 0
        assert "increasing gas" in result["recommendation"].lower() or "Flashbots" in result["recommendation"]

    def test_hex_gas_prices(self):
        tx = {"to": "0xRouter", "gasPrice": hex(50)}
        pending = [{"to": "0xRouter", "gasPrice": hex(100), "hash": "0xp1"}]
        result = detect_frontrun(tx, pending)
        assert result["at_risk"] is True


# ===========================================================================
# MEVProtector
# ===========================================================================

class TestMEVProtectorInit:
    def test_default_config(self):
        protector = _make_protector()
        assert protector.config.strategy == MEVStrategy.FLASHBOTS

    def test_custom_config(self):
        config = MEVConfig(strategy=MEVStrategy.PRIVATE_RPC, chain="base")
        protector = MEVProtector(config)
        assert protector.config.chain == "base"


class TestMEVProtectorProtectTx:
    def test_flashbots_strategy(self):
        protector = _make_protector(strategy=MEVStrategy.FLASHBOTS)
        result = protector.protect_tx(_simple_tx())
        assert isinstance(result, ProtectedTx)
        assert result.strategy == MEVStrategy.FLASHBOTS

    def test_private_rpc_strategy(self):
        protector = _make_protector(strategy=MEVStrategy.PRIVATE_RPC)
        result = protector.protect_tx(_simple_tx())
        assert result.strategy == MEVStrategy.PRIVATE_RPC

    def test_bundle_strategy(self):
        protector = _make_protector(strategy=MEVStrategy.BUNDLE)
        with patch.object(protector, "_get_current_block", return_value=1000):
            result = protector.protect_tx(_simple_tx())
        assert result.strategy == MEVStrategy.BUNDLE
        assert result.target_block == 1001

    def test_none_strategy(self):
        protector = _make_protector(strategy=MEVStrategy.NONE)
        result = protector.protect_tx(_simple_tx())
        assert result.strategy == MEVStrategy.NONE
        assert result.status == "unprotected"


class TestMEVProtectorSendProtected:
    def test_send_flashbots_success(self):
        protector = _make_protector(strategy=MEVStrategy.FLASHBOTS)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": "0xtxhash"}
        protector.session.post = MagicMock(return_value=mock_resp)

        pt = ProtectedTx(
            original_tx=_simple_tx(), protected_tx=_simple_tx(),
            strategy=MEVStrategy.FLASHBOTS,
        )
        result = protector.send_protected(pt)
        assert result == "0xtxhash"
        assert pt.status == "submitted"

    def test_send_flashbots_failure(self):
        protector = _make_protector(strategy=MEVStrategy.FLASHBOTS)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        protector.session.post = MagicMock(return_value=mock_resp)

        pt = ProtectedTx(
            original_tx=_simple_tx(), protected_tx=_simple_tx(),
            strategy=MEVStrategy.FLASHBOTS,
        )
        result = protector.send_protected(pt)
        assert result is None
        assert pt.error != ""

    def test_send_raw_returns_none(self):
        protector = _make_protector(strategy=MEVStrategy.NONE)
        pt = ProtectedTx(
            original_tx=_simple_tx(), protected_tx=_simple_tx(),
            strategy=MEVStrategy.NONE,
        )
        result = protector.send_protected(pt)
        assert result is None

    def test_send_connection_error(self):
        protector = _make_protector(strategy=MEVStrategy.FLASHBOTS)
        protector.session.post = MagicMock(side_effect=ConnectionError("no network"))

        pt = ProtectedTx(
            original_tx=_simple_tx(), protected_tx=_simple_tx(),
            strategy=MEVStrategy.FLASHBOTS,
        )
        result = protector.send_protected(pt)
        assert result is None
        assert pt.error != ""  # error captured in _send_flashbots


class TestMEVProtectorBundle:
    def test_create_bundle_success(self):
        protector = _make_protector()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": "0xbundlehash"}
        protector.session.post = MagicMock(return_value=mock_resp)

        with patch.object(protector, "_get_current_block", return_value=1000):
            result = protector.create_bundle([_simple_tx()], target_block=1001)
        assert result.success is True
        assert result.tx_count == 1

    def test_create_bundle_failure(self):
        protector = _make_protector()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": {"message": "rejected"}}
        protector.session.post = MagicMock(return_value=mock_resp)

        with patch.object(protector, "_get_current_block", return_value=1000):
            result = protector.create_bundle([_simple_tx()], target_block=1001)
        assert result.success is False
        assert "rejected" in result.error

    def test_simulate_bundle(self):
        protector = _make_protector()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"gasUsed": 100000}}
        protector.session.post = MagicMock(return_value=mock_resp)

        with patch.object(protector, "_get_current_block", return_value=1000):
            result = protector.simulate_bundle([_simple_tx()], block_number=1001)
        assert "result" in result

    def test_simulate_bundle_error(self):
        protector = _make_protector()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        protector.session.post = MagicMock(return_value=mock_resp)

        with patch.object(protector, "_get_current_block", return_value=1000):
            result = protector.simulate_bundle([_simple_tx()], block_number=1001)
        assert "error" in result

    def test_bundle_history(self):
        protector = _make_protector()
        assert len(protector.get_bundle_history()) == 0

    def test_pending_bundles(self):
        protector = _make_protector()
        protector._bundles.append(BundleResult("0x1", 100, success=True))
        protector._bundles.append(BundleResult("0x2", 101, success=False))
        assert len(protector.get_pending_bundles()) == 1


class TestMEVProtectorDelegatedMethods:
    def test_check_sandwich_risk_delegated(self):
        protector = _make_protector()
        result = protector.check_sandwich_risk(_simple_tx())
        assert "risk_score" in result

    def test_check_frontrun_risk_delegated(self):
        protector = _make_protector()
        result = protector.check_frontrun_risk(_simple_tx())
        assert "at_risk" in result


class TestMEVProtectorSendPrivateRPC:
    def test_send_private_rpc_success(self):
        protector = _make_protector(strategy=MEVStrategy.PRIVATE_RPC)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": "0xtxhash"}
        protector.session.post = MagicMock(return_value=mock_resp)

        pt = ProtectedTx(
            original_tx=_simple_tx(), protected_tx=_simple_tx(),
            strategy=MEVStrategy.PRIVATE_RPC,
        )
        result = protector.send_protected(pt)
        assert result == "0xtxhash"

    def test_send_private_rpc_all_fail(self):
        protector = _make_protector(strategy=MEVStrategy.PRIVATE_RPC)
        protector.session.post = MagicMock(side_effect=ConnectionError("fail"))

        pt = ProtectedTx(
            original_tx=_simple_tx(), protected_tx=_simple_tx(),
            strategy=MEVStrategy.PRIVATE_RPC,
        )
        result = protector.send_protected(pt)
        assert result is None
        assert "All private RPCs failed" in pt.error
