"""Unit tests for the FX / currency-normalization helpers (M2.5)."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from bot.ingest.provider import FxRate
from bot.storage.db import apply_schema, connect
from bot.utils.fx import (
    ConvertedPrice,
    convert_price,
    get_fx_rate,
    import_fx_rates,
    to_usd,
    upsert_fx_rates,
)
from tests.fake_provider import FakeProvider


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
        rates=[
            FxRate(date=date(2023, 12, 28), rate_to_usd=1.1050),
            FxRate(date=date(2023, 12, 29), rate_to_usd=1.1039),
            FxRate(date=date(2024, 1, 2), rate_to_usd=1.0950),
        ],
        source="fmp",
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
    upsert_fx_rates(
        conn,
        currency="EUR",
        rates=[FxRate(date=date(2024, 1, 2), rate_to_usd=1.0950)],
        source="fmp",
    )
    upsert_fx_rates(
        conn,
        currency="EUR",
        rates=[FxRate(date=date(2024, 1, 2), rate_to_usd=1.0951)],
        source="fmp",
    )
    count = conn.execute("SELECT COUNT(*) FROM currencies WHERE currency = 'EUR'").fetchone()
    assert count == (1,)
    assert get_fx_rate(conn, "EUR", date(2024, 1, 2)) == pytest.approx(1.0951)


def test_upsert_returns_row_count(conn) -> None:
    n = upsert_fx_rates(
        conn,
        currency="EUR",
        rates=[
            FxRate(date=date(2024, 1, 2), rate_to_usd=1.0950),
            FxRate(date=date(2024, 1, 3), rate_to_usd=1.0920),
        ],
        source="fmp",
    )
    assert n == 2


def test_upsert_empty_is_noop(conn) -> None:
    assert upsert_fx_rates(conn, currency="EUR", rates=[], source="fmp") == 0


def test_import_fx_usd_is_success_with_zero_rows(conn) -> None:
    # USD needs no rows; the run still succeeds and is logged. The port is never
    # asked for USD rates (there is nothing to fetch for the numeraire).
    provider = FakeProvider()
    result = import_fx_rates(conn, provider=provider, currency="USD")
    assert result.is_success()
    assert result.rows_affected == 0
    assert provider.calls == []
    logged = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'fake_fx'"
    ).fetchone()
    assert logged == ("success",)


def test_import_fx_rates_writes_rates_through_the_port(conn) -> None:
    provider = FakeProvider(fx={"EUR": [FxRate(date=date(2026, 1, 2), rate_to_usd=1.08)]})
    result = import_fx_rates(conn, provider=provider, currency="EUR")
    assert result.is_success()
    assert conn.execute(
        "SELECT rate_to_usd FROM currencies WHERE currency='EUR'"
    ).fetchone() == (1.08,)


def test_import_fx_records_error_on_provider_failure(conn) -> None:
    class _BoomingProvider(FakeProvider):
        def fx_rates(self, currency, since):  # type: ignore[override]
            raise ValueError("fmp down")

    result = import_fx_rates(conn, provider=_BoomingProvider(), currency="EUR")
    assert result.status == "error"
    assert result.error_message is not None
    logged = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'fake_fx'"
    ).fetchone()
    assert logged == ("error",)


def test_import_fx_end_trims_rows_client_side(conn) -> None:
    """The port has no ``end`` — ``import_fx_rates`` trims the returned rows itself."""
    provider = FakeProvider(
        fx={
            "EUR": [
                FxRate(date=date(2023, 12, 28), rate_to_usd=1.1050),
                FxRate(date=date(2023, 12, 29), rate_to_usd=1.1039),
                FxRate(date=date(2024, 1, 2), rate_to_usd=1.0950),
            ]
        }
    )
    result = import_fx_rates(
        conn, provider=provider, currency="EUR", start=date(2023, 12, 27), end=date(2023, 12, 29)
    )
    assert result.rows_affected == 2
    rows = conn.execute(
        "SELECT date FROM currencies WHERE currency = 'EUR' ORDER BY date"
    ).fetchall()
    assert [str(r[0]) for r in rows] == ["2023-12-28", "2023-12-29"]


# --------------------------------------------------------------------------- #
# convert_price (#222): the one listing -> valuation price conversion          #
# --------------------------------------------------------------------------- #


def _no_rate(_currency: str) -> float | None:
    return None


@pytest.mark.parametrize(
    ("listing", "valuation"), [("usd", "USD"), (" eur", "EUR"), ("EUR", "eur ")]
)
def test_convert_price_same_currency_any_case(listing: str, valuation: str) -> None:
    assert convert_price(110.0, listing, valuation, _no_rate) == ConvertedPrice(110.0, None)


@pytest.mark.parametrize(("listing", "valuation"), [(None, "EUR"), ("USD", None), (None, None)])
def test_convert_price_unknown_currency_uses_close(
    listing: str | None, valuation: str | None
) -> None:
    assert convert_price(110.0, listing, valuation, _no_rate) == ConvertedPrice(110.0, None)


def test_convert_price_cross_rate() -> None:
    rates = {"USD": 1.0, "EUR": 1.10}
    converted = convert_price(110.0, "USD", "EUR", rates.get)
    assert converted.price == pytest.approx(100.0)
    assert converted.fx_rate == pytest.approx(1 / 1.10)


def test_convert_price_usd_needs_no_row(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_fx_rates(
        conn, currency="EUR", rates=[FxRate(date(2026, 5, 29), 1.10)], source="test"
    )
    converted = convert_price(
        110.0, "usd", "eur", lambda ccy: get_fx_rate(conn, ccy, date(2026, 5, 29))
    )
    assert converted.price == pytest.approx(100.0)


@pytest.mark.parametrize("eur_rate", [None, 0.0, -1.0])
def test_convert_price_missing_or_non_positive_rate(eur_rate: float | None) -> None:
    rates = {"USD": 1.0, "EUR": eur_rate}
    assert convert_price(110.0, "USD", "EUR", rates.get) == ConvertedPrice(None, None)
    assert convert_price(110.0, "EUR", "USD", rates.get) == ConvertedPrice(None, None)
