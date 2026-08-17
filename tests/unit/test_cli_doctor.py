import re

from typer.testing import CliRunner

from bot.cli import app


def test_doctor_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ok" in result.stdout.lower()


def test_doctor_reports_at_least_eight_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    match = re.search(r"DB tables:\s+(\d+)", result.stdout)
    assert match is not None
    assert int(match.group(1)) >= 8


def test_doctor_fails_when_user_agent_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.delenv("BOT_SEC_USER_AGENT", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code != 0


def test_doctor_fails_when_fmp_key_is_blank(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_FMP_API_KEY", "")

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "FMP" in result.stdout.upper() or "FMP" in result.stderr.upper()


def test_doctor_expects_the_full_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    match = re.search(r"DB tables:\s+(\d+)", result.stdout)
    assert match is not None
    # Schema should have 15 tables
    assert int(match.group(1)) == 15
