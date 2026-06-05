"""Tests for airdrop executor layer — browser automation."""
import pytest
from unittest.mock import MagicMock

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

requires_playwright = pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed")

from src.airdrop.executor.browser import BrowserManager, BrowserConfig
from src.airdrop.executor.gleam_exec import GleamExecutor, GleamResult, GleamTaskEntry
from src.airdrop.executor.social_exec import (
    TwitterExecutor, DiscordExecutor, TelegramExecutor, SocialExecutorConfig,
)
from src.airdrop.executor.zealy_exec import ZealyExecutor, ZealyResult


# ─── BrowserConfig ────────────────────────────────────────────

class TestBrowserConfig:
    def test_defaults(self):
        cfg = BrowserConfig()
        assert cfg.headless is True
        assert cfg.proxy is None
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 2.0

    def test_custom(self):
        cfg = BrowserConfig(headless=False, proxy="http://localhost:8080", slow_mo=100)
        assert cfg.headless is False
        assert cfg.proxy == "http://localhost:8080"
        assert cfg.slow_mo == 100

    def test_sessions_dir_default(self):
        cfg = BrowserConfig()
        assert "web3-agent-kit" in str(cfg.sessions_dir)


# ─── BrowserManager ──────────────────────────────────────────

@requires_playwright
class TestBrowserManager:
    def test_init(self):
        mgr = BrowserManager()
        assert mgr.config is not None
        assert mgr._browser is None

    def test_init_with_config(self):
        cfg = BrowserConfig(headless=False)
        mgr = BrowserManager(config=cfg)
        assert mgr.config.headless is False

    def test_is_launched_false(self):
        mgr = BrowserManager()
        assert mgr.is_launched is False

    def test_session_path(self):
        mgr = BrowserManager()
        path = mgr.get_session_path("twitter")
        assert "twitter" in str(path)

    def test_has_launch(self):
        mgr = BrowserManager()
        assert hasattr(mgr, "launch")
        assert callable(mgr.launch)

    def test_has_navigate(self):
        mgr = BrowserManager()
        assert hasattr(mgr, "navigate_with_retry")
        assert hasattr(mgr, "click_with_retry")


# ─── GleamTaskEntry ──────────────────────────────────────────

class TestGleamTaskEntry:
    def test_create(self):
        task = GleamTaskEntry(
            entry_id="entry_0",
            task_type="twitter_follow",
            title="Follow @username",
            points=10,
            is_completed=False,
        )
        assert task.entry_id == "entry_0"
        assert task.title == "Follow @username"
        assert task.points == 10
        assert task.is_completed is False

    def test_defaults(self):
        task = GleamTaskEntry(entry_id="e1", task_type="visit_url", title="Visit")
        assert task.is_completed is False
        assert task.points == 1
        assert task.url == ""

    def test_to_airdrop_task(self):
        task = GleamTaskEntry(entry_id="e1", task_type="twitter_follow", title="Follow @x")
        at = task.to_airdrop_task("campaign_123")
        assert at.title == "Follow @x"


# ─── GleamResult ─────────────────────────────────────────────

class TestGleamResult:
    def test_create(self):
        result = GleamResult(
            campaign_url="https://gleam.io/contest/abc",
            campaign_id="abc",
            total_tasks=5,
            completed_tasks=3,
            failed_tasks=2,
        )
        assert result.total_tasks == 5
        assert result.completed_tasks == 3
        assert result.failed_tasks == 2

    def test_success_rate(self):
        result = GleamResult(
            campaign_url="x", campaign_id="x",
            total_tasks=10, completed_tasks=8, failed_tasks=2,
        )
        assert abs(result.success_rate - 0.8) < 0.01

    def test_success_rate_zero(self):
        result = GleamResult(campaign_url="x", campaign_id="x")
        assert result.success_rate == 0.0

    def test_is_fully_completed(self):
        result = GleamResult(
            campaign_url="x", campaign_id="x",
            total_tasks=5, completed_tasks=5, failed_tasks=0,
        )
        assert result.is_fully_completed is True

    def test_is_not_fully_completed(self):
        result = GleamResult(
            campaign_url="x", campaign_id="x",
            total_tasks=5, completed_tasks=3, failed_tasks=2,
        )
        assert result.is_fully_completed is False


# ─── GleamExecutor ───────────────────────────────────────────

class TestGleamExecutor:
    def test_init(self):
        browser = MagicMock()
        exec = GleamExecutor(browser_manager=browser)
        assert exec.browser is browser

    def test_has_methods(self):
        browser = MagicMock()
        exec = GleamExecutor(browser_manager=browser)
        assert hasattr(exec, "visit")
        assert hasattr(exec, "get_tasks")
        assert hasattr(exec, "complete_task")
        assert hasattr(exec, "complete_all")


# ─── SocialExecutorConfig ────────────────────────────────────

class TestSocialExecutorConfig:
    def test_defaults(self):
        cfg = SocialExecutorConfig()
        assert cfg.action_delay_min == 2.0
        assert cfg.action_delay_max == 5.0
        assert cfg.max_retries == 3
        assert cfg.save_cookies is True

    def test_custom(self):
        cfg = SocialExecutorConfig(action_delay_min=1.0, max_retries=5)
        assert cfg.action_delay_min == 1.0
        assert cfg.max_retries == 5


# ─── TwitterExecutor ─────────────────────────────────────────

class TestTwitterExecutor:
    def test_init(self):
        browser = MagicMock()
        exec = TwitterExecutor(browser_manager=browser)
        assert exec.browser is browser

    def test_init_with_config(self):
        browser = MagicMock()
        cfg = SocialExecutorConfig(action_delay_min=1.0)
        exec = TwitterExecutor(browser_manager=browser, config=cfg)
        assert exec.config.action_delay_min == 1.0

    def test_has_methods(self):
        browser = MagicMock()
        exec = TwitterExecutor(browser_manager=browser)
        assert hasattr(exec, "follow")
        assert hasattr(exec, "retweet")
        assert hasattr(exec, "like")


# ─── DiscordExecutor ─────────────────────────────────────────

class TestDiscordExecutor:
    def test_init(self):
        browser = MagicMock()
        exec = DiscordExecutor(browser_manager=browser)
        assert exec.browser is browser


# ─── TelegramExecutor ────────────────────────────────────────

class TestTelegramExecutor:
    def test_init(self):
        browser = MagicMock()
        exec = TelegramExecutor(browser_manager=browser)
        assert exec.browser is browser


# ─── ZealyResult ─────────────────────────────────────────────

class TestZealyResult:
    def test_create(self):
        result = ZealyResult(
            community="TestProject",
            community_url="https://zealy.io/c/test",
            total_quests=10,
            completed_quests=7,
            failed_quests=3,
            xp_earned=500,
        )
        assert result.total_quests == 10
        assert result.completed_quests == 7
        assert result.xp_earned == 500

    def test_success_rate(self):
        result = ZealyResult(
            community="X", community_url="x",
            total_quests=4, completed_quests=3, failed_quests=1, xp_earned=100,
        )
        assert abs(result.success_rate - 0.75) < 0.01

    def test_success_rate_zero(self):
        result = ZealyResult(community="X", community_url="x")
        assert result.success_rate == 0.0


# ─── ZealyExecutor ───────────────────────────────────────────

class TestZealyExecutor:
    def test_init(self):
        browser = MagicMock()
        exec = ZealyExecutor(browser_manager=browser)
        assert exec.browser is browser

    def test_has_methods(self):
        browser = MagicMock()
        exec = ZealyExecutor(browser_manager=browser)
        assert hasattr(exec, "visit")
        assert hasattr(exec, "get_quests")
        assert hasattr(exec, "complete_quest")
