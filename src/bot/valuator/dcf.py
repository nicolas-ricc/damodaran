"""Two-stage DCF model (spec §7.2) as a pure function.

The intrinsic value of a company is the present value of the free cash flows to
the firm (FCFF) it will generate, discounted at its weighted-average cost of
capital (WACC)::

    EV = sum_{t=1..N} FCFF_t / (1+WACC)^t
       + [ FCFF_{N+1} / (WACC - g_terminal) ] / (1+WACC)^N

    Equity     = EV - Net Debt + adjustments
    Per share  = Equity / Shares diluted

    FCFF         = EBIT * (1 - tax) - Reinvestment
    Reinvestment = delta_Revenue / sales_to_capital

What changes by *story type* (spec §7.1) is the projection of the inputs — the
per-year revenue-growth and operating-margin paths — not the arithmetic. So
:func:`dcf` takes the already-projected paths and stays a single, deterministic
formula. Story-type projection logic lives elsewhere and feeds this function.

This module is pure: no I/O, no global state, no mutation of its arguments. WACC
is derived from its capital-structure components so the result can report the
weights actually used (acceptance criterion: "weights used for WACC").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Financials:
    """The current-year financial state a DCF starts from.

    Monetary values share one currency and one scale (e.g. millions USD); the
    function is scale-agnostic as long as ``shares_diluted`` matches.

    Attributes:
        revenue: Base-year (trailing) revenue; year-1 revenue grows from this.
        net_debt: Total debt minus cash and equivalents. Subtracted from EV to
            reach equity value. Negative net debt (net cash) lifts equity value.
        shares_diluted: Fully-diluted share count, used for the per-share value.
        adjustments: Net non-operating equity adjustments (spec §7.2): subtract
            minority interest, add the value of cross-holdings, etc. Added to
            equity value, so credits are positive and charges negative.
    """

    revenue: float
    net_debt: float
    shares_diluted: float
    adjustments: float = 0.0


@dataclass(frozen=True)
class Assumptions:
    """The projection and discount-rate assumptions driving a DCF (spec §7.3).

    ``revenue_growth`` and ``operating_margin`` are per-year paths of equal
    length ``N`` (the explicit forecast horizon); element ``t`` applies to
    forecast year ``t + 1``. WACC is built from its components so the result can
    expose the equity/debt weights used.

    Attributes:
        revenue_growth: Year-by-year revenue growth rates (e.g. ``0.08`` = 8%).
        operating_margin: Year-by-year EBIT / revenue ratios.
        tax_rate: Marginal tax rate applied to EBIT to get NOPAT.
        sales_to_capital: Incremental sales generated per unit of reinvested
            capital; reinvestment = ΔRevenue / sales_to_capital. Must be > 0.
        terminal_growth: Perpetual growth ``g`` past the horizon. Must be
            strictly less than the WACC for the perpetuity to converge.
        cost_of_equity: Required return on equity (CAPM output, spec §7.3).
        pretax_cost_of_debt: Pre-tax cost of debt; the tax shield is applied
            inside :func:`dcf` via ``tax_rate``.
        equity_weight: Equity share of the capital structure (E / (E + D)).
        debt_weight: Debt share of the capital structure (D / (E + D)).
        probability_of_bankruptcy: Probability the firm fails before realising
            the going-concern value (spec §7.3, distressed stories). The
            intrinsic value is the probability-weighted blend of the
            going-concern per-share value and ``distress_value_per_share``.
        distress_value_per_share: Per-share value recovered in bankruptcy
            (e.g. liquidation proceeds to equity). Defaults to zero.
    """

    revenue_growth: tuple[float, ...]
    operating_margin: tuple[float, ...]
    tax_rate: float
    sales_to_capital: float
    terminal_growth: float
    cost_of_equity: float
    pretax_cost_of_debt: float
    equity_weight: float
    debt_weight: float
    probability_of_bankruptcy: float = 0.0
    distress_value_per_share: float = 0.0


@dataclass(frozen=True)
class YearProjection:
    """One forecast year's intermediate figures (for report traceability)."""

    year: int
    revenue: float
    ebit: float
    nopat: float
    reinvestment: float
    fcff: float
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class DCFResult:
    """The output of a two-stage DCF (spec §7.2).

    Attributes:
        intrinsic_value: Probability-weighted intrinsic value per diluted share.
        enterprise_value: Going-concern EV (PV of explicit FCFF + PV of terminal
            value), before the bankruptcy probability is applied.
        equity_value: Probability-weighted total equity value.
        projections: Year-by-year FCFF projection with intermediate figures.
        terminal_value: Undiscounted terminal value at the horizon.
        terminal_value_share: PV(terminal value) / enterprise_value — the
            fraction of EV resting on the perpetuity (spec §7.5 narrative flag).
        wacc: The discount rate used.
        equity_weight: Equity weight that produced ``wacc``.
        debt_weight: Debt weight that produced ``wacc``.
    """

    intrinsic_value: float
    enterprise_value: float
    equity_value: float
    projections: tuple[YearProjection, ...]
    terminal_value: float
    terminal_value_share: float
    wacc: float
    equity_weight: float
    debt_weight: float = field(default=0.0)


def _wacc(assumptions: Assumptions) -> float:
    """Weighted-average cost of capital from its components (spec §7.3)."""
    after_tax_cost_of_debt = assumptions.pretax_cost_of_debt * (1.0 - assumptions.tax_rate)
    return (
        assumptions.equity_weight * assumptions.cost_of_equity
        + assumptions.debt_weight * after_tax_cost_of_debt
    )


def dcf(financials: Financials, assumptions: Assumptions) -> DCFResult:
    """Value a company with the two-stage DCF of spec §7.2.

    Args:
        financials: Current-year financial state to project from.
        assumptions: Projection paths and discount-rate components.

    Returns:
        A :class:`DCFResult` with the per-share intrinsic value and the
        intermediate figures needed for a traceable report.

    Raises:
        ValueError: If the growth and margin paths differ in length, the horizon
            is empty, ``sales_to_capital`` is not positive, ``shares_diluted`` is
            not positive, or ``terminal_growth >= wacc`` (perpetuity diverges).
    """
    growth = assumptions.revenue_growth
    margins = assumptions.operating_margin
    horizon = len(growth)
    if horizon == 0:
        raise ValueError("forecast horizon must be at least one year")
    if len(margins) != horizon:
        raise ValueError("revenue_growth and operating_margin must have equal length")
    if assumptions.sales_to_capital <= 0.0:
        raise ValueError("sales_to_capital must be positive")
    if financials.shares_diluted <= 0.0:
        raise ValueError("shares_diluted must be positive")

    wacc = _wacc(assumptions)
    if assumptions.terminal_growth >= wacc:
        raise ValueError(
            f"terminal_growth ({assumptions.terminal_growth}) must be below "
            f"WACC ({wacc}) for the perpetuity to converge"
        )

    one_minus_tax = 1.0 - assumptions.tax_rate
    projections: list[YearProjection] = []
    pv_explicit = 0.0
    prev_revenue = financials.revenue
    for index in range(horizon):
        margin = margins[index]
        revenue = prev_revenue * (1.0 + growth[index])
        ebit = revenue * margin
        nopat = ebit * one_minus_tax
        reinvestment = (revenue - prev_revenue) / assumptions.sales_to_capital
        fcff = nopat - reinvestment
        year = index + 1
        discount_factor = 1.0 / (1.0 + wacc) ** year
        present_value = fcff * discount_factor
        pv_explicit += present_value
        projections.append(
            YearProjection(
                year=year,
                revenue=revenue,
                ebit=ebit,
                nopat=nopat,
                reinvestment=reinvestment,
                fcff=fcff,
                discount_factor=discount_factor,
                present_value=present_value,
            )
        )
        prev_revenue = revenue

    # Terminal value: FCFF of the first post-horizon year capitalised as a
    # growing perpetuity, then discounted back over the explicit horizon.
    terminal_revenue = revenue * (1.0 + assumptions.terminal_growth)
    terminal_ebit = terminal_revenue * margin
    terminal_nopat = terminal_ebit * one_minus_tax
    terminal_reinvestment = (terminal_revenue - revenue) / assumptions.sales_to_capital
    terminal_fcff = terminal_nopat - terminal_reinvestment
    terminal_value = terminal_fcff / (wacc - assumptions.terminal_growth)
    pv_terminal = terminal_value / (1.0 + wacc) ** horizon

    enterprise_value = pv_explicit + pv_terminal
    terminal_value_share = pv_terminal / enterprise_value if enterprise_value != 0.0 else 0.0

    going_concern_equity = enterprise_value - financials.net_debt + financials.adjustments
    going_concern_per_share = going_concern_equity / financials.shares_diluted

    p_bankrupt = assumptions.probability_of_bankruptcy
    survival = 1.0 - p_bankrupt
    intrinsic_value = (
        survival * going_concern_per_share + p_bankrupt * assumptions.distress_value_per_share
    )
    equity_value = intrinsic_value * financials.shares_diluted

    return DCFResult(
        intrinsic_value=intrinsic_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        projections=tuple(projections),
        terminal_value=terminal_value,
        terminal_value_share=terminal_value_share,
        wacc=wacc,
        equity_weight=assumptions.equity_weight,
        debt_weight=assumptions.debt_weight,
    )
