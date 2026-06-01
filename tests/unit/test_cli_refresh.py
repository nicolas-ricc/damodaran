from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.base import IngestResult
from bot.ingest.universe import UniverseRefreshResult


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


def test_refresh_runs_both_damodaran_and_fmp(tmp_path, monkeypatch):
    """Passing --damodaran and --fmp together must run BOTH sources, not
    short-circuit on --fmp."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    dam = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
        rows_affected=10,
        details={"industry_rows": 5, "country_rows": 5},
    )
    uni = UniverseRefreshResult(
        run_id="r",
        started_at=datetime(2026, 5, 25, 9, 1, 0),
        finished_at=datetime(2026, 5, 25, 9, 1, 8),
        status="success",
        total=2,
        imported=2,
        skipped=0,
        failed=0,
        outcomes=[],
    )
    with (
        patch("bot.cli.import_damodaran", return_value=dam) as mdam,
        patch("bot.cli.refresh_universe_from_fmp", return_value=uni) as mfmp,
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran", "--fmp"])

    assert mdam.called, "--damodaran must run even when --fmp is also passed"
    assert mfmp.called
    assert result.exit_code == 0


def test_refresh_worst_of_exit_code(tmp_path, monkeypatch):
    """A damodaran failure (1) plus an fmp data error (2) exits with the worst (2)."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    dam = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="error",
        rows_affected=0,
        error_message="boom",
    )
    uni = UniverseRefreshResult(
        run_id="r",
        started_at=datetime(2026, 5, 25, 9, 1, 0),
        finished_at=datetime(2026, 5, 25, 9, 1, 8),
        status="error",
        total=4,
        imported=1,
        skipped=0,
        failed=3,
        outcomes=[],
    )
    with (
        patch("bot.cli.import_damodaran", return_value=dam),
        patch("bot.cli.refresh_universe_from_fmp", return_value=uni),
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran", "--fmp"])

    assert result.exit_code == 2


def test_refresh_without_flags_shows_help(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    runner = CliRunner()
    result = runner.invoke(app, ["refresh"])
    assert result.exit_code != 0
    # The error message goes to stderr; CliRunner mixes_stderr=False by default? Check both.
    combined = (result.stdout + (result.stderr or "")).lower()
    assert "specify" in combined or "flag" in combined or "damodaran" in combined
