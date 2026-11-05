"""Every surface labels the shock it applied (#217).

Rate axes move by ±1 percentage point, ``sales_to_capital`` by ×0.8 / ×1.2: the
Markdown report, the HTML charts, the JSON sidecar and the site say which.
Sidecars written before #217 (``row_multipliers``, no ``kind``) read as
multiplicative.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from bot.reporting.analysis_json import render_analysis_json
from bot.reporting.analysis_report import fmt_shock, fmt_step, render_analysis
from bot.reporting.html import sensitivity_heatmap_html, tornado_chart_png
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import Analysis, analyze
from bot.valuator.dcf import Assumptions, Financials
from bot.valuator.sensitivity import SensitivityAxis, ShockKind, grid_2d
from bot.web.index import AnalysisRef, CompanyEntry
from bot.web.site import _renderable, build
from bot.web.svg import tornado_table
from bot.web.views import TornadoBar, detail_view
from tests.unit.test_reporting_analysis import _seed
from tests.web_sidecars import make_sidecar, real_sidecar, write_sidecar


@pytest.fixture(scope="module")
def analysis() -> Analysis:
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    return analyze("AAPL", conn)


def _mixed_grid(*, reference_price: float | None = 50.0) -> Any:
    fin = Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)
    asm = Assumptions(
        revenue_growth=(0.10, 0.08, 0.06, 0.04, 0.02),
        operating_margin=(0.20,) * 5,
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.11,
        pretax_cost_of_debt=0.05,
        equity_weight=0.8,
        debt_weight=0.2,
    )
    return grid_2d(
        fin,
        asm,
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.SALES_TO_CAPITAL,
        reference_price=reference_price,
    )


# --------------------------------------------------------------------------- #
# Formatters                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "kind", "label"),
    [
        (-0.01, ShockKind.ADDITIVE, "-1.0pp"),
        (-0.005, ShockKind.ADDITIVE, "-0.5pp"),
        (0.0, ShockKind.ADDITIVE, "+0.0pp"),
        (0.005, ShockKind.ADDITIVE, "+0.5pp"),
        (0.01, ShockKind.ADDITIVE, "+1.0pp"),
        (0.8, ShockKind.MULTIPLICATIVE, "×0.8"),
        (1.0, ShockKind.MULTIPLICATIVE, "×1.0"),
        (1.2, ShockKind.MULTIPLICATIVE, "×1.2"),
        (0.01, "additive", "+1.0pp"),
        (0.9, "multiplicative", "×0.9"),
    ],
)
def test_fmt_step_labels(value: float, kind: ShockKind | str, label: str) -> None:
    assert fmt_step(value, kind) == label


def test_fmt_step_none_is_a_dash() -> None:
    assert fmt_step(None, ShockKind.ADDITIVE) == "—"


def test_fmt_step_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValueError):
        fmt_step(0.01, "bogus")


def test_fmt_shock_labels() -> None:
    assert fmt_shock(ShockKind.ADDITIVE) == "-1.0pp / +1.0pp"
    assert fmt_shock(ShockKind.MULTIPLICATIVE) == "×0.8 / ×1.2"
    assert fmt_shock("multiplicative") == "×0.8 / ×1.2"


# --------------------------------------------------------------------------- #
# Markdown report §5                                                           #
# --------------------------------------------------------------------------- #


def _section_5(md: str) -> str:
    return md.split("## 5. Sensitivity", 1)[1].split("## 6.", 1)[0]


def test_tornado_table_shows_each_rows_shock(analysis: Analysis) -> None:
    section = _section_5(render_analysis(analysis))
    assert "±20%" not in section
    assert "| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |" in section
    rows = {line.split(" | ")[0].lstrip("| "): line for line in section.splitlines()}
    assert "×0.8 / ×1.2" in rows["sales_to_capital"]
    assert "-1.0pp / +1.0pp" in rows["revenue_growth (yr 1)"]
    assert "-1.0pp / +1.0pp" in rows["terminal_growth"]
    # The convention is stated once, above the table.
    assert "percentage point" in section
    assert "sales_to_capital" in section.split("| Assumption |", 1)[0]


def test_grid_table_labels_match_kind(analysis: Analysis) -> None:
    mixed = dataclasses.replace(analysis, grid=_mixed_grid())
    section = _section_5(render_analysis(mixed))
    assert "| -1.0pp | " in section  # row label of an additive row axis
    assert "| ×0.8 | ×0.9 | ×1.0 | ×1.1 | ×1.2 |" in section  # multiplicative columns
    assert "-20%" not in section


def test_report_grid_of_the_seeded_analysis_has_kind_labels(analysis: Analysis) -> None:
    grid = analysis.grid
    section = _section_5(render_analysis(analysis))
    header = " | ".join(fmt_step(s, grid.col_kind) for s in grid.col_steps)
    assert header in section
    for step in grid.row_steps:
        assert f"| {fmt_step(step, grid.row_kind)} |" in section


# --------------------------------------------------------------------------- #
# HTML                                                                         #
# --------------------------------------------------------------------------- #


def test_heatmap_axes_use_the_kind_labels() -> None:
    fragment = sensitivity_heatmap_html(_mixed_grid())
    assert '"-1.0pp"' in fragment
    assert '"×1.2"' in fragment or '"\\u00d71.2"' in fragment
    assert '"-20%"' not in fragment


def test_tornado_chart_still_renders(analysis: Analysis) -> None:
    assert tornado_chart_png(analysis.tornado).startswith(b"\x89PNG")


# --------------------------------------------------------------------------- #
# JSON sidecar                                                                 #
# --------------------------------------------------------------------------- #


def test_sidecar_names_the_step_kind(analysis: Analysis) -> None:
    payload = json.loads(render_analysis_json(analysis, generated_on=date(2026, 10, 1)))
    assert payload["schema_version"] == 1
    a = payload["analysis"]
    kinds = {t["axis"]: t["kind"] for t in a["tornado"]}
    assert kinds["sales_to_capital"] == "multiplicative"
    assert {k for axis, k in kinds.items() if axis != "sales_to_capital"} == {"additive"}
    grid = a["grid"]
    assert grid["row_kind"] in ("additive", "multiplicative")
    assert grid["col_kind"] in ("additive", "multiplicative")
    assert len(grid["row_steps"]) == 5
    assert len(grid["col_steps"]) == 5
    assert "row_multipliers" not in grid


# --------------------------------------------------------------------------- #
# Site                                                                         #
# --------------------------------------------------------------------------- #


def _ref(payload: dict[str, Any]) -> AnalysisRef:
    return AnalysisRef(ticker=payload["analysis"]["ticker"], date=date(2026, 10, 1), data=payload)


def _entry(ref: AnalysisRef) -> CompanyEntry:
    return CompanyEntry(ticker=ref.ticker, history=(ref,))


def _pre_217(payload: dict[str, Any]) -> dict[str, Any]:
    old = copy.deepcopy(payload)
    grid = old["analysis"]["grid"]
    grid["row_multipliers"] = [0.8, 0.9, 1.0, 1.1, 1.2]
    grid["col_multipliers"] = [0.8, 0.9, 1.0, 1.1, 1.2]
    for key in ("row_steps", "col_steps", "row_kind", "col_kind"):
        del grid[key]
    for t in old["analysis"]["tornado"]:
        del t["kind"]
    return old


def test_scenario_grid_labels_follow_kind() -> None:
    payload = make_sidecar("AAA")
    grid = payload["analysis"]["grid"]
    ref = _ref(payload)
    detail = detail_view(_entry(ref), ref)
    assert detail.grid is not None
    assert detail.grid.row_labels == tuple(fmt_step(s, grid["row_kind"]) for s in grid["row_steps"])
    assert detail.grid.col_labels == tuple(fmt_step(s, grid["col_kind"]) for s in grid["col_steps"])


def test_tornado_bar_carries_shock() -> None:
    ref = _ref(make_sidecar("AAA"))
    bars = {b.label: b for b in detail_view(_entry(ref), ref).tornado}
    assert bars["revenue_growth (yr 1)"].shock == "-1.0pp / +1.0pp"
    assert bars["sales_to_capital"].shock == "×0.8 / ×1.2"


def test_pre_217_sidecar_reads_as_multiplicative() -> None:
    ref = _ref(_pre_217(make_sidecar("AAA")))
    detail = detail_view(_entry(ref), ref)
    assert detail.grid is not None
    labels = ("×0.8", "×0.9", "×1.0", "×1.1", "×1.2")
    assert detail.grid.row_labels == labels
    assert detail.grid.col_labels == labels
    assert detail.tornado
    assert all(b.shock == "×0.8 / ×1.2" for b in detail.tornado)
    assert _renderable(_entry(ref)) is not None


def test_sidecar_without_grid_steps_is_skipped() -> None:
    payload = make_sidecar("AAA")
    del payload["analysis"]["grid"]["row_steps"]
    ref = _ref(payload)
    assert _renderable(_entry(ref)) is None


def test_sidecar_with_an_unknown_kind_is_skipped() -> None:
    payload = make_sidecar("AAA")
    payload["analysis"]["tornado"][0]["kind"] = "bogus"
    ref = _ref(payload)
    assert _renderable(_entry(ref)) is None


def test_tornado_table_renders_the_shock() -> None:
    html = str(tornado_table([TornadoBar("tax_rate", 1.0, 2.0, "-1.0pp / +1.0pp")], price=1.5))
    assert '<span class="shock">-1.0pp / +1.0pp</span>' in html
    plain = str(tornado_table([TornadoBar("tax_rate", 1.0, 2.0)], price=1.5))
    assert 'class="shock"' not in plain


def test_detail_page_ledes_name_both_shocks(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    write_sidecar(reports, "2026-10-01", real_sidecar())
    out = tmp_path / "site"
    build(reports, out, "/")
    page = (out / "c" / "AAPL.html").read_text(encoding="utf-8")
    assert "20% either way" not in page
    assert "each by up to 20%" not in page
    assert "percentage point" in page
    assert "sales_to_capital" in page or "sales-to-capital" in page
