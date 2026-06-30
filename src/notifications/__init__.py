"""Notification System — alerts via Telegram, Discord, webhooks.

Note: Notifications module has been merged into utils/.
This module re-exports from utils for backward compatibility.

Usage::
    from web3_agent_kit.notifications import Notifier, NotifierConfig

    # Or equivalently:
    from web3_agent_kit.utils import Notifier, NotifierConfig
"""

from ..utils import AlertLevel, Notification, Notifier, NotifierConfig
from ..utils.notif_discord import DiscordNotifier
from ..utils.notif_email_notifier import EmailNotifier
from ..utils.notif_telegram import TelegramNotifier

__all__ = [
    "AlertLevel",
    "NotifierConfig",
    "Notification",
    "Notifier",
    "TelegramNotifier",
    "DiscordNotifier",
    "EmailNotifier",
]
