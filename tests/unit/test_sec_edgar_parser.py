from bot.ingest.sec_edgar import parse_company_facts

FAKE_FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                        {
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K/A",
                            "filed": "2024-01-15",
                        },
                        {
                            "end": "2022-09-30",
                            "val": 394328000000,
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2022-10-28",
                        },
                        {
                            "end": "2024-03-30",
                            "val": 90753000000,
                            "fy": 2024,
                            "fp": "Q2",
                            "form": "10-Q",
                            "filed": "2024-05-03",
                        },
                    ]
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "units": {
                    "USD": [
                        {
                            "end": "2023-09-30",
                            "val": 96995000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                    ]
                },
            },
            "Assets": {
                "label": "Total Assets",
                "units": {
                    "USD": [
                        {
                            "end": "2023-09-30",
                            "val": 352583000000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                    ]
                },
            },
        }
    },
}


def test_parse_extracts_annual_revenue_and_net_income():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    assert result.company["ticker"] == "AAPL"
    assert result.company["name"] == "Apple Inc."
    assert result.company["cik"] == "0000320193"

    annual = {row["fiscal_year"]: row for row in result.annual}
    assert 2023 in annual
    assert annual[2023]["revenue"] == 383285000000
    assert annual[2023]["net_income"] == 96995000000
    assert annual[2023]["total_assets"] == 352583000000
    assert annual[2023]["ticker"] == "AAPL"
    assert annual[2022]["revenue"] == 394328000000


def test_parse_prefers_most_recent_filing_for_restated_year():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    annual = {row["fiscal_year"]: row for row in result.annual}
    assert annual[2023]["revenue"] == 383285000000


def test_parse_extracts_quarterly():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    q = [r for r in result.quarterly if r["fiscal_quarter"] == 2 and r["fiscal_year"] == 2024]
    assert len(q) == 1
    assert q[0]["revenue"] == 90753000000


def test_parse_returns_filings_log_entries():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    assert len(result.filings) >= 1
    forms = {f["filing_type"] for f in result.filings}
    assert "10-K" in forms
