"""Unit tests for the pure FMP fundamentals parser (M2.2).

The parser converts FMP's income-statement / balance-sheet / cash-flow JSON
arrays into our normalized ``financials_annual`` / ``financials_quarterly`` row
shape — the same shape the existing ``upsert_financials_*`` helpers consume.

The JSON below mimics the real FMP API structure (camelCase keys, one object
per fiscal period, ``reportedCurrency`` in local currency) but is hand-crafted
and SYNTHETIC. No live calls; values are fabricated, not real filings.
"""

from __future__ import annotations

from typing import Any

import duckdb

from bot.ingest.fmp import parse_fmp_fundamentals
from bot.ingest.sec_edgar import (
    upsert_financials_annual,
    upsert_financials_quarterly,
)
from bot.storage.db import apply_schema

# ---------- Synthetic FMP-shape fixtures ----------

INCOME_ANNUAL: list[dict[str, Any]] = [
    {
        "date": "2023-12-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "fillingDate": "2024-02-22",
        "acceptedDate": "2024-02-22 06:00:00",
        "calendarYear": "2023",
        "period": "FY",
        "revenue": 92990000000,
        "costOfRevenue": 48000000000,
        "grossProfit": 44990000000,
        "operatingExpenses": 30000000000,
        "operatingIncome": 14990000000,
        "ebitda": 18000000000,
        "interestExpense": 900000000,
        "incomeTaxExpense": 3000000000,
        "netIncome": 11210000000,
        "depreciationAndAmortization": 3010000000,
        "weightedAverageShsDilOut": 2700000000,
    },
    {
        "date": "2022-12-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "fillingDate": "2023-02-23",
        "acceptedDate": "2023-02-23 06:00:00",
        "calendarYear": "2022",
        "period": "FY",
        "revenue": 94400000000,
        "costOfRevenue": 49000000000,
        "grossProfit": 45400000000,
        "operatingExpenses": 31000000000,
        "operatingIncome": 14400000000,
        # ebitda intentionally omitted to exercise the EBIT+D&A derivation
        "interestExpense": 850000000,
        "incomeTaxExpense": 3100000000,
        "netIncome": 11600000000,
        "depreciationAndAmortization": 2900000000,
        "weightedAverageShsDilOut": 2750000000,
    },
]

BALANCE_ANNUAL: list[dict[str, Any]] = [
    {
        "date": "2023-12-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2023",
        "period": "FY",
        "totalAssets": 130000000000,
        "totalDebt": 60000000000,
        "cashAndCashEquivalents": 8000000000,
        "totalStockholdersEquity": 45000000000,
        "goodwill": 33000000000,
        "totalCurrentAssets": 40000000000,
        "totalCurrentLiabilities": 50000000000,
    },
    {
        "date": "2022-12-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2022",
        "period": "FY",
        "totalAssets": 128000000000,
        "totalDebt": 58000000000,
        "cashAndCashEquivalents": 5000000000,
        "totalStockholdersEquity": 43000000000,
        "goodwill": 32000000000,
        "totalCurrentAssets": 38000000000,
        "totalCurrentLiabilities": 48000000000,
    },
]

CASHFLOW_ANNUAL: list[dict[str, Any]] = [
    {
        "date": "2023-12-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2023",
        "period": "FY",
        "operatingCashFlow": 16000000000,
        "capitalExpenditure": -4000000000,
        "freeCashFlow": 12000000000,
        "depreciationAndAmortization": 3010000000,
        "dividendsPaid": -8000000000,
    },
    {
        "date": "2022-12-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2022",
        "period": "FY",
        "operatingCashFlow": 15000000000,
        "capitalExpenditure": -3500000000,
        # freeCashFlow omitted -> must derive OCF + capex (capex negative in FMP)
        "depreciationAndAmortization": 2900000000,
        "dividendsPaid": -7800000000,
    },
]

INCOME_QUARTERLY: list[dict[str, Any]] = [
    {
        "date": "2024-06-30",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2024",
        "period": "Q2",
        "revenue": 22000000000,
        "operatingIncome": 3500000000,
        "ebitda": 4200000000,
        "netIncome": 2700000000,
        "depreciationAndAmortization": 700000000,
    },
    {
        "date": "2024-03-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2024",
        "period": "Q1",
        "revenue": 21500000000,
        "operatingIncome": 3400000000,
        "ebitda": 4100000000,
        "netIncome": 2600000000,
        "depreciationAndAmortization": 680000000,
    },
]

BALANCE_QUARTERLY: list[dict[str, Any]] = [
    {
        "date": "2024-06-30",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2024",
        "period": "Q2",
        "totalDebt": 61000000000,
        "cashAndCashEquivalents": 7500000000,
    },
    {
        "date": "2024-03-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2024",
        "period": "Q1",
        "totalDebt": 60500000000,
        "cashAndCashEquivalents": 7000000000,
    },
]

CASHFLOW_QUARTERLY: list[dict[str, Any]] = [
    {
        "date": "2024-06-30",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2024",
        "period": "Q2",
        "operatingCashFlow": 3800000000,
        "capitalExpenditure": -900000000,
        "freeCashFlow": 2900000000,
    },
    {
        "date": "2024-03-31",
        "symbol": "NESN.SW",
        "reportedCurrency": "CHF",
        "calendarYear": "2024",
        "period": "Q1",
        "operatingCashFlow": 3600000000,
        "capitalExpenditure": -850000000,
        "freeCashFlow": 2750000000,
    },
]


def test_parse_returns_company_with_currency_from_source() -> None:
    result = parse_fmp_fundamentals(
        "nesn.sw", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    assert result.company["ticker"] == "NESN.SW"
    assert result.company["currency"] == "CHF"
    assert result.company["source"] == "fmp"


def test_parse_joins_statements_per_fiscal_year() -> None:
    result = parse_fmp_fundamentals(
        "NESN.SW", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    by_year = {r["fiscal_year"]: r for r in result.annual}
    assert set(by_year) == {2022, 2023}

    row = by_year[2023]
    # income statement fields
    assert row["revenue"] == 92990000000
    assert row["cogs"] == 48000000000
    assert row["gross_profit"] == 44990000000
    assert row["operating_expenses"] == 30000000000
    assert row["ebit"] == 14990000000
    assert row["interest_expense"] == 900000000
    assert row["tax_expense"] == 3000000000
    assert row["net_income"] == 11210000000
    assert row["shares_diluted"] == 2700000000
    assert row["depreciation"] == 3010000000
    # balance sheet fields
    assert row["total_assets"] == 130000000000
    assert row["total_debt"] == 60000000000
    assert row["cash"] == 8000000000
    assert row["total_equity"] == 45000000000
    assert row["goodwill"] == 33000000000
    # cash flow fields
    assert row["operating_cashflow"] == 16000000000
    assert row["dividends_paid"] == -8000000000
    # bookkeeping
    assert row["ticker"] == "NESN.SW"
    assert row["currency"] == "CHF"
    assert row["source"] == "fmp"
    assert row["period_end_date"] == "2023-12-31"
    assert row["is_restated"] is False


def test_parse_uses_ebitda_from_source_when_present() -> None:
    result = parse_fmp_fundamentals(
        "NESN.SW", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    by_year = {r["fiscal_year"]: r for r in result.annual}
    assert by_year[2023]["ebitda"] == 18000000000


def test_parse_derives_ebitda_when_missing() -> None:
    result = parse_fmp_fundamentals(
        "NESN.SW", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    by_year = {r["fiscal_year"]: r for r in result.annual}
    # 2022 omits ebitda -> EBIT (14.4bn) + D&A (2.9bn) = 17.3bn
    assert by_year[2022]["ebitda"] == 14400000000 + 2900000000


def test_parse_derives_free_cashflow_when_missing() -> None:
    result = parse_fmp_fundamentals(
        "NESN.SW", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    by_year = {r["fiscal_year"]: r for r in result.annual}
    # 2023 provides freeCashFlow directly
    assert by_year[2023]["free_cashflow"] == 12000000000
    # 2022 omits it -> OCF (15bn) + capex (-3.5bn, FMP sign) = 11.5bn
    assert by_year[2022]["free_cashflow"] == 15000000000 + (-3500000000)


def test_parse_computes_capex_and_working_capital() -> None:
    result = parse_fmp_fundamentals(
        "NESN.SW", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    by_year = {r["fiscal_year"]: r for r in result.annual}
    # capex stored as positive magnitude (FMP reports it negative)
    assert by_year[2023]["capex"] == 4000000000
    # working_capital = current assets - current liabilities
    assert by_year[2023]["working_capital"] == 40000000000 - 50000000000


def test_parse_quarterly_rows() -> None:
    result = parse_fmp_fundamentals(
        "NESN.SW",
        INCOME_QUARTERLY,
        BALANCE_QUARTERLY,
        CASHFLOW_QUARTERLY,
    )
    by_key = {(r["fiscal_year"], r["fiscal_quarter"]): r for r in result.quarterly}
    assert set(by_key) == {(2024, 1), (2024, 2)}
    q2 = by_key[(2024, 2)]
    assert q2["revenue"] == 22000000000
    assert q2["ebit"] == 3500000000
    assert q2["ebitda"] == 4200000000
    assert q2["net_income"] == 2700000000
    assert q2["operating_cashflow"] == 3800000000
    assert q2["free_cashflow"] == 2900000000
    assert q2["total_debt"] == 61000000000
    assert q2["cash"] == 7500000000
    assert q2["currency"] == "CHF"
    assert q2["period_end_date"] == "2024-06-30"
    assert q2["fiscal_quarter"] == 2


def test_parse_detects_restatement() -> None:
    """A later filing for an already-seen fiscal year flags is_restated."""
    income = [
        {
            "date": "2023-12-31",
            "reportedCurrency": "CHF",
            "fillingDate": "2024-02-22",
            "calendarYear": "2023",
            "period": "FY",
            "revenue": 92990000000,
            "netIncome": 11210000000,
        },
        # restated version filed later for the same FY
        {
            "date": "2023-12-31",
            "reportedCurrency": "CHF",
            "fillingDate": "2025-02-20",
            "calendarYear": "2023",
            "period": "FY",
            "revenue": 92500000000,
            "netIncome": 11000000000,
        },
    ]
    result = parse_fmp_fundamentals("NESN.SW", income, [], [])
    rows = result.annual
    assert len(rows) == 1
    row = rows[0]
    # latest filing wins
    assert row["revenue"] == 92500000000
    assert row["net_income"] == 11000000000
    assert row["is_restated"] is True


def test_parse_handles_empty_inputs() -> None:
    result = parse_fmp_fundamentals("NESN.SW", [], [], [])
    assert result.annual == []
    assert result.quarterly == []
    assert result.company["ticker"] == "NESN.SW"


def test_parse_output_upserts_into_db() -> None:
    """Output shape must be directly consumable by the existing upserts."""
    annual = parse_fmp_fundamentals(
        "NESN.SW", INCOME_ANNUAL, BALANCE_ANNUAL, CASHFLOW_ANNUAL
    )
    quarterly = parse_fmp_fundamentals(
        "NESN.SW", INCOME_QUARTERLY, BALANCE_QUARTERLY, CASHFLOW_QUARTERLY
    )
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    n_annual = upsert_financials_annual(conn, annual.annual)
    n_quarterly = upsert_financials_quarterly(conn, quarterly.quarterly)
    assert n_annual == 2
    assert n_quarterly == 2

    rev = conn.execute(
        "SELECT revenue FROM financials_annual WHERE ticker = ? AND fiscal_year = ?",
        ["NESN.SW", 2023],
    ).fetchone()
    assert rev is not None
    assert rev[0] == 92990000000

    q = conn.execute(
        "SELECT ebitda FROM financials_quarterly "
        "WHERE ticker = ? AND fiscal_year = ? AND fiscal_quarter = ?",
        ["NESN.SW", 2024, 2],
    ).fetchone()
    assert q is not None
    assert q[0] == 4200000000
    conn.close()
