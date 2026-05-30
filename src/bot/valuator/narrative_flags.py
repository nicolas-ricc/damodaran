"""Quantitative narrative-consistency flags (spec §7.5, issue #15 / M4.5).

Damodaran's *Narrative and Numbers* insists a valuation only holds together when
the story and the numbers agree. These five flags are cheap quantitative proxies
for that agreement — they do **not** enter the screener ranking (spec §7.5); they
are signals for a human to read and decide.

Each flag is a pure function that returns a :class:`NarrativeFlag` with a
:class:`FlagColor` in ``{green, yellow, red}`` and a human-readable ``reason``.
The five flags (spec §7.5):

1. **Story-margin consistency** — a ``high-growth`` story whose operating margin
   already sits *above* the sector is internally tense (yellow).
2. **Growth-reinvestment consistency** — growth the model never funds out of
   earnings (a forecast year with negative free cash flow) is unsupported (red).
3. **Beta vs business risk** — a defensive sector beta (< 1) paired with high
   operating *and* financial leverage understates real risk (yellow).
4. **Terminal value share > 80%** — a valuation resting almost entirely on the
   perpetuity is fragile (yellow).
5. **Country exposure vs ERP** — mostly-foreign revenue while the weighted ERP
   sits well above the listing country's ERP means the discount rate likely
   understates country risk (red).

The pure DCF types (:class:`bot.valuator.dcf.Financials` / ``Assumptions`` /
``DCFResult``) do not carry every input these flags need — sector margin, sector
beta, leverage ratios, foreign-revenue share, the two ERPs. Those extra,
flag-specific inputs are gathered in :class:`NarrativeContext`, so the flag
functions stay pure: ``(financials, assumptions, result, context) -> flag`` with
no I/O and no global state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from bot.valuator.dcf import Assumptions, DCFResult, Financials

#: Story-margin flag fires only for this story type (spec §7.1 / §7.5).
_HIGH_GROWTH_STORY = "high-growth"

#: Terminal-value share above which the valuation is flagged fragile (spec §7.5).
_TERMINAL_VALUE_SHARE_CEILING = 0.80

#: Foreign-revenue share above which exposure counts as "mostly foreign".
_FOREIGN_REVENUE_MAJORITY = 0.50

#: ERP gap (weighted minus listing) above which country risk is under-priced:
#: 300 basis points (spec §7.5).
_ERP_GAP_THRESHOLD = 0.03

#: A sector beta strictly below this is "defensive" for the beta-vs-risk flag.
_DEFENSIVE_BETA = 1.0

#: Leverage above these counts as "high" for the beta-vs-risk flag. Operating
#: leverage is the elasticity of EBIT to revenue; financial leverage is the
#: debt share of the capital structure (debt_weight).
_HIGH_OPERATING_LEVERAGE = 1.5
_HIGH_FINANCIAL_LEVERAGE = 0.40

#: A reinvestment rate (reinvestment / NOPAT) above this — while still leaving
#: positive free cash flow — is a yellow "stretched but funded" middle band for
#: the growth-reinvestment flag.
_STRETCHED_REINVESTMENT_RATE = 0.90


class FlagColor(StrEnum):
    """Traffic-light verdict of a narrative flag (spec §7.5)."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True)
class NarrativeFlag:
    """One narrative-consistency verdict (spec §7.5).

    Attributes:
        name: Stable identifier of the check (e.g. ``"story_margin"``).
        color: The traffic-light verdict.
        reason: Human-readable explanation of why the flag landed on ``color``.
    """

    name: str
    color: FlagColor
    reason: str


@dataclass(frozen=True)
class NarrativeContext:
    """Flag-specific inputs not carried by the pure DCF types (spec §7.5).

    Every field is optional: a flag whose inputs are missing returns green with a
    reason saying so, rather than inventing a verdict from absent data.

    Attributes:
        story_type: Damodaran story type (spec §7.1), e.g. ``"high-growth"``.
        company_operating_margin: The company's own steady-state EBIT/revenue.
        sector_operating_margin: Sector-median operating margin (Damodaran).
        sector_beta: Sector levered beta used in the CAPM cost of equity.
        operating_leverage: Elasticity of EBIT to revenue (%ΔEBIT / %ΔRevenue).
        foreign_revenue_share: Fraction of revenue earned outside the listing
            country (0..1).
        erp_weighted: Revenue-weighted equity risk premium across the countries
            the company operates in.
        erp_listing: Equity risk premium of the company's listing country.
    """

    story_type: str | None = None
    company_operating_margin: float | None = None
    sector_operating_margin: float | None = None
    sector_beta: float | None = None
    operating_leverage: float | None = None
    foreign_revenue_share: float | None = None
    erp_weighted: float | None = None
    erp_listing: float | None = None


def story_margin_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag a high-growth story whose margin already beats the sector (§7.5).

    A ``high-growth`` story usually projects margins *improving toward* the
    sector; starting *above* it leaves little room for the story to play out, so
    the flag turns yellow. Any other story type, or a margin at/below sector, is
    green.
    """
    name = "story_margin"
    if context.story_type != _HIGH_GROWTH_STORY:
        return NarrativeFlag(
            name=name,
            color=FlagColor.GREEN,
            reason=f"story type {context.story_type!r} is not {_HIGH_GROWTH_STORY!r}",
        )
    company = context.company_operating_margin
    sector = context.sector_operating_margin
    if company is None or sector is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.GREEN,
            reason="company or sector operating margin unavailable",
        )
    if company > sector:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"high-growth story but operating margin {company:.1%} already "
                f"exceeds sector {sector:.1%} — little room to improve"
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"operating margin {company:.1%} at/below sector {sector:.1%}, "
            "consistent with a high-growth story"
        ),
    )


def growth_reinvestment_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag growth the model never funds out of earnings (spec §7.5).

    In the §7.2 model reinvestment is ``ΔRevenue / sales_to_capital``. If, in any
    forecast year, that reinvestment exceeds NOPAT the year's free cash flow is
    negative: the projected growth is not supported by projected earnings, which
    is a red flag. A year whose reinvestment eats most (but not all) of NOPAT is
    a yellow "stretched but funded" middle band. Otherwise green.
    """
    name = "growth_reinvestment"
    worst_rate = 0.0
    worst_year = 0
    any_negative = False
    for projection in result.projections:
        if projection.fcff < 0.0:
            any_negative = True
        if projection.nopat > 0.0:
            rate = projection.reinvestment / projection.nopat
            if rate > worst_rate:
                worst_rate = rate
                worst_year = projection.year
        elif projection.reinvestment > 0.0:
            # Positive reinvestment against non-positive NOPAT is unfunded.
            any_negative = True
    if any_negative:
        return NarrativeFlag(
            name=name,
            color=FlagColor.RED,
            reason=(
                "projected reinvestment exceeds NOPAT in at least one year — "
                "growth is not funded by earnings (negative FCFF)"
            ),
        )
    if worst_rate > _STRETCHED_REINVESTMENT_RATE:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"reinvestment consumes {worst_rate:.0%} of NOPAT in year "
                f"{worst_year} — growth is funded but only just"
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason="projected reinvestment is comfortably funded by NOPAT every year",
    )


def beta_business_risk_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag a defensive beta paired with high real leverage (spec §7.5).

    A sector beta below 1 says "defensive", but high operating leverage (EBIT
    swings hard with revenue) combined with high financial leverage (a debt-heavy
    capital structure) means the equity is riskier than the beta implies. When
    all three hold the flag turns yellow.
    """
    name = "beta_business_risk"
    beta = context.sector_beta
    operating_leverage = context.operating_leverage
    if beta is None or operating_leverage is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.GREEN,
            reason="sector beta or operating leverage unavailable",
        )
    financial_leverage = assumptions.debt_weight
    if (
        beta < _DEFENSIVE_BETA
        and operating_leverage > _HIGH_OPERATING_LEVERAGE
        and financial_leverage > _HIGH_FINANCIAL_LEVERAGE
    ):
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"defensive sector beta {beta:.2f} but operating leverage "
                f"{operating_leverage:.2f} and financial leverage "
                f"{financial_leverage:.0%} are both high — beta understates risk"
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"sector beta {beta:.2f} is consistent with operating leverage "
            f"{operating_leverage:.2f} and financial leverage "
            f"{financial_leverage:.0%}"
        ),
    )


def terminal_value_share_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag a valuation that rests almost entirely on the perpetuity (§7.5).

    When the present value of the terminal value is more than 80% of enterprise
    value, the explicit forecast barely matters and the whole valuation hinges on
    the perpetuity assumptions — fragile, so yellow. Otherwise green.
    """
    name = "terminal_value_share"
    share = result.terminal_value_share
    if share > _TERMINAL_VALUE_SHARE_CEILING:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"terminal value is {share:.0%} of enterprise value "
                f"(> {_TERMINAL_VALUE_SHARE_CEILING:.0%}) — valuation is fragile"
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"terminal value is {share:.0%} of enterprise value "
            f"(<= {_TERMINAL_VALUE_SHARE_CEILING:.0%})"
        ),
    )


def country_exposure_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag mostly-foreign revenue priced at the listing country's ERP (§7.5).

    If the majority of revenue is earned outside the listing country and the
    revenue-weighted equity risk premium sits more than 300 bps above the listing
    country's ERP, the cost of equity built on the listing ERP understates
    country risk — a red flag. Otherwise green.
    """
    name = "country_exposure"
    foreign = context.foreign_revenue_share
    erp_weighted = context.erp_weighted
    erp_listing = context.erp_listing
    if foreign is None or erp_weighted is None or erp_listing is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.GREEN,
            reason="foreign revenue share or ERP figures unavailable",
        )
    gap = erp_weighted - erp_listing
    if foreign > _FOREIGN_REVENUE_MAJORITY and gap > _ERP_GAP_THRESHOLD:
        return NarrativeFlag(
            name=name,
            color=FlagColor.RED,
            reason=(
                f"{foreign:.0%} of revenue is foreign and weighted ERP "
                f"{erp_weighted:.1%} exceeds listing ERP {erp_listing:.1%} by "
                f"{gap * 10000:.0f} bps (> 300) — country risk under-priced"
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"{foreign:.0%} foreign revenue with weighted ERP {erp_weighted:.1%} "
            f"vs listing ERP {erp_listing:.1%} ({gap * 10000:.0f} bps gap)"
        ),
    )


#: The five §7.5 flag functions, in spec order. The aggregator runs each.
_FLAG_FUNCTIONS: tuple[
    Callable[[Financials, Assumptions, DCFResult, NarrativeContext], NarrativeFlag],
    ...,
] = (
    story_margin_flag,
    growth_reinvestment_flag,
    beta_business_risk_flag,
    terminal_value_share_flag,
    country_exposure_flag,
)


def narrative_flags(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> tuple[NarrativeFlag, ...]:
    """Run all five §7.5 narrative-consistency flags, in spec order.

    Args:
        financials: The company's current-year financial state (DCF input).
        assumptions: The projection and discount-rate assumptions (DCF input).
        result: The :class:`DCFResult` produced from ``financials`` and
            ``assumptions``.
        context: Flag-specific inputs not carried by the DCF types (§7.5).

    Returns:
        The five :class:`NarrativeFlag` verdicts, in the spec §7.5 order. These
        are signals for a human and do **not** feed the screener ranking.
    """
    return tuple(flag(financials, assumptions, result, context) for flag in _FLAG_FUNCTIONS)
