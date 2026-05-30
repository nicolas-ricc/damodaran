"""Integration tests for FX ingestion + USD normalization (M2.5).

Network is replayed from VCR cassettes in
``tests/fixtures/cassettes/fmp/``. The FX cassette is SYNTHETIC (hand-authored,
fabricated-but-realistic FMP historical-forex JSON) so the suite runs
deterministically offline. It MUST be re-recorded against the live FMP API with
a real BOT_FMP_API_KEY before production use.
"""

from __future__ import annotations

from datetime import date

import pytest

from bot.ingest.fmp import FmpClient
from bot.storage.db import apply_schema, connect
from bot.utils.fx import get_fx_rate, import_fx_rates, to_usd

API_KEY = "test-fmp-key"

# Reference: EUR/USD daily close on 2023-12-29 was ~1.1039 (synthetic cassette
# mirrors that real figure). The acceptance criterion is a ±0.1% match.
EXPECTED_EURUSD_2023_12_29 = 1.1039


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
def test_fetch_historical_fx_returns_rows() -> None:
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
        result = import_fx_rates(
            conn,
            api_key=API_KEY,
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
