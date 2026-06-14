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

from .discord import DiscordNotifier
from .email_notifier import EmailNotifier
from .notifier import Notifier
from .telegram import TelegramNotifier
from .utils import AlertLevel, Notification, NotifierConfig

__all__ = [
    "AlertLevel",
    "NotifierConfig",
    "Notification",
    "Notifier",
    "TelegramNotifier",
    "DiscordNotifier",
    "EmailNotifier",
]
