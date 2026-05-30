"""CLI tests for `bot refresh --fmp` (M2.6).

The universe refresh itself is unit-tested separately; here we verify the CLI
wiring: the default-vs-custom universe path, progress/summary output, and the
exit-code contract (0 when <=5% failed, 2 otherwise).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.universe import TickerOutcome, UniverseRefreshResult


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_FMP_API_KEY", "test-fmp-key")


def _result(*, total: int, failed: int, status: str) -> UniverseRefreshResult:
    now = datetime.now()
    return UniverseRefreshResult(
        run_id="run-1",
        started_at=now,
        finished_at=now,
        status=status,
        total=total,
        imported=total - failed,
        skipped=0,
        failed=failed,
        outcomes=[
            TickerOutcome(ticker=f"BAD{i}", status="failed", error_message="boom")
            for i in range(failed)
        ],
    )


def test_refresh_fmp_uses_default_universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_refresh(conn: object, *, api_key: str, tickers: list[str]) -> UniverseRefreshResult:
        captured["tickers"] = tickers
        return _result(total=len(tickers), failed=0, status="success")

    with patch("bot.cli.refresh_universe_from_fmp", side_effect=fake_refresh):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--fmp"])
    assert result.exit_code == 0
    assert "imported" in result.stdout
    # Default universe was loaded and passed through.
    assert isinstance(captured["tickers"], list)
    assert "AAPL" in captured["tickers"]


def test_refresh_fmp_custom_universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    uni = tmp_path / "mini.csv"
    uni.write_text("ticker\nAAPL\nMSFT\n")
    captured: dict[str, object] = {}

    def fake_refresh(conn: object, *, api_key: str, tickers: list[str]) -> UniverseRefreshResult:
        captured["tickers"] = tickers
        return _result(total=len(tickers), failed=0, status="success")

    with patch("bot.cli.refresh_universe_from_fmp", side_effect=fake_refresh):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--fmp", "--universe", str(uni)])
    assert result.exit_code == 0
    assert captured["tickers"] == ["AAPL", "MSFT"]


def test_refresh_fmp_exit_code_2_when_over_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    uni = tmp_path / "mini.csv"
    uni.write_text("ticker\n" + "\n".join(f"T{i}" for i in range(20)) + "\n")

    def fake_refresh(conn: object, *, api_key: str, tickers: list[str]) -> UniverseRefreshResult:
        return _result(total=20, failed=6, status="error")

    with patch("bot.cli.refresh_universe_from_fmp", side_effect=fake_refresh):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--fmp", "--universe", str(uni)])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "ERROR" in combined
    assert "BAD0" in combined  # failures reported


def test_refresh_fmp_partial_still_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    uni = tmp_path / "mini.csv"
    uni.write_text("ticker\n" + "\n".join(f"T{i}" for i in range(20)) + "\n")

    def fake_refresh(conn: object, *, api_key: str, tickers: list[str]) -> UniverseRefreshResult:
        return _result(total=20, failed=2, status="partial")

    with patch("bot.cli.refresh_universe_from_fmp", side_effect=fake_refresh):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--fmp", "--universe", str(uni)])
    # > 5% failed -> not 'success' -> exit 2 (data error).
    assert result.exit_code == 2


def test_refresh_fmp_empty_universe_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    uni = tmp_path / "empty.csv"
    uni.write_text("ticker\n")
    runner = CliRunner()
    result = runner.invoke(app, ["refresh", "--fmp", "--universe", str(uni)])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "no tickers" in combined.lower()


def test_refresh_no_flags_mentions_fmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["refresh"])
    assert result.exit_code == 2
    combined = (result.stdout + (result.stderr or "")).lower()
    assert "fmp" in combined
