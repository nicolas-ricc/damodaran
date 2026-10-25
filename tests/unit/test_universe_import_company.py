"""``universe.import_company`` reports annual periods still without revenue (#123)."""

from __future__ import annotations

from typing import Any

import duckdb
from structlog.testing import capture_logs

from bot.ingest.provider import FundamentalsBundle, ParsedCompanyData
from bot.ingest.universe import import_company
from bot.storage.db import apply_schema
from tests.fake_provider import FakeProvider


def _row(year: int, revenue: float | None) -> dict[str, Any]:
    return {
        "ticker": "ACME",
        "fiscal_year": year,
        "period_end_date": f"{year}-12-31",
        "currency": "USD",
        "revenue": revenue,
        "is_restated": False,
        "source": "fake",
    }


def _bundle(annual: list[dict[str, Any]]) -> FundamentalsBundle:
    company = {"ticker": "ACME", "name": "Acme", "currency": "USD", "source": "fake"}
    return FundamentalsBundle(
        info=None,
        annual=ParsedCompanyData(company=company, annual=annual),
        quarterly=ParsedCompanyData(company=company),
        filings=[],
    )


def _import(annual: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    provider = FakeProvider(bundles={"ACME": _bundle(annual)})
    with capture_logs() as logs:
        result = import_company(conn, ticker="ACME", provider=provider)
    return result, [e for e in logs if e["event"] == "ingest.annual_revenue_null"]


def test_import_company_reports_null_revenue_count() -> None:
    result, events = _import([_row(2023, 1e9), _row(2024, None), _row(2025, 2e9)])
    assert result.is_success()
    assert result.details["annual_revenue_null"] == 1
    assert [e["annual_revenue_null"] for e in events] == [1]


def test_import_company_reports_zero_when_every_row_has_revenue() -> None:
    result, _ = _import([_row(2025, 2e9)])
    assert result.details["annual_revenue_null"] == 0


def test_import_company_reports_zero_when_no_annual_rows() -> None:
    result, _ = _import([])
    assert result.details["annual_revenue_null"] == 0
