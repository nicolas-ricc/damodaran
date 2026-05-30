"""Render an :class:`Analysis` as the §7.7 Markdown report via Jinja2.

The valuation pipeline (:mod:`bot.valuator.analysis`) produces a pure
:class:`Analysis` object; this module is the one place that turns it into the
Markdown report of spec §7.7. The layout lives in a bundled Jinja2 template
(``templates/analysis.md.j2``) so the prose is editable without touching code,
and the formatting filters here keep numbers readable (currency scaling,
percentages, ratios) without leaking ``None`` into the output.

:func:`render_analysis` is pure: it takes an :class:`Analysis` and returns a
string. Writing the report to disk is the CLI's job.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from bot.valuator.analysis import Analysis

_DASH = "—"


def _fmt_money(value: Any) -> str:
    """Scale a monetary figure to B/M/K with a thousands separator."""
    if value is None:
        return _DASH
    number = float(value)
    sign = "-" if number < 0 else ""
    magnitude = abs(number)
    if magnitude >= 1e9:
        return f"{sign}{magnitude / 1e9:,.2f}B"
    if magnitude >= 1e6:
        return f"{sign}{magnitude / 1e6:,.2f}M"
    if magnitude >= 1e3:
        return f"{sign}{magnitude / 1e3:,.2f}K"
    return f"{sign}{magnitude:,.2f}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return _DASH
    return f"{float(value):.1%}"


def _fmt_ratio(value: Any) -> str:
    if value is None:
        return _DASH
    return f"{float(value):.2f}x"


def _fmt_num(value: Any) -> str:
    if value is None:
        return _DASH
    return f"{float(value):.2f}"


def _fmt_mult(value: Any) -> str:
    """A grid multiplier like 0.8 rendered as a signed percentage delta."""
    if value is None:
        return _DASH
    delta = (float(value) - 1.0) * 100.0
    return f"{delta:+.0f}%"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    env = Environment(
        loader=PackageLoader("bot.reporting", "templates"),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["money"] = _fmt_money
    env.filters["pct"] = _fmt_pct
    env.filters["ratio"] = _fmt_ratio
    env.filters["num"] = _fmt_num
    env.filters["mult"] = _fmt_mult
    return env


def _grid_table(analysis: Analysis) -> list[str]:
    """Pre-render the 2-D sensitivity grid as Markdown table rows.

    Jinja's ``trim_blocks`` swallows the newline after a ``{% endfor %}``, which
    collapses inline-loop table rows onto one line; building the rows here keeps
    each Markdown row on its own line regardless of whitespace control.
    """
    grid = analysis.grid
    header_cells = " | ".join(_fmt_mult(m) for m in grid.col_multipliers)
    lines = [
        f"| {grid.axis_a} ↓ / {grid.axis_b} → | {header_cells} |",
        "|---|" + "---|" * len(grid.col_multipliers),
    ]
    for row_index, row in enumerate(grid.cells):
        row_label = _fmt_mult(grid.row_multipliers[row_index])
        cells = " | ".join(_fmt_ratio(cell.margin_of_safety) for cell in row)
        lines.append(f"| {row_label} | {cells} |")
    return lines


def _margin_verdict(margin_of_safety: float | None) -> str:
    """One-word read of the headline margin of safety (CONTEXT.md: MoS > 1)."""
    if margin_of_safety is None:
        return "n/a"
    if margin_of_safety >= 1.3:
        return "potentially undervalued"
    if margin_of_safety >= 1.0:
        return "around fair value"
    return "potentially overvalued"


def render_analysis(analysis: Analysis, *, generated_on: date | None = None) -> str:
    """Render ``analysis`` as the §7.7 Markdown report.

    Args:
        analysis: The completed analysis to render.
        generated_on: Date stamped in the report header; defaults to today.

    Returns:
        The full Markdown report as a string.
    """
    template = _environment().get_template("analysis.md.j2")
    stamp = (generated_on or date.today()).isoformat()
    return template.render(
        a=analysis,
        generated_at=stamp,
        verdict=_margin_verdict(analysis.margin_of_safety),
        grid_table=_grid_table(analysis),
    )
