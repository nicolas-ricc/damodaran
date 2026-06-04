"""Render a screen run's shortlist as Markdown + CSV (spec §6.1, §9.1).

A screen run produces a ranked shortlist (:class:`ScreenResult`); this module is
the one place that turns it into the two report artefacts of spec §9.1: the
Markdown table (the primary, human-readable truth) and a machine-readable CSV
with the *same* columns, so a spreadsheet / downstream tool can consume the
shortlist verbatim. Both carry every field an acceptance criterion asks for —
ticker, name, score, the four §6.5 sub-scores, sector, and the key value metrics.

The functions are pure: each takes a :class:`ScreenResult` and returns a string.
Writing the strings to ``reports/YYYY-MM-DD/screen/<preset>.{md,csv}`` is the
CLI's job.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from bot.screener.engine import ScreenedCompany, ScreenResult

_DASH = "—"

#: Shortlist columns, in display order. The CSV header and the Markdown table use
#: this exact list so the two artefacts stay column-for-column identical.
COLUMNS: tuple[str, ...] = (
    "rank",
    "ticker",
    "name",
    "sector",
    "score",
    "value_score",
    "quality_score",
    "growth_score",
    "margin_of_safety",
    "market_cap",
    "pe",
    "ev_ebitda",
    "pbv",
    "roe",
    "roic",
    "fcf_yield",
)


def _money(value: float | None) -> str:
    if value is None:
        return _DASH
    magnitude = abs(value)
    sign = "-" if value < 0 else ""
    if magnitude >= 1e9:
        return f"{sign}{magnitude / 1e9:,.2f}B"
    if magnitude >= 1e6:
        return f"{sign}{magnitude / 1e6:,.2f}M"
    return f"{sign}{magnitude:,.0f}"


def _num(value: float | None, digits: int = 2) -> str:
    return _DASH if value is None else f"{value:.{digits}f}"


def _pct(value: float | None) -> str:
    return _DASH if value is None else f"{value:.1%}"


def _display_cells(rank: int, company: ScreenedCompany) -> dict[str, str]:
    """Human-readable cell text for the Markdown table (one row per company)."""
    return {
        "rank": str(rank),
        "ticker": company.ticker,
        "name": company.name,
        "sector": company.sector or _DASH,
        "score": _num(company.score, 1),
        "value_score": _num(company.value_score, 3),
        "quality_score": _num(company.quality_score, 3),
        "growth_score": _num(company.growth_score, 3),
        "margin_of_safety": _num(company.margin_of_safety, 2),
        "market_cap": _money(company.market_cap),
        "pe": _num(company.pe),
        "ev_ebitda": _num(company.ev_ebitda),
        "pbv": _num(company.pbv),
        "roe": _pct(company.roe),
        "roic": _pct(company.roic),
        "fcf_yield": _pct(company.fcf_yield),
    }


def _csv_cells(rank: int, company: ScreenedCompany) -> dict[str, str]:
    """Raw machine-readable cell text for the CSV (full-precision, no scaling)."""

    def raw(value: float | None) -> str:
        return "" if value is None else repr(value)

    return {
        "rank": str(rank),
        "ticker": company.ticker,
        "name": company.name,
        "sector": company.sector or "",
        "score": raw(company.score),
        "value_score": raw(company.value_score),
        "quality_score": raw(company.quality_score),
        "growth_score": raw(company.growth_score),
        "margin_of_safety": raw(company.margin_of_safety),
        "market_cap": raw(company.market_cap),
        "pe": raw(company.pe),
        "ev_ebitda": raw(company.ev_ebitda),
        "pbv": raw(company.pbv),
        "roe": raw(company.roe),
        "roic": raw(company.roic),
        "fcf_yield": raw(company.fcf_yield),
    }


def render_markdown(result: ScreenResult, *, generated_on: date | None = None) -> str:
    """Render the shortlist as a Markdown report (the primary §9.1 artefact)."""
    stamp = (generated_on or date.today()).isoformat()
    lines = [
        f"# Screen — {result.preset}",
        "",
        f"Generated: {stamp}  ·  Screened {result.screened} companies  ·  "
        f"Shortlist {len(result.shortlist)}",
        "",
    ]
    if not result.shortlist:
        lines.append("_No companies cleared the screen._")
        lines.append("")
        return "\n".join(lines)

    header = "| " + " | ".join(COLUMNS) + " |"
    divider = "|" + "---|" * len(COLUMNS)
    lines.append(header)
    lines.append(divider)
    for rank, company in enumerate(result.shortlist, start=1):
        cells = _display_cells(rank, company)
        lines.append("| " + " | ".join(cells[col] for col in COLUMNS) + " |")
    lines.append("")
    return "\n".join(lines)


def render_csv(result: ScreenResult) -> str:
    """Render the shortlist as CSV with the same columns as the Markdown table."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    for rank, company in enumerate(result.shortlist, start=1):
        writer.writerow(_csv_cells(rank, company))
    return buffer.getvalue()
