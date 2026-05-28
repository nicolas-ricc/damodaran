"""Unit tests for M3.5 trap detection rules."""

from bot.screener.rules import CompanyData, IndustryBenchmarks, get_rule
from bot.screener.trap_rules import (
    AuditorChangesAndLateFilings,
    OperatingMarginNotContracting,
    ROICAboveSectorWACC,
    RevenueNotDeclining,
    ShareCountNotDiluting,
    SloanAccrualsBelow,
)

_BM = IndustryBenchmarks()


# ---------------------------------------------------------------------------
# RevenueNotDeclining
# ---------------------------------------------------------------------------


def test_revenue_not_declining_passes_growing() -> None:
    company = CompanyData(ticker="GROW", revenue_3y=[100.0, 105.0, 110.0])
    result = RevenueNotDeclining().evaluate(company, _BM)
    assert result.passed is True
    assert result.score == 1.0
    assert ">" in result.reason


def test_revenue_not_declining_fails_heavy_decline() -> None:
    # YoY: (80-100)/100 = -20%, (60-80)/80 = -25% → avg -22.5% < -5%
    company = CompanyData(ticker="DROP", revenue_3y=[100.0, 80.0, 60.0])
    result = RevenueNotDeclining().evaluate(company, _BM)
    assert result.passed is False
    assert result.score == 0.0
    assert "<=" in result.reason


def test_revenue_not_declining_fails_missing_data() -> None:
    result = RevenueNotDeclining().evaluate(CompanyData(ticker="NODATA"), _BM)
    assert result.passed is False
    assert "insufficient" in result.reason


def test_revenue_not_declining_fails_single_value() -> None:
    company = CompanyData(ticker="ONE", revenue_3y=[100.0])
    result = RevenueNotDeclining().evaluate(company, _BM)
    assert result.passed is False


def test_revenue_not_declining_registered() -> None:
    assert get_rule("revenue_not_declining") is RevenueNotDeclining


# ---------------------------------------------------------------------------
# OperatingMarginNotContracting
# ---------------------------------------------------------------------------


def test_op_margin_not_contracting_passes_stable() -> None:
    # 20% → 20.5% → 21%: expanded +100bps
    company = CompanyData(ticker="STABLE", op_margin_3y=[0.20, 0.205, 0.21])
    result = OperatingMarginNotContracting().evaluate(company, _BM)
    assert result.passed is True
    assert result.score == 1.0


def test_op_margin_not_contracting_fails_large_contraction() -> None:
    # 20% → 18.5% → 17%: contracted -300bps > 200bps threshold
    company = CompanyData(ticker="CONT", op_margin_3y=[0.20, 0.185, 0.17])
    result = OperatingMarginNotContracting().evaluate(company, _BM)
    assert result.passed is False
    assert result.score == 0.0


def test_op_margin_not_contracting_fails_exactly_at_threshold() -> None:
    # 20% → 19% → 18%: exactly -200bps — must fail (threshold is exclusive)
    company = CompanyData(ticker="EXACT", op_margin_3y=[0.20, 0.19, 0.18])
    result = OperatingMarginNotContracting().evaluate(company, _BM)
    assert result.passed is False


def test_op_margin_not_contracting_fails_missing_data() -> None:
    result = OperatingMarginNotContracting().evaluate(CompanyData(ticker="NODATA"), _BM)
    assert result.passed is False
    assert "insufficient" in result.reason


def test_op_margin_not_contracting_registered() -> None:
    assert get_rule("operating_margin_not_contracting") is OperatingMarginNotContracting


# ---------------------------------------------------------------------------
# ROICAboveSectorWACC
# ---------------------------------------------------------------------------


def test_roic_above_wacc_passes() -> None:
    company = CompanyData(ticker="GOOD", roic=0.15)
    benchmarks = IndustryBenchmarks(wacc=0.08)
    result = ROICAboveSectorWACC().evaluate(company, benchmarks)
    assert result.passed is True
    assert result.score > 0.0
    assert "+" in result.reason


def test_roic_above_wacc_passes_score_capped_at_one() -> None:
    # ROIC=30%, WACC=8% → spread=22% > 10% → score capped at 1.0
    company = CompanyData(ticker="GREAT", roic=0.30)
    benchmarks = IndustryBenchmarks(wacc=0.08)
    result = ROICAboveSectorWACC().evaluate(company, benchmarks)
    assert result.passed is True
    assert result.score == 1.0


def test_roic_above_wacc_fails_below_wacc() -> None:
    company = CompanyData(ticker="BAD", roic=0.05)
    benchmarks = IndustryBenchmarks(wacc=0.08)
    result = ROICAboveSectorWACC().evaluate(company, benchmarks)
    assert result.passed is False
    assert result.score == 0.0


def test_roic_above_wacc_fails_missing_roic() -> None:
    result = ROICAboveSectorWACC().evaluate(
        CompanyData(ticker="NORIC"), IndustryBenchmarks(wacc=0.08)
    )
    assert result.passed is False
    assert "ROIC not available" in result.reason


def test_roic_above_wacc_fails_missing_wacc() -> None:
    result = ROICAboveSectorWACC().evaluate(CompanyData(ticker="NOWACC", roic=0.12), _BM)
    assert result.passed is False
    assert "sector WACC not available" in result.reason


def test_roic_above_wacc_registered() -> None:
    assert get_rule("roic_above_sector_wacc") is ROICAboveSectorWACC


# ---------------------------------------------------------------------------
# SloanAccrualsBelow — explicit hand-computed expected values
# ---------------------------------------------------------------------------


def test_sloan_accruals_passes_hand_computed() -> None:
    # NI=100, OCF=70, TA=1000 → (100 - 70) / 1000 = 0.030 < 0.10
    company = CompanyData(
        ticker="ACOK",
        net_income=100.0,
        operating_cashflow=70.0,
        total_assets=1000.0,
    )
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is True
    assert result.score == 1.0
    assert "0.030" in result.reason


def test_sloan_accruals_fails_hand_computed() -> None:
    # NI=200, OCF=50, TA=1000 → (200 - 50) / 1000 = 0.150 >= 0.10
    company = CompanyData(
        ticker="ACHIGH",
        net_income=200.0,
        operating_cashflow=50.0,
        total_assets=1000.0,
    )
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is False
    assert result.score == 0.0
    assert "0.150" in result.reason


def test_sloan_accruals_passes_negative_accruals() -> None:
    # NI=50, OCF=120, TA=1000 → (50 - 120) / 1000 = -0.070 < 0.10
    company = CompanyData(
        ticker="CASHGEN",
        net_income=50.0,
        operating_cashflow=120.0,
        total_assets=1000.0,
    )
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is True


def test_sloan_accruals_fails_missing_net_income() -> None:
    company = CompanyData(ticker="NONI", operating_cashflow=70.0, total_assets=1000.0)
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is False
    assert "net_income" in result.reason


def test_sloan_accruals_fails_missing_ocf() -> None:
    company = CompanyData(ticker="NOOCF", net_income=100.0, total_assets=1000.0)
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is False
    assert "operating_cashflow" in result.reason


def test_sloan_accruals_fails_missing_total_assets() -> None:
    company = CompanyData(ticker="NOTA", net_income=100.0, operating_cashflow=70.0)
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is False
    assert "total_assets" in result.reason


def test_sloan_accruals_fails_zero_total_assets() -> None:
    company = CompanyData(
        ticker="ZEROTA", net_income=100.0, operating_cashflow=70.0, total_assets=0.0
    )
    result = SloanAccrualsBelow().evaluate(company, _BM)
    assert result.passed is False
    assert "non-positive" in result.reason


def test_sloan_accruals_registered() -> None:
    assert get_rule("sloan_accruals_below") is SloanAccrualsBelow


# ---------------------------------------------------------------------------
# ShareCountNotDiluting
# ---------------------------------------------------------------------------


def test_share_count_not_diluting_passes_buybacks() -> None:
    # Shares declining: 100M → 99M → 98M → avg growth ≈ -1% < 5%
    company = CompanyData(ticker="BUY", shares_diluted_3y=[100.0, 99.0, 98.0])
    result = ShareCountNotDiluting().evaluate(company, _BM)
    assert result.passed is True
    assert result.score == 1.0


def test_share_count_not_diluting_fails_heavy_dilution() -> None:
    # 100M → 110M → 120M → avg growth ≈ 10% > 5%
    company = CompanyData(ticker="DILU", shares_diluted_3y=[100.0, 110.0, 120.0])
    result = ShareCountNotDiluting().evaluate(company, _BM)
    assert result.passed is False
    assert result.score == 0.0
    assert ">=" in result.reason


def test_share_count_not_diluting_passes_slow_dilution() -> None:
    # 100M → 102M → 104M → avg growth ≈ 2% < 5%
    company = CompanyData(ticker="SLOW", shares_diluted_3y=[100.0, 102.0, 104.0])
    result = ShareCountNotDiluting().evaluate(company, _BM)
    assert result.passed is True


def test_share_count_not_diluting_fails_missing_data() -> None:
    result = ShareCountNotDiluting().evaluate(CompanyData(ticker="NOSHARES"), _BM)
    assert result.passed is False
    assert "insufficient" in result.reason


def test_share_count_not_diluting_registered() -> None:
    assert get_rule("share_count_not_diluting") is ShareCountNotDiluting


# ---------------------------------------------------------------------------
# AuditorChangesAndLateFilings
# ---------------------------------------------------------------------------


def test_auditor_no_data_passes_as_best_effort() -> None:
    result = AuditorChangesAndLateFilings().evaluate(CompanyData(ticker="NODATA"), _BM)
    assert result.passed is True
    assert "skipped" in result.reason


def test_auditor_clean_passes() -> None:
    company = CompanyData(ticker="CLEAN", auditor_changed=False, has_late_filings=False)
    result = AuditorChangesAndLateFilings().evaluate(company, _BM)
    assert result.passed is True
    assert "no auditor changes" in result.reason


def test_auditor_change_fails() -> None:
    company = CompanyData(ticker="SWITCH", auditor_changed=True, has_late_filings=False)
    result = AuditorChangesAndLateFilings().evaluate(company, _BM)
    assert result.passed is False
    assert result.score == 0.0
    assert "auditor change" in result.reason


def test_late_filings_fails() -> None:
    company = CompanyData(ticker="LATE", auditor_changed=False, has_late_filings=True)
    result = AuditorChangesAndLateFilings().evaluate(company, _BM)
    assert result.passed is False
    assert result.score == 0.0
    assert "late filings" in result.reason


def test_both_flags_fails_with_combined_reason() -> None:
    company = CompanyData(ticker="BOTH", auditor_changed=True, has_late_filings=True)
    result = AuditorChangesAndLateFilings().evaluate(company, _BM)
    assert result.passed is False
    assert "auditor change" in result.reason
    assert "late filings" in result.reason


def test_auditor_changes_registered() -> None:
    assert get_rule("auditor_changes_and_late_filings") is AuditorChangesAndLateFilings
