"""EdgarTiingoProvider — EDGAR fundamentals + Tiingo EOD prices behind the port."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from bot.ingest.edgar_tiingo import EdgarTiingoProvider
from bot.ingest.provider import MarketDataProvider

# Reuse the EDGAR fixture handler proven by the sibling adapter's tests.
from tests.unit.test_edgar_stooq_provider import _edgar_handler

_PRICES = [
    {"date": "2026-09-14T00:00:00.000Z", "close": 229.87, "volume": 41250300},
    {"date": "2026-09-15T00:00:00.000Z", "close": 231.42, "volume": 35520400},
]


def _tiingo_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("authorization") == "Token test-key"
    assert request.url.path == "/tiingo/daily/aapl/prices"
    return httpx.Response(200, json=_PRICES)


def _provider() -> EdgarTiingoProvider:
    return EdgarTiingoProvider(
        sec_user_agent="Test test@example.com",
        tiingo_api_key="test-key",
        sec_transport=httpx.MockTransport(_edgar_handler),
        tiingo_transport=httpx.MockTransport(_tiingo_handler),
    )


def test_satisfies_the_port_protocol() -> None:
    assert isinstance(_provider(), MarketDataProvider)
    assert _provider().name == "edgar_tiingo"


def test_fundamentals_come_from_edgar_and_restamp_source() -> None:
    bundle = _provider().fundamentals("AAPL")
    assert bundle.info is not None and bundle.info.industry == "Electronic Computers"
    assert bundle.annual.company["source"] == "edgar_tiingo"
    assert bundle.annual.annual[0]["revenue"] == pytest.approx(400000000000)


def test_daily_prices_come_from_tiingo_with_market_cap_on_newest_fresh_bar() -> None:
    bars = _provider().daily_prices("AAPL", since=date(2026, 9, 1))
    assert [b.date for b in bars] == [date(2026, 9, 14), date(2026, 9, 15)]
    newest = max(bars, key=lambda b: b.date)
    if (date.today() - newest.date).days <= 7:
        assert newest.market_cap == pytest.approx(newest.close * 14840392000)  # type: ignore[operator]
    else:
        assert newest.market_cap is None
    assert all(b.market_cap is None for b in bars if b is not newest)


def test_fx_rates_usd_is_a_noop() -> None:
    assert _provider().fx_rates("USD", since=None) == []


def test_latest_filing_date_reads_submissions() -> None:
    assert _provider().latest_filing_date("AAPL") == date(2026, 8, 1)


def test_close_then_reuse_reopens() -> None:
    provider = _provider()
    assert provider.lookup_company("AAPL") is not None
    provider.close()
    assert provider.lookup_company("AAPL") is not None
