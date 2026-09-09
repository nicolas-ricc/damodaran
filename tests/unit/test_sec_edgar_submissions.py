"""EDGAR submissions endpoint — CompanyInfo and latest filing date."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from bot.ingest.provider import ProviderRateLimitError
from bot.ingest.sec_edgar import (
    EdgarRateLimitError,
    SecEdgarClient,
    latest_filing_date_from_submissions,
    parse_submissions_info,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "edgar"


def _submissions() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "aapl_submissions.json").read_text("utf-8"))
    return data


def test_parse_submissions_info_maps_name_sic_and_exchange() -> None:
    info = parse_submissions_info("aapl", _submissions())
    assert info.ticker == "AAPL"
    assert info.name == "Apple Inc."
    assert info.industry == "Electronic Computers"  # sicDescription is the mapping key
    assert info.exchange_short_name == "Nasdaq"
    assert info.country == "US"
    assert info.currency == "USD"
    assert info.is_actively_trading is True
    assert info.ipo_date is None  # EDGAR has no IPO date; documented in ADR 0007


def test_parse_submissions_info_survives_missing_sic_and_exchanges() -> None:
    data = _submissions()
    data["sicDescription"] = ""
    data["exchanges"] = []
    info = parse_submissions_info("AAPL", data)
    assert info.industry is None
    assert info.exchange_short_name is None


def test_latest_filing_date_considers_only_financial_forms() -> None:
    # The 8-K dated 2026-07-15 must not win over the 10-Q dated 2026-08-01.
    assert latest_filing_date_from_submissions(_submissions()) == date(2026, 8, 1)


def test_latest_filing_date_none_when_no_recent_filings() -> None:
    assert latest_filing_date_from_submissions({"filings": {"recent": {}}}) is None


def test_fetch_submissions_hits_the_cik_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_submissions())

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    data = client.fetch_submissions("0000320193")
    assert data["name"] == "Apple Inc."
    assert seen == ["https://data.sec.gov/submissions/CIK0000320193.json"]


def test_edgar_429_raises_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(EdgarRateLimitError):
        client.fetch_submissions("0000320193")


def test_edgar_rate_limit_is_a_provider_rate_limit() -> None:
    assert issubclass(EdgarRateLimitError, ProviderRateLimitError)
