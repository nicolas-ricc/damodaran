"""SMTP email notifier backend."""

from __future__ import annotations

import smtplib
from collections.abc import Callable, Sequence
from typing import Literal

SmtpFactory = Callable[[str, int, float], smtplib.SMTP]
"""Builds an SMTP connection from ``(host, port, timeout)``; injectable for tests."""


class EmailNotifier:
    """Sends the alerts text as an email via SMTP."""

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

    def send(self, text: str) -> None:
        raise NotImplementedError
