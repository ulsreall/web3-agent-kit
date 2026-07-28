"""Coverage tests for the API route handlers.

All network/RPC/web3/service layers are mocked so nothing touches the
network. Exercises both happy paths and error/validation paths for every
route module under web3_agent_kit/api/routes/.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

TEST_API_KEY = "test-key-123"

if FASTAPI_AVAILABLE:
    # Fail-closed startup guard requires WEB3_API_KEY before the app boots.
    os.environ.setdefault("WEB3_API_KEY", TEST_API_KEY)

    from web3_agent_kit.api import app

    client = TestClient(app)
    AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture(autouse=True)
def _ensure_api_key(monkeypatch):
    """Guarantee the known API key is configured for every test."""
    monkeypatch.setenv("WEB3_API_KEY", TEST_API_KEY)


pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")


# === Wallet routes ===


class TestWalletRoutes:
    def test_info_happy(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            inst = MagicMock()
            inst.address = "0xabc"
            inst.get_balance.return_value = 2.0
            MockWallet.from_env.return_value = inst
            resp = client.get("/wallet/info", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["address"] == "0xabc"
            assert data["chain"] == "ethereum"
            assert data["balance"] == "2.0"

    def test_info_error_path(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            MockWallet.from_env.side_effect = ValueError("no wallet")
            resp = client.get("/wallet/info", headers=AUTH_HEADERS)
            assert resp.status_code == 400
            assert "no wallet" in resp.json()["detail"]

    def test_create_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_WALLET_CREATE_ENDPOINT", raising=False)
        resp = client.post("/wallet/create", headers=AUTH_HEADERS)
        assert resp.status_code == 403

    def test_create_enabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_WALLET_CREATE_ENDPOINT", "true")
        resp = client.post("/wallet/create", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["private_key"].startswith("0x")
        assert data["address"].startswith("0x")
        assert data["chain"] == "ethereum"

    def test_create_error_path(self, monkeypatch):
        monkeypatch.setenv("ENABLE_WALLET_CREATE_ENDPOINT", "true")
        with patch("eth_account.Account.create", side_effect=RuntimeError("boom")):
            resp = client.post("/wallet/create", headers=AUTH_HEADERS)
            assert resp.status_code == 400
            assert "boom" in resp.json()["detail"]

    def test_balance_happy(self):
        with patch("web3_agent_kit.chains.chain.ChainManager") as MockManager:
            mgr = MagicMock()
            w3 = MagicMock()
            w3.eth.get_balance.return_value = 3_000_000_000_000_000_000
            w3.from_wei.return_value = 3.0
            w3.to_checksum_address = lambda a: a
            mgr.get_web3.return_value = w3
            MockManager.return_value = mgr
            resp = client.get("/wallet/balance/0xdead", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["address"] == "0xdead"
            assert data["balance"] == "3.0"
            assert data["chain"] == "ethereum"

    def test_balance_unsupported_chain(self):
        resp = client.get(
            "/wallet/balance/0xdead?chain=bogus", headers=AUTH_HEADERS
        )
        assert resp.status_code == 400
        assert "Unsupported chain" in resp.json()["detail"]

    def test_balance_solana_path(self):
        with patch("web3_agent_kit.chains.chain.ChainManager") as MockManager:
            mgr = MagicMock()
            sol = MagicMock()
            resp_obj = MagicMock()
            resp_obj.value = 5_000_000_000  # 5 SOL in lamports
            sol.get_balance.return_value = resp_obj
            mgr.get_solana.return_value = sol
            MockManager.return_value = mgr
            resp = client.get(
                "/wallet/balance/SoLaddr?chain=solana", headers=AUTH_HEADERS
            )
            assert resp.status_code == 200
            assert resp.json()["balance"] == "5.0"

    def test_balance_error_path(self):
        with patch("web3_agent_kit.chains.chain.ChainManager") as MockManager:
            MockManager.side_effect = RuntimeError("rpc down")
            resp = client.get("/wallet/balance/0xdead", headers=AUTH_HEADERS)
            assert resp.status_code == 400
            assert "rpc down" in resp.json()["detail"]


# === Swap routes ===


class TestSwapRoutes:
    def test_quote_happy(self):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni:
            inst = MagicMock()
            inst.get_quote.return_value = {"token_in": "ETH", "estimated_out": "3500"}
            MockUni.return_value = inst
            resp = client.get(
                "/swap/quote?token_in=ETH&token_out=USDC&amount_in=1.0",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json()["token_in"] == "ETH"

    def test_quote_error(self):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni:
            MockUni.side_effect = ValueError("bad token")
            resp = client.get("/swap/quote", headers=AUTH_HEADERS)
            assert resp.status_code == 400
            assert "bad token" in resp.json()["detail"]

    def test_execute_happy(self):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni, patch(
            "web3_agent_kit.wallet.wallet.Wallet"
        ) as MockWallet:
            inst = MagicMock()
            inst.execute.return_value = {"tx_hash": "0x1", "status": "success"}
            MockUni.return_value = inst
            MockWallet.from_env.return_value = MagicMock()
            resp = client.post(
                "/swap/execute?token_in=ETH&token_out=USDC&amount_in=1.0",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    def test_execute_error(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            MockWallet.from_env.side_effect = RuntimeError("no key")
            resp = client.post("/swap/execute", headers=AUTH_HEADERS)
            assert resp.status_code == 400
            assert "no key" in resp.json()["detail"]

    def test_tokens_happy(self):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni:
            inst = MagicMock()
            inst.ROUTERS = {"ethereum": "0xrouter"}
            inst.supported_chains = ["ethereum", "polygon"]
            MockUni.return_value = inst
            resp = client.get("/swap/tokens", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["chain"] == "ethereum"
            assert data["router"] == "0xrouter"

    def test_tokens_error(self):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni:
            MockUni.side_effect = RuntimeError("fail")
            resp = client.get("/swap/tokens", headers=AUTH_HEADERS)
            assert resp.status_code == 400


# === Portfolio routes ===


class TestPortfolioRoutes:
    def test_portfolio_happy(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            inst = MagicMock()
            inst.address = "0xabc"
            inst.get_balance.return_value = 1.0
            MockWallet.from_env.return_value = inst
            resp = client.get("/portfolio/", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["address"] == "0xabc"
            assert data["native_balance"] == "1.0"

    def test_portfolio_error(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            MockWallet.from_env.side_effect = RuntimeError("nope")
            resp = client.get("/portfolio/", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_portfolio_value_happy(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            inst = MagicMock()
            inst.address = "0xabc"
            inst.get_balance.return_value = 4.2
            MockWallet.from_env.return_value = inst
            resp = client.get("/portfolio/value", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["native_balance"] == "4.2"

    def test_portfolio_value_error(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            MockWallet.from_env.side_effect = RuntimeError("nope")
            resp = client.get("/portfolio/value", headers=AUTH_HEADERS)
            assert resp.status_code == 400


# === Gas routes ===


class TestGasRoutes:
    def test_estimate_happy(self):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            inst = MagicMock()
            inst.estimate.return_value = {"chain": "ethereum", "base_fee": 1}
            MockOpt.return_value = inst
            resp = client.get("/gas/estimate", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["chain"] == "ethereum"

    def test_estimate_error(self):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            MockOpt.side_effect = RuntimeError("gas fail")
            resp = client.get("/gas/estimate", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_recommendation_happy(self):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            inst = MagicMock()
            inst.recommend_timing.return_value = {"action": "wait"}
            MockOpt.return_value = inst
            resp = client.get("/gas/recommendation", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["action"] == "wait"

    def test_recommendation_error(self):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            MockOpt.side_effect = RuntimeError("x")
            resp = client.get("/gas/recommendation", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_batch_happy(self):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            inst = MagicMock()
            inst.batch_estimate.return_value = {"swap": 100}
            MockOpt.return_value = inst
            resp = client.get("/gas/batch", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["swap"] == 100

    def test_batch_error(self):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            MockOpt.side_effect = RuntimeError("x")
            resp = client.get("/gas/batch", headers=AUTH_HEADERS)
            assert resp.status_code == 400


# === Watcher routes ===


class TestWatcherRoutes:
    def test_list_happy(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            inst = MagicMock()
            inst.list_wallets.return_value = [{"address": "0x1"}]
            MockW.return_value = inst
            resp = client.get("/watcher/list", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["wallets"][0]["address"] == "0x1"

    def test_list_error(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            MockW.side_effect = RuntimeError("fail")
            resp = client.get("/watcher/list", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_add_happy(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            inst = MagicMock()
            inst.add_wallet.return_value = {"status": "added"}
            MockW.return_value = inst
            resp = client.post(
                "/watcher/add?address=0x1&label=whale", headers=AUTH_HEADERS
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "added"

    def test_add_missing_required_param(self):
        resp = client.post("/watcher/add", headers=AUTH_HEADERS)
        assert resp.status_code == 422

    def test_add_error(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            MockW.side_effect = RuntimeError("fail")
            resp = client.post("/watcher/add?address=0x1", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_remove_happy(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            inst = MagicMock()
            inst.remove_wallet.return_value = {"status": "removed"}
            MockW.return_value = inst
            resp = client.delete("/watcher/remove?address=0x1", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["status"] == "removed"

    def test_remove_error(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            MockW.side_effect = RuntimeError("fail")
            resp = client.delete("/watcher/remove?address=0x1", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_alerts_happy(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            inst = MagicMock()
            inst.get_alerts.return_value = [{"msg": "hi"}]
            MockW.return_value = inst
            resp = client.get("/watcher/alerts?limit=10", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["alerts"][0]["msg"] == "hi"

    def test_alerts_error(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            MockW.side_effect = RuntimeError("fail")
            resp = client.get("/watcher/alerts", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_check_happy(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            inst = MagicMock()
            inst.check_all.return_value = {"checked": 2}
            MockW.return_value = inst
            resp = client.post("/watcher/check", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["checked"] == 2

    def test_check_error(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            MockW.side_effect = RuntimeError("fail")
            resp = client.post("/watcher/check", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_summary_happy(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            inst = MagicMock()
            inst.get_summary.return_value = {"total": 3}
            MockW.return_value = inst
            resp = client.get("/watcher/summary", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["total"] == 3

    def test_summary_error(self):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockW:
            MockW.side_effect = RuntimeError("fail")
            resp = client.get("/watcher/summary", headers=AUTH_HEADERS)
            assert resp.status_code == 400


# === Approval routes ===


class TestApprovalRoutes:
    def test_scan_happy(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            inst = MagicMock()
            inst.scan.return_value = [{"token": "USDC"}]
            MockM.return_value = inst
            resp = client.get("/approval/scan", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["total"] == 1

    def test_scan_error(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            MockM.side_effect = RuntimeError("fail")
            resp = client.get("/approval/scan", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_risk_happy(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            inst = MagicMock()
            inst.get_summary.return_value = {"total_approvals": 2}
            inst.get_risky.return_value = []
            inst.get_unlimited.return_value = []
            MockM.return_value = inst
            resp = client.get("/approval/risk", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["summary"]["total_approvals"] == 2

    def test_risk_error(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            MockM.side_effect = RuntimeError("fail")
            resp = client.get("/approval/risk", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_revoke_happy(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            inst = MagicMock()
            inst.revoke.return_value = {"status": "revoked"}
            MockM.return_value = inst
            resp = client.post(
                "/approval/revoke?token=0xtok&spender=0xspender",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "revoked"

    def test_revoke_error(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            MockM.side_effect = RuntimeError("fail")
            resp = client.post("/approval/revoke", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_revoke_all_unlimited_happy(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            inst = MagicMock()
            inst.revoke_all_unlimited.return_value = {"revoked": 3}
            MockM.return_value = inst
            resp = client.post("/approval/revoke-all-unlimited", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["revoked"] == 3

    def test_revoke_all_unlimited_error(self):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockM:
            MockM.side_effect = RuntimeError("fail")
            resp = client.post("/approval/revoke-all-unlimited", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_known_protocols_happy(self):
        with patch(
            "web3_agent_kit.wallet.approval.KNOWN_SPENDERS",
            {"Uniswap V2": "0xrouter"},
        ):
            resp = client.get("/approval/known-protocols", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert "Uniswap V2" in resp.json()["protocols"]


# === DCA routes ===


class TestDCARoutes:
    def test_list_happy(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.list_orders.return_value = [{"order_id": "d1"}]
            MockBot.return_value = inst
            resp = client.get("/dca/orders", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["orders"][0]["order_id"] == "d1"

    def test_list_error(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            MockBot.side_effect = RuntimeError("fail")
            resp = client.get("/dca/orders", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_create_happy_unlimited(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.create_order.return_value = {"order_id": "d2", "status": "active"}
            MockBot.return_value = inst
            resp = client.post(
                "/dca/orders?token_in=USDC&token_out=ETH&amount_per_buy=100",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            # total_buys defaults 0 -> None passed to create_order
            _, kwargs = inst.create_order.call_args
            assert kwargs["total_buys"] is None

    def test_create_happy_with_total_buys(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.create_order.return_value = {"order_id": "d3"}
            MockBot.return_value = inst
            resp = client.post(
                "/dca/orders?amount_per_buy=100&total_buys=5", headers=AUTH_HEADERS
            )
            assert resp.status_code == 200
            _, kwargs = inst.create_order.call_args
            assert kwargs["total_buys"] == 5

    def test_create_error(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            MockBot.side_effect = RuntimeError("fail")
            resp = client.post("/dca/orders", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_create_validation_error(self):
        resp = client.post("/dca/orders?total_buys=notanint", headers=AUTH_HEADERS)
        assert resp.status_code == 422

    def test_get_order_happy(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.get_order.return_value = {"order_id": "d1", "status": "active"}
            MockBot.return_value = inst
            resp = client.get("/dca/orders/d1", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_get_order_not_found(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.get_order.side_effect = KeyError("missing")
            MockBot.return_value = inst
            resp = client.get("/dca/orders/nope", headers=AUTH_HEADERS)
            assert resp.status_code == 404

    def test_cancel_happy(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.cancel_order.return_value = {"status": "cancelled"}
            MockBot.return_value = inst
            resp = client.delete("/dca/orders/d1", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_cancel_error(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            MockBot.side_effect = RuntimeError("fail")
            resp = client.delete("/dca/orders/d1", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_pause_happy(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.pause_order.return_value = {"status": "paused"}
            MockBot.return_value = inst
            resp = client.post("/dca/orders/d1/pause", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_pause_error(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            MockBot.side_effect = RuntimeError("fail")
            resp = client.post("/dca/orders/d1/pause", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_resume_happy(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.resume_order.return_value = {"status": "active"}
            MockBot.return_value = inst
            resp = client.post("/dca/orders/d1/resume", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_resume_error(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            MockBot.side_effect = RuntimeError("fail")
            resp = client.post("/dca/orders/d1/resume", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_stats_happy(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            inst = MagicMock()
            inst.get_summary.return_value = {"total_orders": 4}
            MockBot.return_value = inst
            resp = client.get("/dca/stats", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["total_orders"] == 4

    def test_stats_error(self):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            MockBot.side_effect = RuntimeError("fail")
            resp = client.get("/dca/stats", headers=AUTH_HEADERS)
            assert resp.status_code == 400


# === Yield routes ===


class TestYieldRoutes:
    def test_opportunities_happy(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            inst = MagicMock()
            inst.scan_opportunities.return_value = [{"protocol": "Aave"}]
            MockO.return_value = inst
            resp = client.get("/yield/opportunities?min_apy=1.5", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["total"] == 1

    def test_opportunities_error(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            MockO.side_effect = RuntimeError("fail")
            resp = client.get("/yield/opportunities", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_best_happy(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            inst = MagicMock()
            inst.find_best.return_value = {"protocol": "Aave", "apy": 5.0}
            MockO.return_value = inst
            resp = client.get("/yield/best", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["apy"] == 5.0

    def test_best_error(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            MockO.side_effect = RuntimeError("fail")
            resp = client.get("/yield/best", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_compare_happy(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            inst = MagicMock()
            inst.compare_protocols.return_value = [{"protocol": "Aave"}]
            MockO.return_value = inst
            resp = client.get("/yield/compare", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_compare_error(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            MockO.side_effect = RuntimeError("fail")
            resp = client.get("/yield/compare", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_portfolio_happy(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            inst = MagicMock()
            inst.get_portfolio_summary.return_value = {"total_value": 100}
            MockO.return_value = inst
            resp = client.get("/yield/portfolio", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["total_value"] == 100

    def test_portfolio_error(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            MockO.side_effect = RuntimeError("fail")
            resp = client.get("/yield/portfolio", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_compound_happy(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            inst = MagicMock()
            inst.auto_compound_all.return_value = {"compounded": 2}
            MockO.return_value = inst
            resp = client.post("/yield/compound", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["compounded"] == 2

    def test_compound_error(self):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockO:
            MockO.side_effect = RuntimeError("fail")
            resp = client.post("/yield/compound", headers=AUTH_HEADERS)
            assert resp.status_code == 400


# === Bridge routes ===


class TestBridgeRoutes:
    def test_quote_happy(self):
        with patch("web3_agent_kit.bridge.bridge.BridgeAgent") as MockA:
            inst = MagicMock()
            inst.get_routes.return_value = {"routes": []}
            MockA.return_value = inst
            resp = client.get(
                "/bridge/quote?from_chain=ethereum&to_chain=arbitrum&token=USDC&amount=100",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json() == {"routes": []}

    def test_quote_error(self):
        with patch("web3_agent_kit.bridge.bridge.BridgeAgent") as MockA:
            MockA.side_effect = RuntimeError("fail")
            resp = client.get("/bridge/quote", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_execute_happy(self):
        with patch("web3_agent_kit.bridge.bridge.BridgeAgent") as MockA, patch(
            "web3_agent_kit.wallet.wallet.Wallet"
        ) as MockWallet:
            inst = MagicMock()
            inst.transfer.return_value = {"tx_hash": "0xbridge"}
            MockA.return_value = inst
            MockWallet.from_env.return_value = MagicMock()
            resp = client.post("/bridge/execute", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["tx_hash"] == "0xbridge"

    def test_execute_error(self):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            MockWallet.from_env.side_effect = RuntimeError("no key")
            resp = client.post("/bridge/execute", headers=AUTH_HEADERS)
            assert resp.status_code == 400

    def test_chains_happy(self):
        with patch(
            "web3_agent_kit.bridge.bridge.LIFI_CHAIN_IDS", {"ethereum": 1}
        ), patch(
            "web3_agent_kit.bridge.bridge.SOCKET_CHAIN_IDS", {"arbitrum": 42161}
        ):
            resp = client.get("/bridge/chains", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert "ethereum" in data["lifi_chains"]
            assert "arbitrum" in data["socket_chains"]


# === Auth enforcement across route modules ===


class TestAuthEnforcement:
    @pytest.mark.parametrize(
        "path",
        [
            "/wallet/info",
            "/swap/quote",
            "/portfolio/",
            "/gas/estimate",
            "/watcher/list",
            "/approval/scan",
            "/dca/orders",
            "/yield/opportunities",
            "/bridge/chains",
        ],
    )
    def test_missing_key_rejected(self, path):
        resp = client.get(path)
        assert resp.status_code == 401
