"""Integration tests for the FMP HTTP client.

Network is replayed from VCR cassettes in
``tests/fixtures/cassettes/fmp/``. The cassettes are SYNTHETIC (hand-authored,
fabricated-but-realistic FMP JSON) so the suite runs deterministically offline.
They MUST be re-recorded against the live FMP API with a real BOT_FMP_API_KEY
before production use.
"""

from __future__ import annotations

import pytest

from bot.ingest.fmp import CompanyInfo, FmpClient

API_KEY = "test-fmp-key"


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "fmp")


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    # The API key is passed as the ``apikey`` query param; scrub it so cassettes
    # never leak a real key and match regardless of the configured key.
    return {
        "filter_query_parameters": [("apikey", "SCRUBBED")],
        "record_mode": "once",
    }


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_company_us() -> None:
    with FmpClient(api_key=API_KEY) as client:
        info = client.lookup_company("AAPL")
    assert info == CompanyInfo(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        exchange_short_name="NASDAQ",
        country="US",
        currency="USD",
        sector="Technology",
        industry="Consumer Electronics",
        is_actively_trading=True,
    )


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_company_switzerland() -> None:
    with FmpClient(api_key=API_KEY) as client:
        info = client.lookup_company("NESN.SW")
    assert info is not None
    assert info.ticker == "NESN.SW"
    assert info.name == "Nestlé S.A."
    assert info.country == "CH"
    assert info.currency == "CHF"
    assert info.exchange_short_name == "SIX"


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_company_japan() -> None:
    with FmpClient(api_key=API_KEY) as client:
        info = client.lookup_company("7203.T")
    assert info is not None
    assert info.ticker == "7203.T"
    assert info.name == "Toyota Motor Corporation"
    assert info.country == "JP"
    assert info.currency == "JPY"
    assert info.exchange_short_name == "TSE"


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_company_unknown_returns_none() -> None:
    with FmpClient(api_key=API_KEY) as client:
        info = client.lookup_company("ZZZNOTREAL")
    assert info is None


@pytest.mark.integration
@pytest.mark.vcr
def test_available_exchanges() -> None:
    with FmpClient(api_key=API_KEY) as client:
        exchanges = client.available_exchanges()
    short_names = {e["shortName"] for e in exchanges}
    assert "NASDAQ" in short_names
    assert "SIX" in short_names
    assert "TSE" in short_names


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ValueError, match="FMP API key"):
        FmpClient(api_key="")
