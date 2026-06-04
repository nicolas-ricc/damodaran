from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.base import IngestResult


def test_refresh_damodaran_calls_importer(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    fake_result = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 10),
        status="success",
        rows_affected=237,
        details={"industry_rows": 100, "country_rows": 137},
    )
    with patch("bot.cli.import_damodaran", return_value=fake_result) as mock:
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran"])
        assert result.exit_code == 0
        assert "237" in result.stdout
        assert mock.called


def test_refresh_without_flags_shows_help(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    runner = CliRunner()
    result = runner.invoke(app, ["refresh"])
    assert result.exit_code != 0
    # The error message goes to stderr; CliRunner mixes_stderr=False by default? Check both.
    combined = (result.stdout + (result.stderr or "")).lower()
    assert "specify" in combined or "flag" in combined or "damodaran" in combined
