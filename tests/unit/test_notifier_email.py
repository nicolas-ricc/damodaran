import smtplib
from email.message import EmailMessage
from typing import ClassVar

import pytest

from bot.notifier import NotificationError
from bot.notifier.email import EmailNotifier


class FakeSMTP(smtplib.SMTP):
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        super().__init__()
        self.args = (host, port, timeout)
        self.calls: list[str] = []
        self.messages: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def starttls(self, *args, **kwargs):  # type: ignore[override]
        self.calls.append("starttls")
        return (220, b"ok")

    def login(self, user, password, **kwargs):  # type: ignore[override]
        self.calls.append(f"login:{user}")
        return (235, b"ok")

    def send_message(self, msg, *args, **kwargs):  # type: ignore[override]
        self.calls.append("send_message")
        self.messages.append(msg)
        return {}


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSMTP.instances.clear()


def _notifier(**kw) -> EmailNotifier:
    base = dict(host="smtp.example.com", port=587, sender="bot@example.com",
                recipients=["a@x.com", "b@y.com"], username="u", password="s3cret",
                smtp_factory=FakeSMTP)
    base.update(kw)
    return EmailNotifier(**base)


def test_send_starttls_login_and_message() -> None:
    text = "# Alerts — 2026-06-01\n\n| position_opened | AAPL |\n"
    _notifier().send(text)
    smtp = FakeSMTP.instances[0]
    assert smtp.args[:2] == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", "login:u", "send_message"]
    msg = smtp.messages[0]
    assert msg["Subject"] == "Alerts — 2026-06-01"
    assert msg["From"] == "bot@example.com"
    assert msg["To"] == "a@x.com, b@y.com"
    assert msg.get_content() == text


def test_no_login_without_username_and_no_starttls_when_security_none() -> None:
    _notifier(username="", password="", security="none").send("hi")
    assert FakeSMTP.instances[0].calls == ["send_message"]


def test_subject_falls_back_when_text_has_no_heading_text() -> None:
    _notifier().send("\n#\n")
    assert FakeSMTP.instances[0].messages[0]["Subject"] == "bot alerts"


def test_smtp_failure_raises_notification_error_without_password() -> None:
    class Refusing(FakeSMTP):
        def login(self, user, password, **kwargs):  # type: ignore[override]
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    with pytest.raises(NotificationError) as exc:
        _notifier(smtp_factory=Refusing).send("hi")
    assert "s3cret" not in str(exc.value)


def test_connection_failure_raises_notification_error() -> None:
    def refuse(host: str, port: int, timeout: float) -> smtplib.SMTP:
        raise ConnectionRefusedError(111, "Connection refused")

    with pytest.raises(NotificationError):
        _notifier(smtp_factory=refuse).send("hi")
