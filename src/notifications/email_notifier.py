"""Email notification sender."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .utils import AlertLevel, Notification, NotifierConfig

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send notifications via SMTP email.

    Requires ``email_smtp_host``, ``email_username``, ``email_password``,
    ``email_from``, and ``email_to`` in :class:`NotifierConfig`.

    Example::

        notifier = EmailNotifier(NotifierConfig(
            email_smtp_host="smtp.gmail.com",
            email_smtp_port=587,
            email_username="user@gmail.com",
            email_password="app-password",
            email_from="user@gmail.com",
            email_to=["recipient@example.com"],
        ))
        notifier.send(Notification(title="Alert", message="Hello!"))
    """

    def __init__(self, config: NotifierConfig) -> None:
        self.config = config

    def send(self, notification: Notification) -> bool:
        """Send a notification via email.

        Args:
            notification: The notification to send.

        Returns:
            True if sent successfully.
        """
        if not all([
            self.config.email_smtp_host,
            self.config.email_username,
            self.config.email_password,
            self.config.email_from,
            self.config.email_to,
        ]):
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{notification.level.value.upper()}] {notification.title}"
            msg["From"] = self.config.email_from
            msg["To"] = ", ".join(self.config.email_to)

            # Plain text body
            body = f"{notification.title}\n\n{notification.message}"
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.config.email_smtp_host, self.config.email_smtp_port) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.sendmail(
                    self.config.email_from,
                    self.config.email_to,
                    msg.as_string(),
                )

            logger.info("Email notification sent: %s", notification.title)
            return True

        except (smtplib.SMTPException, ConnectionError, TimeoutError, OSError) as exc:
            logger.error("Email send failed: %s", exc)
            return False
