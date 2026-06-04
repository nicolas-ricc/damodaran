import pytest

from bot.ingest.sec_edgar import import_company_from_sec
from bot.storage.db import apply_schema, connect


@pytest.fixture(scope="module")
def vcr_cassette_dir(request):
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "sec_edgar")


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [("User-Agent", "Tester t@example.com")],
        "record_mode": "once",
    }


@pytest.mark.integration
@pytest.mark.vcr
def test_import_company_from_sec_populates_db():
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_company_from_sec(conn, ticker="AAPL", user_agent="Tester t@example.com")

    assert result.is_success()
    assert result.rows_affected > 0

    companies = conn.execute(
        "SELECT ticker, cik, name, country FROM companies WHERE ticker = 'AAPL'"
    ).fetchall()
    assert len(companies) == 1
    assert companies[0] == ("AAPL", "0000320193", "Apple Inc.", "US")

    annual_count = conn.execute(
        "SELECT COUNT(*) FROM financials_annual WHERE ticker = 'AAPL'"
    ).fetchone()[0]
    assert annual_count >= 5  # AAPL has > 5 years of XBRL filings

    filings_count = conn.execute(
        "SELECT COUNT(*) FROM filings_log WHERE ticker = 'AAPL'"
    ).fetchone()[0]
    assert filings_count >= 1

    refresh_rows = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'sec_edgar'"
    ).fetchall()
    assert refresh_rows[0][0] == "success"

    conn.close()
