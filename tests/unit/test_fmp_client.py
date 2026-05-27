"""Unit tests for FmpClient and CompanyInfo — no network calls."""

from unittest.mock import patch

import pytest

from bot.ingest.fmp import CompanyInfo, FmpClient, FmpError


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


def test_lookup_company_error_dict_raises_fmp_error() -> None:
    """FMP auth/quota failure returns HTTP 200 with a dict body — must raise FmpError."""
    error_payload = {"Error Message": "Invalid API KEY. Please retry your request with a correct apikey."}
    client = FmpClient(api_key="bad_key")
    with patch.object(client, "_get", return_value=error_payload), pytest.raises(FmpError, match="Invalid API KEY"):
        client.lookup_company("AAPL")
