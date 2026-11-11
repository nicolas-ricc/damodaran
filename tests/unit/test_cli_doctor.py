import re
from datetime import date, timedelta
from pathlib import Path

import pytest
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
    assert "Latest snapshot:" not in result.stdout
    _assert_no_secret(result)


def _expiry_env(tmp_path, monkeypatch, value: str | None) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("BOT_IBKR_FLEX_TOKEN", raising=False)
    monkeypatch.delenv("BOT_IBKR_FLEX_QUERY_ID", raising=False)
    if value is None:
        monkeypatch.delenv("BOT_IBKR_FLEX_TOKEN_EXPIRES", raising=False)
    else:
        monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN_EXPIRES", value)


def _in_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def test_doctor_flex_token_expiry_far_is_info(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, _in_days(30))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert f"Flex token expiry: {_in_days(30)} (30 days left)" in result.stdout
    assert "WARN:" not in result.stdout


def test_doctor_flex_token_expiry_just_outside_window_is_info(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, _in_days(15))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert f"Flex token expiry: {_in_days(15)} (15 days left)" in result.stdout
    assert "WARN:" not in result.stdout


@pytest.mark.parametrize("days", [14, 0])
def test_doctor_flex_token_expiry_within_window_warns(tmp_path, monkeypatch, days):
    _expiry_env(tmp_path, monkeypatch, _in_days(days))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    warn = (
        f"WARN: Flex token expires in {days} day(s) ({_in_days(days)}) — renew it in "
        "Client Portal → Settings → Reporting → Flex Web Service"
    )
    assert warn in result.stdout.splitlines()
    assert "WARN:" not in result.stderr
    assert "All checks OK." in result.stdout


def test_doctor_flex_token_expired_fails(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, _in_days(-1))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    fail = (
        f"FAIL: Flex token expired on {_in_days(-1)} (BOT_IBKR_FLEX_TOKEN_EXPIRES) — "
        "generate a new one in Client Portal → Settings → Reporting → "
        "Flex Web Service and update .env"
    )
    assert fail in result.stderr.splitlines()


def test_doctor_flex_token_expiry_unset(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, None)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "Flex token expiry: not set (BOT_IBKR_FLEX_TOKEN_EXPIRES)" in result.stdout


def test_doctor_flex_token_expiry_blank_is_not_set(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, "  ")

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "Flex token expiry: not set" in result.stdout


def test_doctor_flex_token_expiry_garbage_is_settings_invalid(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, "garbage")

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 2
    assert "Invalid setting BOT_IBKR_FLEX_TOKEN_EXPIRES:" in result.stderr


def test_doctor_flex_token_expiry_follows_query_id_line(tmp_path, monkeypatch):
    _expiry_env(tmp_path, monkeypatch, _in_days(30))

    result = CliRunner().invoke(app, ["doctor"])

    lines = result.stdout.splitlines()
    (index,) = [i for i, line in enumerate(lines) if line.startswith("Flex query id:")]
    assert lines[index + 1].startswith("Flex token expiry:")


NOTIFIER_SECRET = "SECRET-notifier-value"


def _doctor_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _valid_email_env() -> dict[str, str]:
    return {
        "BOT_NOTIFIER": "email",
        "BOT_SMTP_HOST": "smtp.example.com",
        "BOT_SMTP_FROM": "bot@example.com",
        "BOT_SMTP_TO": "me@example.com",
        "BOT_SMTP_USERNAME": "user",
        "BOT_SMTP_PASSWORD": NOTIFIER_SECRET,
        "BOT_SMTP_SECURITY": "starttls",
    }


@pytest.mark.parametrize("channel", ["none", ""])
def test_doctor_notifier_none_passes(tmp_path, monkeypatch, channel):
    _doctor_env(tmp_path, monkeypatch, BOT_NOTIFIER=channel)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Notifier:         none (no alerts are pushed)" in result.stdout
    assert "Notifier misconfigured" not in result.stdout + result.stderr


def test_doctor_email_valid_passes(tmp_path, monkeypatch):
    _doctor_env(tmp_path, monkeypatch, **_valid_email_env())

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Notifier:         email (OK)" in result.stdout
    assert NOTIFIER_SECRET not in result.stdout + result.stderr


def test_doctor_email_missing_host_fails(tmp_path, monkeypatch):
    _doctor_env(tmp_path, monkeypatch, **{**_valid_email_env(), "BOT_SMTP_HOST": ""})

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Notifier:         email (MISCONFIGURED)" in result.stdout
    assert "Notifier misconfigured (BOT_NOTIFIER=email)" in result.stderr
    assert "BOT_SMTP_HOST" in result.stderr
    assert NOTIFIER_SECRET not in result.stdout + result.stderr


def test_doctor_email_cleartext_credentials_fail_without_leaking_password(tmp_path, monkeypatch):
    _doctor_env(tmp_path, monkeypatch, **{**_valid_email_env(), "BOT_SMTP_SECURITY": "none"})

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "BOT_SMTP_SECURITY=none" in result.stderr
    assert NOTIFIER_SECRET not in result.stdout + result.stderr


def test_doctor_telegram_valid_passes(tmp_path, monkeypatch):
    _doctor_env(
        tmp_path,
        monkeypatch,
        BOT_NOTIFIER="telegram",
        BOT_TELEGRAM_BOT_TOKEN=NOTIFIER_SECRET,
        BOT_TELEGRAM_CHAT_ID="12345",
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Notifier:         telegram (OK)" in result.stdout
    assert NOTIFIER_SECRET not in result.stdout + result.stderr


def test_doctor_telegram_missing_token_fails(tmp_path, monkeypatch):
    _doctor_env(
        tmp_path,
        monkeypatch,
        BOT_NOTIFIER="telegram",
        BOT_TELEGRAM_BOT_TOKEN="",
        BOT_TELEGRAM_CHAT_ID="12345",
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Notifier:         telegram (MISCONFIGURED)" in result.stdout
    assert "Notifier misconfigured (BOT_NOTIFIER=telegram)" in result.stderr
    assert "BOT_TELEGRAM_BOT_TOKEN" in result.stderr


def test_doctor_telegram_missing_chat_id_fails_without_leaking_token(tmp_path, monkeypatch):
    _doctor_env(
        tmp_path,
        monkeypatch,
        BOT_NOTIFIER="telegram",
        BOT_TELEGRAM_BOT_TOKEN=NOTIFIER_SECRET,
        BOT_TELEGRAM_CHAT_ID="",
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "BOT_TELEGRAM_CHAT_ID" in result.stderr
    assert NOTIFIER_SECRET not in result.stdout + result.stderr


def test_doctor_reports_notifier_and_fmp_issues_together(tmp_path, monkeypatch):
    _doctor_env(
        tmp_path,
        monkeypatch,
        BOT_DATA_PROVIDER="fmp",
        BOT_FMP_API_KEY="",
        BOT_NOTIFIER="telegram",
        BOT_TELEGRAM_BOT_TOKEN="",
        BOT_TELEGRAM_CHAT_ID="",
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    fails = [line for line in result.stderr.splitlines() if line.startswith("FAIL:")]
    assert len(fails) == 2
    assert any("FMP" in line for line in fails)
    assert any("Notifier misconfigured" in line for line in fails)


def test_doctor_rejects_unknown_notifier(tmp_path, monkeypatch):
    _doctor_env(tmp_path, monkeypatch, BOT_NOTIFIER="slack")

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 2
    assert "Invalid setting BOT_NOTIFIER:" in result.stderr
