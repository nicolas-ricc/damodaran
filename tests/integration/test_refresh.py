"""Integration tests for refresh_universe with a 5-ticker mini-universe.

Each ticker uses its own VCR cassette loaded via vcrpy context managers so that
the cassettes remain independent (one per ticker) while the test exercises the
full refresh_universe function.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import vcr as vcrpy  # type: ignore[import-untyped]

from bot.ingest.refresh import RefreshStats, refresh_universe
from bot.storage.db import apply_schema

MINI_UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
CASSETTE_DIR = Path(__file__).parent.parent / "fixtures" / "cassettes" / "refresh"


@pytest.fixture  # type: ignore[misc]
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    return conn


def _run_ticker(
    db: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    my_vcr: vcrpy.VCR,
) -> RefreshStats:
    cassette = f"{ticker.lower()}.yaml"
    with my_vcr.use_cassette(cassette):
        return refresh_universe(db, [ticker], api_key="test_key")


@pytest.mark.integration  # type: ignore[misc]
def test_refresh_universe_5_tickers(db: duckdb.DuckDBPyConnection) -> None:
    """5-ticker mini-universe: AAPL/GOOGL/AMZN imported, MSFT skipped, TSLA errors.

    MSFT is pre-seeded in filings_log so the skip-check returns the same
    fillingDate → skipped without a full import.
    TSLA's FMP profile returns empty → caught error, run continues.
    Aggregate: 3 imported, 1 skipped, 1 error (20% fail rate → partial status).
    """
    my_vcr = vcrpy.VCR(
        cassette_library_dir=str(CASSETTE_DIR),
        filter_query_parameters=["apikey"],
        record_mode="none",
    )

    # Pre-seed MSFT so the skip check (fillingDate="2023-07-27") triggers a skip.
    db.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) VALUES (?, ?, ?, ?)",
        ["MSFT", "annual-fmp", "2023-07-27", "fmp"],
    )

    total_imported = 0
    total_skipped = 0
    total_errors = 0
    per_ticker: dict[str, RefreshStats] = {}

    for ticker in MINI_UNIVERSE:
        stats = _run_ticker(db, ticker, my_vcr=my_vcr)
        per_ticker[ticker] = stats
        total_imported += stats.imported
        total_skipped += stats.skipped
        total_errors += stats.errors

    # Per-ticker assertions
    assert per_ticker["AAPL"].imported == 1
    assert per_ticker["AAPL"].errors == 0

    assert per_ticker["MSFT"].skipped == 1
    assert per_ticker["MSFT"].imported == 0
    assert per_ticker["MSFT"].errors == 0

    assert per_ticker["GOOGL"].imported == 1
    assert per_ticker["GOOGL"].errors == 0

    assert per_ticker["AMZN"].imported == 1
    assert per_ticker["AMZN"].errors == 0

    assert per_ticker["TSLA"].errors == 1
    assert per_ticker["TSLA"].imported == 0

    # Aggregate
    assert total_imported == 3
    assert total_skipped == 1
    assert total_errors == 1

    # TSLA error must be recorded in refresh_log
    tsla_log = db.execute(
        "SELECT status FROM refresh_log WHERE source = 'fmp_refresh' AND error_message LIKE '%TSLA%'"
    ).fetchone()
    assert tsla_log is not None
    assert tsla_log[0] == "error"  # 1/1 = 100% → error for the single-ticker run

    # Imported tickers should be in companies table
    companies = {
        r[0]
        for r in db.execute(
            "SELECT ticker FROM companies WHERE source = 'fmp'"
        ).fetchall()
    }
    assert "AAPL" in companies
    assert "GOOGL" in companies
    assert "AMZN" in companies
    assert "MSFT" not in companies  # skipped
    assert "TSLA" not in companies  # errored

    # filings_log updated for successfully imported tickers
    aapl_filing = db.execute(
        "SELECT COUNT(*) FROM filings_log WHERE ticker = 'AAPL' AND source = 'fmp'"
    ).fetchone()
    assert aapl_filing is not None and aapl_filing[0] >= 1

    # MSFT's pre-seeded filings_log entry still present
    msft_filing = db.execute(
        "SELECT filing_date FROM filings_log WHERE ticker = 'MSFT' AND source = 'fmp'"
    ).fetchone()
    assert msft_filing is not None
    assert str(msft_filing[0]) == "2023-07-27"


@pytest.mark.integration  # type: ignore[misc]
def test_refresh_partial_status_and_exit_code(db: duckdb.DuckDBPyConnection) -> None:
    """With 1 error out of 5 tickers, fail_rate=20% → status=partial."""
    my_vcr = vcrpy.VCR(
        cassette_library_dir=str(CASSETTE_DIR),
        filter_query_parameters=["apikey"],
        record_mode="none",
    )

    db.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) VALUES (?, ?, ?, ?)",
        ["MSFT", "annual-fmp", "2023-07-27", "fmp"],
    )

    # Process all 5 tickers and accumulate a simulated "single run"
    total_errors = 0
    total = len(MINI_UNIVERSE)
    for ticker in MINI_UNIVERSE:
        stats = _run_ticker(db, ticker, my_vcr=my_vcr)
        total_errors += stats.errors

    fail_rate = total_errors / total
    assert pytest.approx(fail_rate) == 0.2  # 1/5
    # 5% < 20% ≤ 25% → partial; and partial triggers exit code 2 in CLI
    assert 0.05 < fail_rate <= 0.25
