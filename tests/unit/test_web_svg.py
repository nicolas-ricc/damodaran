"""Hand-drawn SVG for the web viewer (issue #92)."""

from __future__ import annotations

import re

import pytest

from bot.web.svg import (
    flag_mark,
    jitter_path,
    scenario_grid_svg,
    seed_of,
    tornado_svg,
    value_line_svg,
    verdict_mark,
)
from bot.web.views import ScenarioGrid, TornadoBar, ValueLine, Verdict


def _vl(price: float = 100.0, intrinsic: float = 150.0) -> ValueLine:
    low, high = min(intrinsic, 120.0), max(intrinsic, 180.0)
    lo = min(price, low)
    hi = max(price * 1.3, high)
    pad = (hi - lo) * 0.05
    return ValueLine(
        price=price,
        intrinsic=intrinsic,
        range_low=low,
        range_high=high,
        axis_min=lo - pad,
        axis_max=hi + pad,
        verdict=Verdict.UNDERVALUED if intrinsic >= price * 1.3 else Verdict.OVERVALUED,
    )


def _grid(axis_a: str = "cost_of_equity") -> ScenarioGrid:
    v = Verdict
    cells = tuple(
        tuple(None if (r, c) == (0, 0) else (v.UNDERVALUED if c > 2 else v.FAIR) for c in range(5))
        for r in range(5)
    )
    labels = ("-20%", "-10%", "+0%", "+10%", "+20%")
    return ScenarioGrid(
        axis_a=axis_a,
        axis_b="operating_margin (yr 1)",
        row_labels=labels,
        col_labels=labels,
        cells=cells,
        matching=10,
        total=24,
    )


def _x(svg: str, role: str, attr: str) -> float:
    match = re.search(rf'<[^>]*data-role="{role}"[^>]*\b{attr}="(-?[\d.]+)"', svg) or re.search(
        rf'<[^>]*\b{attr}="(-?[\d.]+)"[^>]*data-role="{role}"', svg
    )
    assert match, f"no {role} with {attr}"
    return float(match.group(1))


def _filtered_groups(svg: str) -> list[str]:
    groups = []
    for start in [m.start() for m in re.finditer(r"<g [^>]*filter=", svg)]:
        depth, i = 0, start
        while True:
            open_at = svg.find("<g", i + 1)
            close_at = svg.find("</g>", i + 1)
            if open_at != -1 and open_at < close_at:
                depth += 1
                i = open_at
            elif depth:
                depth -= 1
                i = close_at
            else:
                groups.append(svg[start : close_at + 4])
                break
    return groups


def test_seed_is_stable() -> None:
    assert seed_of("AAPL") == seed_of("AAPL")
    assert seed_of("AAPL") != seed_of("MSFT")


def test_jitter_is_deterministic() -> None:
    points = [(0.0, 0.0), (100.0, 0.0)]
    assert jitter_path(points, 7) == jitter_path(points, 7)
    assert jitter_path(points, 7) != jitter_path(points, 8)
    assert jitter_path(points, 7).startswith("M")


def test_value_line_is_deterministic_per_seed() -> None:
    assert value_line_svg(_vl(), mini=False, seed=3) == value_line_svg(_vl(), mini=False, seed=3)
    assert value_line_svg(_vl(), mini=False, seed=3) != value_line_svg(_vl(), mini=False, seed=4)


def test_intrinsic_right_of_price_when_higher() -> None:
    svg = str(value_line_svg(_vl(100.0, 150.0), mini=False, seed=1))
    assert _x(svg, "intrinsic", "cx") > _x(svg, "price", "x1")


def test_mini_has_no_filter_and_no_text() -> None:
    svg = str(value_line_svg(_vl(), mini=True, seed=1))
    assert "filter=" not in svg
    assert "<text" not in svg


def test_detail_wobbles_groups_but_never_text() -> None:
    svg = str(value_line_svg(_vl(), mini=False, seed=1))
    assert 'filter="url(#wobble-' in svg
    assert "<text" in svg
    for group in _filtered_groups(svg):
        assert "<text" not in group
    for drawn in (scenario_grid_svg(_grid(), seed=2), tornado_svg(_bars(), price=100.0, seed=3)):
        assert 'filter="url(#wobble-' in str(drawn)
        for group in _filtered_groups(str(drawn)):
            assert "<text" not in group


def test_negative_intrinsic_renders() -> None:
    vl = ValueLine(
        price=50.0,
        intrinsic=-12.0,
        range_low=-20.0,
        range_high=-5.0,
        axis_min=-24.0,
        axis_max=70.0,
        verdict=Verdict.OVERVALUED,
    )
    svg = str(value_line_svg(vl, mini=False, seed=1))
    assert _x(svg, "intrinsic", "cx") < _x(svg, "price", "x1")
    assert "nan" not in svg.lower()


def _bars(label: str = "cost_of_equity") -> list[TornadoBar]:
    return [TornadoBar(label=label, low=100.0, high=220.0), TornadoBar("tax_rate", 140.0, 150.0)]


def test_labels_are_escaped() -> None:
    assert "a&lt;b&amp;c" in str(tornado_svg(_bars("a<b&c"), price=100.0, seed=1))
    assert "a<b" not in str(tornado_svg(_bars("a<b&c"), price=100.0, seed=1))
    assert "x&lt;y" in str(scenario_grid_svg(_grid("x<y"), seed=1))


@pytest.mark.parametrize("verdict", list(Verdict))
def test_verdict_marks_have_a_title_and_no_filter(verdict: Verdict) -> None:
    svg = str(verdict_mark(verdict))
    assert "<title>" in svg
    assert "filter=" not in svg


@pytest.mark.parametrize("color", ["red", "yellow", "green", "unknown"])
def test_flag_marks_have_a_title(color: str) -> None:
    svg = str(flag_mark(color))
    assert f"<title>{color}</title>" in svg
    assert "filter=" not in svg


def test_marks_differ_in_shape_not_only_colour() -> None:
    shapes = {
        re.sub(r"var\(--[a-z-]+\)|<title>.*?</title>", "", str(verdict_mark(v))) for v in Verdict
    }
    assert len(shapes) == len(Verdict)
    flags = {
        re.sub(r"var\(--[a-z-]+\)|<title>.*?</title>", "", str(flag_mark(c)))
        for c in ("red", "yellow", "green", "unknown")
    }
    assert len(flags) == 4


def test_no_hardcoded_colours() -> None:
    outputs = [
        value_line_svg(_vl(), mini=False, seed=1),
        value_line_svg(_vl(), mini=True, seed=1),
        scenario_grid_svg(_grid(), seed=1),
        tornado_svg(_bars(), price=100.0, seed=1),
        *(verdict_mark(v) for v in Verdict),
        *(flag_mark(c) for c in ("red", "yellow", "green", "unknown")),
    ]
    for svg in map(str, outputs):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", svg.replace("url(#", "url("))
        assert "oklch(" not in svg
        assert "rgb(" not in svg


def _texts(svg: str) -> list[tuple[float, float]]:
    return [
        (float(m.group(1)), float(m.group(2)))
        for m in re.finditer(r'<text x="(-?[\d.]+)" y="(-?[\d.]+)"', svg)
    ]


def test_tornado_labels_stay_in_viewbox_and_clear_of_bar_labels() -> None:
    bars = [TornadoBar("discount rate", 80.0, 140.0), TornadoBar("growth", 95.0, 120.0)]
    svg = str(tornado_svg(bars, price=100.0, seed=1))
    assert all(0 <= x <= 640 for x, _ in _texts(svg))
    label_x = _texts(svg)[0][0]
    low_x = _texts(svg)[1][0]
    assert low_x > label_x


def test_tornado_keeps_input_order() -> None:
    svg = str(
        tornado_svg(
            [TornadoBar("narrow", 1.0, 2.0), TornadoBar("wide", 0.0, 9.0)], price=None, seed=1
        )
    )
    assert svg.index("narrow") < svg.index("wide")


def test_value_line_labels_stay_inside_viewbox() -> None:
    for vl in (_vl(100.0, 1000.0), _vl(100.0, 150.0)):
        svg = str(value_line_svg(vl, mini=False, seed=1))
        assert all(0 <= x <= 640 and 0 <= y < 96 for x, y in _texts(svg))
