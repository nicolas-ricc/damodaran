"""Unit tests for the FX / currency-normalization helpers (M2.5)."""

from __future__ import annotations

from datetime import date

import pytest

from bot.ingest.fmp import FmpClient
from bot.storage.db import apply_schema, connect
from bot.utils.fx import get_fx_rate, import_fx_rates, to_usd, upsert_fx_rates


@pytest.fixture
def conn():
    c = connect(":memory:")
    apply_schema(c)
    yield c
    c.close()


def _seed(conn) -> None:
    upsert_fx_rates(
        conn,
        currency="EUR",
        rows=[
            {"date": "2023-12-28", "rate_to_usd": 1.1050},
            {"date": "2023-12-29", "rate_to_usd": 1.1039},
            {"date": "2024-01-02", "rate_to_usd": 1.0950},
        ],
    )


def test_usd_is_identity_without_any_data(conn) -> None:
    # USD never needs an FX row; it is the numeraire.
    assert get_fx_rate(conn, "USD", date(2024, 1, 1)) == 1.0
    assert to_usd(conn, 1234.5, "USD", date(2024, 1, 1)) == 1234.5


def test_currency_case_is_normalized(conn) -> None:
    _seed(conn)
    assert get_fx_rate(conn, "eur", date(2023, 12, 29)) == pytest.approx(1.1039)


def test_exact_date_match(conn) -> None:
    _seed(conn)
    assert get_fx_rate(conn, "EUR", date(2023, 12, 29)) == pytest.approx(1.1039)


def test_nearest_prior_lookup_on_weekend(conn) -> None:
    # 2023-12-30 and -31 are a weekend; 2024-01-01 is a holiday. The nearest
    # prior available trading day is 2023-12-29.
    _seed(conn)
    assert get_fx_rate(conn, "EUR", date(2023, 12, 31)) == pytest.approx(1.1039)
    assert get_fx_rate(conn, "EUR", date(2024, 1, 1)) == pytest.approx(1.1039)


def test_nearest_prior_never_uses_a_future_rate(conn) -> None:
    _seed(conn)
    # 2024-01-02 exists, but for 2024-01-01 we must use the prior 2023-12-29,
    # never the future 2024-01-02.
    assert get_fx_rate(conn, "EUR", date(2024, 1, 1)) == pytest.approx(1.1039)


def test_missing_rate_before_first_observation_returns_none(conn) -> None:
    _seed(conn)
    assert get_fx_rate(conn, "EUR", date(2020, 1, 1)) is None


def test_unknown_currency_returns_none(conn) -> None:
    assert get_fx_rate(conn, "XYZ", date(2024, 1, 1)) is None


def test_to_usd_converts_with_nearest_prior_rate(conn) -> None:
    _seed(conn)
    # period-end on a weekend resolves to 2023-12-29 close of 1.1039
    assert to_usd(conn, 1_000_000.0, "EUR", date(2023, 12, 31)) == pytest.approx(1_103_900.0)


def test_to_usd_raises_when_rate_unavailable(conn) -> None:
    _seed(conn)
    with pytest.raises(LookupError, match="No FX rate"):
        to_usd(conn, 100.0, "EUR", date(2020, 1, 1))


def test_to_usd_passes_through_none_amount(conn) -> None:
    assert to_usd(conn, None, "EUR", date(2024, 1, 1)) is None


def test_upsert_is_idempotent_and_updates(conn) -> None:
    upsert_fx_rates(conn, currency="EUR", rows=[{"date": "2024-01-02", "rate_to_usd": 1.0950}])
    upsert_fx_rates(conn, currency="EUR", rows=[{"date": "2024-01-02", "rate_to_usd": 1.0951}])
    count = conn.execute("SELECT COUNT(*) FROM currencies WHERE currency = 'EUR'").fetchone()
    assert count == (1,)
    assert get_fx_rate(conn, "EUR", date(2024, 1, 2)) == pytest.approx(1.0951)


def test_upsert_returns_row_count(conn) -> None:
    n = upsert_fx_rates(
        conn,
        currency="EUR",
        rows=[
            {"date": "2024-01-02", "rate_to_usd": 1.0950},
            {"date": "2024-01-03", "rate_to_usd": 1.0920},
        ],
    )
    assert n == 2


def test_upsert_empty_is_noop(conn) -> None:
    assert upsert_fx_rates(conn, currency="EUR", rows=[]) == 0


def test_historical_fx_usd_is_noop_no_request() -> None:
    # USD is the numeraire; no HTTP request is made, so no cassette is needed.
    with FmpClient(api_key="test-fmp-key") as client:
        assert client.historical_fx("USD") == []


def test_import_fx_usd_is_success_with_zero_rows(conn) -> None:
    # USD needs no rows; the run still succeeds and is logged.
    result = import_fx_rates(conn, api_key="test-fmp-key", currency="USD")
    assert result.is_success()
    assert result.rows_affected == 0
    logged = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'fmp_fx'"
    ).fetchone()
    assert logged == ("success",)


def test_import_fx_records_error_on_bad_key(conn) -> None:
    # Empty key fails fast inside FmpClient construction; the run is recorded as
    # an error in refresh_log and never raises out of import_fx_rates.
    result = import_fx_rates(conn, api_key="", currency="EUR")
    assert result.status == "error"
    assert result.error_message is not None
    logged = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'fmp_fx'"
    ).fetchone()
    assert logged == ("error",)
