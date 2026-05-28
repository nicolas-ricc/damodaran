from typing import Any

from bot.reporting.show import format_company_summary


def test_format_company_summary_renders_table() -> None:
    company: dict[str, Any] = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "cik": "0000320193",
        "country": "US",
        "currency": "USD",
    }
    annual_rows: list[dict[str, Any]] = [
        {"fiscal_year": 2022, "revenue": 394_328_000_000, "net_income": 99_803_000_000},
        {"fiscal_year": 2023, "revenue": 383_285_000_000, "net_income": 96_995_000_000},
    ]
    text = format_company_summary(company, annual_rows)
    assert "AAPL" in text
    assert "Apple Inc." in text
    assert "2022" in text
    assert "2023" in text
    assert "394" in text
    assert "USD" in text


def test_format_company_summary_no_financials() -> None:
    company: dict[str, Any] = {
        "ticker": "XYZ",
        "name": "XYZ Corp",
        "cik": None,
        "country": "US",
        "currency": "USD",
    }
    text = format_company_summary(company, [])
    assert "no financials" in text.lower()
