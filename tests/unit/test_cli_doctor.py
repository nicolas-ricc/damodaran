import re
from datetime import date, timedelta
from pathlib import Path

from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect


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
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.delenv("BOT_SEC_USER_AGENT", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code != 0


def test_doctor_fails_when_fmp_key_is_blank(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_DATA_PROVIDER", "fmp")
    monkeypatch.setenv("BOT_FMP_API_KEY", "")

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "FMP" in result.stdout.upper() or "FMP" in result.stderr.upper()


def test_doctor_ok_on_the_free_stack_with_no_fmp_key(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("BOT_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("BOT_FMP_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ok" in result.stdout.lower()


def test_doctor_expects_the_full_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    match = re.search(r"DB tables:\s+(\d+)", result.stdout)
    assert match is not None
    # Schema should have 16 tables
    assert int(match.group(1)) == 16


def test_doctor_warns_but_passes_when_tiingo_key_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_DATA_PROVIDER", "edgar-tiingo")
    monkeypatch.setenv("BOT_TIINGO_API_KEY", "")

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "MISSING" in result.stdout and "tiingo" in result.stdout.lower()


def test_doctor_reports_tiingo_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_DATA_PROVIDER", "edgar-tiingo")
    monkeypatch.setenv("BOT_TIINGO_API_KEY", "sometoken")

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Tiingo API key:   set" in result.stdout


SECRET = "secret-token-value"


def _business_days_ago(n: int) -> date:
    """Step back from today, counting each Monday-Friday date left behind (0 = today)."""
    day = date.today()
    left = n
    while left > 0:
        if day.weekday() < 5:
            left -= 1
        day -= timedelta(days=1)
    return day


def _flex_env(tmp_path, monkeypatch) -> Path:
    db_path = tmp_path / "x.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", SECRET)
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", "123456")
    return db_path


def _seed_snapshot(db_path: Path, day: date) -> None:
    conn = connect(db_path)
    apply_schema(conn)
    conn.execute(
        "INSERT INTO portfolio_snapshots "
        "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
        "VALUES (?, 'DU1', 'AAPL', 1, 10.0, 1000.0, 'USD')",
        [day],
    )
    conn.close()


def _assert_no_secret(result) -> None:
    assert SECRET not in result.stdout
    assert SECRET not in result.stderr


def test_doctor_flex_snapshot_today_is_ok(tmp_path, monkeypatch):
    db_path = _flex_env(tmp_path, monkeypatch)
    day = _business_days_ago(0)
    _seed_snapshot(db_path, day)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "Flex token:       set" in result.stdout
    assert "Flex query id:    set" in result.stdout
    assert f"Latest snapshot:  {day.isoformat()} (0 business day(s) old, OK)" in result.stdout
    _assert_no_secret(result)


def test_doctor_flex_snapshot_two_business_days_old_is_ok(tmp_path, monkeypatch):
    db_path = _flex_env(tmp_path, monkeypatch)
    day = _business_days_ago(2)
    _seed_snapshot(db_path, day)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert f"Latest snapshot:  {day.isoformat()} (2 business day(s) old, OK)" in result.stdout
    _assert_no_secret(result)


def test_doctor_flex_snapshot_three_business_days_old_fails(tmp_path, monkeypatch):
    db_path = _flex_env(tmp_path, monkeypatch)
    day = _business_days_ago(3)
    _seed_snapshot(db_path, day)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    fail_lines = [line for line in result.stderr.splitlines() if line.startswith("FAIL:")]
    assert any(day.isoformat() in line and "business days" in line for line in fail_lines)
    _assert_no_secret(result)


def test_doctor_flex_set_with_empty_snapshots_fails(tmp_path, monkeypatch):
    _flex_env(tmp_path, monkeypatch)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    fail_lines = [line for line in result.stderr.splitlines() if line.startswith("FAIL:")]
    assert any("portfolio_snapshots is empty" in line for line in fail_lines)
    _assert_no_secret(result)


def test_doctor_flex_unset_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("BOT_IBKR_FLEX_TOKEN", raising=False)
    monkeypatch.delenv("BOT_IBKR_FLEX_QUERY_ID", raising=False)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "Flex token:       MISSING" in result.stdout
    assert "Flex query id:    MISSING" in result.stdout
    assert "not configured" in result.stdout
    assert "Latest snapshot:" not in result.stdout


def test_doctor_blank_flex_token_is_not_configured(tmp_path, monkeypatch):
    _flex_env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", "   ")

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "Flex token:       MISSING" in result.stdout
    assert "not configured" in result.stdout


def test_doctor_flex_half_configured_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _flex_env(tmp_path, monkeypatch)
    monkeypatch.delenv("BOT_IBKR_FLEX_QUERY_ID")

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "Flex token:       set" in result.stdout
    assert "Flex query id:    MISSING" in result.stdout
    assert "not configured" in result.stdout
    _assert_no_secret(result)
