"""Tests for the airdrop executor CLI (web3_agent_kit.airdrop.executor.cli).

All browser / playwright / network interactions are mocked so tests are
fully offline. The AirdropTracker is patched with a MagicMock to avoid
touching the filesystem (~/.web3-agent-kit/airdrops.json).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from web3_agent_kit.airdrop.executor import cli as cli_mod
from web3_agent_kit.airdrop.executor.cli import (
    _display_gleam_result,
    _display_zealy_result,
    _make_progress_bar,
    main,
)

runner = CliRunner()


# === main group ===


class TestMainGroup:
    def test_help(self):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Airdrop farming" in result.output

    def test_version(self):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.8.0" in result.output

    def test_farm_group_help(self):
        result = runner.invoke(main, ["farm", "--help"])
        assert result.exit_code == 0
        for sub in ("gleam", "zealy", "status", "export"):
            assert sub in result.output

    def test_browser_group_help(self):
        result = runner.invoke(main, ["browser", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output
        assert "sessions" in result.output


# === helper: _ensure_playwright ===


class TestEnsurePlaywright:
    def test_playwright_available(self):
        mock_browser = SimpleNamespace(HAS_PLAYWRIGHT=True)
        with patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.browser": mock_browser},
        ):
            # should not raise / not exit
            cli_mod._ensure_playwright()

    def test_playwright_missing_exits(self):
        mock_browser = SimpleNamespace(HAS_PLAYWRIGHT=False)
        with patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.browser": mock_browser},
        ):
            try:
                cli_mod._ensure_playwright()
                raised = False
            except SystemExit as e:
                raised = True
                assert e.code == 1
            assert raised


# === farm gleam ===


def _make_gleam_result():
    return SimpleNamespace(
        is_fully_completed=True,
        total_tasks=5,
        completed_tasks=5,
        failed_tasks=0,
        skipped_tasks=0,
        success_rate=1.0,
        elapsed_seconds=12.3,
        errors=[],
    )


class TestFarmGleam:
    def test_farm_gleam_success(self):
        mock_executor = MagicMock()
        mock_executor.complete_all.return_value = _make_gleam_result()
        mock_browser_ctx = MagicMock()
        mock_browser_ctx.__enter__.return_value = MagicMock()
        mock_browser_ctx.__exit__.return_value = False

        fake_browser_mod = SimpleNamespace(
            BrowserConfig=MagicMock(),
            BrowserManager=MagicMock(return_value=mock_browser_ctx),
        )
        fake_gleam_mod = SimpleNamespace(
            GleamExecutor=MagicMock(return_value=mock_executor)
        )

        with patch.object(cli_mod, "_ensure_playwright"), patch.object(
            cli_mod, "AirdropTracker", MagicMock()
        ), patch.dict(
            "sys.modules",
            {
                "web3_agent_kit.airdrop.executor.browser": fake_browser_mod,
                "web3_agent_kit.airdrop.executor.gleam_exec": fake_gleam_mod,
            },
        ):
            result = runner.invoke(main, ["farm", "gleam", "https://gleam.io/abc"])

        assert result.exit_code == 0
        assert "Gleam.io Farming" in result.output
        assert "All tasks completed" in result.output

    def test_farm_gleam_error_exits(self):
        mock_browser_ctx = MagicMock()
        mock_browser_ctx.__enter__.side_effect = RuntimeError("boom")

        fake_browser_mod = SimpleNamespace(
            BrowserConfig=MagicMock(),
            BrowserManager=MagicMock(return_value=mock_browser_ctx),
        )
        fake_gleam_mod = SimpleNamespace(GleamExecutor=MagicMock())

        with patch.object(cli_mod, "_ensure_playwright"), patch.object(
            cli_mod, "AirdropTracker", MagicMock()
        ), patch.dict(
            "sys.modules",
            {
                "web3_agent_kit.airdrop.executor.browser": fake_browser_mod,
                "web3_agent_kit.airdrop.executor.gleam_exec": fake_gleam_mod,
            },
        ):
            result = runner.invoke(
                main, ["farm", "gleam", "https://gleam.io/abc", "--proxy", "http://p"]
            )

        assert result.exit_code == 1
        assert "Error" in result.output


# === farm zealy ===


def _make_zealy_result():
    return SimpleNamespace(
        completed_quests=3,
        total_quests=3,
        xp_earned=300,
        failed_quests=0,
        success_rate=1.0,
        elapsed_seconds=8.0,
        errors=[],
    )


class TestFarmZealy:
    def test_farm_zealy_success(self):
        mock_executor = MagicMock()
        mock_executor.complete_all.return_value = _make_zealy_result()
        mock_browser_ctx = MagicMock()
        mock_browser_ctx.__enter__.return_value = MagicMock()
        mock_browser_ctx.__exit__.return_value = False

        fake_browser_mod = SimpleNamespace(
            BrowserConfig=MagicMock(),
            BrowserManager=MagicMock(return_value=mock_browser_ctx),
        )
        fake_zealy_mod = SimpleNamespace(
            ZealyExecutor=MagicMock(return_value=mock_executor)
        )

        with patch.object(cli_mod, "_ensure_playwright"), patch.object(
            cli_mod, "AirdropTracker", MagicMock()
        ), patch.dict(
            "sys.modules",
            {
                "web3_agent_kit.airdrop.executor.browser": fake_browser_mod,
                "web3_agent_kit.airdrop.executor.zealy_exec": fake_zealy_mod,
            },
        ):
            result = runner.invoke(main, ["farm", "zealy", "https://zealy.io/c/x"])

        assert result.exit_code == 0
        assert "Zealy Quest Farming" in result.output
        assert "All quests completed" in result.output

    def test_farm_zealy_error_exits(self):
        mock_browser_ctx = MagicMock()
        mock_browser_ctx.__enter__.side_effect = RuntimeError("boom")

        fake_browser_mod = SimpleNamespace(
            BrowserConfig=MagicMock(),
            BrowserManager=MagicMock(return_value=mock_browser_ctx),
        )
        fake_zealy_mod = SimpleNamespace(ZealyExecutor=MagicMock())

        with patch.object(cli_mod, "_ensure_playwright"), patch.object(
            cli_mod, "AirdropTracker", MagicMock()
        ), patch.dict(
            "sys.modules",
            {
                "web3_agent_kit.airdrop.executor.browser": fake_browser_mod,
                "web3_agent_kit.airdrop.executor.zealy_exec": fake_zealy_mod,
            },
        ):
            result = runner.invoke(main, ["farm", "zealy", "https://zealy.io/c/x"])

        assert result.exit_code == 1
        assert "Error" in result.output


# === farm status ===


def _make_campaign(**kw):
    defaults = dict(
        name="Test Campaign",
        platform="gleam",
        progress=0.5,
        earned_points=50.0,
        total_points=100.0,
        url="https://gleam.io/abc",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _make_summary(campaigns=0, active=0, rewards=None):
    return SimpleNamespace(
        total_campaigns=campaigns,
        active_campaigns=active,
        completed_tasks=0,
        total_points=0.0,
        total_rewards=rewards or [],
    )


class TestFarmStatus:
    def test_status_empty(self):
        tracker = MagicMock()
        tracker.list_campaigns.return_value = []
        tracker.get_summary.return_value = _make_summary()
        with patch.object(cli_mod, "AirdropTracker", return_value=tracker):
            result = runner.invoke(main, ["farm", "status"])
        assert result.exit_code == 0
        assert "No tracked campaigns" in result.output

    def test_status_with_campaigns_and_rewards(self):
        tracker = MagicMock()
        tracker.list_campaigns.return_value = [_make_campaign()]
        reward = SimpleNamespace(
            claimed=True,
            campaign_name="Test Campaign",
            points=50,
            tokens=1.5,
            token_symbol="ABC",
        )
        tracker.get_summary.return_value = _make_summary(
            campaigns=1, active=1, rewards=[reward]
        )
        with patch.object(cli_mod, "AirdropTracker", return_value=tracker):
            result = runner.invoke(main, ["farm", "status", "--all"])
        assert result.exit_code == 0
        assert "Test Campaign" in result.output
        assert "Rewards" in result.output

    def test_status_platform_filter(self):
        tracker = MagicMock()
        tracker.list_campaigns.return_value = [_make_campaign(url="")]
        tracker.get_summary.return_value = _make_summary(campaigns=1, active=1)
        with patch.object(cli_mod, "AirdropTracker", return_value=tracker):
            result = runner.invoke(
                main, ["farm", "status", "--platform", "gleam"]
            )
        assert result.exit_code == 0
        tracker.list_campaigns.assert_called_once()


# === farm export ===


class TestFarmExport:
    def test_export_json(self):
        tracker = MagicMock()
        with patch.object(cli_mod, "AirdropTracker", return_value=tracker):
            result = runner.invoke(
                main, ["farm", "export", "--format", "json", "-o", "out.json"]
            )
        assert result.exit_code == 0
        assert "Exported to out.json" in result.output
        tracker.export_json.assert_called_once_with("out.json")

    def test_export_csv_default_name(self):
        tracker = MagicMock()
        with patch.object(cli_mod, "AirdropTracker", return_value=tracker):
            result = runner.invoke(main, ["farm", "export"])
        assert result.exit_code == 0
        assert "Exported to" in result.output
        tracker.export_csv.assert_called_once()


# === browser login ===


class TestBrowserLogin:
    def _run_login(self, platform, exec_attr, success):
        mock_browser = MagicMock()
        mock_executor = MagicMock()
        mock_executor.interactive_login.return_value = success
        fake_social = SimpleNamespace(**{exec_attr: MagicMock(return_value=mock_executor)})
        with patch.object(cli_mod, "_ensure_playwright"), patch.object(
            cli_mod, "_get_browser", return_value=mock_browser
        ), patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.social_exec": fake_social},
        ):
            result = runner.invoke(main, ["browser", "login", platform])
        mock_browser.close.assert_called_once()
        return result

    def test_twitter_login_success(self):
        result = self._run_login("twitter", "TwitterExecutor", True)
        assert result.exit_code == 0
        assert "Twitter login saved" in result.output

    def test_twitter_login_failed(self):
        result = self._run_login("twitter", "TwitterExecutor", False)
        assert result.exit_code == 0
        assert "Twitter login failed" in result.output

    def test_discord_login_success(self):
        result = self._run_login("discord", "DiscordExecutor", True)
        assert result.exit_code == 0
        assert "Discord login saved" in result.output

    def test_telegram_login_success(self):
        result = self._run_login("telegram", "TelegramExecutor", True)
        assert result.exit_code == 0
        assert "Telegram login saved" in result.output

    def test_invalid_platform_rejected(self):
        with patch.object(cli_mod, "_ensure_playwright"):
            result = runner.invoke(main, ["browser", "login", "myspace"])
        assert result.exit_code != 0


# === browser sessions ===


class TestBrowserSessions:
    def test_sessions_none(self, tmp_path):
        missing = tmp_path / "nope"
        fake_browser = SimpleNamespace(SESSIONS_DIR=missing)
        with patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.browser": fake_browser},
        ):
            result = runner.invoke(main, ["browser", "sessions"])
        assert result.exit_code == 0
        assert "No saved sessions" in result.output

    def test_sessions_listed(self, tmp_path):
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        sess = sessions / "twitter"
        sess.mkdir()
        (sess / "cookies.json").write_text('{"a": 1}')
        # a platform subdir with cookies
        sub = sess / "sub"
        sub.mkdir()
        (sub / "cookies.json").write_text("{}")
        # a session without cookies
        empty = sessions / "empty"
        empty.mkdir()

        fake_browser = SimpleNamespace(SESSIONS_DIR=sessions)
        with patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.browser": fake_browser},
        ):
            result = runner.invoke(main, ["browser", "sessions"])
        assert result.exit_code == 0
        assert "Saved Sessions" in result.output
        assert "twitter" in result.output
        assert "empty" in result.output


# === _get_browser ===


class TestGetBrowser:
    def test_get_browser_default_config(self):
        fake_browser = SimpleNamespace(
            BrowserConfig=MagicMock(return_value="cfg"),
            BrowserManager=MagicMock(return_value="mgr"),
        )
        with patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.browser": fake_browser},
        ):
            result = cli_mod._get_browser()
        assert result == "mgr"
        fake_browser.BrowserManager.assert_called_once_with("cfg")

    def test_get_browser_explicit_config(self):
        fake_browser = SimpleNamespace(
            BrowserConfig=MagicMock(),
            BrowserManager=MagicMock(return_value="mgr"),
        )
        with patch.dict(
            "sys.modules",
            {"web3_agent_kit.airdrop.executor.browser": fake_browser},
        ):
            result = cli_mod._get_browser(config="mycfg")
        assert result == "mgr"
        fake_browser.BrowserManager.assert_called_once_with("mycfg")
        fake_browser.BrowserConfig.assert_not_called()


# === display helpers ===


class TestDisplayHelpers:
    def test_display_gleam_fully_completed(self):
        # Just ensure no exception; helpers use click.echo which needs no context here.
        _display_gleam_result(_make_gleam_result())

    def test_display_gleam_with_issues(self):
        result = SimpleNamespace(
            is_fully_completed=False,
            total_tasks=5,
            completed_tasks=3,
            failed_tasks=1,
            skipped_tasks=1,
            success_rate=0.6,
            elapsed_seconds=5.0,
            errors=["err1", "err2"],
        )
        _display_gleam_result(result)

    def test_display_zealy_fully_completed(self):
        _display_zealy_result(_make_zealy_result())

    def test_display_zealy_with_issues(self):
        result = SimpleNamespace(
            completed_quests=1,
            total_quests=3,
            xp_earned=100,
            failed_quests=2,
            success_rate=0.33,
            elapsed_seconds=4.0,
            errors=["boom"],
        )
        _display_zealy_result(result)

    def test_make_progress_bar(self):
        assert _make_progress_bar(0.0).count("█") == 0
        assert _make_progress_bar(1.0).count("█") == 20
        # clamps above 1.0
        assert _make_progress_bar(2.0).count("█") == 20
        half = _make_progress_bar(0.5, width=10)
        assert half.count("█") == 5
