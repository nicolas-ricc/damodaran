from datetime import date

import pytest
from structlog.testing import capture_logs

from bot.ingest.sec_edgar import _fiscal_quarter_key, parse_company_facts

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
                            "start": "2022-09-25",
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                        {
                            "start": "2022-09-25",
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "accn": "0000320193-24-000007",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K/A",
                            "filed": "2024-01-15",
                        },
                        {
                            "start": "2021-09-26",
                            "end": "2022-09-30",
                            "val": 394328000000,
                            "accn": "0000320193-22-000108",
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2022-10-28",
                        },
                        {
                            "start": "2023-12-31",
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
                            "start": "2022-09-25",
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
                            "start": "2021-09-26",
                            "end": "2022-09-30",
                            "val": 394000000000,
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K/A",
                            "filed": "2022-12-01",
                        },
                        # Later 10-K supersedes the /A for 2022 — winning form is 10-K
                        {
                            "start": "2021-09-26",
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
                            "start": "2005-01-01",
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


# --- #122: attribute each fact by its own start/end, never by the filing's fy/fp ---


def _fact(
    end: str,
    val: float,
    *,
    start: str | None = None,
    form: str = "10-K",
    fy: int = 2025,
    fp: str = "FY",
    filed: str = "2026-02-20",
    accn: str = "0000063908-26-000010",
) -> dict[str, object]:
    fact: dict[str, object] = {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }
    if start is not None:
        fact["start"] = start
    return fact


def _facts(concepts: dict[str, list[dict[str, object]]], unit: str = "USD") -> dict[str, object]:
    return {
        "cik": 63908,
        "entityName": "McDonald's Corp",
        "facts": {
            "us-gaap": {name: {"units": {unit: entries}} for name, entries in concepts.items()}
        },
    }


def _annual(facts: dict[str, object]) -> dict[int, dict[str, object]]:
    return {r["fiscal_year"]: r for r in parse_company_facts("MCD", facts).annual}


def _quarterly(facts: dict[str, object]) -> dict[tuple[int, int], dict[str, object]]:
    return {
        (r["fiscal_year"], r["fiscal_quarter"]): r
        for r in parse_company_facts("MCD", facts).quarterly
    }


def test_mcd_shape_three_comparatives_in_one_10k() -> None:
    # One FY2025 10-K carries three annual comparatives, all tagged fy=2025, oldest first.
    facts = _facts(
        {
            "Revenues": [
                _fact("2023-12-31", 25_494_000_000, start="2023-01-01"),
                _fact("2024-12-31", 25_920_000_000, start="2024-01-01"),
                _fact("2025-12-31", 26_885_000_000, start="2025-01-01"),
            ]
        }
    )
    annual = _annual(facts)
    assert sorted(annual) == [2023, 2024, 2025]
    assert annual[2025]["revenue"] == 26_885_000_000
    assert annual[2024]["revenue"] == 25_920_000_000
    assert annual[2023]["revenue"] == 25_494_000_000
    assert str(annual[2025]["period_end_date"]) == "2025-12-31"


def test_quarter_length_fy_fact_never_lands_in_annual() -> None:
    facts = _facts({"Revenues": [_fact("2025-12-31", 6_900_000_000, start="2025-10-01")]})
    assert parse_company_facts("MCD", facts).annual == []


def test_transition_period_of_335_days_rejected() -> None:
    facts = _facts({"Revenues": [_fact("2025-12-31", 24_000_000_000, start="2025-01-30")]})
    assert parse_company_facts("MCD", facts).annual == []


def test_instant_fact_attaches_to_annual_row_with_same_end() -> None:
    facts = _facts(
        {
            "Revenues": [_fact("2025-12-31", 26_885_000_000, start="2025-01-01")],
            "Assets": [_fact("2025-12-31", 59_000_000_000)],
        }
    )
    annual = _annual(facts)
    assert annual[2025]["total_assets"] == 59_000_000_000


def test_instant_fact_without_matching_duration_row_is_dropped() -> None:
    facts = _facts(
        {
            "Revenues": [_fact("2025-12-31", 26_885_000_000, start="2025-01-01")],
            "Assets": [_fact("2024-12-31", 55_000_000_000)],
        }
    )
    annual = _annual(facts)
    assert sorted(annual) == [2025]
    assert annual[2025].get("total_assets") is None


def test_instant_concept_with_no_matching_end_falls_back_to_next_concept() -> None:
    facts = _facts(
        {
            "Revenues": [_fact("2025-12-31", 26_885_000_000, start="2025-01-01")],
            "LongTermDebt": [_fact("2024-12-31", 38_000_000_000)],
            "LongTermDebtNoncurrent": [_fact("2025-12-31", 39_000_000_000)],
        }
    )
    assert _annual(facts)[2025]["total_debt"] == 39_000_000_000


def test_52_53_week_year_of_371_days_accepted() -> None:
    facts = _facts({"Revenues": [_fact("2014-02-02", 42_000_000_000, start="2013-01-27")]})
    annual = _annual(facts)
    assert sorted(annual) == [2014]
    assert annual[2014]["revenue"] == 42_000_000_000


def test_january_year_end_is_fiscal_year_of_end() -> None:
    # Best Buy: year ending 2014-02-01 carries frame CY2013 but is fiscal 2014.
    bby = _fact("2014-02-01", 42_410_000_000, start="2013-02-03", fy=2014, filed="2014-03-28")
    bby["frame"] = "CY2013"
    annual = _annual(_facts({"Revenues": [bby]}))
    assert sorted(annual) == [2014]
    assert annual[2014]["revenue"] == 42_410_000_000


@pytest.mark.parametrize("newest_first", [True, False])
def test_later_filed_wins_regardless_of_list_order(newest_first: bool) -> None:
    old = _fact(
        "2024-12-31",
        25_000_000_000,
        start="2024-01-01",
        fy=2024,
        filed="2025-02-20",
        accn="0000063908-25-000010",
    )
    new = _fact(
        "2024-12-31",
        25_920_000_000,
        start="2024-01-01",
        fy=2025,
        filed="2026-02-20",
        accn="0000063908-26-000010",
    )
    entries = [new, old] if newest_first else [old, new]
    assert _annual(_facts({"Revenues": entries}))[2024]["revenue"] == 25_920_000_000


@pytest.mark.parametrize("higher_accn_first", [True, False])
def test_equal_filed_latest_accn_wins(higher_accn_first: bool) -> None:
    low = _fact("2025-12-31", 1.0, start="2025-01-01", accn="0000063908-26-000010")
    high = _fact("2025-12-31", 2.0, start="2025-01-01", accn="0000063908-26-000011")
    entries = [high, low] if higher_accn_first else [low, high]
    assert _annual(_facts({"Revenues": entries}))[2025]["revenue"] == 2.0


def test_fiscal_year_collision_keeps_later_end() -> None:
    # Fiscal-year-end change: two accepted annual periods end in calendar 2014.
    facts = _facts(
        {
            "Revenues": [
                _fact("2014-02-01", 1.0, start="2013-02-03", fy=2014, filed="2014-03-28"),
                _fact("2014-12-31", 2.0, start="2014-01-01", fy=2014, filed="2015-03-01"),
            ]
        }
    )
    with capture_logs() as logs:
        rows = parse_company_facts("MCD", facts).annual
    assert len(rows) == 1
    assert rows[0]["fiscal_year"] == 2014
    assert str(rows[0]["period_end_date"]) == "2014-12-31"
    assert rows[0]["revenue"] == 2.0
    assert [entry["event"] for entry in logs] == ["sec_edgar.fiscal_year_collision"]


def test_malformed_entries_are_skipped() -> None:
    good = _fact("2025-12-31", 26_885_000_000, start="2025-01-01")
    no_end = _fact("2025-12-31", 1.0, start="2025-01-01")
    del no_end["end"]
    no_val = _fact("2024-12-31", 1.0, start="2024-01-01")
    no_val["val"] = None
    bad_start = _fact("2023-12-31", 1.0, start="not-a-date")
    bad_end = _fact("not-a-date", 1.0, start="2023-01-01")
    facts = _facts({"Revenues": [no_end, no_val, bad_start, bad_end, good]})
    annual = _annual(facts)
    assert sorted(annual) == [2025]
    assert annual[2025]["revenue"] == 26_885_000_000


def test_181_day_10q_fact_never_lands_in_quarterly() -> None:
    ytd = _fact("2025-06-30", 13_000_000_000, start="2025-01-01", form="10-Q", fp="Q2")
    assert parse_company_facts("MCD", _facts({"Revenues": [ytd]})).quarterly == []


def test_quarter_ordinal_within_calendar_fiscal_year() -> None:
    facts = _facts(
        {
            "Revenues": [
                _fact("2024-12-31", 25_920_000_000, start="2024-01-01", fy=2024),
                _fact(
                    "2025-03-31",
                    6_000_000_000,
                    start="2025-01-01",
                    form="10-Q",
                    fy=2025,
                    fp="Q1",
                    filed="2025-05-01",
                ),
                _fact(
                    "2024-06-30",
                    6_500_000_000,
                    start="2024-04-01",
                    form="10-Q",
                    fy=2024,
                    fp="Q2",
                    filed="2024-08-01",
                ),
            ]
        }
    )
    quarterly = _quarterly(facts)
    assert sorted(quarterly) == [(2024, 2), (2025, 1)]
    assert quarterly[(2025, 1)]["revenue"] == 6_000_000_000
    assert quarterly[(2024, 2)]["revenue"] == 6_500_000_000


def test_in_progress_fiscal_year_quarter_for_september_filer() -> None:
    # AAPL: Q1 FY2025 ends 2024-12-28, Q1 FY2026 ends 2025-12-27; newest 10-K ends 2025-09-27.
    facts = _facts(
        {
            "Revenues": [
                _fact("2024-09-28", 391_035_000_000, start="2023-10-01", fy=2024),
                _fact("2025-09-27", 416_161_000_000, start="2024-09-29", fy=2025),
                _fact(
                    "2024-12-28",
                    124_300_000_000,
                    start="2024-09-29",
                    form="10-Q",
                    fy=2025,
                    fp="Q1",
                    filed="2025-01-31",
                ),
                _fact(
                    "2025-12-27",
                    143_756_000_000,
                    start="2025-09-28",
                    form="10-Q",
                    fy=2026,
                    fp="Q1",
                    filed="2026-01-30",
                ),
            ]
        }
    )
    quarterly = _quarterly(facts)
    assert sorted(quarterly) == [(2025, 1), (2026, 1)]
    assert quarterly[(2025, 1)]["revenue"] == 124_300_000_000
    assert quarterly[(2026, 1)]["revenue"] == 143_756_000_000


def test_quarter_without_annual_context_falls_back_to_first_filing_fp() -> None:
    first = _fact(
        "2025-03-31",
        6_000_000_000,
        start="2025-01-01",
        form="10-Q",
        fy=2025,
        fp="Q1",
        filed="2025-05-01",
        accn="0000063908-25-000020",
    )
    comparative = _fact(
        "2025-03-31",
        6_000_000_000,
        start="2025-01-01",
        form="10-Q",
        fy=2026,
        fp="Q1",
        filed="2026-05-01",
        accn="0000063908-26-000020",
    )
    quarterly = _quarterly(_facts({"Revenues": [comparative, first]}))
    assert sorted(quarterly) == [(2025, 1)]


def test_quarterly_instant_attaches_by_end_and_prior_year_end_instant_dropped() -> None:
    facts = _facts(
        {
            "Revenues": [
                _fact(
                    "2025-03-31",
                    6_000_000_000,
                    start="2025-01-01",
                    form="10-Q",
                    fy=2025,
                    fp="Q1",
                    filed="2025-05-01",
                )
            ],
            "CashAndCashEquivalentsAtCarryingValue": [
                _fact(
                    "2025-03-31", 1_200_000_000, form="10-Q", fy=2025, fp="Q1", filed="2025-05-01"
                ),
                _fact(
                    "2024-12-31", 1_100_000_000, form="10-Q", fy=2025, fp="Q1", filed="2025-05-01"
                ),
            ],
        }
    )
    quarterly = _quarterly(facts)
    assert sorted(quarterly) == [(2025, 1)]
    assert quarterly[(2025, 1)]["cash"] == 1_200_000_000


def _q(
    end: str, start: str, *, fy: int, fp: str, filed: str, val: float = 1.0
) -> dict[str, object]:
    return _fact(end, val, start=start, form="10-Q", fy=fy, fp=fp, filed=filed)


def test_quarter_number_comes_from_period_not_first_filing_fp() -> None:
    facts = _facts(
        {
            "Revenues": [
                _fact("2024-12-31", 25_920_000_000, start="2024-01-01", fy=2024),
                _q("2025-03-31", "2025-01-01", fy=2025, fp="Q3", filed="2025-05-01"),
            ]
        }
    )
    assert sorted(_quarterly(facts)) == [(2025, 1)]


def test_quarterly_fiscal_quarter_collision_keeps_later_end() -> None:
    facts = _facts(
        {
            "Revenues": [
                _fact("2024-12-31", 25_920_000_000, start="2024-01-01", fy=2024),
                _q("2025-03-31", "2025-01-01", fy=2025, fp="Q1", filed="2025-05-01", val=1.0),
                _q("2025-04-20", "2025-01-21", fy=2025, fp="Q2", filed="2025-06-01", val=2.0),
            ]
        }
    )
    with capture_logs() as logs:
        quarterly = _quarterly(facts)
    assert sorted(quarterly) == [(2025, 1)]
    assert quarterly[(2025, 1)]["revenue"] == 2.0
    assert str(quarterly[(2025, 1)]["period_end_date"]) == "2025-04-20"
    assert [entry["event"] for entry in logs] == ["sec_edgar.fiscal_quarter_collision"]


def test_annual_end_dropped_by_year_collision_still_numbers_quarters() -> None:
    # Annual periods ending 2014-02-01 and 2014-12-31 collide on fiscal_year 2014 and the
    # first is dropped; the quarter ending 2013-11-02 is in range of only that dropped end.
    facts = _facts(
        {
            "Revenues": [
                _fact("2014-02-01", 1.0, start="2013-02-03", fy=2014, filed="2014-03-28"),
                _fact("2014-12-31", 2.0, start="2014-01-01", fy=2014, filed="2015-03-01"),
                _q("2013-11-02", "2013-08-04", fy=2013, fp="Q9", filed="2013-12-01"),
            ]
        }
    )
    assert sorted(_quarterly(facts)) == [(2014, 3)]


def test_fiscal_quarter_key_counts_back_from_next_annual_end() -> None:
    annual_ends = [date(2024, 12, 31)]
    assert _fiscal_quarter_key(date(2024, 9, 30), annual_ends, None) == (2024, 3)


def test_fiscal_quarter_key_counts_forward_from_previous_annual_end() -> None:
    annual_ends = [date(2023, 9, 30)]
    assert _fiscal_quarter_key(date(2024, 3, 30), annual_ends, None) == (2024, 2)


def test_fiscal_quarter_key_prefers_next_annual_end() -> None:
    annual_ends = [date(2023, 12, 31), date(2024, 12, 31)]
    assert _fiscal_quarter_key(date(2024, 3, 31), annual_ends, None) == (2024, 1)


def test_fiscal_quarter_key_without_annual_end_in_range_uses_fallback() -> None:
    assert _fiscal_quarter_key(date(2025, 3, 31), [], (2025, 1)) == (2025, 1)
    assert _fiscal_quarter_key(date(2025, 3, 31), [date(2020, 12, 31)], (2025, 1)) == (2025, 1)


def test_fiscal_quarter_key_out_of_range_ordinal_uses_fallback() -> None:
    # 10 days after the previous annual end rounds to ordinal 0, outside 1..4.
    assert _fiscal_quarter_key(date(2025, 1, 10), [date(2024, 12, 31)], (2025, 1)) == (2025, 1)
    assert _fiscal_quarter_key(date(2025, 1, 10), [date(2024, 12, 31)], None) is None


def test_fiscal_quarter_key_none_without_fallback() -> None:
    assert _fiscal_quarter_key(date(2025, 3, 31), [], None) is None


def test_quarter_with_no_annual_context_and_no_quarter_fp_is_dropped() -> None:
    odd = _q("2025-03-31", "2025-01-01", fy=2025, fp="FY", filed="2025-05-01")
    assert parse_company_facts("MCD", _facts({"Revenues": [odd]})).quarterly == []


def test_fallback_uses_earliest_entry_with_a_quarter_fp() -> None:
    # Earliest-filed entry carries a non-quarter fp; the earliest valid one labels the quarter.
    facts = _facts(
        {
            "Revenues": [
                _q("2025-03-31", "2025-01-01", fy=2025, fp="FY", filed="2025-04-01"),
                _q("2025-03-31", "2025-01-01", fy=2025, fp="Q1", filed="2025-05-01"),
                _q("2025-03-31", "2025-01-01", fy=2026, fp="Q1", filed="2026-05-01"),
            ]
        }
    )
    assert sorted(_quarterly(facts)) == [(2025, 1)]


def test_quarter_created_only_by_a_column_the_table_does_not_store_is_dropped() -> None:
    # AAPL 10-Qs re-report the prior fiscal-year-end quarter's dividends only; that
    # column is not in financials_quarterly, so no (fy, 4) row of bare balances.
    facts = _facts(
        {
            "PaymentsOfDividends": [
                _fact(
                    "2013-09-28",
                    2_800_000_000,
                    start="2013-06-30",
                    form="10-Q",
                    fy=2014,
                    fp="Q1",
                    filed="2014-01-28",
                )
            ],
            "CashAndCashEquivalentsAtCarryingValue": [
                _fact(
                    "2013-09-28", 14_259_000_000, form="10-Q", fy=2014, fp="Q1", filed="2014-01-28"
                ),
            ],
        }
    )
    assert parse_company_facts("AAPL", facts).quarterly == []


# ---------- #123: concept resolved per period, not per column ----------


def test_concept_resolved_per_period_higher_priority_wins_overlap() -> None:
    # Revenues (X) only for 2017-2018; SalesRevenueNet (Y) for 2014-2017.
    facts = _facts(
        {
            "Revenues": [
                _fact("2017-12-31", 17_000_000_000, start="2017-01-01"),
                _fact("2018-12-31", 18_000_000_000, start="2018-01-01"),
            ],
            "SalesRevenueNet": [
                _fact("2014-12-31", 14_000_000_000, start="2014-01-01"),
                _fact("2015-12-31", 15_000_000_000, start="2015-01-01"),
                _fact("2016-12-31", 16_000_000_000, start="2016-01-01"),
                _fact("2017-12-31", 16_900_000_000, start="2017-01-01"),
            ],
        }
    )
    annual = _annual(facts)
    assert sorted(annual) == [2014, 2015, 2016, 2017, 2018]
    assert [annual[y]["revenue"] for y in range(2014, 2019)] == [
        14_000_000_000,
        15_000_000_000,
        16_000_000_000,
        17_000_000_000,
        18_000_000_000,
    ]


# The next three already held under the per-column rule; they guard the per-period one.
def test_short_fact_under_first_concept_does_not_block_second() -> None:
    facts = _facts(
        {
            "Revenues": [_fact("2011-01-31", 249_000_000, start="2011-01-01")],
            "SalesRevenueNet": [_fact("2011-02-26", 49_694_000_000, start="2010-02-28")],
        }
    )
    annual = _annual(facts)
    assert sorted(annual) == [2011]
    assert annual[2011]["revenue"] == 49_694_000_000


def test_higher_priority_concept_wins_even_if_lower_filed_later() -> None:
    facts = _facts(
        {
            "Revenues": [_fact("2025-12-31", 26_885_000_000, start="2025-01-01")],
            "SalesRevenueNet": [
                _fact(
                    "2025-12-31",
                    26_000_000_000,
                    start="2025-01-01",
                    filed="2026-06-01",
                    accn="0000063908-26-000099",
                )
            ],
        }
    )
    assert _annual(facts)[2025]["revenue"] == 26_885_000_000


def test_losing_concept_amendment_does_not_mark_restated() -> None:
    facts = _facts(
        {
            "Revenues": [_fact("2025-12-31", 26_885_000_000, start="2025-01-01")],
            "SalesRevenueNet": [
                _fact("2025-12-31", 26_000_000_000, start="2025-01-01", form="10-K/A")
            ],
        }
    )
    row = _annual(facts)[2025]
    assert row["revenue"] == 26_885_000_000
    assert row["is_restated"] is False


def test_quarterly_concept_resolved_per_period() -> None:
    def q(end: str, start: str, val: float, fp: str) -> dict[str, object]:
        return _fact(end, val, start=start, form="10-Q", fy=2025, fp=fp, filed="2025-08-01")

    facts = _facts(
        {
            "Revenues": [
                q("2025-03-31", "2025-01-01", 6_000_000_000, "Q1"),
                q("2025-06-30", "2025-01-01", 12_500_000_000, "Q2"),  # 181-day YTD
            ],
            "SalesRevenueNet": [q("2025-06-30", "2025-04-01", 6_500_000_000, "Q2")],
        }
    )
    quarterly = _quarterly(facts)
    assert sorted(quarterly) == [(2025, 1), (2025, 2)]
    assert quarterly[(2025, 1)]["revenue"] == 6_000_000_000
    assert quarterly[(2025, 2)]["revenue"] == 6_500_000_000


def test_revenue_list_extended_after_existing_three() -> None:
    from bot.ingest.sec_edgar import ANNUAL_CONCEPT_MAP

    assert ANNUAL_CONCEPT_MAP["revenue"] == [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ]


def test_new_revenue_concepts_fill_periods_the_others_miss() -> None:
    facts = _facts(
        {
            "SalesRevenueNet": [_fact("2023-12-31", 23_000_000_000, start="2023-01-01")],
            "RevenueFromContractWithCustomerIncludingAssessedTax": [
                _fact("2023-12-31", 23_500_000_000, start="2023-01-01"),
                _fact("2024-12-31", 24_000_000_000, start="2024-01-01"),
            ],
            "SalesRevenueGoodsNet": [_fact("2025-12-31", 25_000_000_000, start="2025-01-01")],
        }
    )
    annual = _annual(facts)
    assert annual[2023]["revenue"] == 23_000_000_000
    assert annual[2024]["revenue"] == 24_000_000_000
    assert annual[2025]["revenue"] == 25_000_000_000


def test_instant_concept_resolved_per_period() -> None:
    facts = _facts(
        {
            "Revenues": [
                _fact("2024-12-31", 25_920_000_000, start="2024-01-01"),
                _fact("2025-12-31", 26_885_000_000, start="2025-01-01"),
            ],
            "LongTermDebt": [_fact("2024-12-31", 38_000_000_000)],
            "LongTermDebtNoncurrent": [
                _fact("2024-12-31", 37_000_000_000),
                _fact("2025-12-31", 39_000_000_000),
            ],
        }
    )
    annual = _annual(facts)
    assert annual[2024]["total_debt"] == 38_000_000_000
    assert annual[2025]["total_debt"] == 39_000_000_000


# Best Buy fiscal year ends; the year ending 2013-02-02 is an 11-month transition.
_BBY_ENDS = [
    "2008-03-01", "2009-02-28", "2010-02-27", "2011-02-26", "2012-03-03", "2013-02-02",
    "2014-02-01", "2015-01-31", "2016-01-30", "2017-01-28", "2018-02-03", "2019-02-02",
    "2020-02-01", "2021-01-30", "2022-01-29", "2023-01-28", "2024-02-03", "2025-02-01",
]  # fmt: skip


def test_bby_shaped_series_has_revenue_every_year_from_2009() -> None:
    def year(i: int, val: float, filed: str) -> dict[str, object]:
        # fy is irrelevant here: fp="FY" never feeds the quarterly fallback label.
        start = date.fromisoformat(_BBY_ENDS[i - 1]).toordinal() + 1
        return _fact(
            _BBY_ENDS[i], val, start=date.fromordinal(start).isoformat(), fy=0, filed=filed
        )

    sales = [year(i, 40e9 + i * 1e8, f"{_BBY_ENDS[i][:4]}-03-25") for i in range(1, 11)]
    revenues = [year(i, 40e9 + i * 1e8, f"{_BBY_ENDS[i][:4]}-03-26") for i in range(9, 18)]
    revenues += [
        _fact("2011-01-31", 249_000_000, start="2011-01-01", filed="2014-03-28"),
        _fact("2012-01-31", 189_000_000, start="2012-01-01", filed="2014-03-28"),
    ]
    annual = _annual(_facts({"Revenues": revenues, "SalesRevenueNet": sales}))
    expected = [y for y in range(2009, 2026) if y != 2013]  # 2013: 335-day transition
    assert sorted(annual) == expected
    assert all(
        r["revenue"] is not None and r["revenue"] >= 1_000_000_000 for r in annual.values()
    )
