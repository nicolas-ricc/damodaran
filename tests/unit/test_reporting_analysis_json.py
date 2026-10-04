"""The JSON sidecar ``bot analyze`` writes next to each report (issue #92)."""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from typing import Any

import pytest
from bot.reporting.analysis_json import SCHEMA_VERSION, render_analysis_json

from bot.reporting.analysis_report import margin_verdict
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import Analysis, analyze
from bot.valuator.assumptions import AssumptionSource
from tests.unit.test_reporting_analysis import _seed


@pytest.fixture
def analysis() -> Analysis:
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    return analyze("AAPL", conn)


def _payload(analysis: Analysis) -> dict[str, Any]:
    return json.loads(render_analysis_json(analysis, generated_on=date(2026, 10, 1)))


def test_sidecar_has_the_envelope(analysis: Analysis) -> None:
    payload = _payload(analysis)
    assert SCHEMA_VERSION == 1
    assert payload["schema_version"] == 1
    assert payload["generated_on"] == "2026-10-01"
    assert payload["verdict"] == margin_verdict(analysis.margin_of_safety)
    assert payload["analysis"]["ticker"] == "AAPL"
    sources = {s.value for s in AssumptionSource}
    assert payload["analysis"]["assumptions"]["tax_rate"]["source"] in sources


def test_sidecar_carries_every_section_the_viewer_reads(analysis: Analysis) -> None:
    a = _payload(analysis)["analysis"]
    assert a["dcf_result"]["intrinsic_value"] == pytest.approx(analysis.dcf_result.intrinsic_value)
    assert len(a["tornado"]) == len(analysis.tornado)
    assert {"axis", "intrinsic_low", "intrinsic_high", "impact"} <= set(a["tornado"][0])
    assert len(a["grid"]["cells"]) == 5 and all(len(row) == 5 for row in a["grid"]["cells"])
    assert [f["color"] for f in a["narrative_flags"]] == [
        f.color.value for f in analysis.narrative_flags
    ]
    assert set(a["sanity_check"]) == {
        "implied_pe",
        "sector_pe",
        "implied_ev_sales",
        "sector_ev_sales",
    }
    assert len(a["dcf_result"]["projections"]) == len(analysis.dcf_result.projections)


def test_sidecar_without_price_is_na(analysis: Analysis) -> None:
    no_price = dataclasses.replace(analysis, current_price=None, margin_of_safety=None)
    payload = _payload(no_price)
    assert payload["verdict"] == "n/a"
    assert payload["analysis"]["current_price"] is None


def test_sidecar_preserves_none_grid_cells(analysis: Analysis) -> None:
    grid = analysis.grid
    cells = tuple(
        tuple(dataclasses.replace(cell, margin_of_safety=None) for cell in row)
        for row in grid.cells
    )
    no_price = dataclasses.replace(
        analysis,
        current_price=None,
        margin_of_safety=None,
        grid=dataclasses.replace(grid, cells=cells, reference_price=None),
    )
    payload = _payload(no_price)
    for row in payload["analysis"]["grid"]["cells"]:
        for cell in row:
            assert "margin_of_safety" in cell
            assert cell["margin_of_safety"] is None


@pytest.mark.parametrize(
    ("mos", "word"),
    [
        (1.3, "potentially undervalued"),
        (1.2999, "around fair value"),
        (1.0, "around fair value"),
        (0.9999, "potentially overvalued"),
        (-0.5, "potentially overvalued"),
        (None, "n/a"),
    ],
)
def test_margin_verdict_thresholds(mos: float | None, word: str) -> None:
    assert margin_verdict(mos) == word
