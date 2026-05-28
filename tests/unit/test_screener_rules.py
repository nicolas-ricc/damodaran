import pytest

from bot.screener.rules import (
    _REGISTRY,
    CompanyData,
    IndustryBenchmarks,
    MarketCapMin,
    Rule,
    RuleResult,
    get_rule,
    register,
)

_FIXTURE_COMPANY = CompanyData(ticker="AAPL", market_cap=3_000_000_000_000.0)
_EMPTY_BENCHMARKS = IndustryBenchmarks()


# --- MarketCapMin ---


def test_market_cap_min_passes_large_company() -> None:
    rule = MarketCapMin(min_market_cap=1_000_000_000.0)
    result = rule.evaluate(_FIXTURE_COMPANY, _EMPTY_BENCHMARKS)
    assert result.passed is True
    assert 0.0 < result.score <= 1.0
    assert ">=" in result.reason


def test_market_cap_min_fails_small_company() -> None:
    rule = MarketCapMin(min_market_cap=1_000_000_000.0)
    tiny = CompanyData(ticker="TINY", market_cap=500_000.0)
    result = rule.evaluate(tiny, _EMPTY_BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert "<" in result.reason


def test_market_cap_min_fails_when_market_cap_none() -> None:
    rule = MarketCapMin()
    result = rule.evaluate(CompanyData(ticker="UNKN"), _EMPTY_BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert "not available" in result.reason


def test_rule_result_fields() -> None:
    r = RuleResult(passed=True, score=0.5, reason="ok")
    assert r.passed is True
    assert r.score == 0.5
    assert r.reason == "ok"


# --- Registry ---


def test_market_cap_min_is_registered() -> None:
    assert get_rule("market_cap_min") is MarketCapMin


def test_get_rule_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError, match="no_such_rule"):
        get_rule("no_such_rule")


def test_register_rejects_duplicate() -> None:
    class _Dupe(Rule):
        name = "market_cap_min"

        def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
            return RuleResult(passed=True, score=1.0, reason="dupe")

    with pytest.raises(ValueError, match="already registered"):
        register(_Dupe)


def test_register_and_lookup_new_rule() -> None:
    class _TestRule(Rule):
        name = "test_rule_xyz"

        def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
            return RuleResult(passed=True, score=1.0, reason="test")

    register(_TestRule)
    try:
        assert get_rule("test_rule_xyz") is _TestRule
    finally:
        del _REGISTRY["test_rule_xyz"]
