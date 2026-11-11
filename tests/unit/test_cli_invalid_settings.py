"""Invalid ``BOT_*`` settings exit 2 with one line per variable (issue #89)."""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner, Result

import bot.cli
from bot.cli import app


@pytest.fixture(autouse=True)
def bare_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in list(os.environ):
        if key.startswith("BOT_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))


def _invoke(args: list[str], input: str | None = None) -> Result:
    return CliRunner().invoke(app, args, input=input)


def _stderr_lines(result: Result) -> list[str]:
    return [line for line in result.stderr.splitlines() if line.strip()]


@pytest.mark.parametrize(
    "args",
    [
        ["status"],
        ["doctor"],
        ["notify"],
        ["portfolio"],
        ["refresh", "--damodaran"],
        ["show", "AAPL"],
        ["analyze", "AAPL"],
        ["screen"],
        ["flex-capture"],
    ],
)
def test_invalid_notifier_exits_2_without_traceback(
    monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    monkeypatch.setenv("BOT_NOTIFIER", "slack")

    result = _invoke(args, input="hi")

    assert result.exit_code == 2, result.output
    assert not isinstance(result.exception, ValidationError)
    assert "Traceback" not in result.output
    assert "BOT_NOTIFIER" in result.stderr
    assert "'email', 'telegram' or 'none'" in result.stderr


def test_invalid_smtp_port_names_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_SMTP_PORT", "abc")

    result = _invoke(["status"])

    assert result.exit_code == 2, result.output
    [line] = _stderr_lines(result)
    assert line.startswith("Invalid setting BOT_SMTP_PORT:")


def test_invalid_data_provider_names_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_DATA_PROVIDER", "foo")

    result = _invoke(["status"])

    assert result.exit_code == 2, result.output
    [line] = _stderr_lines(result)
    assert line.startswith("Invalid setting BOT_DATA_PROVIDER:")
    assert "'edgar-tiingo', 'edgar-stooq' or 'fmp'" in line


def test_invalid_settings_list_every_bad_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_NOTIFIER", "slack")
    monkeypatch.setenv("BOT_SMTP_PORT", "abc")
    monkeypatch.setenv("BOT_DATA_PROVIDER", "foo")

    result = _invoke(["status"])

    assert result.exit_code == 2, result.output
    assert len(_stderr_lines(result)) == 3


def test_doctor_matches_other_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_NOTIFIER", "slack")

    doctor = _invoke(["doctor"])
    status = _invoke(["status"])

    assert doctor.exit_code == status.exit_code == 2
    assert doctor.stderr == status.stderr


def test_only_helper_calls_load_settings() -> None:
    assert len(re.findall(r"(?<![\w])load_settings\(\)", inspect.getsource(bot.cli))) == 1
