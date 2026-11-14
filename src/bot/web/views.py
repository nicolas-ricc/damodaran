"""View-models for the web viewer (issue #92).

Pure functions from sidecar data to frozen dataclasses; the templates only
render what is computed here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from bot.reference.company_profiles import CompanyProfile
from bot.reporting.analysis_report import (
    MOS_FAIR,
    MOS_UNDERVALUED,
    fmt_growth_label,
    fmt_growth_path,
    fmt_margin_path,
    fmt_money,
    fmt_num,
    fmt_pct,
    fmt_per_share,
    fmt_ratio,
    fmt_shock,
    fmt_step,
    margin_verdict,
)
from bot.valuator.sensitivity import SensitivityAxis, ShockKind
from bot.web.glossary import Term, axis_term, flag_term, input_term, source_term
from bot.web.index import AnalysisRef, CompanyEntry

_DASH = "—"


class Verdict(StrEnum):
    UNDERVALUED = "undervalued"
    FAIR = "fair"
    OVERVALUED = "overvalued"
    NA = "na"


VERDICT_TEXT: dict[Verdict, str] = {
    Verdict.UNDERVALUED: margin_verdict(MOS_UNDERVALUED),
    Verdict.FAIR: margin_verdict(MOS_FAIR),
    Verdict.OVERVALUED: margin_verdict(0.0),
    Verdict.NA: margin_verdict(None),
}
_TEXT_TO_VERDICT = {text: verdict for verdict, text in VERDICT_TEXT.items()}

#: The short name of each verdict, as the filter chips and the legend print it.
VERDICT_LABEL: dict[Verdict, str] = {
    Verdict.UNDERVALUED: "undervalued",
    Verdict.FAIR: "fair",
    Verdict.OVERVALUED: "overvalued",
    Verdict.NA: "no verdict",
}

FILTERS = ("all", "undervalued", "fair", "overvalued", "na")
SORTS = ("ticker", "mos", "date")
DIRECTIONS = ("asc", "desc")

#: Flag colours as the valuator writes them, read as a severity word.
FLAG_SEVERITY: dict[str, str] = {
    "green": "pass",
    "yellow": "warning",
    "red": "fail",
}
_NOT_EVALUATED = "not evaluated"

#: Assumption sources as the valuator writes them, read as words.
_SECTOR_DEFAULT = "sector_default_damodaran"

#: Corporate suffixes that stay upper-case when a name is re-cased.
_KEEP_UPPER = frozenset({"LLC", "PLC", "SA", "NV", "AG", "SE", "LP", "AB", "ASA", "SPA", "ADR"})


def verdict_of(margin_of_safety: float | None) -> Verdict:
    """Classify a margin of safety using :func:`margin_verdict` thresholds."""
    return verdict_from_text(margin_verdict(margin_of_safety))


def verdict_from_text(text: str) -> Verdict:
    """Inverse of :data:`VERDICT_TEXT`; unknown text is ``NA``."""
    return _TEXT_TO_VERDICT.get(text, Verdict.NA)


def flag_severity(color: str) -> str:
    """``pass`` / ``warning`` / ``fail``, or ``not evaluated`` for any other colour."""
    return FLAG_SEVERITY.get(color, _NOT_EVALUATED)


def source_label(source: str) -> str:
    """An assumption source identifier as words."""
    return source_term(source).label


def display_name(name: str) -> str:
    """EDGAR's upper-case company names re-cased; mixed-case names pass through."""
    if name != name.upper():
        return name
    words = []
    for word in name.split():
        if word in _KEEP_UPPER or not word.isalpha():
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


#: Where a tag's revenue share came from, as the tooltip words it.
SOURCE_WORDS: dict[str, str] = {
    "segment": "reported segment",
    "disaggregation": "revenue disaggregation",
    "judgment": "estimated from the 10-K",
}


@dataclass(frozen=True)
class TagView:
    label: str
    tooltip: str


@dataclass(frozen=True)
class ProfileView:
    description: str
    tags: tuple[TagView, ...]


def profile_view(profile: CompanyProfile | None) -> ProfileView | None:
    """A company profile as the description and one badge per industry tag."""
    if profile is None:
        return None
    tags = tuple(
        TagView(
            label=t.tag.label,
            tooltip=(
                f"{t.tag.description} ~{t.share:.0%} of revenue, "
                f"{SOURCE_WORDS[t.source]}, FY{profile.fiscal_year}."
            ),
        )
        for t in profile.tags
    )
    return ProfileView(description=profile.description, tags=tags)


def search_tags(profile: CompanyProfile | None) -> str:
    """Slugs and labels of the industry tags, lower-cased, for the search box."""
    if profile is None:
        return ""
    return " ".join(f"{t.tag.slug} {t.tag.label}".lower() for t in profile.tags)


@dataclass(frozen=True)
class ValueLine:
    price: float
    intrinsic: float
    range_low: float
    range_high: float
    axis_min: float
    axis_max: float
    verdict: Verdict

    @property
    def fair(self) -> float:
        return self.price * MOS_FAIR

    @property
    def undervalued(self) -> float:
        return self.price * MOS_UNDERVALUED


@dataclass(frozen=True)
class FlagView:
    name: str
    color: str
    reason: str

    @property
    def severity(self) -> str:
        return flag_severity(self.color)

    @property
    def tone(self) -> str:
        """The DaisyUI badge colour for this flag's severity."""
        return {"pass": "success", "warning": "warning", "fail": "error"}.get(self.severity, "ghost")

    @property
    def label(self) -> str:
        return flag_term(self.name).label

    @property
    def description(self) -> str:
        return flag_term(self.name).description

    @property
    def detail(self) -> str:
        """The reason without the ``not evaluated:`` prefix the severity already states."""
        prefix = f"{_NOT_EVALUATED}:"
        text = self.reason.strip()
        if text.lower().startswith(prefix):
            text = text[len(prefix) :].strip()
        return text


@dataclass(frozen=True)
class RowView:
    ticker: str
    name: str
    verdict: Verdict
    mos: float | None
    price: str
    intrinsic: str
    story: str
    flags: tuple[FlagView, ...]
    date: dt.date
    value_line: ValueLine | None
    tags: str = ""


@dataclass(frozen=True)
class ScenarioGrid:
    axis_a: Term
    axis_b: Term
    row_labels: tuple[str, ...]
    col_labels: tuple[str, ...]
    cells: tuple[tuple[Verdict | None, ...], ...]
    matching: int
    total: int


# Sidecars written before #217 carry no shock kind; every shock then was a factor.
_PRE_217_KIND = ShockKind.MULTIPLICATIVE


@dataclass(frozen=True)
class TornadoBar:
    label: str
    low: float
    high: float
    shock: str = ""
    description: str = ""


@dataclass(frozen=True)
class LabelledValue:
    label: str
    value: str
    source: str
    description: str = ""
    source_description: str = ""


@dataclass(frozen=True)
class DetailView:
    ticker: str
    name: str
    date: dt.date
    story: str
    story_reasons: tuple[str, ...]
    verdict: Verdict
    verdict_text: str
    mos: str
    price: float | None
    intrinsic: float
    value_line: ValueLine | None
    grid: ScenarioGrid | None
    tornado: tuple[TornadoBar, ...]
    assumptions: tuple[LabelledValue, ...]
    defaulted: int
    flags: tuple[FlagView, ...]
    sanity: tuple[LabelledValue, ...]
    dcf_rows: tuple[tuple[str, ...], ...]
    dcf_totals: tuple[LabelledValue, ...]
    history: tuple[dt.date, ...]
    #: Haircut the margin of safety is measured after (#197); 0 in older sidecars.
    governance_discount: float = 0.0
    intrinsic_after_governance: float | None = None
    profile: ProfileView | None = None

    @property
    def mos_note(self) -> str:
        """One sentence that turns the margin of safety into its verdict."""
        if self.price is None:
            return "No price, so no margin of safety and no verdict."
        label, value = "Intrinsic value", self.intrinsic
        if self.governance_discount > 0 and self.intrinsic_after_governance is not None:
            label = f"Intrinsic value after the {self.governance_discount:.1%} governance discount"
            value = self.intrinsic_after_governance
        return (
            f"{label} {fmt_per_share(value)} is {self.mos} the price of "
            f"{fmt_per_share(self.price)}. At or above {MOS_UNDERVALUED:.1f}\u00d7 reads as "
            f"undervalued, between {MOS_FAIR:.1f}\u00d7 and {MOS_UNDERVALUED:.1f}\u00d7 as fair, "
            f"below {MOS_FAIR:.1f}\u00d7 as overvalued."
        )


def value_line(analysis: Mapping[str, Any]) -> ValueLine | None:
    """Price/intrinsic positions on one axis; ``None`` without a usable price."""
    price = analysis.get("current_price")
    if price is None or price <= 0:
        return None
    intrinsic = float(analysis["dcf_result"]["intrinsic_value"])
    extremes = [
        float(v)
        for entry in analysis.get("tornado", [])
        for v in (entry["intrinsic_low"], entry["intrinsic_high"])
        if v is not None
    ]
    range_low = min([intrinsic, *extremes])
    range_high = max([intrinsic, *extremes])
    points = [price, price * MOS_UNDERVALUED, range_low, range_high]
    low, high = min(points), max(points)
    pad = (high - low) * 0.05 or 1.0
    return ValueLine(
        price=float(price),
        intrinsic=intrinsic,
        range_low=range_low,
        range_high=range_high,
        axis_min=low - pad,
        axis_max=high + pad,
        verdict=verdict_of(analysis.get("margin_of_safety")),
    )


def scenario_grid(analysis: Mapping[str, Any]) -> ScenarioGrid | None:
    """The two-axis scenario grid as verdicts; ``None`` without a reference price."""
    grid = analysis["grid"]
    if grid.get("reference_price") is None:
        return None
    stored = verdict_of(analysis.get("margin_of_safety"))
    cells = tuple(
        tuple(
            None if cell["margin_of_safety"] is None else verdict_of(cell["margin_of_safety"])
            for cell in row
        )
        for row in grid["cells"]
    )
    flat = [c for row in cells for c in row if c is not None]
    return ScenarioGrid(
        axis_a=axis_term(SensitivityAxis(grid["axis_a"])),
        axis_b=axis_term(SensitivityAxis(grid["axis_b"])),
        row_labels=_step_labels(grid, "row"),
        col_labels=_step_labels(grid, "col"),
        cells=cells,
        matching=sum(1 for c in flat if c == stored),
        total=len(flat),
    )


def _step_labels(grid: Mapping[str, Any], side: str) -> tuple[str, ...]:
    kind = grid.get(f"{side}_kind", _PRE_217_KIND)
    steps = grid[f"{side}_steps"] if f"{side}_steps" in grid else grid[f"{side}_multipliers"]
    return tuple(fmt_step(s, kind) for s in steps)


def _flags(analysis: Mapping[str, Any]) -> tuple[FlagView, ...]:
    return tuple(FlagView(f["name"], f["color"], f["reason"]) for f in analysis["narrative_flags"])


def row_view(ref: AnalysisRef, profile: CompanyProfile | None = None) -> RowView:
    analysis = ref.data["analysis"]
    return RowView(
        ticker=ref.ticker,
        name=display_name(analysis["name"]),
        verdict=verdict_from_text(ref.data["verdict"]),
        mos=analysis.get("margin_of_safety"),
        price=fmt_per_share(analysis.get("current_price")),
        intrinsic=fmt_per_share(analysis["dcf_result"]["intrinsic_value"]),
        story=analysis.get("story_type") or _DASH,
        flags=tuple(f for f in _flags(analysis) if f.color in ("red", "yellow")),
        date=ref.date,
        value_line=value_line(analysis),
        tags=search_tags(profile),
    )


#: Assumption key and formatter, in the order of the Markdown report (analysis.md.j2).
#: Labels and descriptions come from :mod:`bot.web.glossary`; the revenue-growth
#: label alone depends on the value (the length of its path).
_ASSUMPTION_ROWS: tuple[tuple[str, Callable[[Any], str]], ...] = (
    ("revenue_growth", fmt_growth_path),
    ("operating_margin", fmt_margin_path),
    ("sales_to_capital", fmt_num),
    ("cost_of_equity", fmt_pct),
    ("pretax_cost_of_debt", fmt_pct),
    ("equity_weight", fmt_pct),
    ("debt_weight", fmt_pct),
    ("terminal_growth", fmt_pct),
    ("tax_rate", fmt_pct),
    ("probability_of_bankruptcy", fmt_pct),
)

#: The assumption keys the detail page shows, in display order.
ASSUMPTION_KEYS: tuple[str, ...] = tuple(key for key, _ in _ASSUMPTION_ROWS)


def _assumption_label(key: str, value: Any) -> str:
    if key == "revenue_growth":
        return fmt_growth_label(value)
    return input_term(key).label


def _assumptions(assumptions: Mapping[str, Any]) -> tuple[LabelledValue, ...]:
    return tuple(
        LabelledValue(
            _assumption_label(key, assumptions[key]["value"]),
            fmt(assumptions[key]["value"]),
            source_term(str(assumptions[key]["source"])).label,
            description=input_term(key).description,
            source_description=source_term(str(assumptions[key]["source"])).description,
        )
        for key, fmt in _ASSUMPTION_ROWS
    )


def _defaulted(assumptions: Mapping[str, Any]) -> int:
    return sum(1 for key, _ in _ASSUMPTION_ROWS if assumptions[key]["source"] == _SECTOR_DEFAULT)


def _sanity(check: Mapping[str, Any] | None) -> tuple[LabelledValue, ...]:
    if not check:
        return ()
    sector_pe = fmt_num(check["sector_pe"])
    if "market_pe" in check:
        implied_pe, market_pe = check["implied_pe"], check["market_pe"]
    else:  # sidecar from before #219: its implied_pe was the market P/E
        implied_pe, market_pe = None, check["implied_pe"]
    return (
        LabelledValue("P/E implied (DCF)", f"{fmt_num(implied_pe)} / {sector_pe}", ""),
        LabelledValue("P/E market", f"{fmt_num(market_pe)} / {sector_pe}", ""),
        LabelledValue(
            "EV/Sales",
            f"{fmt_num(check['implied_ev_sales'])} / {fmt_num(check['sector_ev_sales'])}",
            "",
        ),
    )


def _dcf_totals(dcf: Mapping[str, Any], financials: Mapping[str, Any]) -> tuple[LabelledValue, ...]:
    """The DCF as a sum: discounted cash flows plus terminal value, down to a share."""
    pv_sum = sum(float(p["present_value"]) for p in dcf["projections"])
    enterprise = float(dcf["enterprise_value"])
    return (
        LabelledValue(
            f"Present value of FCFF, years 1-{len(dcf['projections'])}", fmt_money(pv_sum), ""
        ),
        LabelledValue("Terminal value, discounted", fmt_money(enterprise - pv_sum), ""),
        LabelledValue("Enterprise value", fmt_money(enterprise), ""),
        LabelledValue("Net debt", fmt_money(financials["net_debt"]), ""),
        LabelledValue("Equity value", fmt_money(dcf["equity_value"]), ""),
        LabelledValue("Diluted shares", fmt_money(financials["shares_diluted"]), ""),
        LabelledValue("Intrinsic value per share", fmt_per_share(dcf["intrinsic_value"]), ""),
    )


def detail_view(
    entry: CompanyEntry, ref: AnalysisRef, profile: CompanyProfile | None = None
) -> DetailView:
    analysis = ref.data["analysis"]
    dcf = analysis["dcf_result"]
    verdict = verdict_from_text(ref.data["verdict"])
    mos = analysis.get("margin_of_safety")
    tornado = tuple(
        TornadoBar(
            label=axis_term(SensitivityAxis(t["axis"])).label,
            low=float(t["intrinsic_low"]),
            high=float(t["intrinsic_high"]),
            shock=fmt_shock(t.get("kind", _PRE_217_KIND)),
            description=axis_term(SensitivityAxis(t["axis"])).description,
        )
        for t in analysis["tornado"]
        if t["intrinsic_low"] is not None and t["intrinsic_high"] is not None
    )
    return DetailView(
        ticker=ref.ticker,
        name=display_name(analysis["name"]),
        date=ref.date,
        story=analysis.get("story_type") or _DASH,
        story_reasons=tuple(analysis["story_reasons"]),
        verdict=verdict,
        verdict_text=VERDICT_TEXT[verdict],
        mos="n/a" if mos is None else fmt_ratio(mos),
        price=analysis.get("current_price"),
        intrinsic=float(dcf["intrinsic_value"]),
        value_line=value_line(analysis),
        grid=scenario_grid(analysis),
        tornado=tornado,
        assumptions=_assumptions(analysis["assumptions"]),
        defaulted=_defaulted(analysis["assumptions"]),
        flags=_flags(analysis),
        sanity=_sanity(analysis.get("sanity_check")),
        dcf_rows=tuple(
            (
                str(p["year"]),
                fmt_money(p["revenue"]),
                fmt_money(p["ebit"]),
                fmt_money(p["fcff"]),
                fmt_money(p["present_value"]),
            )
            for p in dcf["projections"]
        ),
        dcf_totals=_dcf_totals(dcf, analysis["financials"]),
        history=tuple(r.date for r in entry.history),
        profile=profile_view(profile),
        governance_discount=float(analysis.get("governance_discount", 0.0)),
        intrinsic_after_governance=analysis.get("intrinsic_value_after_governance"),
    )


def filter_sort(rows: Sequence[RowView], verdict: str, sort: str, direction: str) -> list[RowView]:
    """Filter by verdict then sort; rows without a margin of safety always last."""
    if verdict not in FILTERS:
        raise ValueError(f"unknown filter: {verdict!r}")
    if sort not in SORTS:
        raise ValueError(f"unknown sort: {sort!r}")
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction: {direction!r}")
    kept = [r for r in rows if verdict == "all" or r.verdict.value == verdict]
    reverse = direction == "desc"
    kept.sort(key=lambda r: r.ticker)  # tie-break: ticker ascending (stable sort)
    if sort == "ticker":
        kept.sort(key=lambda r: r.ticker, reverse=reverse)
    elif sort == "date":
        kept.sort(key=lambda r: r.date, reverse=reverse)
    else:
        present = sorted(
            (r for r in kept if r.mos is not None), key=lambda r: r.mos or 0.0, reverse=reverse
        )
        missing = [r for r in kept if r.mos is None]
        return present + missing
    return kept
