"""Provider industry label → Damodaran industry taxonomy (spec §4.3.1).

Every sector-relative comparison in the bot keys off ``companies.industry_damodaran``:
the screener's value indicators and the ROIC-vs-WACC trap detector look their medians
up by it (``screener/benchmarks.py``), and the valuator resolves five of its six
critical assumptions from it (``valuator/assumptions.py``). Providers use their own
taxonomy — FMP emits Yahoo-style labels like ``"Semiconductors"`` — which never match
Damodaran's ``"Semiconductor"``. This module is the single translation point.

The mapping is a CSV — one copy, shipped inside the package — so a new provider
label can be mapped without a code change; ``BOT_INDUSTRY_MAPPING_PATH`` points the
ingest at a user-maintained file instead. Resolution is deliberately forgiving on formatting (case, whitespace,
dash variants) because providers are inconsistent about it, but strict on the target:
a ``damodaran_industry`` that is not in the published taxonomy fails at load time
rather than silently producing a company whose benchmarks never resolve.

Missing file → empty mapping, logged as a warning. Ingest must degrade, not die
(spec §13.2); the cost is that sector-relative rules skip, which the screener
already handles.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_REQUIRED_COLUMNS = ("provider", "provider_industry", "damodaran_industry")

#: Dash characters providers use interchangeably between an industry family and its
#: variant (em dash, en dash, non-breaking hyphen). ASCII hyphen-minus is the
#: normalisation target, not a member of this set.
_DASHES = "\u2014\u2013\u2011"

#: Matches a run of one or more (already-normalised) ASCII dashes, together with
#: any whitespace hugging them, so ``"a - - b"``, ``"a--b"`` and ``"a-b"`` all
#: collapse to the same single separator.
_DASH_RUN_RE = re.compile(r"(?:\s*-\s*)+")

#: The 94 industry labels of Damodaran's ``wacc.xls`` "Industry Averages" sheet,
#: excluding the two aggregate rows ("Total Market", "Total Market (without
#: financials)") which are not industries a company can belong to.
DAMODARAN_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Advertising",
        "Aerospace/Defense",
        "Air Transport",
        "Apparel",
        "Auto & Truck",
        "Auto Parts",
        "Bank (Money Center)",
        "Banks (Regional)",
        "Beverage (Alcoholic)",
        "Beverage (Soft)",
        "Broadcasting",
        "Brokerage & Investment Banking",
        "Building Materials",
        "Business & Consumer Services",
        "Cable TV",
        "Chemical (Basic)",
        "Chemical (Diversified)",
        "Chemical (Specialty)",
        "Coal & Related Energy",
        "Computer Services",
        "Computers/Peripherals",
        "Construction Supplies",
        "Diversified",
        "Drugs (Biotechnology)",
        "Drugs (Pharmaceutical)",
        "Education",
        "Electrical Equipment",
        "Electronics (Consumer & Office)",
        "Electronics (General)",
        "Engineering/Construction",
        "Entertainment",
        "Environmental & Waste Services",
        "Farming/Agriculture",
        "Financial Svcs. (Non-bank & Insurance)",
        "Food Processing",
        "Food Wholesalers",
        "Furn/Home Furnishings",
        "Green & Renewable Energy",
        "Healthcare Products",
        "Healthcare Support Services",
        "Heathcare Information and Technology",
        "Homebuilding",
        "Hospitals/Healthcare Facilities",
        "Hotel/Gaming",
        "Household Products",
        "Information Services",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
        "Investments & Asset Management",
        "Machinery",
        "Metals & Mining",
        "Office Equipment & Services",
        "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)",
        "Oil/Gas Distribution",
        "Oilfield Svcs/Equip.",
        "Packaging & Container",
        "Paper/Forest Products",
        "Power",
        "Precious Metals",
        "Publishing & Newspapers",
        "R.E.I.T.",
        "Real Estate (Development)",
        "Real Estate (General/Diversified)",
        "Real Estate (Operations & Services)",
        "Recreation",
        "Reinsurance",
        "Restaurant/Dining",
        "Retail (Automotive)",
        "Retail (Building Supply)",
        "Retail (Distributors)",
        "Retail (General)",
        "Retail (Grocery and Food)",
        "Retail (REITs)",
        "Retail (Special Lines)",
        "Rubber& Tires",
        "Semiconductor",
        "Semiconductor Equip",
        "Shipbuilding & Marine",
        "Shoe",
        "Software (Entertainment)",
        "Software (Internet)",
        "Software (System & Application)",
        "Steel",
        "Telecom (Wireless)",
        "Telecom. Equipment",
        "Telecom. Services",
        "Tobacco",
        "Transportation",
        "Transportation (Railroads)",
        "Trucking",
        "Utility (General)",
        "Utility (Water)",
    }
)


def normalize_industry_label(raw: str) -> str:
    """Fold a provider label to a comparison key.

    Lower-cases, collapses internal whitespace, and collapses every *run* of one
    or more dash characters (any mix of em dash, en dash, non-breaking hyphen and
    ASCII hyphen-minus, with or without surrounding spaces) to a single ``-``, so
    ``"Banks\u2014Diversified"``, ``"Banks \u2013 \u2013 Diversified"`` and
    ``"banks - diversified"`` all agree.
    """
    text = raw.strip().lower()
    for dash in _DASHES:
        text = text.replace(dash, "-")
    text = " ".join(text.split())
    text = _DASH_RUN_RE.sub("-", text)
    return text


@dataclass(frozen=True)
class IndustryMapping:
    """Immutable provider→Damodaran lookup, keyed by (provider, normalised label)."""

    _entries: dict[tuple[str, str], str]

    def resolve(self, provider: str, industry: str | None) -> str | None:
        """Return the Damodaran industry for ``industry``, or ``None`` if unmapped."""
        if industry is None:
            return None
        key = (provider.strip().lower(), normalize_industry_label(industry))
        return self._entries.get(key)

    def __len__(self) -> int:
        return len(self._entries)


def default_mapping_path() -> Path:
    """Path of the mapping CSV packaged with ``bot.ingest``.

    Returns ``bot/ingest/industry_mapping.csv`` — the copy installed alongside the
    code (``pyproject.toml`` force-include), so the mapping resolves from an
    installed wheel with no repo checkout and independently of the process CWD.
    There is deliberately no repo-relative fallback: a second committed copy would
    drift, and which one won would depend on where the process was started.
    """
    return Path(str(resources.files("bot.ingest").joinpath("industry_mapping.csv")))


def resolve_mapping_path(configured: Path | None) -> Path:
    """Pick the mapping CSV to read: the configured path, else the packaged one.

    ``Settings.industry_mapping_path`` (``BOT_INDUSTRY_MAPPING_PATH``) lets a user
    point the ingest at their own edited CSV. An explicitly configured path that
    does not exist is a misconfiguration, not a reason to run with an empty
    mapping, so it is logged and the packaged default is used instead.

    Args:
        configured: The ``Settings``-supplied path, or ``None`` for the default.

    Returns:
        An existing CSV path, or the packaged default if neither exists (in which
        case :func:`load_industry_mapping` logs and yields an empty mapping).
    """
    if configured is None:
        return default_mapping_path()
    if configured.exists():
        return configured
    fallback = default_mapping_path()
    log.warning(
        "industry_mapping.configured_path_absent",
        configured_path=str(configured),
        fallback_path=str(fallback),
    )
    return fallback


def load_industry_mapping(path: Path | None = None) -> IndustryMapping:
    """Load the provider→Damodaran mapping CSV.

    Args:
        path: CSV location; defaults to :func:`default_mapping_path`.

    Returns:
        The loaded mapping, or an empty mapping when the file does not exist.

    Raises:
        ValueError: On a missing required column, a duplicate
            ``(provider, provider_industry)`` pair, or a ``damodaran_industry``
            outside :data:`DAMODARAN_INDUSTRIES`.
    """
    target = path if path is not None else default_mapping_path()
    if not target.exists():
        log.warning("industry_mapping.absent", path=str(target))
        return IndustryMapping(_entries={})

    with target.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in _REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise ValueError(f"{target}: missing required column(s): {', '.join(missing)}")
        entries: dict[tuple[str, str], str] = {}
        for lineno, row in enumerate(reader, start=2):
            provider = (row["provider"] or "").strip().lower()
            provider_industry = (row["provider_industry"] or "").strip()
            damodaran = (row["damodaran_industry"] or "").strip()
            if not provider or not provider_industry or not damodaran:
                continue
            if damodaran not in DAMODARAN_INDUSTRIES:
                raise ValueError(
                    f"{target}:{lineno}: {damodaran!r} is not a Damodaran industry"
                )
            key = (provider, normalize_industry_label(provider_industry))
            if key in entries:
                raise ValueError(
                    f"{target}:{lineno}: duplicate mapping for "
                    f"provider {provider!r} industry {provider_industry!r}"
                )
            entries[key] = damodaran

    log.info("industry_mapping.loaded", path=str(target), entries=len(entries))
    return IndustryMapping(_entries=entries)
