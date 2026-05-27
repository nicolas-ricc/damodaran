from datetime import datetime

from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect


def test_status_with_no_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no refresh history" in result.stdout.lower()


def test_status_with_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        """
        INSERT INTO refresh_log (source, run_id, started_at, finished_at, status, rows_affected)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "damodaran",
            "run-1",
            datetime(2026, 5, 25, 9, 0),
            datetime(2026, 5, 25, 9, 0, 30),
            "success",
            237,
        ],
    )
    conn.execute(
        """
        INSERT INTO refresh_log (source, run_id, started_at, finished_at, status, rows_affected)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "sec_edgar",
            "run-2",
            datetime(2026, 5, 25, 9, 5),
            datetime(2026, 5, 25, 9, 5, 10),
            "success",
            50,
        ],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "damodaran" in result.stdout
    assert "sec_edgar" in result.stdout
    assert "237" in result.stdout
