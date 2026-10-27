"""Charts and glyphs of the web viewer (issue #92)."""

from __future__ import annotations

import re

import pytest

from bot.web.svg import (
    flag_mark,
    scenario_grid_table,
    tornado_table,
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


def _label_lefts(html: str) -> dict[str, float]:
    return {
        m.group(2): float(m.group(1))
        for m in re.finditer(r'style="left:([\d.]+)%">([^<]*)</span>', html)
    }


def test_value_line_is_deterministic() -> None:
    assert value_line_svg(_vl(), mini=False) == value_line_svg(_vl(), mini=False)


def test_intrinsic_right_of_price_when_higher() -> None:
    svg = str(value_line_svg(_vl(100.0, 150.0), mini=False))
    assert _x(svg, "intrinsic", "cx") > _x(svg, "price", "x1")


def test_mini_has_no_text() -> None:
    svg = str(value_line_svg(_vl(), mini=True))
    assert "<text" not in svg
    assert "<span" not in svg
    assert svg.startswith("<svg")


def test_full_value_line_labels_are_html_outside_the_svg() -> None:
    html = str(value_line_svg(_vl(), mini=False))
    assert "<text" not in html
    lefts = _label_lefts(html)
    assert set(lefts) == {
        "fair 1.0\u00d7",
        "undervalued 1.3\u00d7",
        "price 100.00",
        "intrinsic 150.00",
    }
    assert all(0 <= left <= 100 for left in lefts.values())
    assert lefts["price 100.00"] < lefts["intrinsic 150.00"]


def test_charts_carry_no_filter() -> None:
    for markup in (
        value_line_svg(_vl(), mini=False),
        scenario_grid_table(_grid()),
        tornado_table([TornadoBar("a", 1.0, 2.0)], price=1.5),
    ):
        assert "filter=" not in str(markup)


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
    svg = str(value_line_svg(vl, mini=False))
    assert _x(svg, "intrinsic", "cx") < _x(svg, "price", "x1")
    assert "nan" not in svg.lower()


def _bars(label: str = "cost_of_equity") -> list[TornadoBar]:
    return [TornadoBar(label=label, low=100.0, high=220.0), TornadoBar("tax_rate", 140.0, 150.0)]


def test_labels_are_escaped() -> None:
    assert "a&lt;b&amp;c" in str(tornado_table(_bars("a<b&c"), price=100.0))
    assert "a<b" not in str(tornado_table(_bars("a<b&c"), price=100.0))
    assert "x&lt;y" in str(scenario_grid_table(_grid("x<y")))


@pytest.mark.parametrize("verdict", list(Verdict))
def test_verdict_marks_have_a_title_and_no_filter(verdict: Verdict) -> None:
    svg = str(verdict_mark(verdict))
    assert "<title>" in svg
    assert "filter=" not in svg
    assert verdict_mark(verdict.value) == svg
    plain = str(verdict_mark(verdict, decorative=True))
    assert "<title>" not in plain and 'aria-hidden="true"' in plain


@pytest.mark.parametrize(
    ("color", "severity"),
    [("red", "fail"), ("yellow", "warning"), ("green", "pass"), ("unknown", "not evaluated")],
)
def test_flag_marks_are_titled_by_severity_not_colour(color: str, severity: str) -> None:
    svg = str(flag_mark(color))
    assert f"<title>{severity}</title>" in svg
    assert f"<title>{color}</title>" not in svg
    assert f"<title>{severity}: story margin</title>" in str(flag_mark(color, "story_margin"))


def test_marks_differ_in_shape_not_only_colour() -> None:
    shapes = {
        re.sub(r"var\(--[a-z0-9-]+\)|<title>.*?</title>", "", str(verdict_mark(v))) for v in Verdict
    }
    assert len(shapes) == len(Verdict)
    flags = {
        re.sub(r"var\(--[a-z0-9-]+\)|<title>.*?</title>", "", str(flag_mark(c)))
        for c in ("red", "yellow", "green", "unknown")
    }
    assert len(flags) == 4


def test_no_hardcoded_colours() -> None:
    outputs = [
        value_line_svg(_vl(), mini=False),
        value_line_svg(_vl(), mini=True),
        scenario_grid_table(_grid()),
        tornado_table(_bars(), price=100.0),
        *(verdict_mark(v) for v in Verdict),
        *(flag_mark(c) for c in ("red", "yellow", "green", "unknown")),
    ]
    for svg in map(str, outputs):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", svg.replace("url(#", "url("))
        assert "oklch(" not in svg
        assert "rgb(" not in svg


def test_scenario_grid_is_a_table_with_headers_and_a_verdict_per_cell() -> None:
    html = str(scenario_grid_table(_grid()))
    assert 'aria-label="Scenarios 10/24"' in html
    assert html.count('<th scope="row">') == 5
    assert html.count('<th scope="col">') == 5
    assert '<th scope="col" class="axis">cost_of_equity ↓</th>' in html
    assert html.count('class="cell cell-undervalued"') == 10
    assert html.count('class="cell cell-fair"') == 14
    assert html.count("cell-none") == 1
    assert "operating_margin (yr 1)" in html and "cost_of_equity" in html


def test_tornado_keeps_input_order_and_sorts_each_bar() -> None:
    html = str(
        tornado_table([TornadoBar("narrow", 2.0, 1.0), TornadoBar("wide", 0.0, 9.0)], price=None)
    )
    assert html.index("narrow") < html.index("wide")
    row = html[html.index("narrow") : html.index("wide")]
    assert row.index("1.00") < row.index("2.00")
