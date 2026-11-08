"""CLI test for ``bot notify`` (#321): send stdin through the configured notifier.

Monkeypatches ``bot.cli.build_notifier`` with a recorder (or a failing notifier) so no
message leaves the process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import bot.cli
from bot.cli import app
from bot.notifier import NotificationError, NotifierConfigError

ROOT = Path(__file__).resolve().parents[2]


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    return db_path


def _misconfigured(settings: object) -> None:
    raise NotifierConfigError("missing BOT_SMTP_HOST")


def test_notify_sends_stdin_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "telegram")
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)
    text = "\n# daily.sh failed: portfolio (exit 1)\n\nlog tail — € ✓ café\n"

    result = CliRunner().invoke(app, ["notify"], input=text)

    assert result.exit_code == 0, result.output
    assert rec.sent == [text]
    assert "Sent via telegram" in result.stdout


def test_notify_without_notifier_sends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "none")  # process env beats a developer's .env

    result = CliRunner().invoke(app, ["notify"], input="")

    assert result.exit_code == 0, result.output
    assert "No notifier configured (BOT_NOTIFIER=none), nothing sent" in result.stdout
    assert "Nothing to send" not in result.output


def test_notify_misconfigured_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "email")
    monkeypatch.setattr(bot.cli, "build_notifier", _misconfigured)

    result = CliRunner().invoke(app, ["notify"], input="# hello\n")

    assert result.exit_code == 2
    assert "Notifier misconfigured (BOT_NOTIFIER=email): missing BOT_SMTP_HOST" in result.stderr


def test_notify_misconfigured_wins_over_empty_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "email")
    monkeypatch.setattr(bot.cli, "build_notifier", _misconfigured)

    result = CliRunner().invoke(app, ["notify"], input="")

    assert result.exit_code == 2
    assert "Notifier misconfigured" in result.stderr
    assert "Nothing to send" not in result.output


@pytest.mark.parametrize("text", ["", " ", "\n", "\r\n", "  \n\t"])
def test_notify_empty_stdin_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "telegram")
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)

    result = CliRunner().invoke(app, ["notify"], input=text)

    assert result.exit_code == 2
    assert "Nothing to send: the message on stdin is empty" in result.stderr
    assert rec.sent == []


def test_notify_send_failure_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "telegram")

    class _Failing:
        def send(self, text: str) -> None:
            raise NotificationError("Telegram sendMessage HTTP 400: chat not found")

    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: _Failing())

    result = CliRunner().invoke(app, ["notify"], input="# daily.sh failed\n")

    assert result.exit_code == 1
    assert "Message not sent: Telegram sendMessage HTTP 400: chat not found" in result.stderr


def test_notify_never_opens_the_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "telegram")
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", "")  # empty env beats a developer's .env
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", "")
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)

    result = CliRunner().invoke(app, ["notify"], input="# hello\n")

    assert result.exit_code == 0, result.output
    assert rec.sent == ["# hello\n"]
    assert not db_path.exists()


def test_notify_is_listed_in_help() -> None:
    root_help = CliRunner().invoke(app, ["--help"])
    assert root_help.exit_code == 0
    assert "notify" in root_help.stdout

    notify_help = CliRunner().invoke(app, ["notify", "--help"])
    assert notify_help.exit_code == 0, notify_help.output


def _notifications_section(readme: str) -> str:
    start = readme.index("### Notifications")
    lines = readme[start:].splitlines()
    end = next(i for i, line in enumerate(lines[1:], 1) if line.startswith(("## ", "### ")))
    return " ".join(" ".join(lines[:end]).split())


def test_readme_documents_bot_notify() -> None:
    section = _notifications_section((ROOT / "README.md").read_text(encoding="utf-8"))
    assert "bot notify" in section
    assert "stdin" in section
    assert "daily.sh" in section
    assert "exit code 2" in section
    assert "exit code 1" in section
