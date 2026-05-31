"""Unit tests for the screener rule abstraction + registry (issue #3 / M3.2)."""

from __future__ import annotations

import pytest

from bot.screener.rules import (
    MinMarketCap,
    Rule,
    RuleResult,
    get_rule,
    register,
    registered_rules,
)
from bot.screener.types import CompanyData, IndustryBenchmarks


@pytest.fixture
def benchmarks() -> IndustryBenchmarks:
    return IndustryBenchmarks(
        industry="Software",
        region="US",
        year=2025,
        pe=25.0,
        roic=0.12,
        wacc=0.09,
    )


@pytest.fixture
def big_company() -> CompanyData:
    return CompanyData(
        ticker="AAA",
        name="Big Co",
        industry="Software",
        region="US",
        market_cap=5_000_000_000.0,
    )


@pytest.fixture
def small_company() -> CompanyData:
    return CompanyData(
        ticker="BBB",
        name="Small Co",
        industry="Software",
        region="US",
        market_cap=50_000_000.0,
    )


def test_rule_result_defaults() -> None:
    r = RuleResult(passed=True)
    assert r.passed is True
    assert r.score == 0.0
    assert r.reason == ""


def test_market_cap_min_is_registered_and_resolvable() -> None:
    assert get_rule("min_market_cap") is MinMarketCap
    assert "min_market_cap" in registered_rules()


def test_market_cap_min_passes_large_company(
    big_company: CompanyData, benchmarks: IndustryBenchmarks
) -> None:
    result = MinMarketCap().evaluate(big_company, benchmarks)
    assert result.passed is True
    assert "market_cap" in result.reason


def test_market_cap_min_fails_small_company(
    small_company: CompanyData, benchmarks: IndustryBenchmarks
) -> None:
    result = MinMarketCap().evaluate(small_company, benchmarks)
    assert result.passed is False


def test_market_cap_min_fails_when_datum_missing(
    benchmarks: IndustryBenchmarks,
) -> None:
    company = CompanyData(ticker="CCC", name="Unknown", market_cap=None)
    result = MinMarketCap().evaluate(company, benchmarks)
    assert result.passed is False
    assert "unavailable" in result.reason


def test_market_cap_min_honours_configured_threshold(
    small_company: CompanyData, benchmarks: IndustryBenchmarks
) -> None:
    # A 10M floor lets the 50M company through.
    result = MinMarketCap(minimum_usd=10_000_000.0).evaluate(small_company, benchmarks)
    assert result.passed is True


def test_registry_rejects_duplicate_name() -> None:
    with pytest.raises(ValueError, match="already registered"):

        @register
        class DuplicateMarketCap(Rule):
            name = "min_market_cap"

            def evaluate(
                self, company: CompanyData, benchmarks: IndustryBenchmarks
            ) -> RuleResult:
                return RuleResult(passed=True)


def test_registry_rejects_rule_without_name() -> None:
    with pytest.raises(ValueError, match="non-empty"):

        @register
        class NamelessRule(Rule):
            def evaluate(
                self, company: CompanyData, benchmarks: IndustryBenchmarks
            ) -> RuleResult:
                return RuleResult(passed=True)


def test_get_rule_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError, match="unknown rule"):
        get_rule("does_not_exist")


def test_registered_rules_returns_a_copy() -> None:
    snapshot = registered_rules()
    snapshot.clear()
    # Mutating the returned dict must not affect the live registry.
    assert get_rule("min_market_cap") is MinMarketCap
