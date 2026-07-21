"""Tests for the REST API endpoints."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Try to import FastAPI test client
try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

TEST_API_KEY = "test-key-123"

if FASTAPI_AVAILABLE:
    # The API server requires WEB3_API_KEY to be set before the app/lifespan
    # will even start (fail-closed startup guard). Set it once at import
    # time so the module-level TestClient/app work in tests; individual
    # tests use monkeypatch to exercise auth failure/success paths.
    os.environ.setdefault("WEB3_API_KEY", TEST_API_KEY)

    from web3_agent_kit.api import app

    client = TestClient(app)
    AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def mock_env_api_key(monkeypatch):
    """Set API key for testing."""
    monkeypatch.setenv("WEB3_API_KEY", TEST_API_KEY)


@pytest.fixture
def mock_no_api_key(monkeypatch):
    """Ensure the expected test API key is set (kept for readability in
    existing tests — auth is always required now, so this fixture just
    guarantees a known key is configured and supplies auth headers via
    AUTH_HEADERS)."""
    monkeypatch.setenv("WEB3_API_KEY", TEST_API_KEY)


# === System Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestSystemEndpoints:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_requires_no_auth(self):
        """Health check must work with no X-API-Key header at all."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_root(self):
        resp = client.get("/", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "endpoints" in data
        assert "wallet" in data["endpoints"]
        assert "swap" in data["endpoints"]

    def test_docs_available(self):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_available(self):
        resp = client.get("/redoc")
        assert resp.status_code == 200


# === API Key Auth ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestAPIKeyAuth:
    def test_no_key_configured_denies_access(self, mock_no_api_key, monkeypatch):
        """When WEB3_API_KEY is unset, protected endpoints must fail closed (401),
        never fall open."""
        monkeypatch.delenv("WEB3_API_KEY", raising=False)
        resp = client.get("/wallet/info", headers=AUTH_HEADERS)
        assert resp.status_code == 401

    def test_health_open_even_without_key(self, monkeypatch):
        """Health check remains available even with no WEB3_API_KEY set."""
        monkeypatch.delenv("WEB3_API_KEY", raising=False)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_wrong_key_rejected(self, mock_env_api_key):
        """Wrong API key should be rejected with 401 on auth-protected endpoints."""
        resp = client.get("/wallet/info", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_missing_key_rejected(self, mock_env_api_key):
        """Missing API key should be rejected with 401 on auth-protected endpoints."""
        resp = client.get("/wallet/info")
        assert resp.status_code == 401

    def test_correct_key_passes_auth(self, mock_env_api_key):
        """Correct API key should pass the auth dependency (may still 400 on
        downstream wallet errors, but must not be 401)."""
        resp = client.get("/wallet/info", headers=AUTH_HEADERS)
        assert resp.status_code != 401

    # --- Task 1.5: explicit proof for a sensitive on-chain-executing endpoint ---

    def test_swap_execute_without_key_returns_401(self, mock_env_api_key):
        """POST /swap/execute without X-API-Key must be rejected (401), even
        though it would otherwise execute a real on-chain swap."""
        resp = client.post(
            "/swap/execute?token_in=ETH&token_out=USDC&amount_in=1.0"
        )
        assert resp.status_code == 401

    def test_swap_execute_with_key_passes_auth(self, mock_env_api_key):
        """POST /swap/execute with the correct X-API-Key passes auth (the
        actual swap execution is mocked so no real transaction happens)."""
        with patch("web3_agent_kit.defi.Uniswap") as MockUni, patch(
            "web3_agent_kit.wallet.wallet.Wallet"
        ) as MockWallet:
            mock_uni_instance = MagicMock()
            mock_uni_instance.execute.return_value = {
                "tx_hash": "0xdeadbeef",
                "status": "success",
            }
            MockUni.return_value = mock_uni_instance
            MockWallet.from_env.return_value = MagicMock()

            resp = client.post(
                "/swap/execute?token_in=ETH&token_out=USDC&amount_in=1.0",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200


# === Wallet Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestWalletEndpoints:
    def test_wallet_info(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.wallet.Wallet") as MockWallet:
            mock_instance = MagicMock()
            mock_instance.address = "0x721e885BE237Ef193807d7a912C201c6a53dA522"
            mock_instance.get_balance.return_value = 1.5
            MockWallet.from_env.return_value = mock_instance
            resp = client.get("/wallet/info", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["chain"] == "ethereum"

    def test_wallet_balance(self, mock_no_api_key):
        with patch("web3_agent_kit.chains.chain.ChainManager") as MockManager:
            mock_manager_instance = MagicMock()
            mock_w3 = MagicMock()
            mock_w3.eth.get_balance.return_value = 1500000000000000000
            mock_w3.from_wei.return_value = 1.5
            mock_w3.to_checksum_address = lambda a: a
            mock_manager_instance.get_web3.return_value = mock_w3
            MockManager.return_value = mock_manager_instance

            resp = client.get(
                "/wallet/balance/0x721e885BE237Ef193807d7a912C201c6a53dA522",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["address"] == "0x721e885BE237Ef193807d7a912C201c6a53dA522"

    def test_wallet_balance_uses_requested_address(self, mock_no_api_key):
        """Regression test for Task 6: different addresses must yield the
        balance query for THAT address, not a fixed env-wallet balance."""
        addr_a = "0x1111111111111111111111111111111111111111"
        addr_b = "0x2222222222222222222222222222222222222222"

        def fake_get_balance(addr):
            return {
                addr_a: 1_000_000_000_000_000_000,  # 1 ETH
                addr_b: 2_000_000_000_000_000_000,  # 2 ETH
            }[addr]

        with patch("web3_agent_kit.chains.chain.ChainManager") as MockManager:
            mock_manager_instance = MagicMock()
            mock_w3 = MagicMock()
            mock_w3.eth.get_balance.side_effect = fake_get_balance
            mock_w3.from_wei.side_effect = lambda wei, unit: wei / 1e18
            mock_w3.to_checksum_address = lambda a: a
            mock_manager_instance.get_web3.return_value = mock_w3
            MockManager.return_value = mock_manager_instance

            resp_a = client.get(f"/wallet/balance/{addr_a}", headers=AUTH_HEADERS)
            resp_b = client.get(f"/wallet/balance/{addr_b}", headers=AUTH_HEADERS)

            assert resp_a.status_code == 200
            assert resp_b.status_code == 200
            assert resp_a.json()["balance"] != resp_b.json()["balance"]
            assert resp_a.json()["address"] == addr_a
            assert resp_b.json()["address"] == addr_b

    def test_create_wallet_disabled_by_default(self, mock_no_api_key, monkeypatch):
        """Task 3 defense-in-depth: /wallet/create is disabled unless
        ENABLE_WALLET_CREATE_ENDPOINT=true is explicitly set."""
        monkeypatch.delenv("ENABLE_WALLET_CREATE_ENDPOINT", raising=False)
        resp = client.post("/wallet/create", headers=AUTH_HEADERS)
        assert resp.status_code == 403

    def test_create_wallet_enabled_returns_warning(self, mock_no_api_key, monkeypatch):
        monkeypatch.setenv("ENABLE_WALLET_CREATE_ENDPOINT", "true")
        resp = client.post("/wallet/create", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "private_key" in data
        assert "HTTPS" in data["warning"]
        assert "never log" in data["warning"].lower()

    def test_create_wallet_requires_auth(self, mock_env_api_key, monkeypatch):
        monkeypatch.setenv("ENABLE_WALLET_CREATE_ENDPOINT", "true")
        resp = client.post("/wallet/create")
        assert resp.status_code == 401


# === Swap Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestSwapEndpoints:
    def test_swap_quote(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni:
            mock_instance = MagicMock()
            mock_instance.get_quote.return_value = {
                "token_in": "ETH",
                "token_out": "USDC",
                "amount_in": 1.0,
                "estimated_out": 3500.0,
                "price_impact": 0.01,
                "route": ["ETH", "USDC"],
            }
            MockUni.return_value = mock_instance
            resp = client.get(
                "/swap/quote?token_in=ETH&token_out=USDC&amount_in=1.0",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["token_in"] == "ETH"

    def test_swap_tokens(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.Uniswap") as MockUni:
            mock_instance = MagicMock()
            mock_instance.ROUTERS = {"ethereum": "0x..."}
            mock_instance.supported_chains = ["ethereum", "polygon"]
            MockUni.return_value = mock_instance
            resp = client.get("/swap/tokens", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === Gas Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestGasEndpoints:
    def test_gas_estimate(self, mock_no_api_key):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.estimate.return_value = {
                "chain": "ethereum",
                "base_fee": 30000000000,
                "low": {"max_fee": 31000000000},
                "medium": {"max_fee": 35000000000},
                "high": {"max_fee": 45000000000},
                "recommendation": "execute_now",
            }
            MockOpt.return_value = mock_instance
            resp = client.get("/gas/estimate", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_gas_recommendation(self, mock_no_api_key):
        with patch("web3_agent_kit.gas.optimizer.GasOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.recommend_timing.return_value = {
                "action": "wait",
                "reason": "Gas expected to drop 20% in 5 minutes",
            }
            MockOpt.return_value = mock_instance
            resp = client.get("/gas/recommendation", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === Watcher Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestWatcherEndpoints:
    def test_list_watched(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockWatcher:
            mock_instance = MagicMock()
            mock_instance.list_wallets.return_value = [
                {"address": "0x123", "label": "whale", "tags": ["whale"]}
            ]
            MockWatcher.return_value = mock_instance
            resp = client.get("/watcher/list", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_add_watched(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockWatcher:
            mock_instance = MagicMock()
            mock_instance.add_wallet.return_value = {"status": "added", "address": "0x123"}
            MockWatcher.return_value = mock_instance
            resp = client.post(
                "/watcher/add?address=0x123&chain=ethereum&label=test",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200

    def test_get_alerts(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockWatcher:
            mock_instance = MagicMock()
            mock_instance.get_alerts.return_value = []
            MockWatcher.return_value = mock_instance
            resp = client.get("/watcher/alerts", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_check_wallets(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.watcher.WalletWatcher") as MockWatcher:
            mock_instance = MagicMock()
            mock_instance.check_all.return_value = {"checked": 0, "alerts": 0}
            MockWatcher.return_value = mock_instance
            resp = client.post("/watcher/check", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === Approval Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestApprovalEndpoints:
    def test_scan_approvals(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.scan.return_value = [
                {
                    "token": "USDC",
                    "spender": "Uniswap V3",
                    "amount": "unlimited",
                    "risk": "low",
                }
            ]
            MockMgr.return_value = mock_instance
            resp = client.get("/approval/scan", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_risk_report(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.approval.ApprovalManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.get_summary.return_value = {
                "total_approvals": 5,
                "unlimited": 2,
            }
            mock_instance.get_risky.return_value = []
            mock_instance.get_unlimited.return_value = []
            MockMgr.return_value = mock_instance
            resp = client.get("/approval/risk", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_known_protocols(self, mock_no_api_key):
        with patch("web3_agent_kit.wallet.approval.KNOWN_SPENDERS", {"Uniswap V2": "0x..."}):
            resp = client.get("/approval/known-protocols", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === DCA Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestDCAEndpoints:
    def test_list_orders(self, mock_no_api_key):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            mock_instance = MagicMock()
            mock_instance.list_orders.return_value = []
            MockBot.return_value = mock_instance
            resp = client.get("/dca/orders", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_create_order(self, mock_no_api_key):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            mock_instance = MagicMock()
            mock_instance.create_order.return_value = {
                "order_id": "dca_123",
                "status": "active",
            }
            MockBot.return_value = mock_instance
            resp = client.post(
                "/dca/orders?token_in=USDC&token_out=ETH&amount_per_buy=100&frequency=daily",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200

    def test_get_order(self, mock_no_api_key):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            mock_instance = MagicMock()
            mock_instance.get_order.return_value = {
                "order_id": "dca_123",
                "status": "active",
            }
            MockBot.return_value = mock_instance
            resp = client.get("/dca/orders/dca_123", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_cancel_order(self, mock_no_api_key):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            mock_instance = MagicMock()
            mock_instance.cancel_order.return_value = {"status": "cancelled"}
            MockBot.return_value = mock_instance
            resp = client.delete("/dca/orders/dca_123", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_stats(self, mock_no_api_key):
        with patch("web3_agent_kit.trading.dca.DCABot") as MockBot:
            mock_instance = MagicMock()
            mock_instance.get_summary.return_value = {"total_orders": 0}
            MockBot.return_value = mock_instance
            resp = client.get("/dca/stats", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === Yield Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestYieldEndpoints:
    def test_scan_opportunities(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.scan_opportunities.return_value = [
                {
                    "protocol": "Aave V3",
                    "apy": 4.5,
                    "tvl": 1000000000,
                    "category": "lending",
                }
            ]
            MockOpt.return_value = mock_instance
            resp = client.get("/yield/opportunities", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_best_yield(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.find_best.return_value = {
                "protocol": "Aave V3",
                "apy": 4.5,
            }
            MockOpt.return_value = mock_instance
            resp = client.get("/yield/best", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_compare_protocols(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.compare_protocols.return_value = []
            MockOpt.return_value = mock_instance
            resp = client.get("/yield/compare", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_yield_portfolio(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.get_portfolio_summary.return_value = {"total_value": 0}
            MockOpt.return_value = mock_instance
            resp = client.get("/yield/portfolio", headers=AUTH_HEADERS)
            assert resp.status_code == 200

    def test_auto_compound(self, mock_no_api_key):
        with patch("web3_agent_kit.defi.yield_optimizer.YieldOptimizer") as MockOpt:
            mock_instance = MagicMock()
            mock_instance.auto_compound_all.return_value = {"compounded": 0}
            MockOpt.return_value = mock_instance
            resp = client.post("/yield/compound", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === Bridge Endpoints ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestBridgeEndpoints:
    def test_bridge_quote(self, mock_no_api_key):
        with patch("web3_agent_kit.bridge.bridge.BridgeAgent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.get_routes.return_value = {
                "from_chain": "ethereum",
                "to_chain": "arbitrum",
                "routes": [],
            }
            MockAgent.return_value = mock_instance
            resp = client.get(
                "/bridge/quote?from_chain=ethereum&to_chain=arbitrum&token=USDC&amount=100",
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200

    def test_bridge_chains(self, mock_no_api_key):
        with patch("web3_agent_kit.bridge.bridge.LIFI_CHAIN_IDS", {"ethereum": 1}), patch(
            "web3_agent_kit.bridge.bridge.SOCKET_CHAIN_IDS", {"arbitrum": 42161}
        ):
            resp = client.get("/bridge/chains", headers=AUTH_HEADERS)
            assert resp.status_code == 200


# === CORS ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestCORSConfig:
    def test_cors_defaults_to_empty_allowlist(self, monkeypatch):
        """Task 5: with no CORS_ALLOWED_ORIGINS set, the origin allowlist
        must default to empty (no cross-origin access), not '*'."""
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        from web3_agent_kit.api import _build_cors_config

        origins, allow_credentials = _build_cors_config()
        assert origins == []
        assert "*" not in origins

    def test_cors_rejects_wildcard_with_credentials(self, monkeypatch):
        """Setting CORS_ALLOWED_ORIGINS to '*' with credentials enabled
        must raise at startup — never silently allow the unsafe combo."""
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
        from web3_agent_kit.api import _build_cors_config

        with pytest.raises(RuntimeError):
            _build_cors_config()

    def test_cors_accepts_explicit_origin_list(self, monkeypatch):
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS", "https://app.example.com,https://admin.example.com"
        )
        from web3_agent_kit.api import _build_cors_config

        origins, allow_credentials = _build_cors_config()
        assert origins == ["https://app.example.com", "https://admin.example.com"]


# === Startup fail-closed guard ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestStartupGuard:
    def test_lifespan_raises_without_api_key(self, monkeypatch):
        """Task 1.2: the server must refuse to start at all if WEB3_API_KEY
        is not set, rather than silently defaulting to open access."""
        monkeypatch.delenv("WEB3_API_KEY", raising=False)
        from web3_agent_kit.api import lifespan, app as _app

        async def _run():
            async with lifespan(_app):
                pass

        import asyncio

        with pytest.raises(RuntimeError, match="WEB3_API_KEY"):
            asyncio.run(_run())

    def test_lifespan_succeeds_with_api_key(self, monkeypatch):
        monkeypatch.setenv("WEB3_API_KEY", TEST_API_KEY)
        from web3_agent_kit.api import lifespan, app as _app

        async def _run():
            async with lifespan(_app):
                pass

        import asyncio

        asyncio.run(_run())  # should not raise


# === OpenAPI Schema ===


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestOpenAPISchema:
    def test_schema_generated(self):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/health" in schema["paths"]
        assert "/wallet/info" in schema["paths"]
        assert "/swap/quote" in schema["paths"]
        assert "/gas/estimate" in schema["paths"]
        assert "/watcher/list" in schema["paths"]
        assert "/approval/scan" in schema["paths"]
        assert "/dca/orders" in schema["paths"]
        assert "/yield/opportunities" in schema["paths"]
        assert "/bridge/quote" in schema["paths"]

    def test_schema_version(self):
        resp = client.get("/openapi.json")
        schema = resp.json()
        assert "info" in schema
        assert "version" in schema["info"]
