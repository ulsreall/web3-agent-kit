"""Telegram notification sender."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .notif_utils import AlertLevel, Notification, NotifierConfig

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram Bot API.

    Example::

        notifier = TelegramNotifier(NotifierConfig(
            telegram_bot_token="123:ABC",
            telegram_chat_id="-100123456",
        ))
        notifier.send(Notification(title="Alert", message="Hello!"))
    """

    def __init__(self, config: NotifierConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def send(self, notification: Notification) -> bool:
        """Send a notification to Telegram.

        Args:
            notification: The notification to send.

        Returns:
            True if sent successfully.
        """
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
        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            logger.error("Telegram send failed: %s", exc)
            return False
