"""Sector classifications over the Damodaran industry taxonomy.

Two questions the rest of the bot asks about an industry, answered in one place so
the answers cannot drift:

- **Is it financial services?** The §6.2 quality gate excludes banks and insurers
  because their balance sheets make the leverage and cashflow gates meaningless.
  Substring-matching ``"bank"``/``"insurance"`` misses
  ``"Investments & Asset Management"``, ``"Brokerage & Investment Banking"``,
  ``"Financial Svcs. (Non-bank & Insurance)"``, ``"Reinsurance"`` and ``"R.E.I.T."``.
- **Is it cyclical?** ``StoryType.CYCLICAL`` (§7.1) needs a sector signal; without
  one the classifier can never reach that archetype.

Membership is exact against the published labels, never substring: an unmapped
free-text provider label must not accidentally classify. Both sets are asserted to
be subsets of :data:`bot.reference.industries.DAMODARAN_INDUSTRIES` by the tests,
so a typo fails loudly.
"""

from __future__ import annotations

#: Industries whose balance sheets make the §6.2 leverage / cashflow gates
#: meaningless. Excluded by the default screener preset.
FINANCIAL_SERVICES_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Bank (Money Center)",
        "Banks (Regional)",
        "Brokerage & Investment Banking",
        "Financial Svcs. (Non-bank & Insurance)",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
        "Investments & Asset Management",
        "R.E.I.T.",
        "Reinsurance",
        "Retail (REITs)",
    }
)

#: Industries whose earnings swing with the economic cycle, so a single year's
#: margin or growth rate is a poor guide to the next (spec §7.1).
CYCLICAL_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Air Transport",
        "Auto & Truck",
        "Auto Parts",
        "Building Materials",
        "Chemical (Basic)",
        "Coal & Related Energy",
        "Construction Supplies",
        "Engineering/Construction",
        "Furn/Home Furnishings",
        "Homebuilding",
        "Hotel/Gaming",
        "Machinery",
        "Metals & Mining",
        "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)",
        "Oilfield Svcs/Equip.",
        "Paper/Forest Products",
        "Precious Metals",
        "Real Estate (Development)",
        "Retail (Automotive)",
        "Rubber& Tires",
        "Semiconductor",
        "Semiconductor Equip",
        "Shipbuilding & Marine",
        "Steel",
        "Transportation",
        "Trucking",
    }
)


def is_financial_services(industry: str | None) -> bool:
    """Whether ``industry`` is a Damodaran financial-services label (exact match)."""
    return industry in FINANCIAL_SERVICES_INDUSTRIES


def is_cyclical(industry: str | None) -> bool:
    """Whether ``industry`` is a Damodaran cyclical label (exact match)."""
    return industry in CYCLICAL_INDUSTRIES
