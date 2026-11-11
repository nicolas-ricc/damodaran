"""One readable line per invalid ``BOT_*`` setting (issue #89)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import pytest
from pydantic import Field, ValidationError

from bot.config import Settings, load_settings, settings_error_lines


@pytest.fixture(autouse=True)
def bare_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in list(os.environ):
        if key.startswith("BOT_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")


def _lines() -> list[str]:
    with pytest.raises(ValidationError) as info:
        load_settings()
    return settings_error_lines(info.value)


def test_settings_error_lines_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_NOTIFIER", "slack")

    assert _lines() == ["Invalid setting BOT_NOTIFIER: Input should be 'email', 'telegram' or 'none'"]


def test_settings_error_lines_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_SMTP_PORT", "abc")

    [line] = _lines()
    assert line.startswith("Invalid setting BOT_SMTP_PORT: ")
    assert "valid integer" in line


def test_settings_error_lines_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_IBKR_FLEX_TZ", "Mars/Nowhere")

    [line] = _lines()
    assert line.startswith("Invalid setting BOT_IBKR_FLEX_TZ: ")
    assert "unknown time zone" in line


def test_settings_error_lines_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_SEC_USER_AGENT")

    assert _lines() == ["Invalid setting BOT_SEC_USER_AGENT: Field required"]


def test_settings_error_lines_one_per_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_NOTIFIER", "slack")
    monkeypatch.setenv("BOT_SMTP_PORT", "abc")
    monkeypatch.setenv("BOT_DATA_PROVIDER", "foo")

    lines = _lines()

    names = {line.removeprefix("Invalid setting ").split(":")[0] for line in lines}
    assert len(lines) == 3
    assert names == {"BOT_DATA_PROVIDER", "BOT_NOTIFIER", "BOT_SMTP_PORT"}
    [provider] = [line for line in lines if "BOT_DATA_PROVIDER" in line]
    assert "'edgar-tiingo', 'edgar-stooq' or 'fmp'" in provider


def test_settings_error_lines_honours_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Aliased(Settings):
        notifier: Literal["none"] = Field(default="none", alias="MY_NOTIFIER")

    monkeypatch.setenv("MY_NOTIFIER", "slack")

    with pytest.raises(ValidationError) as info:
        _Aliased()  # type: ignore[call-arg]  # values supplied via env vars

    [line] = settings_error_lines(info.value)
    assert line.startswith("Invalid setting MY_NOTIFIER: ")


def test_settings_error_lines_do_not_echo_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_SMTP_PORT", "s3cr3t-port")

    [line] = _lines()
    assert "s3cr3t-port" not in line
