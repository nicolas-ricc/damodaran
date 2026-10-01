"""SMTP email notifier backend."""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Sequence
from email.message import EmailMessage
from typing import Literal

from bot.notifier.base import NotificationError

SmtpFactory = Callable[[str, int, float], smtplib.SMTP]
"""Builds an SMTP connection from ``(host, port, timeout)``; injectable for tests."""


class EmailNotifier:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipients: Sequence[str],
        username: str = "",
        password: str = "",
        security: Literal["starttls", "ssl", "none"] = "starttls",
        timeout: float = 30.0,
        smtp_factory: SmtpFactory | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = tuple(recipients)
        self.username = username
        self._password = password
        self.security = security
        self._timeout = timeout
        self._smtp_factory = smtp_factory

    def _connect(self) -> smtplib.SMTP:
        if self._smtp_factory is not None:
            return self._smtp_factory(self.host, self.port, self._timeout)
        if self.security == "ssl":
            return smtplib.SMTP_SSL(
                self.host, self.port, timeout=self._timeout, context=ssl.create_default_context()
            )
        return smtplib.SMTP(self.host, self.port, timeout=self._timeout)

    def send(self, text: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = _subject(text)
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(text)
        try:
            with self._connect() as smtp:
                if self.security == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if self.username:
                    smtp.login(self.username, self._password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationError(f"SMTP send to {self.host}:{self.port} failed: {exc}") from None


def _subject(text: str) -> str:
    """First non-empty line with leading ``#`` stripped; ``bot alerts`` if none."""
    for line in text.splitlines():
        if line.strip():
            return line.lstrip("#").strip() or "bot alerts"
    return "bot alerts"
