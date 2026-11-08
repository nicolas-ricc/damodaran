from datetime import date

import pytest

from bot.ingest.base import transaction
from bot.ingest.sec_edgar import (
    SecEdgarClient,
    parse_company_facts,
    upsert_company,
    upsert_filings,
    upsert_financials_annual,
    upsert_financials_quarterly,
)
from bot.storage.db import apply_schema, connect


@pytest.mark.integration
@pytest.mark.vcr
def test_parse_company_facts_from_cassette_populates_db():
    conn = connect(":memory:")
    apply_schema(conn)

    with SecEdgarClient(user_agent="Tester t@example.com") as client:
        cik = client.lookup_cik("AAPL")
        assert cik == "0000320193"
        facts = client.fetch_company_facts(cik)
    parsed = parse_company_facts("AAPL", facts)

    with transaction(conn):
        upsert_company(conn, parsed.company)
        annual = upsert_financials_annual(conn, parsed.annual)
        quarterly = upsert_financials_quarterly(conn, parsed.quarterly)
        filings = upsert_filings(conn, parsed.filings)

    assert annual + quarterly + filings > 0

    companies = conn.execute(
        "SELECT ticker, cik, name, country FROM companies WHERE ticker = 'AAPL'"
    ).fetchall()
    assert len(companies) == 1
    assert companies[0] == ("AAPL", "0000320193", "Apple Inc.", "US")

    annual_count = conn.execute(
        "SELECT COUNT(*) FROM financials_annual WHERE ticker = 'AAPL'"
    ).fetchone()[0]
    assert annual_count >= 5  # AAPL has > 5 years of XBRL filings

    # Facts are attributed by their own period: the newest annual row is the
    # latest fiscal year end in the cassette, not a comparative re-filed later.
    newest = conn.execute(
        "SELECT fiscal_year, period_end_date FROM financials_annual "
        "WHERE ticker = 'AAPL' ORDER BY period_end_date DESC LIMIT 1"
    ).fetchone()
    assert newest == (2025, date(2025, 9, 27))

    # PaymentsToAcquireBusinessesNetOfCashAcquired, as the 10-Ks in the cassette report it.
    acquisitions = conn.execute(
        "SELECT fiscal_year, acquisitions FROM financials_annual "
        "WHERE ticker = 'AAPL' AND fiscal_year IN (2020, 2021) ORDER BY fiscal_year"
    ).fetchall()
    assert acquisitions == [(2020, 1_524_000_000.0), (2021, 33_000_000.0)]

    filings_count = conn.execute(
        "SELECT COUNT(*) FROM filings_log WHERE ticker = 'AAPL'"
    ).fetchone()[0]
    assert filings_count >= 1

    conn.close()
