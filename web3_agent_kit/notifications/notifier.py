"""Notifier facade — orchestrates notifications across all channels."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from .discord import DiscordNotifier
from .email_notifier import EmailNotifier
from .telegram import TelegramNotifier
from .utils import AlertLevel, Notification, NotifierConfig, log_notification_to_file

logger = logging.getLogger(__name__)


class Notifier:
    """Send notifications across multiple channels.

    Supports Telegram, Discord, Slack, Email, and generic webhooks.

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

    def __init__(self, config: Optional[NotifierConfig] = None) -> None:
        """Initialize notifier.

        Args:
            config: Notification configuration.
        """
        self.config = config or NotifierConfig()
        self.session = requests.Session()
        self._history: list[Notification] = []
        self._last_send: float = 0

        # Sub-notifiers
        self._telegram = TelegramNotifier(self.config)
        self._discord = DiscordNotifier(self.config)
        self._email = EmailNotifier(self.config)

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
                success = self._telegram.send(notification) or success
            if self.config.discord_webhook_url:
                success = self._discord.send(notification) or success
            if self.config.slack_webhook_url:
                success = self._send_slack(notification) or success
            if self.config.email_smtp_host:
                success = self._email.send(notification) or success
            for url in self.config.webhook_urls:
                success = self._send_webhook(url, notification) or success

        notification.sent = success
        self._history.append(notification)
        self._last_send = time.time()

        # Log to file
        if self.config.log_path:
            log_notification_to_file(notification, self.config.log_path)

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
            return self._telegram.send(notification)
        elif channel == "discord":
            return self._discord.send(notification)
        elif channel == "slack":
            return self._send_slack(notification)
        elif channel == "email":
            return self._email.send(notification)
        else:
            return self._send_webhook(channel, notification)

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
        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            logger.error("Slack send failed: %s", exc)
            return False

    def _send_webhook(self, url: str, notification: Notification) -> bool:
        """Send to generic webhook."""
        try:
            payload = notification.to_dict()
            resp = self.session.post(url, json=payload, timeout=10)
            return resp.status_code in (200, 201, 204)
        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            logger.error("Webhook send failed: %s", exc)
            return False
