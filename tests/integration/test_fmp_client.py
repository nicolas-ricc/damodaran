"""Integration tests for FmpClient using VCR cassettes."""

import pytest

from bot.ingest.fmp import FmpClient


@pytest.fixture  # type: ignore[misc]
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "fmp")


@pytest.fixture  # type: ignore[misc]
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["apikey"],
        "record_mode": "none",  # always use cassettes, never hit real API
    }


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_lookup_company_aapl() -> None:
    client = FmpClient(api_key="test_key")
    company = client.lookup_company("AAPL")
    assert company is not None
    assert company.ticker == "AAPL"
    assert company.name == "Apple Inc."
    assert company.currency == "USD"
    assert company.country == "US"
    assert company.exchange == "NASDAQ"
    assert company.cik == "0000320193"
    assert company.is_actively_trading is True
    assert company.status == "active"
    assert company.source == "fmp"


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_lookup_company_nesn_sw() -> None:
    client = FmpClient(api_key="test_key")
    company = client.lookup_company("NESN.SW")
    assert company is not None
    assert company.ticker == "NESN.SW"
    assert company.name == "Nestlé S.A."
    assert company.currency == "CHF"
    assert company.country == "CH"
    assert company.exchange == "SIX"
    assert company.cik is None
    assert company.isin == "CH0012221716"


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_lookup_company_7203_t() -> None:
    client = FmpClient(api_key="test_key")
    company = client.lookup_company("7203.T")
    assert company is not None
    assert company.ticker == "7203.T"
    assert company.name == "Toyota Motor Corporation"
    assert company.currency == "JPY"
    assert company.country == "JP"
    assert company.exchange == "TSE"
    assert company.isin == "JP3633400001"


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_lookup_company_unknown_returns_none() -> None:
    client = FmpClient(api_key="test_key")
    result = client.lookup_company("ZZZNOTREAL")
    assert result is None
