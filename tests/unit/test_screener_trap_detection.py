"""Unit tests for the trap-detection rules (issue #6 / M3.5, spec §6.4).

Trap detectors are *eliminatory*: a company that trips one is dropped even if it
looks cheap. These are the most Damodaran-specific filters — the central one,
:class:`ROICAboveSectorWACC`, eliminates value destroyers (ROIC < sector WACC).

Every rule gets a passing and a failing fixture. Best-effort SEC flags
(:class:`AuditorChangesAndLateFilings`) pass when the datum is unknown rather
than punishing a company for a gap in the data. The Sloan-accruals rule carries
an explicit hand-computed expected-value test.
"""

from __future__ import annotations

from bot.screener.rules import (
    AuditorChangesAndLateFilings,
    OperatingMarginNotContracting,
    RevenueNotDeclining,
    ROICAboveSectorWACC,
    ShareCountNotDiluting,
    SloanAccrualsBelow,
    get_rule,
)
from bot.screener.types import CompanyData, IndustryBenchmarks


def _company(**overrides: object) -> CompanyData:
    base: dict[str, object] = {
        "ticker": "AAA",
        "name": "Test Co",
        "industry": "Software",
        "region": "US",
    }
    base.update(overrides)
    return CompanyData(**base)  # type: ignore[arg-type]


def _benchmarks(**overrides: object) -> IndustryBenchmarks:
    base: dict[str, object] = {"industry": "Software", "region": "US", "year": 2025}
    base.update(overrides)
    return IndustryBenchmarks(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# RevenueNotDeclining
# --------------------------------------------------------------------------- #
def test_revenue_not_declining_registered() -> None:
    assert get_rule("revenue_not_declining") is RevenueNotDeclining


def test_revenue_not_declining_pass_growing() -> None:
    # Steady growth -> avg growth well above the -5% floor.
    result = RevenueNotDeclining().evaluate(
        _company(revenue_history=(100.0, 110.0, 120.0, 130.0)), _benchmarks()
    )
    assert result.passed is True


def test_revenue_not_declining_fail_collapsing() -> None:
    # ~-15% per year -> below the -5% floor -> trap.
    result = RevenueNotDeclining().evaluate(
        _company(revenue_history=(200.0, 170.0, 144.0, 122.0)), _benchmarks()
    )
    assert result.passed is False


def test_revenue_not_declining_pass_mild_dip() -> None:
    # -2% per year is within the -5% tolerance.
    result = RevenueNotDeclining().evaluate(
        _company(revenue_history=(100.0, 98.0, 96.04, 94.12)), _benchmarks()
    )
    assert result.passed is True


def test_revenue_not_declining_insufficient_history_fails() -> None:
    # Need 3 growth observations (4 years). Two years cannot be judged -> fail.
    result = RevenueNotDeclining().evaluate(
        _company(revenue_history=(100.0, 90.0)), _benchmarks()
    )
    assert result.passed is False
    assert "insufficient" in result.reason


def test_revenue_not_declining_nonpositive_revenue_fails() -> None:
    result = RevenueNotDeclining().evaluate(
        _company(revenue_history=(100.0, 0.0, 50.0, 40.0)), _benchmarks()
    )
    assert result.passed is False


def test_revenue_not_declining_configurable() -> None:
    # Loosen the floor to -20%: a -15% decliner now survives.
    result = RevenueNotDeclining(max_decline=-0.20).evaluate(
        _company(revenue_history=(200.0, 170.0, 144.0, 122.0)), _benchmarks()
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# OperatingMarginNotContracting
# --------------------------------------------------------------------------- #
def test_operating_margin_not_contracting_registered() -> None:
    assert get_rule("operating_margin_not_contracting") is OperatingMarginNotContracting


def test_operating_margin_not_contracting_pass_stable() -> None:
    # Margin flat / improving over the window.
    result = OperatingMarginNotContracting().evaluate(
        _company(operating_margin_history=(0.18, 0.19, 0.20, 0.21)), _benchmarks()
    )
    assert result.passed is True


def test_operating_margin_not_contracting_fail_eroding() -> None:
    # 20% -> 16% = -400bps, beyond the -200bps tolerance -> trap.
    result = OperatingMarginNotContracting().evaluate(
        _company(operating_margin_history=(0.20, 0.19, 0.17, 0.16)), _benchmarks()
    )
    assert result.passed is False


def test_operating_margin_not_contracting_pass_within_tolerance() -> None:
    # 20% -> 18.5% = -150bps, within the -200bps tolerance.
    result = OperatingMarginNotContracting().evaluate(
        _company(operating_margin_history=(0.20, 0.195, 0.19, 0.185)), _benchmarks()
    )
    assert result.passed is True


def test_operating_margin_not_contracting_insufficient_history_fails() -> None:
    result = OperatingMarginNotContracting().evaluate(
        _company(operating_margin_history=(0.20,)), _benchmarks()
    )
    assert result.passed is False
    assert "insufficient" in result.reason


def test_operating_margin_not_contracting_configurable() -> None:
    # Tighten tolerance to -100bps: a -150bps contraction now fails.
    result = OperatingMarginNotContracting(max_contraction_bps=-100.0).evaluate(
        _company(operating_margin_history=(0.20, 0.195, 0.19, 0.185)), _benchmarks()
    )
    assert result.passed is False


# --------------------------------------------------------------------------- #
# ROICAboveSectorWACC — the central Damodaran filter
# --------------------------------------------------------------------------- #
def test_roic_above_sector_wacc_registered() -> None:
    assert get_rule("roic_above_sector_wacc") is ROICAboveSectorWACC


def test_roic_above_sector_wacc_pass_value_creator() -> None:
    # ROIC 15% comfortably above sector WACC 9% -> creates value.
    result = ROICAboveSectorWACC().evaluate(
        _company(roic=0.15), _benchmarks(wacc=0.09)
    )
    assert result.passed is True


def test_roic_above_sector_wacc_fail_value_destroyer() -> None:
    # ROIC 6% below sector WACC 9% -> destroys value -> trap.
    result = ROICAboveSectorWACC().evaluate(
        _company(roic=0.06), _benchmarks(wacc=0.09)
    )
    assert result.passed is False


def test_roic_above_sector_wacc_uses_sector_wacc_lookup() -> None:
    # Same ROIC, two different sector WACCs flips the verdict -> the rule reads
    # the Damodaran sector WACC, not an absolute hurdle.
    company = _company(roic=0.10)
    assert ROICAboveSectorWACC().evaluate(company, _benchmarks(wacc=0.08)).passed is True
    assert (
        ROICAboveSectorWACC().evaluate(company, _benchmarks(wacc=0.12)).passed is False
    )


def test_roic_above_sector_wacc_missing_roic_fails() -> None:
    result = ROICAboveSectorWACC().evaluate(_company(roic=None), _benchmarks(wacc=0.09))
    assert result.passed is False
    assert "unavailable" in result.reason


def test_roic_above_sector_wacc_missing_wacc_skips() -> None:
    # No sector WACC median -> the central filter cannot run; skip, do not
    # disqualify on a data gap alone.
    result = ROICAboveSectorWACC().evaluate(_company(roic=0.15), _benchmarks(wacc=None))
    assert result.skipped is True
    assert result.passed is False


# --------------------------------------------------------------------------- #
# SloanAccrualsBelow — explicit hand-computed math
# --------------------------------------------------------------------------- #
def test_sloan_accruals_registered() -> None:
    assert get_rule("sloan_accruals_below") is SloanAccrualsBelow


def test_sloan_accruals_handcomputed_value() -> None:
    # Sloan ratio = (NI - OCF) / TA.
    # NI=100, OCF=40, TA=700 -> (100 - 40) / 700 = 60 / 700 = 0.0857142857...
    company = _company(net_income=100.0, operating_cashflow=40.0, total_assets=700.0)
    result = SloanAccrualsBelow().evaluate(company, _benchmarks())
    assert result.passed is True
    # Confirm the exact computed ratio surfaces in the reason for traceability.
    assert "0.086" in result.reason  # 0.0857 rounded to 3dp


def test_sloan_accruals_pass_low() -> None:
    # Earnings backed by cash -> low/negative accruals.
    company = _company(net_income=80.0, operating_cashflow=120.0, total_assets=700.0)
    result = SloanAccrualsBelow().evaluate(company, _benchmarks())
    assert result.passed is True


def test_sloan_accruals_fail_high() -> None:
    # NI=200, OCF=40, TA=700 -> 160/700 = 0.2286 > 0.10 -> trap.
    company = _company(net_income=200.0, operating_cashflow=40.0, total_assets=700.0)
    result = SloanAccrualsBelow().evaluate(company, _benchmarks())
    assert result.passed is False


def test_sloan_accruals_boundary_fails() -> None:
    # Exactly at the 0.10 threshold: not strictly below -> fail.
    # NI=110, OCF=40, TA=700 -> 70/700 = 0.10 exactly.
    company = _company(net_income=110.0, operating_cashflow=40.0, total_assets=700.0)
    result = SloanAccrualsBelow().evaluate(company, _benchmarks())
    assert result.passed is False


def test_sloan_accruals_missing_fails() -> None:
    result = SloanAccrualsBelow().evaluate(
        _company(net_income=100.0, operating_cashflow=40.0), _benchmarks()
    )
    assert result.passed is False
    assert "unavailable" in result.reason


def test_sloan_accruals_nonpositive_assets_fails() -> None:
    result = SloanAccrualsBelow().evaluate(
        _company(net_income=100.0, operating_cashflow=40.0, total_assets=0.0),
        _benchmarks(),
    )
    assert result.passed is False


def test_sloan_accruals_configurable() -> None:
    # Loosen the threshold to 0.30: the 0.2286 case now passes.
    company = _company(net_income=200.0, operating_cashflow=40.0, total_assets=700.0)
    result = SloanAccrualsBelow(maximum=0.30).evaluate(company, _benchmarks())
    assert result.passed is True


# --------------------------------------------------------------------------- #
# ShareCountNotDiluting
# --------------------------------------------------------------------------- #
def test_share_count_not_diluting_registered() -> None:
    assert get_rule("share_count_not_diluting") is ShareCountNotDiluting


def test_share_count_not_diluting_pass_buyback() -> None:
    # Shrinking share count (buybacks) -> no dilution.
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(110.0, 105.0, 100.0)), _benchmarks()
    )
    assert result.passed is True


def test_share_count_not_diluting_fail_heavy_issuance() -> None:
    # ~10%/yr issuance, no M&A -> trap.
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(100.0, 110.0, 121.0)), _benchmarks()
    )
    assert result.passed is False


def test_share_count_not_diluting_pass_when_ma_justified() -> None:
    # Same heavy issuance but funded by a material acquisition -> not a trap.
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(100.0, 110.0, 121.0), had_recent_ma=True),
        _benchmarks(),
    )
    assert result.passed is True


def test_share_count_not_diluting_pass_within_tolerance() -> None:
    # ~3%/yr is below the 5% default.
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(100.0, 103.0, 106.09)), _benchmarks()
    )
    assert result.passed is True


def test_share_count_not_diluting_insufficient_history_fails() -> None:
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(100.0,)), _benchmarks()
    )
    assert result.passed is False
    assert "insufficient" in result.reason


def test_share_count_not_diluting_nonpositive_fails() -> None:
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(0.0, 110.0)), _benchmarks()
    )
    assert result.passed is False


def test_share_count_not_diluting_configurable() -> None:
    # Tighten to 2%: a 3%/yr issuer now fails.
    result = ShareCountNotDiluting(max_annual_growth=0.02).evaluate(
        _company(share_count_history=(100.0, 103.0, 106.09)), _benchmarks()
    )
    assert result.passed is False


# --------------------------------------------------------------------------- #
# AuditorChangesAndLateFilings — best-effort SEC flags
# --------------------------------------------------------------------------- #
def test_auditor_changes_registered() -> None:
    assert get_rule("auditor_changes_and_late_filings") is AuditorChangesAndLateFilings


def test_auditor_changes_pass_clean() -> None:
    result = AuditorChangesAndLateFilings().evaluate(
        _company(auditor_changed=False, late_filings=False), _benchmarks()
    )
    assert result.passed is True


def test_auditor_changes_fail_on_auditor_change() -> None:
    result = AuditorChangesAndLateFilings().evaluate(
        _company(auditor_changed=True, late_filings=False), _benchmarks()
    )
    assert result.passed is False
    assert "auditor" in result.reason.lower()


def test_auditor_changes_fail_on_late_filings() -> None:
    result = AuditorChangesAndLateFilings().evaluate(
        _company(auditor_changed=False, late_filings=True), _benchmarks()
    )
    assert result.passed is False
    assert "late" in result.reason.lower()


def test_auditor_changes_unknown_data_passes() -> None:
    # Best-effort: when SEC data carries neither flag (both None), do not punish
    # the company for a data gap -> pass (skip-like, but not eliminatory).
    result = AuditorChangesAndLateFilings().evaluate(
        _company(auditor_changed=None, late_filings=None), _benchmarks()
    )
    assert result.passed is True


def test_auditor_changes_partial_unknown_clean_leg_passes() -> None:
    # One flag known-clean, the other unknown -> nothing adverse -> pass.
    result = AuditorChangesAndLateFilings().evaluate(
        _company(auditor_changed=False, late_filings=None), _benchmarks()
    )
    assert result.passed is True
