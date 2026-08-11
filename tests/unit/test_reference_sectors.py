"""Canonical sector classifications over the Damodaran taxonomy."""

from __future__ import annotations

from bot.reference.industries import DAMODARAN_INDUSTRIES
from bot.reference.sectors import (
    CYCLICAL_INDUSTRIES,
    FINANCIAL_SERVICES_INDUSTRIES,
    is_cyclical,
    is_financial_services,
)


def test_every_classified_industry_is_in_the_taxonomy() -> None:
    # A typo here would silently classify nothing, so pin it.
    assert FINANCIAL_SERVICES_INDUSTRIES <= DAMODARAN_INDUSTRIES
    assert CYCLICAL_INDUSTRIES <= DAMODARAN_INDUSTRIES


def test_financials_the_substring_match_used_to_miss() -> None:
    # These are exactly the labels that "bank"/"insurance" substring matching
    # let through before this module existed.
    for industry in (
        "Investments & Asset Management",
        "Brokerage & Investment Banking",
        "Financial Svcs. (Non-bank & Insurance)",
        "Reinsurance",
        "R.E.I.T.",
    ):
        assert is_financial_services(industry), industry


def test_obvious_financials_still_classified() -> None:
    for industry in (
        "Bank (Money Center)",
        "Banks (Regional)",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
    ):
        assert is_financial_services(industry), industry


def test_non_financials_not_classified() -> None:
    for industry in ("Semiconductor", "Software (System & Application)", "Steel"):
        assert not is_financial_services(industry)


def test_cyclicals_classified() -> None:
    for industry in (
        "Auto & Truck",
        "Steel",
        "Semiconductor",
        "Oil/Gas (Production and Exploration)",
        "Homebuilding",
        "Metals & Mining",
    ):
        assert is_cyclical(industry), industry


def test_defensives_not_cyclical() -> None:
    for industry in (
        "Household Products",
        "Food Processing",
        "Utility (Water)",
        "Tobacco",
        "Drugs (Pharmaceutical)",
    ):
        assert not is_cyclical(industry), industry


def test_none_industry_is_neither() -> None:
    assert not is_financial_services(None)
    assert not is_cyclical(None)


def test_classification_is_exact_not_substring() -> None:
    # "Bank" appears inside "Brokerage & Investment Banking"; exactness matters
    # so an unmapped free-text label cannot accidentally classify.
    assert not is_financial_services("Investment Bank of Nowhere")
    assert not is_cyclical("Steel Drums Appreciation Society")
