"""Charts and glyphs for the web viewer (issue #92).

The value axis is inline SVG with its labels in HTML beside it, so the text
keeps its size when the axis scales to the pane. The scenario grid and the
drivers chart are HTML tables (real headers for screen readers, text that never
shrinks); only the bar inside each driver row is SVG. Colours only come from
CSS custom properties; the ``#hatch`` pattern lives in ``base.html``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from markupsafe import Markup, escape

from bot.web.views import (
    VERDICT_LABEL,
    VERDICT_TEXT,
    ScenarioGrid,
    TornadoBar,
    ValueLine,
    Verdict,
    flag_severity,
)

_INK = "var(--color-ink)"
_SOFT = "var(--color-muted)"
_INTRINSIC = "var(--color-accent-2)"
_VERDICT_COLOR = {
    Verdict.UNDERVALUED: "var(--color-under)",
    Verdict.FAIR: "var(--color-fair)",
    Verdict.OVERVALUED: "var(--color-over)",
    Verdict.NA: _SOFT,
}
_FLAG_VERDICT = {
    "green": Verdict.UNDERVALUED,
    "yellow": Verdict.FAIR,
    "red": Verdict.OVERVALUED,
}


def _n(value: float) -> str:
    """Plain decimal with at most one decimal place; never ``nan``/``inf``."""
    if not math.isfinite(value):
        value = 0.0
    text = f"{value:.1f}"
    return "0.0" if text == "-0.0" else text


def _scaler(lo: float, hi: float, left: float, right: float) -> Callable[[float], float]:
    span = hi - lo if math.isfinite(hi - lo) and hi != lo else 1.0

    def scale(value: float) -> float:
        if not math.isfinite(value):
            return left
        return left + (value - lo) / span * (right - left)

    return scale


def _line(
    x0: float, y0: float, x1: float, y1: float, color: str, width: float, extra: str = ""
) -> str:
    return (
        f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" stroke="{color}" '
        f'stroke-width="{_n(width)}" stroke-linecap="round"{extra}/>'
    )


def _num(value: float) -> str:
    return f"{value:,.2f}" if math.isfinite(value) else "n/a"


def _pct(x: float, width: float) -> str:
    return f"{x / width * 100:.2f}%"


def _anchor(x: float, width: float, margin: float = 60.0) -> str:
    """Label alignment that keeps it inside the chart near either edge."""
    if x < margin:
        return "start"
    return "end" if x > width - margin else "middle"


def value_line_svg(vl: ValueLine, *, mini: bool) -> Markup:
    """Price vs intrinsic value on one axis, with the fair and undervalued ticks.

    The full version is a figure: the SVG axis plus HTML labels positioned by
    percentage, so they keep their font size at every pane width. Its strokes
    are set in CSS pixels (``vector-effect``) so the axis scales without the
    lines thickening.
    """
    color = _VERDICT_COLOR[vl.verdict]
    if mini:
        width, height, left, right, mid = 120.0, 16.0, 4.0, 116.0, 8.0
        half, tick, sw = 3.0, 4.0, 1.2
        fixed = ""
    else:
        width, height, left, right, mid = 320.0, 24.0, 10.0, 310.0, 12.0
        half, tick, sw = 7.0, 6.0, 1.5
        fixed = ' vector-effect="non-scaling-stroke"'
    scale = _scaler(vl.axis_min, vl.axis_max, left, right)
    px, ix = scale(vl.price), scale(vl.intrinsic)
    fair_x, under_x = scale(vl.fair), scale(vl.undervalued)
    lo_x, hi_x = scale(vl.range_low), scale(vl.range_high)
    end_x = scale(vl.axis_max)

    parts: list[str] = []
    zone_w = max(end_x - under_x, 0.0)
    parts.append(
        f'<rect x="{_n(under_x)}" y="{_n(mid - half)}" width="{_n(zone_w)}" '
        f'height="{_n(half * 2)}" fill="{_VERDICT_COLOR[Verdict.UNDERVALUED]}" fill-opacity="0.18"/>'
    )
    band_w = max(hi_x - lo_x, 0.0)
    parts.append(
        f'<rect x="{_n(lo_x)}" y="{_n(mid - half * 0.6)}" width="{_n(band_w)}" '
        f'height="{_n(half * 1.2)}" fill="{_INTRINSIC}" fill-opacity="0.22"/>'
    )
    parts.append(_line(left, mid, right, mid, _INK, sw, fixed))
    for x in (fair_x, under_x):
        parts.append(_line(x, mid - tick, x, mid + tick, _SOFT, sw, fixed))
    parts.append(_line(px, mid, ix, mid, color, sw * 2.5, fixed))
    parts.append(
        _line(
            px, mid - half * 1.4, px, mid + half * 1.4, _INK, sw * 1.6, f' data-role="price"{fixed}'
        )
    )
    parts.append(
        f'<circle data-role="intrinsic" cx="{_n(ix)}" cy="{_n(mid)}" r="{_n(half * 0.55)}" '
        f'fill="{_INTRINSIC}" stroke="{_INK}" stroke-width="{_n(sw * 0.7)}"{fixed}/>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(width)} {_n(height)}" '
        f'class="value-line{" mini" if mini else ""}" role="img" '
        f'aria-label="{escape(VERDICT_TEXT[vl.verdict])}"><g>{"".join(parts)}</g></svg>'
    )
    if mini:
        return Markup(svg)

    def label(x: float, text: str, cls: str, anchor: str | None = None) -> str:
        return (
            f'<span class="axis-label {cls} at-{anchor or _anchor(x, width, 30.0)}" '
            f'style="left:{_pct(x, width)}">{escape(text)}</span>'
        )

    # the fair tick always sits left of the undervalued one: label them away from each other
    return Markup(
        '<figure class="value-axis">'
        '<div class="axis-row axis-ticks">'
        + label(fair_x, "fair 1.0\u00d7", "tick", "end")
        + label(under_x, "undervalued 1.3\u00d7", "tick", "start")
        + "</div>"
        + svg
        + '<div class="axis-row">'
        + label(px, f"price {_num(vl.price)}", "price")
        + "</div>"
        + '<div class="axis-row">'
        + label(ix, f"intrinsic {_num(vl.intrinsic)}", "intrinsic")
        + "</div></figure>"
    )


def _shape(verdict: Verdict) -> str:
    """Verdict glyph in a 16x16 box; the shape alone distinguishes verdicts."""
    color = _VERDICT_COLOR[verdict]
    if verdict is Verdict.UNDERVALUED:
        d = "M3 8.5 L6.5 12 L13 4"
        return (
            f'<path class="glyph" d="{d}" fill="none" stroke="{color}" stroke-width="3" '
            'stroke-linecap="round"/>'
            f'<path class="glyph" d="{d}" fill="none" stroke="{_INK}" stroke-width="0.8" '
            'stroke-linecap="round"/>'
        )
    if verdict is Verdict.FAIR:
        return (
            f'<circle class="glyph" cx="8" cy="8" r="5" fill="none" stroke="{color}" '
            'stroke-width="2"/>'
        )
    if verdict is Verdict.OVERVALUED:
        return (
            f'<rect class="glyph" x="2" y="3" width="8" height="10" fill="url(#hatch)" '
            f'stroke="{color}" stroke-width="1.6"/>'
            f'<path class="glyph" d="M10 10 L14 10 L14 14" fill="none" stroke="{color}" '
            'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return (
        f'<path class="glyph" d="M4 8 L12 8" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round"/>'
    )


def _mark(inner: str, title: str | None) -> Markup:
    if title is None:
        head = 'class="mark" aria-hidden="true" focusable="false">'
    else:
        head = f'class="mark" role="img"><title>{escape(title)}</title>'
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16" '
        f"{head}{inner}</svg>"
    )


def verdict_mark(v: Verdict | str, *, decorative: bool = False) -> Markup:
    """16x16 verdict glyph: check / open circle / hatched gate / dash.

    ``decorative`` drops the title for a glyph that sits beside its own label.
    """
    verdict = Verdict(v)
    return _mark(_shape(verdict), None if decorative else VERDICT_TEXT[verdict])


def flag_mark(color: str, name: str | None = None) -> Markup:
    """16x16 flag glyph named by severity: pass / warning / fail / not evaluated."""
    verdict = _FLAG_VERDICT.get(color)
    if verdict is None:
        inner = (
            f'<rect class="glyph" x="3" y="3" width="10" height="10" fill="none" stroke="{_SOFT}" '
            'stroke-width="1.4" stroke-dasharray="1.5 2.5" stroke-linecap="round"/>'
        )
    else:
        inner = _shape(verdict)
    title = flag_severity(color)
    if name:
        title = f"{title}: {name.replace('_', ' ')}"
    return _mark(inner, title)


def scenario_grid_table(grid: ScenarioGrid) -> Markup:
    """The scenario grid as a table: one axis down, one across, a verdict per cell."""
    head = [
        '<tr><td class="corner"></td>'
        f'<th scope="colgroup" colspan="{len(grid.col_labels)}" class="axis">'
        f"{escape(grid.axis_b)} →</th></tr>",
        f'<tr><th scope="col" class="axis">{escape(grid.axis_a)} ↓</th>'
        + "".join(f'<th scope="col">{escape(label)}</th>' for label in grid.col_labels)
        + "</tr>",
    ]
    body: list[str] = []
    for label, row in zip(grid.row_labels, grid.cells, strict=False):
        cells = []
        for verdict in row:
            if verdict is None:
                cells.append('<td class="cell cell-none"><span class="sr">no verdict</span></td>')
            else:
                cells.append(
                    f'<td class="cell cell-{verdict.value}">{verdict_mark(verdict)}'
                    f'<span class="sr">{escape(VERDICT_LABEL[verdict])}</span></td>'
                )
        body.append(f'<tr><th scope="row">{escape(label)}</th>{"".join(cells)}</tr>')
    return Markup(
        f'<table class="scenario-grid" aria-label="Scenarios {grid.matching}/{grid.total}">'
        f"<thead>{''.join(head)}</thead><tbody>{''.join(body)}</tbody></table>"
    )


def tornado_table(bars: Sequence[TornadoBar], *, price: float | None) -> Markup:
    """One row per input: its label, the low and high intrinsic value, and a bar between."""
    ordered = list(bars)
    values = [v for b in ordered for v in (b.low, b.high)]
    if price is not None:
        values.append(price)
    finite = [v for v in values if math.isfinite(v)] or [0.0, 1.0]
    lo, hi = min(finite), max(finite)
    pad = (hi - lo) * 0.03 or 1.0
    scale = _scaler(lo - pad, hi + pad, 0.0, 100.0)
    rows: list[str] = []
    for bar in ordered:
        x0, x1 = sorted((scale(bar.low), scale(bar.high)))
        lo_val, hi_val = sorted((bar.low, bar.high))
        track = (
            f'<rect x="{_n(x0)}" y="2" width="{_n(x1 - x0)}" height="8" fill="{_INTRINSIC}" '
            f'fill-opacity="0.35" stroke="{_INK}" stroke-width="0.6" vector-effect="non-scaling-stroke"/>'
        )
        if price is not None:
            px = scale(price)
            track += _line(
                px, 0, px, 12, _INK, 2.0, ' data-role="price" vector-effect="non-scaling-stroke"'
            )
        rows.append(
            f'<tr><th scope="row">{escape(bar.label)}</th>'
            f'<td class="num low">{_num(lo_val)}</td>'
            f'<td class="track"><svg viewBox="0 0 100 12" preserveAspectRatio="none" '
            f'aria-hidden="true" focusable="false">{track}</svg></td>'
            f'<td class="num high">{_num(hi_val)}</td></tr>'
        )
    price_head = f"price {_num(price)}" if price is not None else "range"
    return Markup(
        '<table class="tornado" aria-label="Drivers"><thead><tr>'
        '<th scope="col">Input</th><th scope="col" class="num">Low</th>'
        f'<th scope="col" class="track-head">{escape(price_head)}</th>'
        '<th scope="col" class="num">High</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
