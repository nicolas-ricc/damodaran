import pytest

from bot.ingest.sec_edgar import SecEdgarClient


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_cik_for_known_ticker():
    client = SecEdgarClient(user_agent="Tester t@example.com")
    cik = client.lookup_cik("AAPL")
    assert cik == "0000320193"


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_cik_unknown_returns_none():
    client = SecEdgarClient(user_agent="Tester t@example.com")
    cik = client.lookup_cik("ZZZNOTREAL")
    assert cik is None


@pytest.mark.integration
@pytest.mark.vcr
def test_fetch_company_facts_returns_json():
    client = SecEdgarClient(user_agent="Tester t@example.com")
    facts = client.fetch_company_facts("0000320193")  # AAPL
    assert "entityName" in facts
    assert "facts" in facts
    assert "us-gaap" in facts["facts"]
