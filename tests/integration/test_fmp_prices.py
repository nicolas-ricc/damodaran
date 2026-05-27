"""Integration tests for import_prices_from_fmp using VCR cassettes."""

from datetime import date

import duckdb
import pytest

from bot.ingest.fmp import import_prices_from_fmp
from bot.storage.db import apply_schema


@pytest.fixture  # type: ignore[misc]
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "prices")


@pytest.fixture  # type: ignore[misc]
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["apikey"],
        "record_mode": "none",
    }


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_import_prices_aapl_inserts_rows() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)

    result = import_prices_from_fmp(conn, "AAPL", api_key="test_key")

    assert result.status == "success"
    assert result.rows_affected == 3
    assert result.details["currency"] == "USD"

    rows = conn.execute(
        "SELECT ticker, date, close, volume FROM prices_daily WHERE ticker = 'AAPL'"
        " ORDER BY date"
    ).fetchall()
    assert len(rows) == 3
    assert rows[0] == ("AAPL", date(2024, 1, 3), 184.25, 58414500)
    assert rows[2] == ("AAPL", date(2024, 1, 5), 181.18, 62303300)

    currency_rows = conn.execute(
        "SELECT currency FROM prices_daily WHERE ticker = 'AAPL' LIMIT 1"
    ).fetchone()
    assert currency_rows is not None
    assert currency_rows[0] == "USD"


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_import_prices_second_run_inserts_zero() -> None:
    """Second run inserts zero new rows when the DB is already current."""
    conn = duckdb.connect(":memory:")
    apply_schema(conn)

    # Pre-seed DB so max(date) = 2024-01-05 — simulates a completed first run.
    for d, close, vol in [
        ("2024-01-03", 184.25, 58414500),
        ("2024-01-04", 181.91, 71983900),
        ("2024-01-05", 181.18, 62303300),
    ]:
        conn.execute(
            "INSERT INTO prices_daily (ticker, date, close, volume, currency)"
            " VALUES ('AAPL', ?, ?, ?, 'USD')",
            [d, close, vol],
        )

    # Importer should detect max(date)=2024-01-05, fetch from=2024-01-05,
    # receive only that date back, filter it out (already stored), insert 0.
    result = import_prices_from_fmp(conn, "AAPL", api_key="test_key")

    assert result.status == "success"
    assert result.rows_affected == 0

    count = conn.execute(
        "SELECT COUNT(*) FROM prices_daily WHERE ticker = 'AAPL'"
    ).fetchone()
    assert count is not None
    assert count[0] == 3
