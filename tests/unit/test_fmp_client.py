"""Unit tests for FmpClient and CompanyInfo — no network calls."""

import pytest

from bot.ingest.fmp import CompanyInfo, FmpClient


def test_fmp_client_rejects_empty_key() -> None:
    with pytest.raises(ValueError, match="empty"):
        FmpClient(api_key="")


def test_company_info_status_active() -> None:
    c = CompanyInfo(
        ticker="AAPL",
        name="Apple Inc.",
        currency="USD",
        country="US",
        exchange="NASDAQ",
        industry="Tech",
        isin="US0378331005",
        cik="0000320193",
        is_actively_trading=True,
    )
    assert c.status == "active"


def test_company_info_status_delisted() -> None:
    c = CompanyInfo(
        ticker="FOO",
        name="Foo Corp",
        currency="USD",
        country="US",
        exchange="NYSE",
        industry=None,
        isin=None,
        cik=None,
        is_actively_trading=False,
    )
    assert c.status == "delisted"
