"""The words the web viewer uses for the model's identifiers.

Every DCF input, narrative flag and assumption source has a label in plain
English and a one-sentence description the templates show as a tooltip. The
identifiers themselves (``sales_to_capital``, ``terminal_value_share``) never
reach the page.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.valuator.sensitivity import PATH_AXES, SensitivityAxis


@dataclass(frozen=True)
class Term:
    label: str
    description: str


#: The DCF assumptions, keyed by their field name in :class:`bot.valuator.dcf.Assumptions`.
INPUTS: dict[str, Term] = {
    "revenue_growth": Term(
        "Revenue growth",
        "Year-on-year growth of revenue over the forecast horizon. "
        "The story type sets its shape: a fade for a maturing company, a ramp for a young one.",
    ),
    "operating_margin": Term(
        "Operating margin",
        "Operating profit (EBIT) as a share of revenue, year by year. "
        "Together with revenue it sets the pre-tax earnings being valued.",
    ),
    "sales_to_capital": Term(
        "Sales-to-capital",
        "Revenue generated per unit of capital reinvested. "
        "Each year's reinvestment is the revenue added divided by this ratio, so a higher ratio makes growth cheaper to fund.",
    ),
    "cost_of_equity": Term(
        "Cost of equity",
        "The return shareholders require for this company's risk (CAPM: risk-free rate plus beta times the equity risk premium). "
        "The equity leg of the discount rate.",
    ),
    "pretax_cost_of_debt": Term(
        "Pre-tax cost of debt",
        "The interest rate the company would pay on new borrowing, before the tax shield. "
        "The debt leg of the discount rate.",
    ),
    "equity_weight": Term(
        "Equity weight",
        "Equity as a share of total capital (equity plus debt), at market values. "
        "Weights the cost of equity in the discount rate.",
    ),
    "debt_weight": Term(
        "Debt weight",
        "Debt as a share of total capital (equity plus debt), at market values. "
        "Weights the after-tax cost of debt in the discount rate.",
    ),
    "terminal_growth": Term(
        "Terminal growth",
        "The perpetual growth rate assumed after the forecast horizon. "
        "It must stay below the discount rate, and small changes move the terminal value a lot.",
    ),
    "tax_rate": Term(
        "Tax rate",
        "The tax rate applied to operating profit to reach after-tax operating income (NOPAT). "
        "Also sets the tax shield on debt.",
    ),
    "probability_of_bankruptcy": Term(
        "Probability of bankruptcy",
        "The chance the company fails before the forecast plays out. "
        "The intrinsic value blends the going-concern value with the distress value by this probability.",
    ),
}

#: The narrative flags, keyed by the ``name`` each check in ``bot.valuator.narrative_flags`` emits.
FLAGS: dict[str, Term] = {
    "story_margin": Term(
        "Story vs margin",
        "A high-growth story whose operating margin already beats the sector. "
        "The story expects margins to improve, but there is little room left for them to.",
    ),
    "growth_reinvestment": Term(
        "Growth vs reinvestment",
        "Growth the model never funds out of earnings. "
        "Revenue grows while the reinvestment that should pay for it is missing.",
    ),
    "beta_business_risk": Term(
        "Beta vs leverage",
        "A defensive beta paired with high real leverage. "
        "The discount rate says low risk while the balance sheet says otherwise.",
    ),
    "terminal_value_share": Term(
        "Terminal value share",
        "How much of the value rests on the perpetuity after the forecast horizon. "
        "A very high share means the verdict hangs on the terminal assumptions.",
    ),
    "country_exposure": Term(
        "Country exposure",
        "Mostly foreign revenue priced at the listing country's equity risk premium. "
        "The discount rate may understate where the business actually operates.",
    ),
    "hypergrowth_story": Term(
        "Hypergrowth story",
        "The company shows hypergrowth signals but has no hand-written story file. "
        "It is valued as high-growth instead, which may understate its path.",
    ),
    "hypergrowth_revenue_scale": Term(
        "Hypergrowth revenue scale",
        "The projected year-10 revenue is larger than any company earns today. "
        "The story asks for a scale no business has reached.",
    ),
    "hypergrowth_terminal_roic": Term(
        "Hypergrowth terminal return",
        "The return on capital assumed in the terminal year is more than twice the sector's. "
        "A durable advantage that large is rare.",
    ),
}

#: Where an assumption came from, keyed by the ``source`` stored with each assumption.
SOURCES: dict[str, Term] = {
    "manual": Term(
        "manual override",
        "Written by hand in the company's assumptions file.",
    ),
    "sector_default_damodaran": Term(
        "sector default (Damodaran)",
        "Damodaran's industry average for this company's sector, not a fact about the company itself.",
    ),
    "sector_default_damodaran_cross_region": Term(
        "sector default (Damodaran, other region)",
        "Damodaran's industry average for this company's sector, taken from a different region "
        "than the company's own because its own region has no data.",
    ),
    "country_default_damodaran": Term(
        "country default (Damodaran)",
        "Damodaran's corporate tax rate for this company's country, used when its sector has no tax rate.",
    ),
    "rule_based": Term(
        "rule",
        "Set by a rule of the model, such as the terminal growth capped at the risk-free rate.",
    ),
    "historical_average": Term(
        "historical average",
        "The company's own average over its reported history.",
    ),
    "story_pattern": Term(
        "story pattern",
        "A path the company's story type draws from its own history and its sector, "
        "such as growth fading to the terminal rate.",
    ),
    "story": Term(
        "story file",
        "Set by or derived from the story section of the company's assumptions file.",
    ),
    "unresolved": Term(
        "unresolved",
        "No value was produced: no source had the data, so the model shows a gap instead of a number.",
    ),
}


def _fallback(name: str) -> Term:
    return Term(name.replace("_", " "), "")


def input_term(key: str) -> Term:
    """The term for a DCF assumption; an unknown key becomes words without a description."""
    return INPUTS.get(key) or _fallback(key)


def axis_term(axis: SensitivityAxis) -> Term:
    """The term for a sensitivity axis, marking a path axis as year-1-only.

    The tornado and the scenario grid swing ``revenue_growth`` and
    ``operating_margin`` by the same step every year but report year 1 only,
    so their labels carry the same ``(yr 1)`` suffix the assumptions table uses.
    """
    term = input_term(axis.value)
    if axis in PATH_AXES:
        return Term(f"{term.label} (yr 1)", term.description)
    return term


def flag_term(name: str) -> Term:
    """The term for a narrative flag; an unknown name becomes words without a description."""
    return FLAGS.get(name) or _fallback(name)


def source_term(source: str) -> Term:
    """The term for an assumption source; an unknown one becomes words without a description."""
    return SOURCES.get(source) or _fallback(source)
