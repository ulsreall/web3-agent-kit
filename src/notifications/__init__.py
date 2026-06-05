"""Notification System — alerts via Telegram, Discord, webhooks.

Sends notifications for important events: token listings,
gas alerts, wallet movements, trade confirmations.

Usage::

    from web3_agent_kit.notifications import Notifier, NotifierConfig

    notifier = Notifier(NotifierConfig(
        telegram_bot_token="...",
        telegram_chat_id="...",
    ))
    notifier.send("Trade executed!", level="success")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Notification alert levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class NotifierConfig:
    """Configuration for notifications."""
    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # Discord
    discord_webhook_url: str = ""
    # Slack
    slack_webhook_url: str = ""
    # Generic webhook
    webhook_urls: list[str] = field(default_factory=list)
    # Settings
    enabled: bool = True
    min_level: AlertLevel = AlertLevel.INFO
    rate_limit_seconds: float = 5.0
    # File logging
    log_path: Optional[str] = None


@dataclass
class Notification:
    """A notification message."""
    title: str
    message: str
    level: AlertLevel = AlertLevel.INFO
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict = field(default_factory=dict)
    channels: list[str] = field(default_factory=list)
    sent: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }

    def format_markdown(self) -> str:
        """Format as markdown."""
        level_emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.SUCCESS: "✅",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨",
        }
        emoji = level_emoji.get(self.level, "📢")
        return f"{emoji} **{self.title}**\n\n{self.message}"


class Notifier:
    """Send notifications across multiple channels.

    Supports Telegram, Discord, Slack, and generic webhooks.

    Example::

        notifier = Notifier(NotifierConfig(
            telegram_bot_token="123:ABC",
            telegram_chat_id="-100123456",
            discord_webhook_url="https://discord.com/api/webhooks/...",
        ))

        # Send to all configured channels
        notifier.send("Swap executed: 0.1 ETH → USDC", level="success")

        # Send to specific channel
        notifier.send("Alert!", channel="telegram")
    """

    def __init__(self, config: Optional[NotifierConfig] = None):
        """Initialize notifier.

        Args:
            config: Notification configuration.
        """
        self.config = config or NotifierConfig()
        self.session = requests.Session()
        self._history: list[Notification] = []
        self._last_send: float = 0
        logger.info("Notifier initialized")

    def send(
        self,
        message: str,
        title: str = "",
        level: str = "info",
        channel: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> bool:
        """Send a notification.

        Args:
            message: Notification message.
            title: Optional title.
            level: Alert level (info, success, warning, error, critical).
            channel: Specific channel, or None for all.
            data: Optional data dict.

        Returns:
            True if sent successfully.
        """
        if not self.config.enabled:
            return False

        # Create notification
        alert_level = AlertLevel(level.lower())
        notification = Notification(
            title=title or level.upper(),
            message=message,
            level=alert_level,
            data=data or {},
        )

        # Check minimum level
        level_order = [AlertLevel.INFO, AlertLevel.SUCCESS, AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL]
        if level_order.index(alert_level) < level_order.index(self.config.min_level):
            return False

        # Rate limiting
        elapsed = time.time() - self._last_send
        if elapsed < self.config.rate_limit_seconds:
            time.sleep(self.config.rate_limit_seconds - elapsed)

        # Send to channels
        success = False

        if channel:
            success = self._send_to_channel(channel, notification)
        else:
            if self.config.telegram_bot_token:
                success = self._send_telegram(notification) or success
            if self.config.discord_webhook_url:
                success = self._send_discord(notification) or success
            if self.config.slack_webhook_url:
                success = self._send_slack(notification) or success
            for url in self.config.webhook_urls:
                success = self._send_webhook(url, notification) or success

        notification.sent = success
        self._history.append(notification)
        self._last_send = time.time()

        # Log to file
        if self.config.log_path:
            self._log_to_file(notification)

        return success

    def send_trade_alert(
        self,
        action: str,
        token: str,
        amount: float,
        price: float,
        tx_hash: str = "",
    ) -> bool:
        """Send a trade alert.

        Args:
            action: Trade action (buy, sell, swap).
            token: Token symbol.
            amount: Amount traded.
            price: Price in USD.
            tx_hash: Transaction hash.

        Returns:
            True if sent.
        """
        message = (
            f"**{action.upper()}** {amount} {token}\n"
            f"Price: ${price:,.2f}\n"
        )
        if tx_hash:
            message += f"TX: `{tx_hash[:10]}...`"

        return self.send(message, title="Trade Alert", level="success")

    def send_gas_alert(self, chain: str, gas_gwei: float, threshold: float) -> bool:
        """Send a gas price alert.

        Args:
            chain: Chain name.
            gas_gwei: Current gas in Gwei.
            threshold: Alert threshold.

        Returns:
            True if sent.
        """
        message = (
            f"Gas on {chain}: **{gas_gwei:.1f} Gwei**\n"
            f"Threshold: {threshold:.1f} Gwei\n"
            f"{'✅ Good time to transact!' if gas_gwei < threshold else '⏳ Wait for lower gas'}"
        )
        return self.send(message, title="Gas Alert", level="info")

    def send_wallet_alert(self, wallet: str, action: str, details: str) -> bool:
        """Send a wallet activity alert.

        Args:
            wallet: Wallet address.
            action: Action detected.
            details: Additional details.

        Returns:
            True if sent.
        """
        message = (
            f"Wallet: `{wallet[:10]}...`\n"
            f"Action: {action}\n"
            f"{details}"
        )
        return self.send(message, title="Wallet Alert", level="warning")

    def send_price_alert(self, token: str, price: float, change_percent: float) -> bool:
        """Send a price alert.

        Args:
            token: Token symbol.
            price: Current price.
            change_percent: Price change percentage.

        Returns:
            True if sent.
        """
        emoji = "📈" if change_percent > 0 else "📉"
        message = (
            f"{emoji} **{token}** ${price:,.4f}\n"
            f"Change: {change_percent:+.1f}%"
        )
        level = "warning" if abs(change_percent) > 10 else "info"
        return self.send(message, title="Price Alert", level=level)

    def send_airdrop_alert(self, platform: str, campaign: str, url: str) -> bool:
        """Send an airdrop alert.

        Args:
            platform: Platform name.
            campaign: Campaign name.
            url: Campaign URL.

        Returns:
            True if sent.
        """
        message = (
            f"Platform: {platform}\n"
            f"Campaign: {campaign}\n"
            f"URL: {url}"
        )
        return self.send(message, title="🪂 New Airdrop", level="info")

    def get_history(self, limit: int = 50) -> list[Notification]:
        """Get notification history.

        Args:
            limit: Max notifications to return.

        Returns:
            List of Notification objects.
        """
        return self._history[-limit:]

    def clear_history(self) -> None:
        """Clear notification history."""
        self._history.clear()

    # ─── Channel Senders ──────────────────────────────────────────

    def _send_to_channel(self, channel: str, notification: Notification) -> bool:
        """Send to a specific channel."""
        if channel == "telegram":
            return self._send_telegram(notification)
        elif channel == "discord":
            return self._send_discord(notification)
        elif channel == "slack":
            return self._send_slack(notification)
        else:
            return self._send_webhook(channel, notification)

    def _send_telegram(self, notification: Notification) -> bool:
        """Send to Telegram."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return False

        try:
            text = notification.format_markdown()
            resp = self.session.post(
                f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": self.config.telegram_chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def _send_discord(self, notification: Notification) -> bool:
        """Send to Discord webhook."""
        if not self.config.discord_webhook_url:
            return False

        try:
            level_colors = {
                AlertLevel.INFO: 0x3498db,
                AlertLevel.SUCCESS: 0x2ecc71,
                AlertLevel.WARNING: 0xf39c12,
                AlertLevel.ERROR: 0xe74c3c,
                AlertLevel.CRITICAL: 0x8e44ad,
            }

            payload = {
                "embeds": [{
                    "title": notification.title,
                    "description": notification.message,
                    "color": level_colors.get(notification.level, 0x95a5a6),
                    "timestamp": notification.timestamp.isoformat(),
                }]
            }

            resp = self.session.post(
                self.config.discord_webhook_url,
                json=payload,
                timeout=10,
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return False

    def _send_slack(self, notification: Notification) -> bool:
        """Send to Slack webhook."""
        if not self.config.slack_webhook_url:
            return False

        try:
            payload = {
                "text": f"*{notification.title}*\n{notification.message}",
            }
            resp = self.session.post(
                self.config.slack_webhook_url,
                json=payload,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False

    def _send_webhook(self, url: str, notification: Notification) -> bool:
        """Send to generic webhook."""
        try:
            payload = notification.to_dict()
            resp = self.session.post(url, json=payload, timeout=10)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False

    def _log_to_file(self, notification: Notification) -> None:
        """Log notification to file."""
        if not self.config.log_path:
            return
        try:
            path = Path(self.config.log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(notification.to_dict()) + "\n")
        except Exception:
            pass

__all__ = [
    "AlertLevel",
    "NotifierConfig",
    "Notification",
    "Notifier",
]
