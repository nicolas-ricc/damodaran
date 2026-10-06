"""Shape of the parsed FMP output, independent of the (synthetic) values.

Each cassette is replayed through ``FmpProvider`` in replay-only mode. The
exact-value checks stay in the integration tests; this file asserts only types
and nullness, so it keeps holding once the cassettes are re-recorded live.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import vcr

from bot.ingest.fmp import FmpClient, FmpProvider
from bot.ingest.provider import CompanyInfo, FundamentalsBundle
from tests.vcr_settings import VCR_CONFIG

CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes"

CASES = [
    ("universe/AAPL.yaml", "AAPL"),
    ("universe/MSFT.yaml", "MSFT"),
    ("universe/NVDA.yaml", "NVDA"),
    ("universe/NESN.SW.yaml", "NESN.SW"),
    ("universe/SAP.DE.yaml", "SAP.DE"),
    ("fmp/test_import_company_from_fmp_us_populates_db.yaml", "AAPL"),
    ("fmp/test_import_company_from_fmp_non_us_has_local_currency.yaml", "NESN.SW"),
]


def _replay(cassette: str) -> Any:
    return vcr.VCR(**VCR_CONFIG).use_cassette(str(CASSETTES / cassette))


def _assert_info_shape(info: CompanyInfo | None) -> None:
    assert info is not None
    assert isinstance(info.currency, str)
    assert len(info.currency) == 3 and info.currency.isalpha() and info.currency.isupper()
    assert isinstance(info.country, str)
    assert len(info.country) == 2 and info.country.isalpha() and info.country.isupper()
    assert info.ipo_date is None or isinstance(info.ipo_date, date)


def _assert_iso_date(value: object) -> None:
    # The parser emits DB-row dates as ISO strings (see plan assumption A1).
    assert isinstance(value, str)
    assert isinstance(date.fromisoformat(value), date)


def _assert_bundle_shape(bundle: FundamentalsBundle) -> None:
    _assert_info_shape(bundle.info)
    assert len(bundle.annual.annual) >= 1
    for row in [*bundle.annual.annual, *bundle.quarterly.quarterly]:
        assert type(row["fiscal_year"]) is int
        assert 1990 <= row["fiscal_year"] <= 2100
        _assert_iso_date(row["period_end_date"])
    for filing in bundle.filings:
        _assert_iso_date(filing["filing_date"])


@pytest.mark.parametrize(("cassette", "ticker"), CASES, ids=[c for c, _ in CASES])
def test_fundamentals_shape(cassette: str, ticker: str) -> None:
    with _replay(cassette), FmpProvider(api_key="shape-test") as provider:
        bundle = provider.fundamentals(ticker)
    _assert_bundle_shape(bundle)


@pytest.mark.parametrize(("cassette", "ticker"), CASES, ids=[c for c, _ in CASES])
def test_lookup_company_shape(cassette: str, ticker: str) -> None:
    # A separate cassette context: each recorded response replays only once.
    with _replay(cassette), FmpProvider(api_key="shape-test") as provider:
        info = provider.lookup_company(ticker)
    _assert_info_shape(info)


def test_historical_prices_market_cap_shape() -> None:
    # The fundamentals parser carries no market cap; FMP's EOD rows are where it lives.
    with (
        _replay("fmp/test_fetch_historical_prices_returns_rows.yaml"),
        FmpClient(api_key="shape-test") as client,
    ):
        rows = client.historical_prices("AAPL", start=date(2023, 12, 27), end=date(2023, 12, 29))
    assert rows
    assert any(row["market_cap"] is not None for row in rows)
    for row in rows:
        cap = row["market_cap"]
        assert cap is None or (isinstance(cap, float) and cap > 0)
