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


def test_daily_prices_without_key_fails_with_a_clear_message() -> None:
    import pytest as _pytest

    provider = EdgarTiingoProvider(
        sec_user_agent="Test test@example.com",
        tiingo_api_key="",
        sec_transport=httpx.MockTransport(_edgar_handler),
    )
    with _pytest.raises(RuntimeError, match="BOT_TIINGO_API_KEY"):
        provider.daily_prices("AAPL", since=None)


# ---------------------------------------------------------------------------
# #275 — the governance filings of the submissions index
# ---------------------------------------------------------------------------


def test_fundamentals_includes_the_governance_filings() -> None:
    bundle = _provider().fundamentals("AAPL")
    keys = {(r["filing_type"], r["filing_date"], r.get("items")) for r in bundle.filings}
    assert keys >= {("8-K", "2026-05-20", "4.01,9.01"), ("NT 10-Q", "2026-04-30", None)}
    governance = [r for r in bundle.filings if r["filing_type"] in {"8-K", "NT 10-Q"}]
    assert {r["source"] for r in governance} == {"edgar_tiingo"}


def test_import_company_stores_the_governance_filings() -> None:
    from bot.ingest.universe import import_company
    from bot.storage.db import apply_schema, connect

    conn = connect(":memory:")
    apply_schema(conn)
    import_company(conn, ticker="AAPL", provider=_provider())
    rows = conn.execute(
        "SELECT filing_type, filing_date, items FROM filings_log "
        "WHERE ticker = 'AAPL' AND (filing_type LIKE 'NT %' OR items IS NOT NULL)"
    ).fetchall()
    assert set(rows) == {
        ("8-K", date(2026, 5, 20), "4.01,9.01"),
        ("NT 10-Q", date(2026, 4, 30), None),
    }
