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


# --- Fix 2: is_restated tracks all historical forms, not just the winning form ---

FAKE_FACTS_RESTATEMENT = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        # 10-K/A filed first for 2022
                        {
                            "end": "2022-09-30",
                            "val": 394000000000,
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K/A",
                            "filed": "2022-12-01",
                        },
                        # Later 10-K supersedes the /A for 2022 — winning form is 10-K
                        {
                            "end": "2022-09-30",
                            "val": 394328000000,
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-01-15",
                        },
                    ]
                },
            }
        }
    },
}


def test_is_restated_true_when_amendment_in_history_even_if_later_10k_wins():
    """If a /A was ever filed for a period, is_restated must be True even when a
    later plain 10-K wins the slot."""
    result = parse_company_facts("AAPL", FAKE_FACTS_RESTATEMENT)
    annual = {row["fiscal_year"]: row for row in result.annual}
    assert 2022 in annual
    # The winning value comes from the later 10-K
    assert annual[2022]["revenue"] == 394328000000
    # But is_restated must still be True because a 10-K/A was observed for this period
    assert annual[2022]["is_restated"] is True


# --- Fix 3: tightened form matching — 10-KSB must be excluded ---

FAKE_FACTS_10KSB = {
    "cik": 99999,
    "entityName": "Small Co.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        # 10-KSB should NOT be included in annual rows
                        {
                            "end": "2005-12-31",
                            "val": 1000000,
                            "fy": 2005,
                            "fp": "FY",
                            "form": "10-KSB",
                            "filed": "2006-03-15",
                        },
                    ]
                },
            }
        }
    },
}


def test_10ksb_excluded_from_annual_rows():
    """10-KSB is not a valid annual form and must not appear in annual_rows."""
    result = parse_company_facts("SMCO", FAKE_FACTS_10KSB)
    assert result.annual == [], "10-KSB entries must be excluded from annual rows"
