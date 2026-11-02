"""Two-stage DCF model (spec §7.2) as a pure function.

The intrinsic value of a company is the present value of the free cash flows to
the firm (FCFF) it will generate, discounted at its weighted-average cost of
capital (WACC)::

    EV = sum_{t=1..N} FCFF_t / (1+WACC)^t
       + [ FCFF_{N+1} / (WACC - g_terminal) ] / (1+WACC)^N

    Equity     = EV - Net Debt - fixed commitments + extra cash + adjustments
    Per share  = Equity / Shares diluted

    FCFF         = EBIT * (1 - tax) - Reinvestment
    Reinvestment = delta_Revenue / sales_to_capital

Optional extensions (each defaults to off, and with every default in place the
arithmetic above is unchanged to the last bit):

* ``wacc_path`` replaces the flat rate with a per-year path. Year ``t`` is
  discounted by the cumulative factor ``1 / prod_{i<=t}(1 + WACC_i)``, and the
  terminal value uses the last rate, ``FCFF_{N+1} / (WACC_N - g)``, discounted
  by the year-``N`` factor.
* ``tax_rate_path`` gives each explicit year its own tax rate; the terminal year
  and the WACC tax shield keep the scalar ``tax_rate``.
* ``terminal_roic`` sets terminal reinvestment to ``NOPAT_{N+1} * g / ROIC``
  instead of ``delta_Revenue / sales_to_capital``.
* ``distress_proceeds_pct`` models failure as a share of EV recovered rather than
  a per-share value: ``EV_after = EV * (1 - p) + EV * pct * p``, and the equity
  bridge is applied to ``EV_after``.

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
        fixed_commitments: Fixed obligations that are not debt (e.g. long-term
            purchase or lease commitments). Subtracted in the equity bridge, one
            for one, like ``net_debt``; EV is unchanged.
        extra_cash: Cash not already netted in ``net_debt`` (e.g. IPO
            proceeds). Added in the equity bridge, one for one; EV is unchanged.

    ``adjustments`` (minority interests, cross-holdings) is a supported input of the
    equity bridge that the analysis pipeline does not populate: no ingest path supplies
    either figure, so it defaults to 0.0. It is kept because the bridge is arithmetically
    correct with it and a manual override can supply it.
    """

    revenue: float
    net_debt: float
    shares_diluted: float
    adjustments: float = 0.0
    fixed_commitments: float = 0.0
    extra_cash: float = 0.0


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
            (e.g. liquidation proceeds to equity). Defaults to zero. Ignored
            when ``distress_proceeds_pct`` is set.
        wacc_path: Optional per-year WACC of length ``N``. When set it replaces
            the capital-structure WACC (the scalar components are ignored); the
            last element is the terminal WACC.
        tax_rate_path: Optional per-year tax rate of length ``N`` for the
            explicit-year NOPAT. The terminal year uses ``tax_rate``.
        terminal_roic: Optional return on invested capital in the terminal year.
            Terminal reinvestment is ``NOPAT * g / terminal_roic``. Must be > 0.
        distress_proceeds_pct: Optional share of EV recovered on failure, in
            ``[0, 1]``. When set, the bankruptcy blend is applied to EV and
            ``distress_value_per_share`` is ignored.

    ``distress_value_per_share`` pairs with ``probability_of_bankruptcy`` to blend a
    going-concern value with a liquidation value. Neither is populated automatically —
    §7.3's rating/Altman-Z derivation for distressed companies is not implemented — so
    both come from a manual override or stay at 0.0.
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
    wacc_path: tuple[float, ...] | None = None
    tax_rate_path: tuple[float, ...] | None = None
    terminal_roic: float | None = None
    distress_proceeds_pct: float | None = None


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
        wacc: The discount rate used (the terminal WACC when ``wacc_path`` is set).
        equity_weight: Equity weight that produced ``wacc``; only echoed when
            ``wacc_path`` is set, since the path replaces the built-up WACC.
        debt_weight: Debt weight that produced ``wacc``; only echoed when
            ``wacc_path`` is set.
        enterprise_value_after_failure: EV blended with the failure recovery
            (``distress_proceeds_pct`` mode); ``None`` otherwise.
        wacc_path: The per-year WACC path used, echoed; ``None`` for a flat rate.
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
    enterprise_value_after_failure: float | None = None
    wacc_path: tuple[float, ...] | None = None


def _wacc(assumptions: Assumptions) -> float:
    """Weighted-average cost of capital from its components (spec §7.3)."""
    after_tax_cost_of_debt = assumptions.pretax_cost_of_debt * (1.0 - assumptions.tax_rate)
    return (
        assumptions.equity_weight * assumptions.cost_of_equity
        + assumptions.debt_weight * after_tax_cost_of_debt
    )


def _equity_bridge(enterprise_value: float, financials: Financials) -> float:
    """EV to equity, operands applied left to right (``0.0`` terms are exact no-ops)."""
    return (
        enterprise_value
        - financials.net_debt
        - financials.fixed_commitments
        + financials.extra_cash
        + financials.adjustments
    )


def terminal_wacc(assumptions: Assumptions) -> float:
    """The WACC the perpetuity is capitalised at: last path element, else scalar."""
    if assumptions.wacc_path:
        return assumptions.wacc_path[-1]
    return _wacc(assumptions)


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
            not positive, ``wacc_path`` or ``tax_rate_path`` is set with a length
            other than the horizon, ``terminal_roic`` is not positive,
            ``distress_proceeds_pct`` is outside ``[0, 1]``, or
            ``terminal_growth >= wacc`` (perpetuity diverges).
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

    wacc_path = assumptions.wacc_path
    tax_path = assumptions.tax_rate_path
    if wacc_path is not None and len(wacc_path) != horizon:
        raise ValueError("wacc_path must have the same length as revenue_growth")
    if tax_path is not None and len(tax_path) != horizon:
        raise ValueError("tax_rate_path must have the same length as revenue_growth")
    if assumptions.terminal_roic is not None and assumptions.terminal_roic <= 0.0:
        raise ValueError("terminal_roic must be positive")
    proceeds_pct = assumptions.distress_proceeds_pct
    if proceeds_pct is not None and not 0.0 <= proceeds_pct <= 1.0:
        raise ValueError("distress_proceeds_pct must be within [0, 1]")

    wacc = terminal_wacc(assumptions)
    if assumptions.terminal_growth >= wacc:
        raise ValueError(
            f"terminal_growth ({assumptions.terminal_growth}) must be below "
            f"WACC ({wacc}) for the perpetuity to converge"
        )

    one_minus_tax = 1.0 - assumptions.tax_rate
    projections: list[YearProjection] = []
    pv_explicit = 0.0
    prev_revenue = financials.revenue
    cumulative_discount = 1.0
    for index in range(horizon):
        margin = margins[index]
        revenue = prev_revenue * (1.0 + growth[index])
        ebit = revenue * margin
        nopat = ebit * (one_minus_tax if tax_path is None else 1.0 - tax_path[index])
        reinvestment = (revenue - prev_revenue) / assumptions.sales_to_capital
        fcff = nopat - reinvestment
        year = index + 1
        if wacc_path is None:
            discount_factor = 1.0 / (1.0 + wacc) ** year
        else:
            cumulative_discount /= 1.0 + wacc_path[index]
            discount_factor = cumulative_discount
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
    if assumptions.terminal_roic is None:
        terminal_reinvestment = (terminal_revenue - revenue) / assumptions.sales_to_capital
    else:
        terminal_reinvestment = (
            terminal_nopat * assumptions.terminal_growth / assumptions.terminal_roic
        )
    terminal_fcff = terminal_nopat - terminal_reinvestment
    terminal_value = terminal_fcff / (wacc - assumptions.terminal_growth)
    if wacc_path is None:
        pv_terminal = terminal_value / (1.0 + wacc) ** horizon
    else:
        pv_terminal = terminal_value * cumulative_discount

    enterprise_value = pv_explicit + pv_terminal
    terminal_value_share = pv_terminal / enterprise_value if enterprise_value != 0.0 else 0.0

    p_bankrupt = assumptions.probability_of_bankruptcy
    survival = 1.0 - p_bankrupt
    enterprise_value_after_failure: float | None = None
    if proceeds_pct is None:
        going_concern_equity = _equity_bridge(enterprise_value, financials)
        going_concern_per_share = going_concern_equity / financials.shares_diluted
        intrinsic_value = (
            survival * going_concern_per_share + p_bankrupt * assumptions.distress_value_per_share
        )
        equity_value = intrinsic_value * financials.shares_diluted
    else:
        enterprise_value_after_failure = (
            enterprise_value * survival + enterprise_value * proceeds_pct * p_bankrupt
        )
        equity_value = _equity_bridge(enterprise_value_after_failure, financials)
        intrinsic_value = equity_value / financials.shares_diluted

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
        enterprise_value_after_failure=enterprise_value_after_failure,
        wacc_path=wacc_path,
    )
