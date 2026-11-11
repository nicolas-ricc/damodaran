"""View-models for the web viewer (issue #92)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest

from bot.web.index import AnalysisRef, CompanyEntry
from bot.web.views import (
    FILTERS,
    VERDICT_TEXT,
    FlagView,
    Verdict,
    detail_view,
    filter_sort,
    row_view,
    scenario_grid,
    value_line,
    verdict_from_text,
    verdict_of,
)
from tests.web_sidecars import make_sidecar, real_sidecar


def _ref(payload: dict[str, Any], day: date = date(2026, 10, 1)) -> AnalysisRef:
    return AnalysisRef(ticker=payload["analysis"]["ticker"], date=day, data=payload)


def _entry(*refs: AnalysisRef) -> CompanyEntry:
    return CompanyEntry(ticker=refs[0].ticker, history=refs)


@pytest.mark.parametrize(
    ("mos", "verdict"),
    [
        (1.3, Verdict.UNDERVALUED),
        (1.0, Verdict.FAIR),
        (0.99, Verdict.OVERVALUED),
        (-0.2, Verdict.OVERVALUED),
        (None, Verdict.NA),
    ],
)
def test_verdict_of_thresholds(mos: float | None, verdict: Verdict) -> None:
    assert verdict_of(mos) == verdict


def test_verdict_text_round_trips() -> None:
    for verdict, text in VERDICT_TEXT.items():
        assert verdict_from_text(text) == verdict
    assert VERDICT_TEXT[Verdict.UNDERVALUED] == "potentially undervalued"
    assert VERDICT_TEXT[Verdict.NA] == "n/a"
    assert FILTERS == ("all", "undervalued", "fair", "overvalued", "na")


def test_row_uses_the_stored_verdict() -> None:
    row = row_view(_ref(make_sidecar("AAA", mos=1.5)))
    assert row.verdict == Verdict.UNDERVALUED
    assert row.mos == pytest.approx(1.5)
    assert row.value_line is not None
    assert row.story == "mature-stable"


def test_row_flags_are_only_red_and_yellow() -> None:
    payload = make_sidecar("AAA", red_flag=True)
    # seeded flags: green, green, unknown, green, unknown; the first turned red. The
    # terminal-value share is green (68% of EV over 10 years), so turn it yellow here.
    payload["analysis"]["narrative_flags"][3]["color"] = "yellow"
    row = row_view(_ref(payload))
    assert [f.color for f in row.flags] == ["red", "yellow"]
    assert [f.severity for f in row.flags] == ["fail", "warning"]


def test_no_price_means_na_without_value_line_or_grid() -> None:
    payload = make_sidecar("CCC", mos=None)
    ref = _ref(payload)
    row = row_view(ref)
    detail = detail_view(_entry(ref), ref)
    assert row.verdict == Verdict.NA
    assert row.value_line is None
    assert detail.value_line is None
    assert detail.grid is None
    assert detail.mos == "n/a"
    assert value_line(payload["analysis"]) is None
    assert scenario_grid(payload["analysis"]) is None


def test_value_line_positions() -> None:
    analysis = make_sidecar("AAA", mos=1.5)["analysis"]
    vl = value_line(analysis)
    assert vl is not None
    intrinsic = analysis["dcf_result"]["intrinsic_value"]
    assert vl.price == pytest.approx(intrinsic / 1.5)
    assert vl.intrinsic == pytest.approx(intrinsic)
    assert vl.fair == pytest.approx(vl.price)
    assert vl.undervalued == pytest.approx(vl.price * 1.3)
    extremes = [
        v
        for t in analysis["tornado"]
        for v in (t["intrinsic_low"], t["intrinsic_high"])
        if v is not None
    ]
    assert vl.range_low == pytest.approx(min([*extremes, intrinsic]))
    assert vl.range_high == pytest.approx(max([*extremes, intrinsic]))
    assert vl.axis_min < min(vl.price, vl.range_low)
    assert vl.axis_max > max(vl.undervalued, vl.range_high)
    assert vl.verdict == Verdict.UNDERVALUED


def test_value_line_without_tornado_extremes_collapses_to_intrinsic() -> None:
    payload = make_sidecar("AAA", mos=1.1)
    for entry in payload["analysis"]["tornado"]:
        entry["intrinsic_low"] = None
        entry["intrinsic_high"] = None
    vl = value_line(payload["analysis"])
    assert vl is not None
    assert vl.range_low == vl.range_high == pytest.approx(vl.intrinsic)
    ref = _ref(payload)
    assert detail_view(_entry(ref), ref).tornado == ()


def test_negative_intrinsic_is_overvalued_and_axis_goes_below_zero() -> None:
    payload = make_sidecar("NEG", mos=1.0)
    analysis = payload["analysis"]
    analysis["dcf_result"]["intrinsic_value"] = -12.0
    analysis["current_price"] = 50.0
    analysis["margin_of_safety"] = -12.0 / 50.0
    payload["verdict"] = "potentially overvalued"
    vl = value_line(analysis)
    assert vl is not None
    assert vl.verdict == Verdict.OVERVALUED
    assert vl.axis_min < -12.0
    ref = _ref(payload)
    assert detail_view(_entry(ref), ref).verdict == Verdict.OVERVALUED


def test_scenario_grid_counts_matching_cells_and_skips_none() -> None:
    payload = make_sidecar("AAA", mos=0.95)
    payload["verdict"] = "potentially overvalued"
    cells = payload["analysis"]["grid"]["cells"]
    cells[0][0]["margin_of_safety"] = None
    cells[4][4]["margin_of_safety"] = None
    grid = scenario_grid(payload["analysis"])
    assert grid is not None
    assert grid.total == 23
    expected = sum(
        1
        for row in cells
        for cell in row
        if cell["margin_of_safety"] is not None
        and verdict_of(cell["margin_of_safety"]) == Verdict.OVERVALUED
    )
    assert grid.matching == expected
    assert grid.cells[0][0] is None
    assert len(grid.row_labels) == len(grid.col_labels) == 5


def test_detail_from_a_real_analysis() -> None:
    payload = real_sidecar()
    older = _ref(payload, date(2026, 9, 1))
    latest = _ref(payload)
    detail = detail_view(_entry(latest, older), latest)
    assert detail.ticker == "AAPL"
    assert detail.name == "Apple Inc"
    assert detail.history == (date(2026, 10, 1), date(2026, 9, 1))
    growth = payload["analysis"]["assumptions"]["revenue_growth"]["value"]
    assert [a.label for a in detail.assumptions] == [
        f"Revenue growth (yr 1 → yr {len(growth)})",
        "Operating margin",
        "Sales-to-capital",
        "Cost of equity",
        "Pre-tax cost of debt",
        "Equity weight",
        "Debt weight",
        "Terminal growth",
        "Tax rate",
        "Probability of bankruptcy",
    ]
    assert all(a.source for a in detail.assumptions)
    assert detail.assumptions[0].value == f"{growth[0]:.1%} → {growth[-1]:.1%}"
    # story_margin only comes out for a high-growth story (#265); this one is mature.
    assert [f.color for f in detail.flags] == ["green", "unknown", "green", "unknown"]
    assert [s.label for s in detail.sanity] == ["P/E implied (DCF)", "P/E market", "EV/Sales"]
    assert len(detail.dcf_rows) == len(payload["analysis"]["dcf_result"]["projections"])
    assert [t.label for t in detail.dcf_totals] == [
        f"Present value of FCFF, years 1-{len(payload['analysis']['dcf_result']['projections'])}",
        "Terminal value, discounted",
        "Enterprise value",
        "Net debt",
        "Equity value",
        "Diluted shares",
        "Intrinsic value per share",
    ]
    assert "sector default" in " ".join(a.source for a in detail.assumptions)
    assert 0 <= detail.defaulted <= len(detail.assumptions)
    assert "reads as undervalued" in detail.mos_note
    assert detail.tornado
    assert detail.grid is not None


def test_sanity_of_a_pre_219_sidecar() -> None:
    # Before #219 there was no market_pe and implied_pe held the market P/E.
    payload = real_sidecar()
    check = payload["analysis"]["sanity_check"]
    del check["market_pe"]
    check["implied_pe"] = 23.25
    check["sector_pe"] = 22.0
    latest = _ref(payload)
    detail = detail_view(_entry(latest), latest)
    values = {s.label: s.value for s in detail.sanity}
    assert values["P/E implied (DCF)"] == "— / 22.00"
    assert values["P/E market"] == "23.25 / 22.00"


def _rows() -> list[Any]:
    return [
        row_view(_ref(make_sidecar("BBB", mos=1.5), date(2026, 9, 1))),
        row_view(_ref(make_sidecar("AAA", mos=None), date(2026, 10, 1))),
        row_view(_ref(make_sidecar("CCC", mos=0.8), date(2026, 8, 1))),
    ]


def test_sort_by_mos_puts_missing_last_in_both_directions() -> None:
    desc = filter_sort(_rows(), "all", "mos", "desc")
    asc = filter_sort(_rows(), "all", "mos", "asc")
    assert [r.ticker for r in desc] == ["BBB", "CCC", "AAA"]
    assert [r.ticker for r in asc] == ["CCC", "BBB", "AAA"]


def test_sort_by_ticker_and_date() -> None:
    assert [r.ticker for r in filter_sort(_rows(), "all", "ticker", "asc")] == ["AAA", "BBB", "CCC"]
    assert [r.ticker for r in filter_sort(_rows(), "all", "date", "desc")] == ["AAA", "BBB", "CCC"]


def test_filter_by_verdict() -> None:
    assert [r.ticker for r in filter_sort(_rows(), "na", "mos", "desc")] == ["AAA"]
    assert [r.ticker for r in filter_sort(_rows(), "undervalued", "mos", "desc")] == ["BBB"]
    assert filter_sort(_rows(), "fair", "mos", "desc") == []


def test_unknown_filter_or_sort_raises() -> None:
    with pytest.raises(ValueError):
        filter_sort(_rows(), "bogus", "mos", "desc")
    with pytest.raises(ValueError):
        filter_sort(_rows(), "all", "price", "desc")
    with pytest.raises(ValueError):
        filter_sort(_rows(), "all", "mos", "up")


@pytest.mark.parametrize(
    ("color", "tone"),
    [
        ("green", "success"),
        ("yellow", "warning"),
        ("red", "error"),
        ("unknown", "ghost"),
        ("purple", "ghost"),
    ],
)
def test_flag_tone_follows_severity(color: str, tone: str) -> None:
    assert FlagView("x", color, "").tone == tone


def test_detail_labels_carry_descriptions_and_no_identifiers() -> None:
    payload = real_sidecar()
    detail = detail_view(_entry(_ref(payload)), _ref(payload))
    snake = re.compile(r"[a-z]+_[a-z_]+")
    for a in detail.assumptions:
        assert a.description and not snake.search(a.label), a
    for bar in detail.tornado:
        assert bar.description and not snake.search(bar.label), bar
    for f in detail.flags:
        assert f.description and not snake.search(f.label), f
    assert detail.grid is not None
    assert detail.grid.axis_a.description and not snake.search(detail.grid.axis_a.label)
    assert detail.grid.axis_b.description and not snake.search(detail.grid.axis_b.label)
    assert detail.grid.axis_a.label == "Cost of equity"


def test_country_tax_source_is_worded_with_a_tooltip() -> None:
    payload = real_sidecar()
    payload["analysis"]["assumptions"]["tax_rate"]["source"] = "country_default_damodaran"
    detail = detail_view(_entry(_ref(payload)), _ref(payload))
    tax = next(a for a in detail.assumptions if a.label == "Tax rate")
    assert tax.source == "country default (Damodaran)"
    assert tax.source_description
    assert "_" not in tax.source + tax.source_description
