"""Hand-drawn SVG for the web viewer (issue #92).

Charts are built from jittered paths so they look pencilled; the wobble filters
and the ``#hatch`` pattern live in ``base.html``. Colours only come from CSS
custom properties, and text is never placed inside a filtered group.
"""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Callable, Sequence
from itertools import pairwise

from markupsafe import Markup, escape

from bot.web.views import VERDICT_TEXT, ScenarioGrid, TornadoBar, ValueLine, Verdict

_INK = "var(--ink)"
_SOFT = "var(--ink-soft)"
_INTRINSIC = "var(--p-valua)"
_VERDICT_COLOR = {
    Verdict.UNDERVALUED: "var(--p-selecciona)",
    Verdict.FAIR: "var(--p-datos)",
    Verdict.OVERVALUED: "var(--p-elimina)",
    Verdict.NA: _SOFT,
}
_FLAG_VERDICT = {
    "green": Verdict.UNDERVALUED,
    "yellow": Verdict.FAIR,
    "red": Verdict.OVERVALUED,
}
_STEP = 8.0


def seed_of(key: str) -> int:
    """Stable seed from a string (``hash()`` is randomised per process)."""
    return zlib.crc32(key.encode())


def _n(value: float) -> str:
    """Plain decimal with at most one decimal place; never ``nan``/``inf``."""
    if not math.isfinite(value):
        value = 0.0
    text = f"{value:.1f}"
    return "0.0" if text == "-0.0" else text


def jitter_path(points: Sequence[tuple[float, float]], seed: int, amp: float = 0.6) -> str:
    """SVG ``d`` string through ``points`` with a perpendicular wobble.

    Each segment is subdivided into ~8px steps; interior points are offset
    perpendicular to the segment, endpoints stay fixed.
    """
    rng = random.Random(seed)
    out: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in pairwise(points):
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, round(length / _STEP))
        nx, ny = ((y0 - y1) / length, (x1 - x0) / length) if length else (0.0, 0.0)
        if not out:
            out.append((x0, y0))
        for i in range(1, steps + 1):
            t = i / steps
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if i < steps:
                off = rng.uniform(-amp, amp)
                x, y = x + nx * off, y + ny * off
            out.append((x, y))
    if not out and points:
        out.append(points[0])
    return " ".join(f"{'M' if i == 0 else 'L'}{_n(x)} {_n(y)}" for i, (x, y) in enumerate(out))


def _wobble(seed: int) -> str:
    return f"url(#wobble-{seed % 4 + 1})"


def _stroke(
    points: Sequence[tuple[float, float]], seed: int, color: str, width: float, extra: str = ""
) -> str:
    return (
        f'<path d="{jitter_path(points, seed)}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round"{extra}/>'
    )


def _scaler(lo: float, hi: float, left: float, right: float) -> Callable[[float], float]:
    span = hi - lo if math.isfinite(hi - lo) and hi != lo else 1.0

    def scale(value: float) -> float:
        if not math.isfinite(value):
            return left
        return left + (value - lo) / span * (right - left)

    return scale


def _text(x: float, y: float, content: str, anchor: str = "middle", cls: str = "lbl") -> str:
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" text-anchor="{anchor}" class="{cls}" '
        f'fill="{_INK}">{escape(content)}</text>'
    )


def _anchor(x: float, width: float, margin: float = 60.0) -> str:
    """Text anchor that keeps a label inside the viewBox near either edge."""
    if x < margin:
        return "start"
    return "end" if x > width - margin else "middle"


def _num(value: float) -> str:
    return f"{value:,.2f}" if math.isfinite(value) else "n/a"


def value_line_svg(vl: ValueLine, *, mini: bool, seed: int) -> Markup:
    """Price vs intrinsic value on one axis, with the 1.0x / 1.3x ticks."""
    color = _VERDICT_COLOR[vl.verdict]
    if mini:
        width, height, left, right, mid = 120.0, 16.0, 4.0, 116.0, 8.0
    else:
        width, height, left, right, mid = 640.0, 96.0, 20.0, 620.0, 48.0
    scale = _scaler(vl.axis_min, vl.axis_max, left, right)
    px, ix = scale(vl.price), scale(vl.intrinsic)
    fair_x, under_x = scale(vl.fair), scale(vl.undervalued)
    lo_x, hi_x = scale(vl.range_low), scale(vl.range_high)
    end_x = scale(vl.axis_max)
    half = 3.0 if mini else 12.0
    tick = 4.0 if mini else 10.0
    sw = 1.2 if mini else 2.0

    parts: list[str] = []
    zone_w = max(end_x - under_x, 0.0)
    parts.append(
        f'<rect x="{_n(under_x)}" y="{_n(mid - half)}" width="{_n(zone_w)}" '
        f'height="{_n(half * 2)}" fill="var(--p-selecciona)" fill-opacity="0.18"/>'
    )
    band_w = max(hi_x - lo_x, 0.0)
    parts.append(
        f'<rect x="{_n(lo_x)}" y="{_n(mid - half * 0.6)}" width="{_n(band_w)}" '
        f'height="{_n(half * 1.2)}" fill="{_INTRINSIC}" fill-opacity="0.22"/>'
    )
    parts.append(_stroke([(left, mid), (right, mid)], seed, _INK, sw))
    for i, x in enumerate((fair_x, under_x)):
        parts.append(_stroke([(x, mid - tick), (x, mid + tick)], seed + 11 + i, _SOFT, sw))
    parts.append(_stroke([(px, mid), (ix, mid)], seed + 5, color, sw * 2))
    parts.append(
        f'<line data-role="price" x1="{_n(px)}" y1="{_n(mid - half * 1.4)}" x2="{_n(px)}" '
        f'y2="{_n(mid + half * 1.4)}" stroke="{_INK}" stroke-width="{sw * 1.5}" '
        'stroke-linecap="round"/>'
    )
    parts.append(
        f'<circle data-role="intrinsic" cx="{_n(ix)}" cy="{_n(mid)}" r="{_n(half * 0.5)}" '
        f'fill="{_INTRINSIC}" stroke="{_INK}" stroke-width="{sw * 0.6}"/>'
    )
    group = "<g>" if mini else f'<g filter="{_wobble(seed)}">'
    body = f"{group}{''.join(parts)}</g>"
    if not mini:
        body += (
            _text(fair_x, mid - 20, "1.0\u00d7", _anchor(fair_x, width))
            + _text(under_x, mid - 32, "1.3\u00d7", _anchor(under_x, width))
            + _text(px, mid + 30, f"price {_num(vl.price)}", _anchor(px, width))
            + _text(ix, mid + 42, f"intrinsic {_num(vl.intrinsic)}", _anchor(ix, width))
        )
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(width)} {_n(height)}" '
        f'class="value-line{" mini" if mini else ""}" role="img" '
        f'aria-label="{escape(VERDICT_TEXT[vl.verdict])}">{body}</svg>'
    )


def _shape(verdict: Verdict) -> str:
    """Verdict glyph in a 16x16 box; the shape alone distinguishes verdicts."""
    color = _VERDICT_COLOR[verdict]
    if verdict is Verdict.UNDERVALUED:
        d = "M3 8.5 L6.5 12 L13 4"
        return (
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="{_INK}" stroke-width="0.8" stroke-linecap="round"/>'
        )
    if verdict is Verdict.FAIR:
        return f'<circle cx="8" cy="8" r="5" fill="none" stroke="{color}" stroke-width="2"/>'
    if verdict is Verdict.OVERVALUED:
        return (
            f'<rect x="2" y="3" width="8" height="10" fill="url(#hatch)" stroke="{color}" '
            'stroke-width="1.6"/>'
            f'<path d="M10 10 L14 10 L14 14" fill="none" stroke="{color}" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return f'<path d="M4 8 L12 8" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'


def _mark(inner: str, title: str) -> Markup:
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16" '
        f'class="mark" role="img"><title>{escape(title)}</title>{inner}</svg>'
    )


def verdict_mark(v: Verdict) -> Markup:
    """16x16 verdict glyph: check / open circle / hatched gate / dash."""
    return _mark(_shape(v), VERDICT_TEXT[v])


def flag_mark(color: str) -> Markup:
    """16x16 flag glyph: hatched gate / open circle / check / dotted outline."""
    verdict = _FLAG_VERDICT.get(color)
    if verdict is None:
        inner = (
            f'<rect x="3" y="3" width="10" height="10" fill="none" stroke="{_SOFT}" '
            'stroke-width="1.4" stroke-dasharray="1.5 2.5" stroke-linecap="round"/>'
        )
    else:
        inner = _shape(verdict)
    return _mark(inner, color)


def scenario_grid_svg(grid: ScenarioGrid, *, seed: int) -> Markup:
    """5x5 scenario grid: pigment fill plus the verdict shape in each cell."""
    cell, left, top = 44.0, 84.0, 44.0
    rows, cols = len(grid.cells), max((len(r) for r in grid.cells), default=0)
    width, height = left + cell * cols + 8, top + cell * rows + 24
    drawn: list[str] = []
    labels: list[str] = [
        _text(left + cell * cols / 2, 14, grid.axis_b, cls="axis"),
        _text(6, top + cell * rows + 18, grid.axis_a, anchor="start", cls="axis"),
    ]
    for r, row in enumerate(grid.cells):
        for c, verdict in enumerate(row):
            x, y = left + c * cell, top + r * cell
            outline = [(x + 2, y + 2), (x + cell - 2, y + 2), (x + cell - 2, y + cell - 2)]
            outline += [(x + 2, y + cell - 2), (x + 2, y + 2)]
            if verdict is None:
                drawn.append(
                    _stroke(outline, seed + r * 7 + c, _SOFT, 1.0, ' stroke-dasharray="1 4"')
                )
                continue
            drawn.append(
                f'<rect x="{_n(x + 2)}" y="{_n(y + 2)}" width="{_n(cell - 4)}" '
                f'height="{_n(cell - 4)}" fill="{_VERDICT_COLOR[verdict]}" fill-opacity="0.28"/>'
            )
            drawn.append(_stroke(outline, seed + r * 7 + c, _INK, 1.0))
            drawn.append(
                f'<g transform="translate({_n(x + cell / 2 - 12)} {_n(y + cell / 2 - 12)}) '
                f'scale(1.5)">{_shape(verdict)}</g>'
            )
    for i, label in enumerate(grid.col_labels):
        labels.append(_text(left + i * cell + cell / 2, top - 6, label))
    for i, label in enumerate(grid.row_labels):
        labels.append(_text(left - 6, top + i * cell + cell / 2 + 4, label, anchor="end"))
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(width)} {_n(height)}" '
        f'class="scenario-grid" role="img"><g filter="{_wobble(seed)}">{"".join(drawn)}</g>'
        f"{''.join(labels)}</svg>"
    )


def tornado_svg(bars: Sequence[TornadoBar], *, price: float | None, seed: int) -> Markup:
    """One horizontal low-high bar per input (input order) on a shared axis."""
    ordered = list(bars)
    values = [v for b in ordered for v in (b.low, b.high)]
    finite = [v for v in values if math.isfinite(v)] or [0.0, 1.0]
    if price is not None and not min(finite) <= price <= max(finite):
        price = None
    left, right, row_h, top = 250.0, 580.0, 28.0, 8.0
    scale = _scaler(min(finite), max(finite), left, right)
    height = top + row_h * len(ordered) + 8
    drawn: list[str] = []
    labels: list[str] = []
    for i, bar in enumerate(ordered):
        y = top + i * row_h + row_h / 2
        x0, x1 = sorted((scale(bar.low), scale(bar.high)))
        h = row_h * 0.5
        drawn.append(
            f'<rect x="{_n(x0)}" y="{_n(y - h / 2)}" width="{_n(x1 - x0)}" height="{_n(h)}" '
            f'fill="{_INTRINSIC}" fill-opacity="0.35"/>'
        )
        outline = [
            (x0, y - h / 2),
            (x1, y - h / 2),
            (x1, y + h / 2),
            (x0, y + h / 2),
            (x0, y - h / 2),
        ]
        drawn.append(_stroke(outline, seed + i, _INK, 1.2))
        labels.append(_text(196, y + 4, bar.label, anchor="end"))
        lo_val, hi_val = sorted((bar.low, bar.high))
        labels.append(_text(x0 - 4, y + 4, _num(lo_val), anchor="end", cls="val"))
        labels.append(_text(x1 + 4, y + 4, _num(hi_val), anchor="start", cls="val"))
    if price is not None:
        px = scale(price)
        drawn.append(
            _stroke([(px, 2.0), (px, height - 2)], seed + 99, _INK, 2.0, ' data-role="price"')
        )
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 {_n(height)}" '
        f'class="tornado" role="img"><g filter="{_wobble(seed)}">{"".join(drawn)}</g>'
        f"{''.join(labels)}</svg>"
    )
