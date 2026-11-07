"""Quantitative narrative-consistency flags (spec §7.5, issue #15 / M4.5).

Damodaran's *Narrative and Numbers* insists a valuation only holds together when
the story and the numbers agree. These flags are cheap quantitative proxies
for that agreement — they do **not** enter the screener ranking (spec §7.5); they
are signals for a human to read and decide.

Each flag is a pure function that returns a :class:`NarrativeFlag` with a
:class:`FlagColor` in ``{green, yellow, red, unknown}`` and a human-readable
``reason``. ``unknown`` means the check could not run for lack of data — it is
deliberately distinct from ``green`` so an un-run check never reads as a pass.
The flags (spec §7.5) are four that always run, plus ``story_margin``, which
runs only for a ``high-growth`` story:

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

The hypergrowth flags (issues #195, #197) sit outside the §7.5 flags: they
are produced by :func:`hypergrowth_flags` and never by :func:`narrative_flags`.
:func:`hypergrowth_flags` emits up to three: ``hypergrowth_story`` when signals
or the hypergrowth story type call for it, then ``hypergrowth_revenue_scale``
and ``hypergrowth_terminal_roic`` when the story type is ``hypergrowth``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from bot.valuator.dcf import Assumptions, DCFResult, Financials

#: Story-margin flag fires only for this story type (spec §7.1 / §7.5).
_HIGH_GROWTH_STORY = "high-growth"

#: Story type for which the hypergrowth flag always runs (issue #195).
_HYPERGROWTH_STORY = "hypergrowth"

#: Revenue of the largest company today, in the financials' currency units
#: (~750B). A year-10 revenue above it asks the story to beat every company
#: that exists (issue #197).
_LARGEST_COMPANY_REVENUE = 750e9

#: A terminal ROIC above this multiple of the sector ROIC claims a lasting
#: competitive advantage far beyond the sector norm (issue #197).
_ROIC_SECTOR_MULTIPLE = 2.0

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
    #: The check could not run for lack of data. Deliberately distinct from
    #: GREEN: an un-run check must never read as a pass (spec §7.5).
    UNKNOWN = "unknown"


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

    Every field is optional: a flag whose inputs are missing returns
    :attr:`FlagColor.UNKNOWN` with a reason saying so, rather than inventing a
    verdict from absent data.

    Attributes:
        story_type: Damodaran story type (spec §7.1), e.g. ``"high-growth"``.
        company_operating_margin: The company's *realised* EBIT/revenue from its
            own latest income statement. Never the modelled steady-state margin:
            that is itself drawn from the sector row, so passing it would compare
            ``sector_operating_margin`` against itself.
        sector_operating_margin: Sector-median operating margin (Damodaran).
        sector_beta: Sector levered beta used in the CAPM cost of equity.
        operating_leverage: Elasticity of EBIT to revenue (%ΔEBIT / %ΔRevenue).
        foreign_revenue_share: Fraction of revenue earned outside the listing
            country (0..1).
        erp_weighted: Revenue-weighted equity risk premium across the countries
            the company operates in.
        erp_listing: Equity risk premium of the company's listing country.
        company_debt_weight: The company's own debt / (debt + equity) from its
            latest balance sheet. Distinct from ``Assumptions.debt_weight``,
            which is derived from the *sector's* D/E and drives the WACC.
        hypergrowth_signals: The classifier's hypergrowth signals fired (#195).
        story_file_present: A hand-written story file exists for the company
            (#195).
        terminal_roic: Return on invested capital the story implies in the
            terminal period (#197).
        sector_roic: Sector-median ROIC the terminal ROIC is compared against
            (#197).
    """

    story_type: str | None = None
    company_operating_margin: float | None = None
    sector_operating_margin: float | None = None
    sector_beta: float | None = None
    operating_leverage: float | None = None
    foreign_revenue_share: float | None = None
    erp_weighted: float | None = None
    erp_listing: float | None = None
    company_debt_weight: float | None = None
    hypergrowth_signals: bool = False
    story_file_present: bool = False
    terminal_roic: float | None = None
    sector_roic: float | None = None


def story_margin_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag a high-growth story whose margin already beats the sector (§7.5).

    A ``high-growth`` story usually projects margins *improving toward* the
    sector; starting *above* it leaves little room for the story to play out, so
    the flag turns yellow; a margin at/below sector is green. The flag has no
    branch for other story types: :func:`narrative_flags` only calls it for a
    ``high-growth`` story. Without both margins the check cannot run and returns ``unknown`` — an
    un-run check must never read as a pass (spec §7.5).
    """
    name = "story_margin"
    company = context.company_operating_margin
    sector = context.sector_operating_margin
    if company is None or sector is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.UNKNOWN,
            reason=(
                "not evaluated: the company's latest operating margin or the "
                "sector's median margin is missing."
            ),
        )
    if company > sector:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"A high-growth story, but the operating margin of {company:.1%} "
                f"already exceeds the sector's {sector:.1%}: little room left for "
                "the margin to improve."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"A high-growth story with an operating margin of {company:.1%}, at "
            f"or below the sector's {sector:.1%}: there is room for the margin "
            "to improve."
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
                "In at least one year growth needs more reinvestment than "
                "after-tax operating profit (NOPAT) provides, so free cash flow "
                "to the firm (FCFF) turns negative."
            ),
        )
    if worst_rate > _STRETCHED_REINVESTMENT_RATE:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"In year {worst_year} reinvestment takes {worst_rate:.0%} of "
                "after-tax operating profit (NOPAT): growth is funded, but only "
                "just."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            "Every year the reinvestment growth needs fits within after-tax "
            "operating profit (NOPAT)."
        ),
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

    Financial leverage here is the *company's own* debt / (debt + equity), not
    ``Assumptions.debt_weight`` — that is derived from the sector's D/E and
    drives the WACC, not a proxy for this company's actual capital structure.
    """
    name = "beta_business_risk"
    beta = context.sector_beta
    operating_leverage = context.operating_leverage
    financial_leverage = context.company_debt_weight
    if beta is None or operating_leverage is None or financial_leverage is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.UNKNOWN,
            reason=(
                "not evaluated: the sector beta, the operating leverage or the "
                "company's debt share is missing."
            ),
        )
    if (
        beta < _DEFENSIVE_BETA
        and operating_leverage > _HIGH_OPERATING_LEVERAGE
        and financial_leverage > _HIGH_FINANCIAL_LEVERAGE
    ):
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"The sector beta of {beta:.2f} is below {_DEFENSIVE_BETA:g}, "
                "which looks defensive, but operating leverage of "
                f"{operating_leverage:.2f} is above {_HIGH_OPERATING_LEVERAGE:g} "
                f"and debt at {financial_leverage:.0%} of capital is above "
                f"{_HIGH_FINANCIAL_LEVERAGE:.0%}: the beta understates the risk."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"The sector beta of {beta:.2f} fits operating leverage of "
            f"{operating_leverage:.2f} and debt at {financial_leverage:.0%} of "
            "capital."
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
                f"{share:.0%} of enterprise value comes from the terminal value, "
                f"above the {_TERMINAL_VALUE_SHARE_CEILING:.0%} ceiling: the "
                "valuation rests almost entirely on the perpetuity."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"{share:.0%} of enterprise value comes from the terminal value, "
            f"within the {_TERMINAL_VALUE_SHARE_CEILING:.0%} ceiling."
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
            color=FlagColor.UNKNOWN,
            reason=(
                "not evaluated: it needs revenue by geography and a "
                "revenue-weighted equity risk premium (ERP), and no data source "
                "supplies either."
            ),
        )
    gap = erp_weighted - erp_listing
    gap_bps = round(gap * 10000)
    threshold_bps = round(_ERP_GAP_THRESHOLD * 10000)
    if foreign > _FOREIGN_REVENUE_MAJORITY and gap > _ERP_GAP_THRESHOLD:
        return NarrativeFlag(
            name=name,
            color=FlagColor.RED,
            reason=(
                f"{foreign:.0%} of revenue is earned abroad and the "
                f"revenue-weighted equity risk premium (ERP) of {erp_weighted:.1%} "
                f"is {gap_bps} basis points above the listing country's "
                f"{erp_listing:.1%}, more than the {threshold_bps} basis points "
                "allowed: the discount rate under-prices country risk."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"{foreign:.0%} of revenue is earned abroad and the "
            f"revenue-weighted equity risk premium (ERP) is {erp_weighted:.1%} "
            f"against {erp_listing:.1%} for the listing country, a gap of "
            f"{gap_bps} basis points."
        ),
    )


def hypergrowth_story_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag hypergrowth signals that lack a story file (issue #195).

    Signals without a story file is red: the default valuation is not reliable.
    A story file without signals is yellow (the two disagree). Both present is
    green; so is neither present (story type set by other means).
    """
    name = "hypergrowth_story"
    signals = context.hypergrowth_signals
    story = context.story_file_present
    if signals and not story:
        return NarrativeFlag(
            name=name,
            color=FlagColor.RED,
            reason=(
                "The classifier sees hypergrowth signals but there is no story "
                "file, so the default valuation is not reliable."
            ),
        )
    if story and not signals:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                "A story file is present but the classifier sees no hypergrowth "
                "signals: the two disagree."
            ),
        )
    if signals and story:
        return NarrativeFlag(
            name=name,
            color=FlagColor.GREEN,
            reason="The classifier's hypergrowth signals and the story file agree.",
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason="No hypergrowth signals and no story file: there is nothing to reconcile.",
    )


def hypergrowth_revenue_scale_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag a year-10 revenue larger than any company's revenue today (#197)."""
    name = "hypergrowth_revenue_scale"
    revenue = result.projections[-1].revenue
    largest_b = _LARGEST_COMPANY_REVENUE / 1e9
    if revenue > _LARGEST_COMPANY_REVENUE:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                f"Year-10 revenue of {revenue / 1e9:,.0f} billion is larger than "
                "the revenue of the largest company today, about "
                f"{largest_b:,.0f} billion."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            f"Year-10 revenue of {revenue / 1e9:,.0f} billion is within the "
            "revenue of the largest company today, about "
            f"{largest_b:,.0f} billion."
        ),
    )


def hypergrowth_terminal_roic_flag(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> NarrativeFlag:
    """Flag a terminal ROIC above twice the sector's ROIC (#197).

    Unknown when either ROIC is missing, or when the sector ROIC is not positive.
    """
    name = "hypergrowth_terminal_roic"
    terminal = context.terminal_roic
    sector = context.sector_roic
    if terminal is None or sector is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.UNKNOWN,
            reason=(
                "not evaluated: the terminal return on invested capital (ROIC) "
                "or the sector's ROIC is missing."
            ),
        )
    if sector <= 0.0:
        # A loss-making sector has no multiple to compare against.
        return NarrativeFlag(
            name=name,
            color=FlagColor.UNKNOWN,
            reason=(
                "not evaluated: a sector return on invested capital (ROIC) of "
                f"{sector:.1%} is not a usable benchmark."
            ),
        )
    limit = _ROIC_SECTOR_MULTIPLE * sector
    if terminal > limit:
        return NarrativeFlag(
            name=name,
            color=FlagColor.YELLOW,
            reason=(
                "The terminal return on invested capital (ROIC) of "
                f"{terminal:.1%} is above {limit:.1%}, {_ROIC_SECTOR_MULTIPLE:g} "
                f"times the sector's {sector:.1%}: the story claims an advantage "
                "far beyond the sector's."
            ),
        )
    return NarrativeFlag(
        name=name,
        color=FlagColor.GREEN,
        reason=(
            "The terminal return on invested capital (ROIC) of "
            f"{terminal:.1%} is within {limit:.1%}, {_ROIC_SECTOR_MULTIPLE:g} "
            f"times the sector's {sector:.1%}."
        ),
    )


def hypergrowth_flags(
    financials: Financials,
    assumptions: Assumptions,
    result: DCFResult,
    context: NarrativeContext,
) -> tuple[NarrativeFlag, ...]:
    """Return the hypergrowth flags: up to three, in a fixed order (#195, #197).

    ``hypergrowth_story`` comes first when signals or the hypergrowth story type
    call for it; the revenue-scale and terminal-ROIC flags follow only for the
    ``hypergrowth`` story type.
    """
    if not (context.hypergrowth_signals or context.story_type == _HYPERGROWTH_STORY):
        return ()
    story = hypergrowth_story_flag(financials, assumptions, result, context)
    if context.story_type != _HYPERGROWTH_STORY:
        return (story,)
    return (
        story,
        hypergrowth_revenue_scale_flag(financials, assumptions, result, context),
        hypergrowth_terminal_roic_flag(financials, assumptions, result, context),
    )


#: The §7.5 flag functions, in spec order. The aggregator runs each, except
#: ``story_margin_flag`` outside a high-growth story.
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
    """Run the §7.5 narrative-consistency flags, in spec order.

    The four flags that always apply run for every story;
    ``story_margin`` runs, first, only for a ``high-growth`` story. A check
    that does not apply is not emitted, but ``unknown`` stays visible.

    Args:
        financials: The company's current-year financial state (DCF input).
        assumptions: The projection and discount-rate assumptions (DCF input).
        result: The :class:`DCFResult` produced from ``financials`` and
            ``assumptions``.
        context: Flag-specific inputs not carried by the DCF types (§7.5).

    Returns:
        Four :class:`NarrativeFlag` verdicts (five with ``story_margin`` for a
        high-growth story), in the spec §7.5 order. These
        are signals for a human and do **not** feed the screener ranking.
    """
    return tuple(
        flag(financials, assumptions, result, context)
        for flag in _FLAG_FUNCTIONS
        if flag is not story_margin_flag or context.story_type == _HIGH_GROWTH_STORY
    )
