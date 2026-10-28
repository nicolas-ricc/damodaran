"""Derived financial fields and shares outstanding for the EDGAR path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from bot.ingest.sec_edgar import SecEdgarClient, _derive_financial_fields

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "edgar"


def test_derives_ebitda_free_cashflow_and_working_capital() -> None:
    row: dict[str, Any] = {
        "ebit": 100.0,
        "depreciation": 20.0,
        "operating_cashflow": 90.0,
        "capex": 30.0,
        "_current_assets": 500.0,
        "_current_liabilities": 320.0,
    }
    _derive_financial_fields(row)
    assert row["ebitda"] == pytest.approx(120.0)
    assert row["free_cashflow"] == pytest.approx(60.0)
    assert row["working_capital"] == pytest.approx(180.0)
    assert "_current_assets" not in row and "_current_liabilities" not in row


def test_derivation_leaves_gaps_when_inputs_missing() -> None:
    row: dict[str, Any] = {"ebit": 100.0}  # no depreciation, no ocf/capex, no current a/l
    _derive_financial_fields(row)
    assert row.get("ebitda") is None
    assert row.get("free_cashflow") is None
    assert row.get("working_capital") is None


def test_derivation_never_overwrites_reported_values() -> None:
    row: dict[str, Any] = {"ebit": 100.0, "depreciation": 20.0, "ebitda": 999.0}
    _derive_financial_fields(row)
    assert row["ebitda"] == pytest.approx(999.0)


def test_derives_ebit_from_pretax_income_plus_interest() -> None:
    # No operating-income line (banks, insurers, some industrials): EBIT is
    # approximated as pretax income plus interest expense.
    row: dict[str, Any] = {"_pretax_income": 80.0, "interest_expense": 20.0, "depreciation": 5.0}
    _derive_financial_fields(row)
    assert row["ebit"] == pytest.approx(100.0)
    assert row["ebitda"] == pytest.approx(105.0)  # derived EBIT feeds EBITDA
    assert "_pretax_income" not in row


def test_derived_ebit_treats_missing_interest_as_zero() -> None:
    row: dict[str, Any] = {"_pretax_income": 80.0}
    _derive_financial_fields(row)
    assert row["ebit"] == pytest.approx(80.0)


def test_derived_ebit_never_overwrites_reported_operating_income() -> None:
    row: dict[str, Any] = {"ebit": 100.0, "_pretax_income": 500.0, "interest_expense": 20.0}
    _derive_financial_fields(row)
    assert row["ebit"] == pytest.approx(100.0)
    assert "_pretax_income" not in row


def test_ebit_stays_none_without_pretax_income() -> None:
    row: dict[str, Any] = {"interest_expense": 20.0}
    _derive_financial_fields(row)
    assert row.get("ebit") is None


def test_derives_interest_expense_from_net_interest_when_net_cost() -> None:
    # InterestIncomeExpense*Net is signed income: a negative figure is net expense.
    row: dict[str, Any] = {"_net_interest": -64.0}
    _derive_financial_fields(row)
    assert row["interest_expense"] == pytest.approx(64.0)
    assert "_net_interest" not in row


def test_net_interest_income_means_zero_interest_expense() -> None:
    row: dict[str, Any] = {"_net_interest": 267.0}
    _derive_financial_fields(row)
    assert row["interest_expense"] == pytest.approx(0.0)


def test_net_interest_never_overwrites_reported_interest_expense() -> None:
    row: dict[str, Any] = {"interest_expense": 20.0, "_net_interest": -500.0}
    _derive_financial_fields(row)
    assert row["interest_expense"] == pytest.approx(20.0)


def test_interest_derived_from_net_feeds_ebit_derivation() -> None:
    row: dict[str, Any] = {"_pretax_income": 80.0, "_net_interest": -20.0}
    _derive_financial_fields(row)
    assert row["interest_expense"] == pytest.approx(20.0)
    assert row["ebit"] == pytest.approx(100.0)


def test_derives_total_debt_from_noncurrent_plus_current_portion() -> None:
    row: dict[str, Any] = {"_debt_noncurrent": 900.0, "_debt_current": 100.0}
    _derive_financial_fields(row)
    assert row["total_debt"] == pytest.approx(1000.0)
    assert "_debt_noncurrent" not in row and "_debt_current" not in row


def test_derives_total_debt_from_a_single_tranche() -> None:
    row: dict[str, Any] = {"_debt_noncurrent": 900.0}
    _derive_financial_fields(row)
    assert row["total_debt"] == pytest.approx(900.0)
    row = {"_debt_current": 100.0}
    _derive_financial_fields(row)
    assert row["total_debt"] == pytest.approx(100.0)


def test_total_debt_total_concept_beats_tranches() -> None:
    row: dict[str, Any] = {"total_debt": 1500.0, "_debt_noncurrent": 900.0, "_debt_current": 100.0}
    _derive_financial_fields(row)
    assert row["total_debt"] == pytest.approx(1500.0)


def test_total_debt_stays_none_without_any_debt_concept() -> None:
    row: dict[str, Any] = {"cash": 50.0}
    _derive_financial_fields(row)
    assert row.get("total_debt") is None


def test_shares_outstanding_returns_newest_value() -> None:
    payload = json.loads((FIXTURES / "aapl_shares_concept.json").read_text("utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert "companyconcept/CIK0000320193/dei/EntityCommonStockSharesOutstanding" in str(
            request.url
        )
        return httpx.Response(200, json=payload)

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    assert client.shares_outstanding("0000320193") == pytest.approx(14840392000)


def test_shares_outstanding_none_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    assert client.shares_outstanding("0000320193") is None
