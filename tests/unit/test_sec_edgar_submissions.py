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
    LATE_FILING_FORMS,
    EdgarRateLimitError,
    SecEdgarClient,
    governance_filings_from_submissions,
    is_auditor_change,
    is_late_filing,
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


# ---------------------------------------------------------------------------
# Governance filings: auditor-change 8-Ks and NT notices (#275)
# ---------------------------------------------------------------------------


def _recent(**arrays: list[Any]) -> dict[str, Any]:
    return {"filings": {"recent": arrays}}


def _with_entry(form: str, filed: str, items: str) -> dict[str, Any]:
    data = _submissions()
    recent = data["filings"]["recent"]
    recent["form"].append(form)
    recent["filingDate"].append(filed)
    recent["accessionNumber"].append("0000320193-26-000099")
    recent["items"].append(items)
    return data


def _keys(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (r["filing_type"], r["filing_date"], r["accession_number"], r["items"]) for r in rows
    ]


@pytest.mark.parametrize(
    ("form", "items"),
    [("8-K", " 4.01 , 9.01"), ("8-K", "4.01"), ("8-K/A", "4.01"), ("8-K", "4.01,9.01")],
)
def test_is_auditor_change_matches_the_item_token(form: str, items: str) -> None:
    assert is_auditor_change(form, items) is True


@pytest.mark.parametrize(
    ("form", "items"),
    [
        ("8-K", "2.02,9.01"),
        ("8-K", "14.01"),
        ("8-K", None),
        ("8-K", ""),
        ("10-K", "4.01"),
        (None, "4.01"),
    ],
)
def test_is_auditor_change_rejects_other_items_and_forms(
    form: str | None, items: str | None
) -> None:
    assert is_auditor_change(form, items) is False


def test_is_late_filing_matches_the_nt_forms() -> None:
    assert all(is_late_filing(form) for form in LATE_FILING_FORMS)
    assert frozenset({"NT 10-K", "NT 10-K/A", "NT 10-Q", "NT 10-Q/A"}) == LATE_FILING_FORMS
    assert not any(is_late_filing(form) for form in ("10-K", "NT 20-F", "8-K", None))


def test_governance_filings_from_fixture_returns_the_two_governance_rows() -> None:
    rows = governance_filings_from_submissions("aapl", _submissions())
    assert _keys(rows) == [
        ("8-K", "2026-05-20", "0000320193-26-000050", "4.01,9.01"),
        ("NT 10-Q", "2026-04-30", "0000320193-26-000041", None),
    ]
    assert all(r["ticker"] == "AAPL" and r["source"] == "sec_edgar" for r in rows)


def test_governance_filings_without_items_array_keeps_only_nt_rows() -> None:
    data = _submissions()
    del data["filings"]["recent"]["items"]
    rows = governance_filings_from_submissions("AAPL", data)
    assert _keys(rows) == [("NT 10-Q", "2026-04-30", "0000320193-26-000041", None)]


def test_governance_filings_merges_items_of_same_form_and_date() -> None:
    data = _recent(
        form=["8-K", "8-K"],
        filingDate=["2026-05-20", "2026-05-20"],
        accessionNumber=["A", "B"],
        items=["4.01", "9.01"],
    )
    assert _keys(governance_filings_from_submissions("AAPL", data)) == [
        ("8-K", "2026-05-20", "A", "4.01,9.01")
    ]


def test_governance_filings_merged_group_keeps_the_first_governance_accession() -> None:
    data = _recent(
        form=["8-K", "8-K"],
        filingDate=["2026-05-20", "2026-05-20"],
        accessionNumber=["A", "B"],
        items=["9.01", "4.01"],
    )
    assert _keys(governance_filings_from_submissions("AAPL", data)) == [
        ("8-K", "2026-05-20", "B", "4.01,9.01")
    ]


def test_governance_filings_skips_a_day_of_ordinary_8ks() -> None:
    data = _recent(
        form=["8-K", "8-K"],
        filingDate=["2026-05-20", "2026-05-20"],
        accessionNumber=["A", "B"],
        items=["2.02", "9.01"],
    )
    assert governance_filings_from_submissions("AAPL", data) == []


def test_governance_filings_drops_unparseable_dates() -> None:
    data = _recent(
        form=["NT 10-K", "NT 10-Q"],
        filingDate=["not-a-date", "2026-04-30"],
        accessionNumber=["A", "B"],
        items=["", ""],
    )
    assert _keys(governance_filings_from_submissions("AAPL", data)) == [
        ("NT 10-Q", "2026-04-30", "B", None)
    ]
    assert latest_filing_date_from_submissions(data) == date(2026, 4, 30)


def test_governance_filings_tolerates_short_items_array() -> None:
    data = _recent(
        form=["8-K", "NT 10-K", "8-K"],
        filingDate=["2026-06-01", "2026-05-01", "2026-04-01"],
        accessionNumber=["A", "B", "C"],
        items=["4.01"],
    )
    assert _keys(governance_filings_from_submissions("AAPL", data)) == [
        ("8-K", "2026-06-01", "A", "4.01"),
        ("NT 10-K", "2026-05-01", "B", None),
    ]


def test_governance_filings_null_items_is_no_items() -> None:
    data = _recent(
        form=["NT 10-K", "8-K"],
        filingDate=["2026-05-01", "2026-04-01"],
        accessionNumber=["A", "B"],
        items=[None, None],
    )
    assert _keys(governance_filings_from_submissions("AAPL", data)) == [
        ("NT 10-K", "2026-05-01", "A", None)
    ]


def test_governance_filings_of_an_empty_payload_is_empty() -> None:
    assert governance_filings_from_submissions("AAPL", {}) == []
    assert governance_filings_from_submissions("AAPL", {"filings": {"recent": {}}}) == []


def test_latest_filing_date_counts_auditor_changes() -> None:
    assert latest_filing_date_from_submissions(_with_entry("8-K", "2026-09-01", "4.01")) == date(
        2026, 9, 1
    )


def test_latest_filing_date_ignores_ordinary_8ks() -> None:
    assert latest_filing_date_from_submissions(_with_entry("8-K", "2026-09-01", "2.02")) == date(
        2026, 8, 1
    )


def test_latest_filing_date_counts_late_filings() -> None:
    assert latest_filing_date_from_submissions(_with_entry("NT 10-K", "2026-09-15", "")) == date(
        2026, 9, 15
    )


def test_every_governance_date_of_the_watermark_is_stored() -> None:
    data = _with_entry("NT 10-K", "2026-09-15", "")
    rows = governance_filings_from_submissions("AAPL", data)
    assert ("NT 10-K", "2026-09-15") in {(r["filing_type"], r["filing_date"]) for r in rows}
