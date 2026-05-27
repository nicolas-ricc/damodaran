"""Unit tests for parse_fmp_fundamentals — no network, hand-crafted FMP-shape JSON."""

from __future__ import annotations

from typing import Any

import pytest

from bot.ingest.fmp import parse_fmp_fundamentals

# ---------------------------------------------------------------------------
# Helpers — hand-crafted FMP response shapes
# ---------------------------------------------------------------------------

def _income(
    year: str,
    period: str,
    currency: str = "USD",
    filling_date: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "symbol": "AAPL",
        "date": f"{year}-09-30",
        "reportedCurrency": currency,
        "cik": "0000320193",
        "fillingDate": filling_date or f"{year}-11-02",
        "acceptedDate": filling_date or f"{year}-11-02",
        "calendarYear": year,
        "period": period,
        "revenue": 383_285_000_000.0,
        "costOfRevenue": 214_137_000_000.0,
        "grossProfit": 169_148_000_000.0,
        "operatingExpenses": 54_438_000_000.0,
        "operatingIncome": 114_301_000_000.0,
        "ebitda": 123_200_000_000.0,
        "interestExpense": 3_933_000_000.0,
        "incomeTaxExpense": 29_749_000_000.0,
        "netIncome": 96_995_000_000.0,
        "depreciationAndAmortization": 11_519_000_000.0,
        "weightedAverageShsOutDil": 15_812_547_000.0,
    }
    base.update(kwargs)
    return base


def _balance(
    year: str,
    period: str,
    currency: str = "USD",
    filling_date: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "symbol": "AAPL",
        "date": f"{year}-09-30",
        "reportedCurrency": currency,
        "fillingDate": filling_date or f"{year}-11-02",
        "calendarYear": year,
        "period": period,
        "cashAndCashEquivalents": 29_965_000_000.0,
        "totalAssets": 352_583_000_000.0,
        "totalDebt": 105_103_000_000.0,
        "totalStockholdersEquity": 62_146_000_000.0,
        "goodwill": 0.0,
    }
    base.update(kwargs)
    return base


def _cashflow(
    year: str,
    period: str,
    currency: str = "USD",
    filling_date: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "symbol": "AAPL",
        "date": f"{year}-09-30",
        "reportedCurrency": currency,
        "fillingDate": filling_date or f"{year}-11-02",
        "calendarYear": year,
        "period": period,
        "depreciationAndAmortization": 11_519_000_000.0,
        "operatingCashFlow": 110_543_000_000.0,
        "capitalExpenditure": -10_959_000_000.0,
        "freeCashFlow": 99_584_000_000.0,
        "dividendsPaid": -15_025_000_000.0,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Basic annual parsing
# ---------------------------------------------------------------------------

class TestAnnualParsing:
    def test_single_fy_row_populates_all_fields(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        assert len(result.annual) == 1
        assert result.quarterly == []
        row = result.annual[0]
        assert row["ticker"] == "AAPL"
        assert row["fiscal_year"] == 2023
        assert row["currency"] == "USD"
        assert row["source"] == "fmp"
        assert row["is_restated"] is False

    def test_multiple_fiscal_years(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY"), _income("2022", "FY"), _income("2021", "FY")],
            balance_json=[_balance("2023", "FY"), _balance("2022", "FY"), _balance("2021", "FY")],
            cashflow_json=[
                _cashflow("2023", "FY"), _cashflow("2022", "FY"), _cashflow("2021", "FY")
            ],
        )
        assert len(result.annual) == 3
        years = {r["fiscal_year"] for r in result.annual}
        assert years == {2021, 2022, 2023}

    def test_income_statement_mapping(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        row = result.annual[0]
        assert row["revenue"] == 383_285_000_000.0
        assert row["cogs"] == 214_137_000_000.0
        assert row["gross_profit"] == 169_148_000_000.0
        assert row["operating_expenses"] == 54_438_000_000.0
        assert row["ebit"] == 114_301_000_000.0
        assert row["ebitda"] == 123_200_000_000.0
        assert row["interest_expense"] == 3_933_000_000.0
        assert row["tax_expense"] == 29_749_000_000.0
        assert row["net_income"] == 96_995_000_000.0
        assert row["shares_diluted"] == 15_812_547_000.0

    def test_balance_sheet_mapping(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        row = result.annual[0]
        assert row["total_assets"] == 352_583_000_000.0
        assert row["total_debt"] == 105_103_000_000.0
        assert row["cash"] == 29_965_000_000.0
        assert row["total_equity"] == 62_146_000_000.0
        assert row["goodwill"] == 0.0

    def test_cashflow_mapping_and_positive_capex(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        row = result.annual[0]
        assert row["operating_cashflow"] == 110_543_000_000.0
        assert row["capex"] == 10_959_000_000.0  # stored as positive
        assert row["free_cashflow"] == 99_584_000_000.0
        assert row["dividends_paid"] == 15_025_000_000.0  # stored as positive

    def test_period_end_date_populated(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        assert result.annual[0]["period_end_date"] == "2023-09-30"

    def test_ticker_uppercased(self) -> None:
        result = parse_fmp_fundamentals(
            "aapl",
            income_json=[_income("2023", "FY")],
            balance_json=[],
            cashflow_json=[],
        )
        assert result.annual[0]["ticker"] == "AAPL"
        assert result.company["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# Quarterly parsing
# ---------------------------------------------------------------------------

class TestQuarterlyParsing:
    def test_quarterly_rows_split_correctly(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[
                _income("2023", "Q1"),
                _income("2023", "Q2"),
                _income("2023", "Q3"),
                _income("2023", "Q4"),
            ],
            balance_json=[
                _balance("2023", "Q1"),
                _balance("2023", "Q2"),
                _balance("2023", "Q3"),
                _balance("2023", "Q4"),
            ],
            cashflow_json=[
                _cashflow("2023", "Q1"),
                _cashflow("2023", "Q2"),
                _cashflow("2023", "Q3"),
                _cashflow("2023", "Q4"),
            ],
        )
        assert result.annual == []
        assert len(result.quarterly) == 4
        quarters = sorted(r["fiscal_quarter"] for r in result.quarterly)
        assert quarters == [1, 2, 3, 4]

    def test_mixed_annual_and_quarterly(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY"), _income("2023", "Q1"), _income("2023", "Q2")],
            balance_json=[_balance("2023", "FY"), _balance("2023", "Q1"), _balance("2023", "Q2")],
            cashflow_json=[
                _cashflow("2023", "FY"), _cashflow("2023", "Q1"), _cashflow("2023", "Q2")
            ],
        )
        assert len(result.annual) == 1
        assert len(result.quarterly) == 2

    def test_fiscal_quarter_field_set(self) -> None:
        result = parse_fmp_fundamentals(
            "MSFT",
            income_json=[_income("2023", "Q3")],
            balance_json=[_balance("2023", "Q3")],
            cashflow_json=[_cashflow("2023", "Q3")],
        )
        assert result.quarterly[0]["fiscal_quarter"] == 3


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------

class TestDerivedMetrics:
    def test_ebitda_derived_when_missing(self) -> None:
        inc = _income("2023", "FY", ebitda=None)
        del inc["ebitda"]
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[inc],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        row = result.annual[0]
        # ebit=114_301_000_000 + depreciation from cashflow=11_519_000_000
        assert row["ebitda"] == pytest.approx(125_820_000_000.0)

    def test_ebitda_from_fmp_preferred_over_derived(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],  # ebitda=123_200_000_000
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        # FMP ebitda (123.2B) differs from ebit+D&A (125.82B); FMP value wins.
        assert result.annual[0]["ebitda"] == pytest.approx(123_200_000_000.0)

    def test_fcf_derived_when_missing(self) -> None:
        cf = _cashflow("2023", "FY")
        del cf["freeCashFlow"]
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[cf],
        )
        # OCF=110_543_000_000 - |capex|=10_959_000_000
        assert result.annual[0]["free_cashflow"] == pytest.approx(99_584_000_000.0)

    def test_capex_stored_as_positive(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY", capitalExpenditure=-5_000_000_000.0)],
        )
        assert result.annual[0]["capex"] == 5_000_000_000.0

    def test_dividends_stored_as_positive(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY", dividendsPaid=-2_000_000_000.0)],
        )
        assert result.annual[0]["dividends_paid"] == 2_000_000_000.0


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

class TestCurrency:
    def test_currency_from_income_reported_currency(self) -> None:
        result = parse_fmp_fundamentals(
            "NESN.SW",
            income_json=[_income("2023", "FY", currency="CHF")],
            balance_json=[_balance("2023", "FY", currency="CHF")],
            cashflow_json=[_cashflow("2023", "FY", currency="CHF")],
        )
        assert result.annual[0]["currency"] == "CHF"

    def test_currency_falls_back_to_balance_then_cashflow(self) -> None:
        inc = _income("2023", "FY")
        inc.pop("reportedCurrency", None)
        inc["reportedCurrency"] = None  # type: ignore[assignment]
        result = parse_fmp_fundamentals(
            "7203.T",
            income_json=[inc],
            balance_json=[_balance("2023", "FY", currency="JPY")],
            cashflow_json=[_cashflow("2023", "FY", currency="JPY")],
        )
        assert result.annual[0]["currency"] == "JPY"

    def test_company_currency_populated(self) -> None:
        result = parse_fmp_fundamentals(
            "NESN.SW",
            income_json=[_income("2023", "FY", currency="CHF")],
            balance_json=[],
            cashflow_json=[],
        )
        assert result.company["currency"] == "CHF"


# ---------------------------------------------------------------------------
# Restatement detection
# ---------------------------------------------------------------------------

class TestRestatements:
    def test_no_restatement_for_single_entry(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY", filling_date="2023-11-02")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        assert result.annual[0]["is_restated"] is False

    def test_earlier_duplicate_period_marked_restated(self) -> None:
        # Two entries for the same (calendarYear, period): earlier fillingDate is the restated one.
        inc_original = _income("2023", "FY", filling_date="2023-11-02")
        inc_amended = _income("2023", "FY", filling_date="2024-01-15", revenue=390_000_000_000.0)
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[inc_original, inc_amended],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        # Two rows: the original (restated) and the amendment (current).
        assert len(result.annual) == 2
        restated_rows = [r for r in result.annual if r["is_restated"]]
        current_rows = [r for r in result.annual if not r["is_restated"]]
        assert len(restated_rows) == 1
        assert len(current_rows) == 1
        # The latest fillingDate (amended) is the current one.
        assert current_rows[0]["revenue"] == pytest.approx(390_000_000_000.0)

    def test_restatement_in_quarterly(self) -> None:
        q1_v1 = _income("2023", "Q1", filling_date="2023-05-01")
        q1_v2 = _income("2023", "Q1", filling_date="2023-07-15")
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[q1_v1, q1_v2],
            balance_json=[],
            cashflow_json=[],
        )
        assert len(result.quarterly) == 2
        assert any(r["is_restated"] for r in result.quarterly)
        assert any(not r["is_restated"] for r in result.quarterly)


# ---------------------------------------------------------------------------
# Empty / missing statement arrays
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_inputs_return_empty_results(self) -> None:
        result = parse_fmp_fundamentals("AAPL", income_json=[], balance_json=[], cashflow_json=[])
        assert result.annual == []
        assert result.quarterly == []

    def test_missing_balance_data_does_not_crash(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[],  # no balance data
            cashflow_json=[_cashflow("2023", "FY")],
        )
        row = result.annual[0]
        assert row["total_assets"] is None
        assert row["revenue"] == 383_285_000_000.0  # income still parsed

    def test_missing_cashflow_data_does_not_crash(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[_balance("2023", "FY")],
            cashflow_json=[],
        )
        row = result.annual[0]
        assert row["operating_cashflow"] is None
        assert row["capex"] is None
        assert row["revenue"] == 383_285_000_000.0

    def test_unknown_period_string_ignored(self) -> None:
        inc = _income("2023", "TTM")  # trailing-twelve-months — not a standard period
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[inc],
            balance_json=[_balance("2023", "TTM")],
            cashflow_json=[_cashflow("2023", "TTM")],
        )
        assert result.annual == []
        assert result.quarterly == []

    def test_totalequity_fallback_when_stockholders_missing(self) -> None:
        bal = _balance("2023", "FY")
        del bal["totalStockholdersEquity"]
        bal["totalEquity"] = 55_000_000_000.0
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[bal],
            cashflow_json=[_cashflow("2023", "FY")],
        )
        assert result.annual[0]["total_equity"] == 55_000_000_000.0

    def test_cik_in_company_stub(self) -> None:
        result = parse_fmp_fundamentals(
            "AAPL",
            income_json=[_income("2023", "FY")],
            balance_json=[],
            cashflow_json=[],
        )
        assert result.company["cik"] == "0000320193"

    def test_non_us_company_null_cik(self) -> None:
        inc = _income("2023", "FY", currency="JPY")
        inc["cik"] = None
        result = parse_fmp_fundamentals(
            "7203.T", income_json=[inc], balance_json=[], cashflow_json=[]
        )
        assert result.company["cik"] is None
