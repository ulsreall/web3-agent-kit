"""Notification shared types, enums, and dataclasses."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


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
    # Email
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: list[str] = field(default_factory=list)
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


def log_notification_to_file(notification: Notification, log_path: str) -> None:
    """Append a notification to a JSON-lines log file.

    Args:
        notification: The notification to log.
        log_path: Path to the log file.
    """
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(notification.to_dict()) + "\n")
    except (OSError, PermissionError):
        pass
