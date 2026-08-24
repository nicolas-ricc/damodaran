"""Integration tests for FMP daily EOD price ingestion (M2.4).

Network is replayed from VCR cassettes in ``tests/fixtures/cassettes/fmp/``.
The price cassette is SYNTHETIC (hand-authored, fabricated-but-realistic FMP
historical-price JSON) so the suite runs deterministically offline. It MUST be
re-recorded against the live FMP API with a real BOT_FMP_API_KEY before
production use.
"""

from __future__ import annotations

from datetime import date

import pytest

from bot.ingest.fmp import FmpProvider
from bot.ingest.universe import refresh_prices
from bot.storage.db import apply_schema, connect

API_KEY = "test-fmp-key"


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "fmp")


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": [("apikey", "SCRUBBED")],
        "record_mode": "once",
    }


@pytest.mark.integration
@pytest.mark.vcr
def test_fetch_historical_prices_returns_rows() -> None:
    with FmpProvider(api_key=API_KEY) as provider:
        bars = provider.daily_prices("AAPL", date(2023, 12, 27))
    by_date = {b.date.isoformat(): b for b in bars}
    assert "2023-12-29" in by_date
    bar = by_date["2023-12-29"]
    assert bar.close == pytest.approx(192.53)
    assert bar.volume == pytest.approx(42672148.0)
    assert bar.market_cap == pytest.approx(2994000000000.0)


@pytest.mark.integration
@pytest.mark.vcr
def test_import_prices_populates_table() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    try:
        conn.execute(
            "INSERT INTO companies (ticker, name, currency, source) "
            "VALUES ('AAPL', 'Apple Inc.', 'USD', 'fmp')"
        )
        with FmpProvider(api_key=API_KEY) as provider:
            result = refresh_prices(
                conn, provider=provider, tickers=["AAPL"], since_date=date(2023, 12, 27)
            )
        assert result.status == "success"
        assert result.imported == 1
        assert result.outcomes[0].rows_affected == 3

        rows = conn.execute(
            "SELECT date, close, volume, market_cap, currency, source "
            "FROM prices_daily WHERE ticker = 'AAPL' ORDER BY date"
        ).fetchall()
        assert len(rows) == 3
        # Most recent stored close matches the synthetic 2023-12-29 figure.
        last = rows[-1]
        assert str(last[0]) == "2023-12-29"
        assert last[1] == pytest.approx(192.53)
        assert last[4] == "USD"
        assert last[5] == "fmp"
    finally:
        conn.close()


@pytest.mark.integration
@pytest.mark.vcr
def test_second_run_is_incremental_zero_inserts() -> None:
    """A second import with already-current data performs zero new INSERTs.

    Incremental semantics: the fetch's ``since`` is the newest stored date
    itself (``_max_price_date``, inclusive) — the DELETE+INSERT upsert makes
    re-fetching that day idempotent, so a re-run with no new remote data still
    performs zero net-new rows.
    """
    conn = connect(":memory:")
    apply_schema(conn)
    try:
        conn.execute(
            "INSERT INTO companies (ticker, name, currency, source) "
            "VALUES ('AAPL', 'Apple Inc.', 'USD', 'fmp')"
        )
        with FmpProvider(api_key=API_KEY) as provider:
            first = refresh_prices(
                conn, provider=provider, tickers=["AAPL"], since_date=date(2023, 12, 27)
            )
        assert first.status == "success"
        assert first.outcomes[0].rows_affected == 3

        count_after_first = conn.execute(
            "SELECT count(*) FROM prices_daily WHERE ticker = 'AAPL'"
        ).fetchone()
        assert count_after_first is not None
        assert count_after_first[0] == 3

        # Second run: no since_date given, so the fetch starts at the newest
        # stored date (2023-12-29), for which the cassette returns an empty
        # history -> no new INSERTs.
        with FmpProvider(api_key=API_KEY) as provider:
            second = refresh_prices(conn, provider=provider, tickers=["AAPL"])
        assert second.status == "success"
        assert second.outcomes[0].rows_affected == 0

        count_after_second = conn.execute(
            "SELECT count(*) FROM prices_daily WHERE ticker = 'AAPL'"
        ).fetchone()
        assert count_after_second is not None
        assert count_after_second[0] == 3
    finally:
        conn.close()
