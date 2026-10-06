"""Integration tests for FX ingestion + USD normalization (M2.5).

Network is replayed from VCR cassettes in
``tests/fixtures/cassettes/fmp/``. The FX cassette is SYNTHETIC (hand-authored,
fabricated-but-realistic FMP historical-forex JSON) so the suite runs
deterministically offline. Re-record it against the live API with a real
BOT_FMP_API_KEY via ``uv run pytest -m integration --vcr-record=all``.
"""

from __future__ import annotations

from datetime import date

import pytest

from bot.ingest.fmp import FmpClient, FmpProvider
from bot.storage.db import apply_schema, connect
from bot.utils.fx import get_fx_rate, import_fx_rates, to_usd

API_KEY = "test-fmp-key"

# Reference: EUR/USD daily close on 2023-12-29 was ~1.1039 (synthetic cassette
# mirrors that real figure). The acceptance criterion is a ±0.1% match.
EXPECTED_EURUSD_2023_12_29 = 1.1039


@pytest.mark.integration
@pytest.mark.vcr
def test_fetch_historical_fx_returns_rows() -> None:
    # Exercises the low-level FmpClient directly (unrelated to the provider-port
    # rename) — start/end bound the fetch window, matching the recorded cassette.
    with FmpClient(api_key=API_KEY) as client:
        rows = client.historical_fx("EUR", start=date(2023, 12, 27), end=date(2023, 12, 29))
    by_date = {r["date"]: r["rate_to_usd"] for r in rows}
    assert by_date["2023-12-29"] == pytest.approx(EXPECTED_EURUSD_2023_12_29, rel=1e-3)


@pytest.mark.integration
@pytest.mark.vcr
def test_import_fx_rates_populates_currencies_table() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    try:
        with FmpProvider(api_key=API_KEY) as provider:
            result = import_fx_rates(
                conn,
                provider=provider,
                currency="EUR",
                start=date(2023, 12, 27),
                end=date(2023, 12, 29),
            )
        assert result.is_success()
        assert result.rows_affected >= 1

        # Acceptance: EUR/USD at a known date matches expectation within +/-0.1%.
        rate = get_fx_rate(conn, "EUR", date(2023, 12, 29))
        assert rate is not None
        assert rate == pytest.approx(EXPECTED_EURUSD_2023_12_29, rel=1e-3)

        # to_usd uses the same nearest-prior lookup. A period-end on the
        # following (weekend) day still resolves to the 2023-12-29 close.
        usd = to_usd(conn, 1_000_000.0, "EUR", date(2023, 12, 31))
        assert usd is not None
        assert usd == pytest.approx(1_000_000.0 * EXPECTED_EURUSD_2023_12_29, rel=1e-3)
    finally:
        conn.close()
