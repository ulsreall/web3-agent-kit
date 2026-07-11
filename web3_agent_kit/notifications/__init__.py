"""Notification System — alerts via Telegram, Discord, webhooks.

Canonical implementation lives here. ``web3_agent_kit.utils`` re-exports
the same symbols for convenience.

Usage::
    from web3_agent_kit.notifications import Notifier, NotifierConfig
"""

from .discord import DiscordNotifier
from .email_notifier import EmailNotifier
from .notifier import Notifier
from .telegram import TelegramNotifier
from .utils import AlertLevel, Notification, NotifierConfig, log_notification_to_file

__all__ = [
    "AlertLevel",
    "NotifierConfig",
    "Notification",
    "Notifier",
    "TelegramNotifier",
    "DiscordNotifier",
    "EmailNotifier",
    "log_notification_to_file",
]
