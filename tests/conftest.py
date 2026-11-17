"""Shared test environment.

The API and integration suites build wallets from ``PRIVATE_KEY`` and the API
needs ``WEB3_API_KEY``. Setting both here keeps the suite hermetic: it no longer
passes or fails depending on what the developer happens to have exported.
"""

import pytest

TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_API_KEY = "test-key-123"


@pytest.fixture(autouse=True)
def _isolated_dca_storage(tmp_path, monkeypatch):
    """Point the DCA order store at a temp file.

    ``DCABot.__init__`` loads the store before a test can override the instance
    attribute, so a developer's ``~/.web3-agent-kit/dca_orders.json`` used to leak
    into assertions.
    """
    from web3_agent_kit.trading.dca import DCABot

    monkeypatch.setattr(DCABot, "STORAGE_PATH", str(tmp_path / "dca_orders.json"))


@pytest.fixture(autouse=True)
def _deterministic_env(monkeypatch):
    monkeypatch.setenv("PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setenv("WEB3_API_KEY", TEST_API_KEY)
    monkeypatch.delenv("WEB3_AUTO_AUTHORIZE", raising=False)
    monkeypatch.delenv("WEB3_ALLOWED_CHAINS", raising=False)
    monkeypatch.delenv("WEB3_ALLOWED_CONTRACTS", raising=False)
