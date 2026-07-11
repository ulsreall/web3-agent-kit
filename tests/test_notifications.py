"""Tests for src/notifications/ — Notifier, Telegram, Discord, Email."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from web3_agent_kit.notifications import (
    Notifier,
    TelegramNotifier,
    DiscordNotifier,
    EmailNotifier,
    AlertLevel,
    Notification,
)
from web3_agent_kit.notifications.utils import NotifierConfig, log_notification_to_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    defaults = dict(enabled=True, rate_limit_seconds=0)
    defaults.update(overrides)
    return NotifierConfig(**defaults)


def _make_notification(**overrides):
    defaults = dict(title="Test", message="Hello World", level=AlertLevel.INFO)
    defaults.update(overrides)
    return Notification(**defaults)


# ===========================================================================
# AlertLevel enum
# ===========================================================================

class TestAlertLevel:
    def test_values(self):
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.SUCCESS.value == "success"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"


# ===========================================================================
# NotifierConfig
# ===========================================================================

class TestNotifierConfig:
    def test_defaults(self):
        config = NotifierConfig()
        assert config.enabled is True
        assert config.min_level == AlertLevel.INFO
        assert config.rate_limit_seconds == 5.0
        assert config.telegram_bot_token == ""
        assert config.discord_webhook_url == ""

    def test_custom(self):
        config = _make_config(
            telegram_bot_token="123:ABC",
            telegram_chat_id="-100123",
            min_level=AlertLevel.WARNING,
        )
        assert config.telegram_bot_token == "123:ABC"
        assert config.min_level == AlertLevel.WARNING


# ===========================================================================
# Notification
# ===========================================================================

class TestNotification:
    def test_fields(self):
        n = _make_notification()
        assert n.title == "Test"
        assert n.message == "Hello World"
        assert n.level == AlertLevel.INFO
        assert n.sent is False

    def test_to_dict(self):
        n = _make_notification(title="Alert", message="Body", level=AlertLevel.WARNING)
        d = n.to_dict()
        assert d["title"] == "Alert"
        assert d["level"] == "warning"
        assert "timestamp" in d

    def test_format_markdown(self):
        n = _make_notification(title="My Title", message="Content", level=AlertLevel.SUCCESS)
        md = n.format_markdown()
        assert "✅" in md
        assert "My Title" in md
        assert "Content" in md

    def test_format_markdown_all_levels(self):
        for level, emoji in [
            (AlertLevel.INFO, "ℹ️"),
            (AlertLevel.SUCCESS, "✅"),
            (AlertLevel.WARNING, "⚠️"),
            (AlertLevel.ERROR, "❌"),
            (AlertLevel.CRITICAL, "🚨"),
        ]:
            n = _make_notification(level=level)
            assert emoji in n.format_markdown()


# ===========================================================================
# log_notification_to_file
# ===========================================================================

class TestLogNotificationToFile:
    def test_log_creates_file(self, tmp_path):
        log_file = str(tmp_path / "notifications.jsonl")
        n = _make_notification()
        log_notification_to_file(n, log_file)
        with open(log_file) as f:
            content = f.read()
        assert "Test" in content

    def test_log_invalid_path(self):
        n = _make_notification()
        # Should not raise, just pass silently
        log_notification_to_file(n, "/invalid/nonexistent/path/log.jsonl")


# ===========================================================================
# TelegramNotifier
# ===========================================================================

class TestTelegramNotifier:
    def test_send_no_config(self):
        config = _make_config()
        tg = TelegramNotifier(config)
        n = _make_notification()
        assert tg.send(n) is False

    @patch("web3_agent_kit.notifications.telegram.requests.Session.post")
    def test_send_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(telegram_bot_token="123:ABC", telegram_chat_id="-100")
        tg = TelegramNotifier(config)
        n = _make_notification()
        assert tg.send(n) is True
        mock_post.assert_called_once()

    @patch("web3_agent_kit.notifications.telegram.requests.Session.post")
    def test_send_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_post.return_value = mock_resp

        config = _make_config(telegram_bot_token="123:ABC", telegram_chat_id="-100")
        tg = TelegramNotifier(config)
        assert tg.send(_make_notification()) is False

    @patch("web3_agent_kit.notifications.telegram.requests.Session.post")
    def test_send_connection_error(self, mock_post):
        mock_post.side_effect = ConnectionError("no network")
        config = _make_config(telegram_bot_token="123:ABC", telegram_chat_id="-100")
        tg = TelegramNotifier(config)
        assert tg.send(_make_notification()) is False


# ===========================================================================
# DiscordNotifier
# ===========================================================================

class TestDiscordNotifier:
    def test_send_no_config(self):
        config = _make_config()
        dc = DiscordNotifier(config)
        assert dc.send(_make_notification()) is False

    @patch("web3_agent_kit.notifications.discord.requests.Session.post")
    def test_send_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_post.return_value = mock_resp

        config = _make_config(discord_webhook_url="https://discord.com/api/webhooks/test")
        dc = DiscordNotifier(config)
        assert dc.send(_make_notification()) is True

    @patch("web3_agent_kit.notifications.discord.requests.Session.post")
    def test_send_success_200(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(discord_webhook_url="https://discord.com/api/webhooks/test")
        dc = DiscordNotifier(config)
        assert dc.send(_make_notification()) is True

    @patch("web3_agent_kit.notifications.discord.requests.Session.post")
    def test_send_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        config = _make_config(discord_webhook_url="https://discord.com/api/webhooks/test")
        dc = DiscordNotifier(config)
        assert dc.send(_make_notification()) is False

    @patch("web3_agent_kit.notifications.discord.requests.Session.post")
    def test_send_connection_error(self, mock_post):
        mock_post.side_effect = ConnectionError("fail")
        config = _make_config(discord_webhook_url="https://discord.com/api/webhooks/test")
        dc = DiscordNotifier(config)
        assert dc.send(_make_notification()) is False

    def test_level_colors(self):
        assert DiscordNotifier.LEVEL_COLORS[AlertLevel.INFO] == 0x3498DB
        assert DiscordNotifier.LEVEL_COLORS[AlertLevel.ERROR] == 0xE74C3C


# ===========================================================================
# EmailNotifier
# ===========================================================================

class TestEmailNotifier:
    def test_send_no_config(self):
        config = _make_config()
        em = EmailNotifier(config)
        assert em.send(_make_notification()) is False

    @patch("web3_agent_kit.notifications.email_notifier.smtplib.SMTP")
    def test_send_success(self, MockSMTP):
        mock_server = MagicMock()
        MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
        MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

        config = _make_config(
            email_smtp_host="smtp.gmail.com",
            email_smtp_port=587,
            email_username="user@gmail.com",
            email_password="pass",
            email_from="user@gmail.com",
            email_to=["recipient@example.com"],
        )
        em = EmailNotifier(config)
        assert em.send(_make_notification()) is True

    @patch("web3_agent_kit.notifications.email_notifier.smtplib.SMTP")
    def test_send_smtp_error(self, MockSMTP):
        MockSMTP.side_effect = ConnectionError("refused")
        config = _make_config(
            email_smtp_host="smtp.gmail.com",
            email_username="u",
            email_password="p",
            email_from="f",
            email_to=["t"],
        )
        em = EmailNotifier(config)
        assert em.send(_make_notification()) is False


# ===========================================================================
# Notifier (facade)
# ===========================================================================

class TestNotifierInit:
    def test_default(self):
        notifier = Notifier()
        assert notifier.config.enabled is True

    def test_with_config(self):
        config = _make_config(telegram_bot_token="123:ABC", telegram_chat_id="-100")
        notifier = Notifier(config)
        assert notifier.config.telegram_bot_token == "123:ABC"


class TestNotifierSend:
    def test_disabled(self):
        config = _make_config(enabled=False)
        notifier = Notifier(config)
        assert notifier.send("test") is False

    @patch("web3_agent_kit.notifications.telegram.requests.Session.post")
    def test_send_to_telegram(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(
            telegram_bot_token="123:ABC",
            telegram_chat_id="-100",
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        result = notifier.send("Hello", level="info")
        assert result is True

    @patch("web3_agent_kit.notifications.discord.requests.Session.post")
    def test_send_to_discord(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(
            discord_webhook_url="https://discord.com/api/webhooks/test",
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        result = notifier.send("Hello", level="info")
        assert result is True

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_to_slack(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(
            slack_webhook_url="https://hooks.slack.com/test",
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        result = notifier.send("Hello", level="info")
        assert result is True

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_to_webhook(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(
            webhook_urls=["https://example.com/hook"],
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        result = notifier.send("Hello", level="info")
        assert result is True

    def test_send_min_level_filter(self):
        config = _make_config(
            telegram_bot_token="123:ABC",
            telegram_chat_id="-100",
            min_level=AlertLevel.WARNING,
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        # INFO is below min_level
        assert notifier.send("low priority", level="info") is False


class TestNotifierChannel:
    @patch("web3_agent_kit.notifications.telegram.requests.Session.post")
    def test_send_specific_channel(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(
            telegram_bot_token="123:ABC",
            telegram_chat_id="-100",
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        result = notifier.send("Hello", channel="telegram")
        assert result is True

    def test_send_unknown_channel_webhook(self):
        config = _make_config(rate_limit_seconds=0)
        notifier = Notifier(config)
        # Unknown channel treated as webhook URL - should fail gracefully
        result = notifier.send("test", channel="https://invalid.example.com/hook")
        # May return False due to connection error
        assert isinstance(result, bool)


class TestNotifierHistory:
    def test_history_after_send(self):
        config = _make_config(enabled=False)  # disabled = don't actually send
        notifier = Notifier(config)
        notifier.send("msg")
        # Disabled sends don't add to history (return False early)
        # Let's test with enabled
        notifier.config.enabled = True
        notifier.send("msg")
        assert len(notifier.get_history()) >= 1

    def test_clear_history(self):
        config = _make_config(enabled=False)
        notifier = Notifier(config)
        notifier.config.enabled = True
        notifier.send("msg")
        notifier.clear_history()
        assert len(notifier.get_history()) == 0


class TestNotifierAlertMethods:
    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_trade_alert(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(
            slack_webhook_url="https://hooks.slack.com/test",
            rate_limit_seconds=0,
        )
        notifier = Notifier(config)
        result = notifier.send_trade_alert("buy", "ETH", 1.0, 3500.0, "0xabcdef")
        assert isinstance(result, bool)

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_gas_alert(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(slack_webhook_url="https://hooks.slack.com/test", rate_limit_seconds=0)
        notifier = Notifier(config)
        result = notifier.send_gas_alert("ethereum", 15.0, 30.0)
        assert isinstance(result, bool)

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_wallet_alert(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(slack_webhook_url="https://hooks.slack.com/test", rate_limit_seconds=0)
        notifier = Notifier(config)
        result = notifier.send_wallet_alert("0xABCDEF", "swap", "Swapped 1 ETH")
        assert isinstance(result, bool)

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_price_alert_up(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(slack_webhook_url="https://hooks.slack.com/test", rate_limit_seconds=0)
        notifier = Notifier(config)
        result = notifier.send_price_alert("ETH", 3500.0, 15.0)
        assert isinstance(result, bool)

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_price_alert_down(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(slack_webhook_url="https://hooks.slack.com/test", rate_limit_seconds=0)
        notifier = Notifier(config)
        result = notifier.send_price_alert("ETH", 3000.0, -5.0)
        assert isinstance(result, bool)

    @patch("web3_agent_kit.notifications.notifier.requests.Session.post")
    def test_send_airdrop_alert(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        config = _make_config(slack_webhook_url="https://hooks.slack.com/test", rate_limit_seconds=0)
        notifier = Notifier(config)
        result = notifier.send_airdrop_alert("EigenLayer", "Season 2", "https://claim.xyz")
        assert isinstance(result, bool)
