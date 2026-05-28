from pathlib import Path

import pytest
from typer.testing import CliRunner

from bot.cli import app


def test_doctor_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ok" in result.stdout.lower()


def test_doctor_fails_when_user_agent_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.delenv("BOT_SEC_USER_AGENT", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code != 0
