"""Every CLI command closes the DuckDB connection it opened, however it ends (#87)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

import bot.cli
from bot.cli import app
from bot.ingest.ibkr_flex import FlexError
from bot.storage import db

PRESETS_DIR = Path(__file__).resolve().parents[2] / "config" / "presets"


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_PRESETS_DIR", str(PRESETS_DIR))
    conn = db.connect(path)
    db.apply_schema(conn)
    conn.close()
    return path


@pytest.fixture
def opened(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[duckdb.DuckDBPyConnection]:
    """Record every connection the CLI opens through ``bot.cli.connect``."""
    conns: list[duckdb.DuckDBPyConnection] = []

    def recording_connect(path: Path) -> duckdb.DuckDBPyConnection:
        conn = db.connect(path)
        conns.append(conn)
        return conn

    monkeypatch.setattr(bot.cli, "connect", recording_connect)
    return conns


def _assert_all_closed(conns: list[duckdb.DuckDBPyConnection]) -> None:
    assert conns, "the command opened no connection"
    for conn in conns:
        with pytest.raises(duckdb.ConnectionException):
            conn.execute("SELECT 1")


def _seed(db_path: Path, sql: str, params: list[object]) -> None:
    conn = db.connect(db_path)
    conn.execute(sql, params)
    conn.close()


def _boom(*_: object, **__: object) -> int:
    raise RuntimeError("boom")


def test_open_db_closes_after_block(db_path: Path, opened: list[duckdb.DuckDBPyConnection]) -> None:
    with bot.cli._open_db() as (conn, settings):
        conn.execute("SELECT 1")
    assert settings.db_path == db_path
    _assert_all_closed(opened)


def test_open_db_closes_when_body_raises(opened: list[duckdb.DuckDBPyConnection]) -> None:
    with pytest.raises(RuntimeError, match="boom"), bot.cli._open_db():
        raise RuntimeError("boom")
    _assert_all_closed(opened)


def test_open_db_closes_when_apply_schema_raises(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "apply_schema", _boom)
    with pytest.raises(RuntimeError, match="boom"), bot.cli._open_db():
        pass
    _assert_all_closed(opened)


def test_refresh_closes_db(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "_refresh_fx", lambda conn, settings: 0)
    result = CliRunner().invoke(app, ["refresh", "--fx"])
    assert result.exit_code == 0, result.output
    _assert_all_closed(opened)


def test_refresh_closes_db_when_it_raises(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "_refresh_fx", _boom)
    result = CliRunner().invoke(app, ["refresh", "--fx"])
    assert isinstance(result.exception, RuntimeError)
    _assert_all_closed(opened)


def test_show_closes_db(db_path: Path, opened: list[duckdb.DuckDBPyConnection]) -> None:
    _seed(
        db_path,
        "INSERT INTO companies (ticker, name, cik, country, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAA", "Aaa Inc", "0000000001", "US", "USD", "sec_edgar"],
    )
    result = CliRunner().invoke(app, ["show", "AAA", "--no-fetch"])
    assert result.exit_code == 0, result.output
    _assert_all_closed(opened)


def test_show_closes_db_on_early_exit(opened: list[duckdb.DuckDBPyConnection]) -> None:
    result = CliRunner().invoke(app, ["show", "ZZZZ", "--no-fetch"])
    assert result.exit_code == 2, result.output
    _assert_all_closed(opened)


def test_analyze_closes_db(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "_analyze_one", lambda *_args: 0)
    result = CliRunner().invoke(app, ["analyze", "AAA"])
    assert result.exit_code == 0, result.output
    _assert_all_closed(opened)


def test_analyze_closes_db_on_early_exit(opened: list[duckdb.DuckDBPyConnection]) -> None:
    result = CliRunner().invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 2, result.output
    _assert_all_closed(opened)


def test_analyze_closes_db_when_it_raises(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "_analyze_one", _boom)
    result = CliRunner().invoke(app, ["analyze", "AAA"])
    assert isinstance(result.exception, RuntimeError)
    _assert_all_closed(opened)


def test_screen_closes_db(opened: list[duckdb.DuckDBPyConnection]) -> None:
    result = CliRunner().invoke(app, ["screen"])
    assert result.exit_code == 0, result.output
    _assert_all_closed(opened)


def test_screen_closes_db_on_early_exit(
    tmp_path: Path, opened: list[duckdb.DuckDBPyConnection]
) -> None:
    result = CliRunner().invoke(app, ["screen", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 2, result.output
    _assert_all_closed(opened)


def test_screen_closes_db_when_it_raises(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "run_screen", _boom)
    result = CliRunner().invoke(app, ["screen"])
    assert isinstance(result.exception, RuntimeError)
    _assert_all_closed(opened)


@pytest.fixture
def flex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", "tok")
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", "123")
    monkeypatch.setattr(
        bot.cli.FlexPortfolioClient, "from_settings", classmethod(lambda cls, settings: object())
    )


def test_portfolio_closes_db_on_flex_failure(
    flex_env: None, opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    def flex_fails(*_: object, **__: object) -> None:
        raise FlexError("1020 Invalid request")

    monkeypatch.setattr(bot.cli, "run_portfolio", flex_fails)
    result = CliRunner().invoke(app, ["portfolio"])
    assert result.exit_code == 1, result.output
    _assert_all_closed(opened)


def test_portfolio_closes_db_when_it_raises(
    flex_env: None, opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot.cli, "run_portfolio", _boom)
    result = CliRunner().invoke(app, ["portfolio"])
    assert isinstance(result.exception, RuntimeError)
    _assert_all_closed(opened)


def test_status_closes_db(db_path: Path, opened: list[duckdb.DuckDBPyConnection]) -> None:
    _seed(
        db_path,
        "INSERT INTO refresh_log (source, run_id, started_at, finished_at, status, rows_affected) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["damodaran", "run-1", datetime(2026, 5, 25, 9), datetime(2026, 5, 25, 9, 1), "success", 1],
    )
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "damodaran" in result.output
    _assert_all_closed(opened)


def test_status_closes_db_on_early_return(opened: list[duckdb.DuckDBPyConnection]) -> None:
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    _assert_all_closed(opened)


def test_doctor_closes_db_when_probe_raises(
    opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("BOT_STOOQ_DIR", raising=False)

    def probe_fails() -> int:
        raise RuntimeError("probe")

    monkeypatch.setattr(bot.cli, "schema_table_count", probe_fails)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1, result.output
    assert "DB error — probe" in result.output
    _assert_all_closed(opened)
