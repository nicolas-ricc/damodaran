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

from bot.reporting.analysis_report import (
    fmt_axis_label,
    fmt_margin_path,
    fmt_money,
    fmt_mult,
    fmt_num,
    fmt_pct,
    fmt_per_share,
    fmt_ratio,
    margin_verdict,
)
from bot.valuator.sensitivity import SensitivityAxis
from bot.web.index import AnalysisRef, CompanyEntry

_DASH = "—"


class Verdict(StrEnum):
    UNDERVALUED = "undervalued"
    FAIR = "fair"
    OVERVALUED = "overvalued"
    NA = "na"


VERDICT_TEXT: dict[Verdict, str] = {
    Verdict.UNDERVALUED: margin_verdict(1.3),
    Verdict.FAIR: margin_verdict(1.0),
    Verdict.OVERVALUED: margin_verdict(0.0),
    Verdict.NA: margin_verdict(None),
}
_TEXT_TO_VERDICT = {text: verdict for verdict, text in VERDICT_TEXT.items()}

FILTERS = ("all", "undervalued", "fair", "overvalued", "na")
SORTS = ("ticker", "mos", "date")
DIRECTIONS = ("asc", "desc")


def verdict_of(margin_of_safety: float | None) -> Verdict:
    """Classify a margin of safety using :func:`margin_verdict` thresholds."""
    return verdict_from_text(margin_verdict(margin_of_safety))


def verdict_from_text(text: str) -> Verdict:
    """Inverse of :data:`VERDICT_TEXT`; unknown text is ``NA``."""
    return _TEXT_TO_VERDICT.get(text, Verdict.NA)


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
        return self.price

    @property
    def undervalued(self) -> float:
        return self.price * 1.3


@dataclass(frozen=True)
class RowView:
    ticker: str
    name: str
    verdict: Verdict
    mos: float | None
    price: str
    intrinsic: str
    story: str
    flags: tuple[str, ...]
    date: dt.date
    value_line: ValueLine | None


@dataclass(frozen=True)
class ScenarioGrid:
    axis_a: str
    axis_b: str
    row_labels: tuple[str, ...]
    col_labels: tuple[str, ...]
    cells: tuple[tuple[Verdict | None, ...], ...]
    matching: int
    total: int


@dataclass(frozen=True)
class TornadoBar:
    label: str
    low: float
    high: float


@dataclass(frozen=True)
class LabelledValue:
    label: str
    value: str
    source: str


@dataclass(frozen=True)
class FlagView:
    name: str
    color: str
    reason: str


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
    flags: tuple[FlagView, ...]
    sanity: tuple[LabelledValue, ...]
    dcf_rows: tuple[tuple[str, ...], ...]
    dcf_totals: tuple[LabelledValue, ...]
    history: tuple[dt.date, ...]


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
    points = [price, price * 1.3, range_low, range_high]
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
        axis_a=fmt_axis_label(SensitivityAxis(grid["axis_a"])),
        axis_b=fmt_axis_label(SensitivityAxis(grid["axis_b"])),
        row_labels=tuple(fmt_mult(m) for m in grid["row_multipliers"]),
        col_labels=tuple(fmt_mult(m) for m in grid["col_multipliers"]),
        cells=cells,
        matching=sum(1 for c in flat if c == stored),
        total=len(flat),
    )


def row_view(ref: AnalysisRef) -> RowView:
    analysis = ref.data["analysis"]
    return RowView(
        ticker=ref.ticker,
        name=analysis["name"],
        verdict=verdict_from_text(ref.data["verdict"]),
        mos=analysis.get("margin_of_safety"),
        price=fmt_per_share(analysis.get("current_price")),
        intrinsic=fmt_per_share(analysis["dcf_result"]["intrinsic_value"]),
        story=analysis.get("story_type") or _DASH,
        flags=tuple(
            f["color"] for f in analysis["narrative_flags"] if f["color"] in ("red", "yellow")
        ),
        date=ref.date,
        value_line=value_line(analysis),
    )


def _fmt_first_year(path: Any) -> str:
    return fmt_pct(path[0]) if path else _DASH


#: Label, assumption key and formatter, in the order of the Markdown report (analysis.md.j2).
_ASSUMPTION_ROWS: tuple[tuple[str, str, Callable[[Any], str]], ...] = (
    ("Revenue growth (yr 1)", "revenue_growth", _fmt_first_year),
    ("Operating margin", "operating_margin", fmt_margin_path),
    ("Sales-to-capital", "sales_to_capital", fmt_num),
    ("Cost of equity", "cost_of_equity", fmt_pct),
    ("Pre-tax cost of debt", "pretax_cost_of_debt", fmt_pct),
    ("Equity weight", "equity_weight", fmt_pct),
    ("Debt weight", "debt_weight", fmt_pct),
    ("Terminal growth", "terminal_growth", fmt_pct),
    ("Tax rate", "tax_rate", fmt_pct),
    ("Probability of bankruptcy", "probability_of_bankruptcy", fmt_pct),
)


def _assumptions(assumptions: Mapping[str, Any]) -> tuple[LabelledValue, ...]:
    return tuple(
        LabelledValue(label, fmt(assumptions[key]["value"]), str(assumptions[key]["source"]))
        for label, key, fmt in _ASSUMPTION_ROWS
    )


def _sanity(check: Mapping[str, Any] | None) -> tuple[LabelledValue, ...]:
    if not check:
        return ()
    return (
        LabelledValue("P/E", f"{fmt_num(check['implied_pe'])} / {fmt_num(check['sector_pe'])}", ""),
        LabelledValue(
            "EV/Sales",
            f"{fmt_num(check['implied_ev_sales'])} / {fmt_num(check['sector_ev_sales'])}",
            "",
        ),
    )


def detail_view(entry: CompanyEntry, ref: AnalysisRef) -> DetailView:
    analysis = ref.data["analysis"]
    dcf = analysis["dcf_result"]
    verdict = verdict_from_text(ref.data["verdict"])
    mos = analysis.get("margin_of_safety")
    tornado = tuple(
        TornadoBar(
            label=fmt_axis_label(SensitivityAxis(t["axis"])),
            low=float(t["intrinsic_low"]),
            high=float(t["intrinsic_high"]),
        )
        for t in analysis["tornado"]
        if t["intrinsic_low"] is not None and t["intrinsic_high"] is not None
    )
    return DetailView(
        ticker=ref.ticker,
        name=analysis["name"],
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
        flags=tuple(
            FlagView(f["name"], f["color"], f["reason"]) for f in analysis["narrative_flags"]
        ),
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
        dcf_totals=(
            LabelledValue("Enterprise value", fmt_money(dcf["enterprise_value"]), ""),
            LabelledValue("Net debt", fmt_money(analysis["financials"]["net_debt"]), ""),
            LabelledValue("Equity value", fmt_money(dcf["equity_value"]), ""),
        ),
        history=tuple(r.date for r in entry.history),
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
