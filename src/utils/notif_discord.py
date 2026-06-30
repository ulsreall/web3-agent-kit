"""Discord notification sender."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .notif_utils import AlertLevel, Notification, NotifierConfig

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Send notifications via Discord webhook.

    Example::

        notifier = DiscordNotifier(NotifierConfig(
            discord_webhook_url="https://discord.com/api/webhooks/...",
        ))
        notifier.send(Notification(title="Alert", message="Hello!"))
    """

    LEVEL_COLORS: dict[AlertLevel, int] = {
        AlertLevel.INFO: 0x3498DB,
        AlertLevel.SUCCESS: 0x2ECC71,
        AlertLevel.WARNING: 0xF39C12,
        AlertLevel.ERROR: 0xE74C3C,
        AlertLevel.CRITICAL: 0x8E44AD,
    }

    def __init__(self, config: NotifierConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def send(self, notification: Notification) -> bool:
        """Send a notification to Discord.

        Args:
            notification: The notification to send.

        Returns:
            True if sent successfully.
        """
        if not self.config.discord_webhook_url:
            return False

        try:
            payload = {
                "embeds": [{
                    "title": notification.title,
                    "description": notification.message,
                    "color": self.LEVEL_COLORS.get(notification.level, 0x95A5A6),
                    "timestamp": notification.timestamp.isoformat(),
                }],
            }

            resp = self.session.post(
                self.config.discord_webhook_url,
                json=payload,
                timeout=10,
            )
            return resp.status_code in (200, 204)
        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            logger.error("Discord send failed: %s", exc)
            return False
