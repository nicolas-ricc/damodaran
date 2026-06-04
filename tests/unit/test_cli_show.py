from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.base import IngestResult


def test_show_existing_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    from bot.storage.db import apply_schema, connect

    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO companies (ticker, name, country, currency, source) VALUES (?, ?, ?, ?, ?)",
        ["FAKE", "Fake Co", "US", "USD", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, revenue, source) VALUES (?, ?, ?, ?)",
        ["FAKE", 2023, 1_000_000_000, "sec_edgar"],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["show", "FAKE"])
    assert result.exit_code == 0
    assert "FAKE" in result.stdout
    assert "Fake Co" in result.stdout


def test_show_missing_ticker_triggers_sec_import(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    fake_result = IngestResult(
        source="sec_edgar",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
        rows_affected=10,
    )

    def populate_then_return(conn, *, ticker, user_agent):
        conn.execute(
            "INSERT INTO companies (ticker, name, country, currency, source) VALUES (?, ?, ?, ?, ?)",
            [ticker, f"{ticker} Inc", "US", "USD", "sec_edgar"],
        )
        return fake_result

    with patch("bot.cli.import_company_from_sec", side_effect=populate_then_return) as mock:
        runner = CliRunner()
        result = runner.invoke(app, ["show", "NEW"])
        assert result.exit_code == 0
        assert mock.called
        assert "NEW Inc" in result.stdout
