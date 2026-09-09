"""EdgarStooqProvider — the free-stack adapter behind the MarketDataProvider port."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from bot.ingest.edgar_stooq import EdgarStooqProvider
from bot.ingest.provider import MarketDataProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_TICKER_TABLE = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _edgar_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("company_tickers.json"):
        return httpx.Response(200, json=_TICKER_TABLE)
    if "submissions/CIK0000320193" in url:
        payload: dict[str, Any] = json.loads(
            (FIXTURES / "edgar" / "aapl_submissions.json").read_text("utf-8")
        )
        return httpx.Response(200, json=payload)
    if "companyconcept/CIK0000320193" in url:
        return httpx.Response(
            200, json=json.loads((FIXTURES / "edgar" / "aapl_shares_concept.json").read_text("utf-8"))
        )
    if "companyfacts/CIK0000320193" in url:
        # Minimal but real-shaped company-facts body: one revenue fact.
        return httpx.Response(
            200,
            json={
                "cik": 320193,
                "entityName": "Apple Inc.",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "units": {
                                "USD": [
                                    {
                                        "end": "2025-09-27",
                                        "val": 400000000000,
                                        "fy": 2025,
                                        "fp": "FY",
                                        "form": "10-K",
                                        "filed": "2025-11-01",
                                        "accn": "0000320193-25-000106",
                                    }
                                ]
                            }
                        }
                    }
                },
            },
        )
    raise AssertionError(f"unexpected EDGAR request: {url}")


def _stooq_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, text=(FIXTURES / "stooq" / "aapl_daily.csv").read_text(encoding="utf-8")
    )


def _provider() -> EdgarStooqProvider:
    return EdgarStooqProvider(
        sec_user_agent="Test test@example.com",
        sec_transport=httpx.MockTransport(_edgar_handler),
        stooq_transport=httpx.MockTransport(_stooq_handler),
    )


def test_satisfies_the_port_protocol() -> None:
    assert isinstance(_provider(), MarketDataProvider)
    assert _provider().name == "edgar_stooq"


def test_lookup_company_carries_the_sic_description_as_industry() -> None:
    info = _provider().lookup_company("aapl")
    assert info is not None
    assert info.name == "Apple Inc."
    assert info.industry == "Electronic Computers"


def test_lookup_unknown_ticker_returns_none() -> None:
    def edgar(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("company_tickers.json"):
            return httpx.Response(200, json=_TICKER_TABLE)
        raise AssertionError("should not fetch beyond the ticker table")

    provider = EdgarStooqProvider(
        sec_user_agent="Test test@example.com",
        sec_transport=httpx.MockTransport(edgar),
        stooq_transport=httpx.MockTransport(_stooq_handler),
    )
    assert provider.lookup_company("NOPE") is None


def test_fundamentals_bundles_info_annual_and_filings() -> None:
    bundle = _provider().fundamentals("AAPL")
    assert bundle.info is not None and bundle.info.industry == "Electronic Computers"
    assert bundle.annual.company["source"] == "sec_edgar"
    assert len(bundle.annual.annual) == 1
    assert bundle.annual.annual[0]["revenue"] == pytest.approx(400000000000)
    assert bundle.quarterly.quarterly == []


def test_daily_prices_come_from_stooq_with_market_cap_on_newest_fresh_bar() -> None:
    bars = _provider().daily_prices("AAPL", since=None)
    assert len(bars) == 3
    newest = max(bars, key=lambda b: b.date)
    if (date.today() - newest.date).days <= 7:
        assert newest.market_cap == pytest.approx(newest.close * 14840392000)  # type: ignore[operator]
    else:  # fixture aged past freshness — cap must stay honest: None
        assert newest.market_cap is None
    assert all(b.market_cap is None for b in bars if b is not newest)


def test_fx_rates_usd_is_a_noop() -> None:
    assert _provider().fx_rates("USD", since=None) == []


def test_fx_rates_non_usd_returns_empty_and_does_not_raise() -> None:
    assert _provider().fx_rates("EUR", since=None) == []


def test_latest_filing_date_reads_submissions() -> None:
    assert _provider().latest_filing_date("AAPL") == date(2026, 8, 1)


def test_close_then_reuse_reopens() -> None:
    provider = _provider()
    assert provider.lookup_company("AAPL") is not None
    provider.close()
    assert provider.lookup_company("AAPL") is not None
