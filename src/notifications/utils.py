"""Notification shared types — re-export from utils module.

This module exists for backward compatibility. All notification
types have been moved to src/utils/notif_utils.py.
"""

# Re-export everything from the new location
from ..utils.notif_utils import *  # noqa: F401,F403
from ..utils.notif_utils import AlertLevel, Notification, NotifierConfig, log_notification_to_file

__all__ = [
    "AlertLevel",
    "Notification",
    "NotifierConfig",
    "log_notification_to_file",
]