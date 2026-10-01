from pathlib import Path

import pytest
from bot.notifier import NotifierConfigError, build_notifier, notify_alerts
from bot.notifier.email import EmailNotifier
from bot.notifier.telegram import TelegramNotifier

from bot.config import Settings


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, sec_user_agent="X Y x@y.com", **overrides)  # type: ignore[call-arg]


def test_notify_alerts_sends_file_contents(tmp_path: Path) -> None:
    path = tmp_path / "alerts.md"
    path.write_text("# Alerts — 2026-06-01\n\n| a | b |\n")
    rec = _Recorder()
    assert notify_alerts(path, rec) is True
    assert rec.sent == ["# Alerts — 2026-06-01\n\n| a | b |\n"]


@pytest.mark.parametrize("content", ["", "\n", "  \n\t"])
def test_notify_alerts_skips_blank_file(tmp_path: Path, content: str) -> None:
    path = tmp_path / "alerts.md"
    path.write_text(content)
    rec = _Recorder()
    assert notify_alerts(path, rec) is False
    assert rec.sent == []


def test_notify_alerts_without_notifier_does_not_read(tmp_path: Path) -> None:
    assert notify_alerts(tmp_path / "missing.md", None) is False


def test_build_notifier_none() -> None:
    assert build_notifier(_settings()) is None


def test_build_notifier_email_parses_recipients() -> None:
    n = build_notifier(
        _settings(
            notifier="email",
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_security="ssl",
            smtp_username="u",
            smtp_password="p",
            smtp_from="bot@example.com",
            smtp_to=" a@x.com, b@y.com ,",
        )
    )
    assert isinstance(n, EmailNotifier)
    assert n.recipients == ("a@x.com", "b@y.com")
    assert (n.host, n.port, n.security, n.sender) == ("smtp.example.com", 465, "ssl", "bot@example.com")


def test_build_notifier_email_missing_fields_names_env_vars() -> None:
    with pytest.raises(NotifierConfigError) as exc:
        build_notifier(_settings(notifier="email", smtp_to=" , "))
    msg = str(exc.value)
    assert "BOT_SMTP_HOST" in msg and "BOT_SMTP_FROM" in msg and "BOT_SMTP_TO" in msg


def test_build_notifier_rejects_cleartext_login() -> None:
    with pytest.raises(NotifierConfigError) as exc:
        build_notifier(
            _settings(
                notifier="email",
                smtp_host="h",
                smtp_from="f@x.com",
                smtp_to="t@x.com",
                smtp_security="none",
                smtp_username="u",
            )
        )
    assert "BOT_SMTP_SECURITY" in str(exc.value)


def test_build_notifier_telegram() -> None:
    n = build_notifier(_settings(notifier="telegram", telegram_bot_token="123:abc", telegram_chat_id="-100"))
    assert isinstance(n, TelegramNotifier)
    assert n.chat_id == "-100"


def test_build_notifier_telegram_missing_fields() -> None:
    with pytest.raises(NotifierConfigError) as exc:
        build_notifier(_settings(notifier="telegram"))
    assert "BOT_TELEGRAM_BOT_TOKEN" in str(exc.value)
    assert "BOT_TELEGRAM_CHAT_ID" in str(exc.value)
