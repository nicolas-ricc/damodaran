"""The interface every notifier backend implements, and its two errors."""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    """Delivers a text message to one channel."""

    def send(self, text: str) -> None: ...


class NotifierConfigError(ValueError):
    """``BOT_NOTIFIER`` names a channel whose required settings are missing or unsafe."""


class NotificationError(RuntimeError):
    """A backend could not deliver; the message never contains credentials."""
