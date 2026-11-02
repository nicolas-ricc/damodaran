"""Hypergrowth sections of the Markdown, HTML and JSON reports (#197).

One Anthropic-shaped analysis (the full story, a 20% governance discount, and
Damodaran's worst and best scenarios) rendered through all three reports.
Every other story type is pinned byte for byte by
``tests/unit/test_valuator_isolation_golden.py``.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import duckdb
import pytest

from bot.reporting.analysis_json import render_analysis_json
from bot.reporting.analysis_report import render_analysis
from bot.reporting.html import render_analysis_html
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import Analysis
from tests.unit.test_valuator_analysis import hypergrowth_analysis

#: Strings the issue asks every hypergrowth report to show.
_EXPECTED = (
    "Scenario range",
    "| base |",
    "| worst |",
    "| best |",
    "WACC path (story):",
    "after governance discount",
    "Operating assets after failure risk",
    "Fixed commitments",
)


def _conn() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


@pytest.fixture
def analysis(tmp_path: Path) -> Analysis:
    return hypergrowth_analysis(_conn(), tmp_path)


def test_markdown_shows_the_hypergrowth_sections(analysis: Analysis) -> None:
    md = render_analysis(analysis, generated_on=date(2026, 11, 2))
    for text in _EXPECTED:
        assert text in md, text
    assert re.search(r"^\| .+ \| story \|$", md, flags=re.MULTILINE)
    assert "computed from the components" not in md
    worst = next(line for line in md.splitlines() if line.startswith("| worst |"))
    assert worst.split("|")[2].strip().startswith("-")
    assert "Margin of safety (on the value after governance discount):" in md


def test_markdown_scenario_table_sits_under_the_tornado(analysis: Analysis) -> None:
    md = render_analysis(analysis, generated_on=date(2026, 11, 2))
    assert md.index("### Tornado") < md.index("Scenario range") < md.index("### 2-D grid")


def test_html_shows_the_hypergrowth_sections(analysis: Analysis) -> None:
    html = render_analysis_html(analysis, generated_on=date(2026, 11, 2))
    for text in ("Scenario range", "worst", "best", "WACC path (story)", "story"):
        assert text in html, text
    for text in ("after governance discount", "Operating assets after failure risk"):
        assert text in html, text
    assert "Fixed commitments" in html
    assert '<img' in html and "data:image/png;base64," in html
    assert len(analysis.tornado) == 6


def test_json_sidecar_carries_scenarios_and_governance(analysis: Analysis) -> None:
    payload = json.loads(render_analysis_json(analysis, generated_on=date(2026, 11, 2)))
    assert payload["schema_version"] == 1
    body = payload["analysis"]
    assert [s["name"] for s in body["scenarios"]] == ["base", "worst", "best"]
    assert body["governance_discount"] == 0.2
    assert body["intrinsic_value_after_governance"] == analysis.intrinsic_value_after_governance
    assert list(body["assumptions"]["scenarios"]) == ["worst", "best"]


def test_markdown_without_scenarios_has_no_range(tmp_path: Path) -> None:
    md = render_analysis(hypergrowth_analysis(_conn(), tmp_path, scenarios=False))
    assert "Scenario range" not in md
    assert "after governance discount" in md


def test_markdown_governance_without_price(tmp_path: Path) -> None:
    a = hypergrowth_analysis(_conn(), tmp_path, price=False)
    md = render_analysis(a)
    assert a.margin_of_safety is None
    assert "after governance discount" in md
    assert "margin of safety cannot be computed" in md
