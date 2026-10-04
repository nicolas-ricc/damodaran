"""Optional push of ``alerts.md`` to email or Telegram (spec §15, #32)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bot.notifier.base import NotificationError, Notifier, NotifierConfigError
from bot.notifier.email import EmailNotifier
from bot.notifier.telegram import TelegramNotifier
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    from bot.config import Settings

__all__ = ["NotificationError", "Notifier", "NotifierConfigError", "build_notifier", "notify_alerts"]

log = get_logger(__name__)


def _require(pairs: list[tuple[str, str]]) -> None:
    """Raise :class:`NotifierConfigError` naming every blank env var."""
    missing = [env for env, value in pairs if not value.strip()]
    if missing:
        raise NotifierConfigError(f"missing {', '.join(missing)}")


def build_notifier(settings: Settings) -> Notifier | None:
    """Build the notifier selected by ``BOT_NOTIFIER``; ``None`` when it is ``none``."""
    if settings.notifier == "none":
        return None
    if settings.notifier == "email":
        recipients = [r.strip() for r in settings.smtp_to.split(",") if r.strip()]
        _require(
            [
                ("BOT_SMTP_HOST", settings.smtp_host),
                ("BOT_SMTP_FROM", settings.smtp_from),
                ("BOT_SMTP_TO", ",".join(recipients)),
            ]
        )
        if settings.smtp_security == "none" and settings.smtp_username.strip():
            raise NotifierConfigError(
                "BOT_SMTP_SECURITY=none would send BOT_SMTP_PASSWORD in cleartext; "
                "use starttls or ssl, or drop BOT_SMTP_USERNAME"
            )
        return EmailNotifier(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.smtp_from,
            recipients=recipients,
            username=settings.smtp_username,
            password=settings.smtp_password,
            security=settings.smtp_security,
        )
    _require(
        [
            ("BOT_TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
            ("BOT_TELEGRAM_CHAT_ID", settings.telegram_chat_id),
        ]
    )
    return TelegramNotifier(bot_token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)


def notify_alerts(alerts_path: Path, notifier: Notifier | None) -> bool:
    """Send the contents of ``alerts_path``; ``True`` iff something was sent.

    A blank file is not sent, and with no notifier the file is not read.
    """
    if notifier is None:
        return False
    text = alerts_path.read_text()
    if not text.strip():
        log.debug("alerts_empty_not_sent", alerts=str(alerts_path))
        return False
    notifier.send(text)
    log.info("alerts_sent", alerts=str(alerts_path), notifier=type(notifier).__name__)
    return True
