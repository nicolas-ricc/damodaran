"""Trap detection rules — M3.5 (all eliminatory)."""

from __future__ import annotations

from typing import ClassVar

from bot.screener.rules import CompanyData, IndustryBenchmarks, Rule, RuleResult, register


@register
class RevenueNotDeclining(Rule):
    """Avg revenue growth over last 3 years must be > threshold (default -5%)."""

    name: ClassVar[str] = "revenue_not_declining"

    def __init__(self, min_avg_growth: float = -0.05) -> None:
        self.min_avg_growth = min_avg_growth

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        revenues = company.revenue_3y
        if revenues is None or len(revenues) < 2:
            return RuleResult(passed=False, score=0.0, reason="insufficient revenue history")
        growth_rates: list[float] = []
        for i in range(1, len(revenues)):
            base = revenues[i - 1]
            if base <= 0:
                return RuleResult(passed=False, score=0.0, reason="non-positive base revenue")
            growth_rates.append((revenues[i] - base) / base)
        avg_growth = sum(growth_rates) / len(growth_rates)
        if avg_growth > self.min_avg_growth:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"avg revenue growth {avg_growth:.1%} > {self.min_avg_growth:.1%}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"avg revenue growth {avg_growth:.1%} <= {self.min_avg_growth:.1%}",
        )


@register
class OperatingMarginNotContracting(Rule):
    """Operating margin must not contract more than max_contraction_bps (default 200bps) over period."""

    name: ClassVar[str] = "operating_margin_not_contracting"

    def __init__(self, max_contraction_bps: float = 200.0) -> None:
        self.max_contraction_bps = max_contraction_bps

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        margins = company.op_margin_3y
        if margins is None or len(margins) < 2:
            return RuleResult(
                passed=False, score=0.0, reason="insufficient operating margin history"
            )
        # Positive = expansion, negative = contraction; compare oldest to most recent.
        contraction_bps = (margins[-1] - margins[0]) * 10_000
        if contraction_bps > -self.max_contraction_bps:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=(
                    f"margin change {contraction_bps:+.0f}bps over period "
                    f"(threshold: -{self.max_contraction_bps:.0f}bps)"
                ),
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=(
                f"margin contracted {contraction_bps:.0f}bps over period "
                f"(exceeds -{self.max_contraction_bps:.0f}bps)"
            ),
        )


@register
class ROICAboveSectorWACC(Rule):
    """ROIC must exceed sector WACC (Damodaran lookup) — central value-creation filter."""

    name: ClassVar[str] = "roic_above_sector_wacc"

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.roic is None:
            return RuleResult(passed=False, score=0.0, reason="ROIC not available")
        if benchmarks.wacc is None:
            return RuleResult(passed=False, score=0.0, reason="sector WACC not available")
        spread = company.roic - benchmarks.wacc
        if spread > 0:
            return RuleResult(
                passed=True,
                score=min(spread / 0.10, 1.0),
                reason=(
                    f"ROIC {company.roic:.1%} > WACC {benchmarks.wacc:.1%} (spread {spread:+.1%})"
                ),
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=(
                f"ROIC {company.roic:.1%} <= WACC {benchmarks.wacc:.1%} (spread {spread:+.1%})"
            ),
        )


@register
class SloanAccrualsBelow(Rule):
    """Sloan accruals ratio (NI - OCF) / TA must be below threshold (default 0.10)."""

    name: ClassVar[str] = "sloan_accruals_below"

    def __init__(self, max_ratio: float = 0.10) -> None:
        self.max_ratio = max_ratio

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.net_income is None:
            return RuleResult(passed=False, score=0.0, reason="net_income not available")
        if company.operating_cashflow is None:
            return RuleResult(passed=False, score=0.0, reason="operating_cashflow not available")
        if company.total_assets is None or company.total_assets <= 0:
            return RuleResult(
                passed=False, score=0.0, reason="total_assets not available or non-positive"
            )
        ratio = (company.net_income - company.operating_cashflow) / company.total_assets
        if ratio < self.max_ratio:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"Sloan accruals ratio {ratio:.3f} < {self.max_ratio:.2f}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"Sloan accruals ratio {ratio:.3f} >= {self.max_ratio:.2f}",
        )


@register
class ShareCountNotDiluting(Rule):
    """Avg annual growth in diluted share count must be below threshold (default 5%)."""

    name: ClassVar[str] = "share_count_not_diluting"

    def __init__(self, max_annual_growth: float = 0.05) -> None:
        self.max_annual_growth = max_annual_growth

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        shares = company.shares_diluted_3y
        if shares is None or len(shares) < 2:
            return RuleResult(passed=False, score=0.0, reason="insufficient share count history")
        growth_rates: list[float] = []
        for i in range(1, len(shares)):
            base = shares[i - 1]
            if base <= 0:
                return RuleResult(passed=False, score=0.0, reason="non-positive base share count")
            growth_rates.append((shares[i] - base) / base)
        avg_growth = sum(growth_rates) / len(growth_rates)
        if avg_growth < self.max_annual_growth:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"avg share growth {avg_growth:.1%} < {self.max_annual_growth:.1%}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"avg share growth {avg_growth:.1%} >= {self.max_annual_growth:.1%}",
        )


@register
class AuditorChangesAndLateFilings(Rule):
    """Flag companies with recent auditor changes or late SEC filings (best-effort)."""

    name: ClassVar[str] = "auditor_changes_and_late_filings"

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.auditor_changed is None and company.has_late_filings is None:
            return RuleResult(
                passed=True,
                score=1.0,
                reason="auditor/filing data unavailable — skipped (best-effort)",
            )
        flags: list[str] = []
        if company.auditor_changed:
            flags.append("auditor change detected")
        if company.has_late_filings:
            flags.append("late filings detected")
        if flags:
            return RuleResult(passed=False, score=0.0, reason="; ".join(flags))
        return RuleResult(
            passed=True,
            score=1.0,
            reason="no auditor changes or late filings",
        )
