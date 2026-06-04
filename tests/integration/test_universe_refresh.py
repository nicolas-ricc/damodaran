"""Integration test for the bulk universe refresh (M2.6).

Drives ``refresh_universe_from_fmp`` over a 5-ticker mini-universe with one VCR
cassette per ticker (US + international). The cassettes are SYNTHETIC
(hand-authored, fabricated-but-realistic FMP JSON) so the suite runs offline and
deterministically; they MUST be re-recorded against the live FMP API with a real
BOT_FMP_API_KEY before production use.

The incremental-skip path and per-ticker error isolation are covered exhaustively
in ``tests/unit/test_universe_refresh.py`` with injected fakes; this test proves
the orchestration drives the *real* single-ticker importer end-to-end across the
mini-universe via replayed HTTP.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
import vcr

from bot.ingest.fmp import import_company_from_fmp
from bot.ingest.universe import refresh_universe_from_fmp
from bot.storage.db import apply_schema, connect

API_KEY = "test-fmp-key"
MINI_UNIVERSE = ["AAPL", "MSFT", "NVDA", "NESN.SW", "SAP.DE"]


@pytest.fixture
def cassette_dir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootpath) / "tests" / "fixtures" / "cassettes" / "universe"


def _cassette_vcr() -> vcr.VCR:
    return vcr.VCR(
        filter_query_parameters=[("apikey", "SCRUBBED")],
        record_mode="none",
    )


def _cassette_importer(cassette_dir: Path) -> object:
    """Wrap the real FMP importer, replaying each ticker's own cassette."""
    my_vcr = _cassette_vcr()

    def importer(conn: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> object:
        cassette = cassette_dir / f"{ticker}.yaml"
        with my_vcr.use_cassette(str(cassette)):
            return import_company_from_fmp(conn, ticker=ticker, api_key=api_key)

    return importer


@pytest.mark.integration
def test_bulk_refresh_imports_full_mini_universe(cassette_dir: Path) -> None:
    conn = connect(":memory:")
    apply_schema(conn)

    result = refresh_universe_from_fmp(
        conn,
        api_key=API_KEY,
        tickers=MINI_UNIVERSE,
        importer=_cassette_importer(cassette_dir),  # type: ignore[arg-type]
        # First run: empty filings_log, so nothing is skipped regardless of probe.
        latest_filing_probe=lambda _t: None,
    )

    assert result.total == 5
    assert result.imported == 5
    assert result.skipped == 0
    assert result.failed == 0
    assert result.status == "success"
    assert result.failure_rate == 0.0

    # Companies for every ticker, US + international currencies preserved.
    companies = dict(
        conn.execute("SELECT ticker, currency FROM companies").fetchall()
    )
    assert set(companies) == set(MINI_UNIVERSE)
    assert companies["AAPL"] == "USD"
    assert companies["NESN.SW"] == "CHF"
    assert companies["SAP.DE"] == "EUR"

    # filings_log populated for each ticker (drives the next run's incremental skip).
    filings = conn.execute(
        "SELECT ticker, COUNT(*) FROM filings_log GROUP BY ticker"
    ).fetchall()
    assert {t for t, _ in filings} == set(MINI_UNIVERSE)

    # A single fmp_universe summary row recorded the run.
    summary = conn.execute(
        "SELECT status, rows_affected, error_message "
        "FROM refresh_log WHERE source = 'fmp_universe'"
    ).fetchall()
    assert len(summary) == 1
    assert summary[0][0] == "success"
    assert summary[0][1] == 5  # imported count
    assert summary[0][2] is None  # no failures

    conn.close()


@pytest.mark.integration
def test_second_run_skips_unchanged_tickers(cassette_dir: Path) -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    importer = _cassette_importer(cassette_dir)

    # First run imports everything and populates filings_log.
    refresh_universe_from_fmp(
        conn,
        api_key=API_KEY,
        tickers=MINI_UNIVERSE,
        importer=importer,  # type: ignore[arg-type]
        latest_filing_probe=lambda _t: None,
    )

    # Second run: probe reports each ticker's newest filing has NOT advanced
    # (use a deliberately old date so every local latest is >= remote) -> all skipped.
    result = refresh_universe_from_fmp(
        conn,
        api_key=API_KEY,
        tickers=MINI_UNIVERSE,
        importer=importer,  # type: ignore[arg-type]
        latest_filing_probe=lambda _t: date(2000, 1, 1),
    )

    assert result.skipped == 5
    assert result.imported == 0
    assert result.status == "success"

    conn.close()
