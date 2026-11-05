"""Isolation golden for the valuator (#193, story #192).

The hypergrowth story extends the DCF behind defaults. Every other story type
(``mature-stable``, ``high-growth``, ``cyclical``, ``distressed``,
``mature-decline``) must value exactly as before. This test pins, per story
type, the Markdown report byte for byte and the JSON sidecar by projection: the
new document must carry every key of the golden with an equal value, while keys
that only exist in the new document are allowed (later tasks add optional
fields with defaults). JSON floats are written with ``repr``, so the projection
compares them exactly.

The fixtures under ``tests/fixtures/valuator/isolation/`` were captured on
commit ``4caf8e1`` (the ``src`` tree before the DCF changes of #193) with::

    uv run python -c "
    from tests.unit.test_valuator_isolation_golden import regenerate
    regenerate()
    "

Regenerate them the same way only when a deliberate behavior change is intended
for these story types.

Regenerated for #215 (growth path is the revenue CAGR, not the mean of yearly
growth): last-digit drift. That run also pinned the optional keys added since
``4caf8e1`` (``wacc_path``, ``story``, ``scenarios``, ...).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import duckdb
import pytest

from bot.reporting.analysis_json import render_analysis_json
from bot.reporting.analysis_report import render_analysis
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import Analysis, analyze
from bot.valuator.story_types import StoryType
from tests.unit.test_valuator_analysis import (
    _MILLIONS,
    _seed,
    _seed_company,
    _seed_high_cagr_financials,
    _seed_volatile_financials,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "valuator" / "isolation"

#: The date stamped on every rendered report, so the golden never drifts.
_GENERATED_ON = date(2026, 1, 1)

#: Override for the distressed case: the per-share failure blend of today.
_DISTRESSED_OVERRIDE = "probability_of_bankruptcy: 0.2\ndistress_value_per_share: 3.0\n"

#: Override with list paths, weights, tax rate and notes (spec §7.6).
_MANUAL_OVERRIDE = (
    "revenue_growth: [0.08, 0.07, 0.06, 0.05, 0.04]\n"
    "operating_margin: [0.30, 0.29, 0.28, 0.27, 0.26]\n"
    "equity_weight: 0.85\n"
    "tax_rate: 0.23\n"
    "notes: isolation golden override\n"
)


def _insert_years(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    rows: tuple[tuple[int, float, float, float, float, float, float], ...],
) -> None:
    """Insert ``(year, revenue, ebit, net_income, interest, debt, cash)`` rows, in millions."""
    for year, revenue, ebit, net_income, interest, debt, cash in rows:
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                ticker,
                year,
                revenue * _MILLIONS,
                ebit * _MILLIONS,
                net_income * _MILLIONS,
                interest * _MILLIONS,
                debt * _MILLIONS,
                cash * _MILLIONS,
                1_000.0 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )


def _price(conn: duckdb.DuckDBPyConnection, ticker: str, close: float) -> None:
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "2025-12-31", close, close * 1_000.0 * _MILLIONS, "USD", "stooq"],
    )


def _mature_stable(conn: duckdb.DuckDBPyConnection, tmp: Path) -> Analysis:
    _seed(conn)
    return analyze("AAPL", conn)


def _high_growth(conn: duckdb.DuckDBPyConnection, tmp: Path) -> Analysis:
    _seed_company(conn, ticker="HGRO", industry_damodaran="Software (System & Application)")
    _seed_high_cagr_financials(conn, ticker="HGRO")
    _price(conn, "HGRO", 40.0)
    return analyze("HGRO", conn, age_years=10)


def _cyclical(conn: duckdb.DuckDBPyConnection, tmp: Path) -> Analysis:
    _seed_company(conn, ticker="CYCL", industry_damodaran="Steel")
    _seed_volatile_financials(conn, ticker="CYCL")
    _price(conn, "CYCL", 0.9)
    return analyze("CYCL", conn)


def _distressed(conn: duckdb.DuckDBPyConnection, tmp: Path) -> Analysis:
    _seed_company(conn, ticker="DIST", industry_damodaran="Retail (General)")
    # EBIT 40 against interest 60: coverage ≈ 0.67, below _DISTRESS_INTEREST_COVERAGE.
    _insert_years(
        conn,
        "DIST",
        (
            (2022, 1_000.0, 60.0, -10.0, 60.0, 900.0, 30.0),
            (2023, 990.0, 50.0, -20.0, 60.0, 920.0, 25.0),
            (2024, 1_000.0, 45.0, -25.0, 60.0, 930.0, 20.0),
            (2025, 1_010.0, 40.0, -30.0, 60.0, 940.0, 20.0),
        ),
    )
    _price(conn, "DIST", 1.5)
    override = tmp / "DIST.yaml"
    override.write_text(_DISTRESSED_OVERRIDE)
    return analyze("DIST", conn, override_path=override)


def _mature_decline(conn: duckdb.DuckDBPyConnection, tmp: Path) -> Analysis:
    _seed_company(conn, ticker="DECL", industry_damodaran="Publishing & Newspapers")
    _insert_years(
        conn,
        "DECL",
        (
            (2022, 1_200.0, 144.0, 100.0, 0.0, 0.0, 100.0),
            (2023, 1_140.0, 137.0, 95.0, 0.0, 0.0, 100.0),
            (2024, 1_080.0, 130.0, 90.0, 0.0, 0.0, 100.0),
            (2025, 1_020.0, 122.0, 85.0, 0.0, 0.0, 100.0),
        ),
    )
    _price(conn, "DECL", 1.2)
    return analyze("DECL", conn)


def _override(conn: duckdb.DuckDBPyConnection, tmp: Path) -> Analysis:
    _seed(conn)
    override = tmp / "AAPL.yaml"
    override.write_text(_MANUAL_OVERRIDE)
    return analyze("AAPL", conn, override_path=override)


#: Case name, its seed-and-analyze function, and the story type it must land on.
_CASES: dict[str, tuple[Callable[[duckdb.DuckDBPyConnection, Path], Analysis], StoryType]] = {
    "mature_stable": (_mature_stable, StoryType.MATURE_STABLE),
    "high_growth": (_high_growth, StoryType.HIGH_GROWTH),
    "cyclical": (_cyclical, StoryType.CYCLICAL),
    "distressed": (_distressed, StoryType.DISTRESSED),
    "mature_decline": (_mature_decline, StoryType.MATURE_DECLINE),
    "override": (_override, StoryType.MATURE_STABLE),
}

CASES: tuple[str, ...] = tuple(_CASES)


def _run(case: str, tmp: Path) -> Analysis:
    conn = connect(":memory:")
    apply_schema(conn)
    build, _ = _CASES[case]
    return build(conn, tmp)


def _render(analysis: Analysis) -> tuple[str, str]:
    return (
        render_analysis(analysis, generated_on=_GENERATED_ON),
        render_analysis_json(analysis, generated_on=_GENERATED_ON),
    )


def _project(golden: object, actual: object, path: str = "$") -> None:
    """Assert ``actual`` carries every key of ``golden`` with an equal value."""
    if isinstance(golden, dict):
        assert isinstance(actual, dict), f"{path}: expected an object"
        for key, value in golden.items():
            assert key in actual, f"{path}.{key}: missing"
            _project(value, actual[key], f"{path}.{key}")
    elif isinstance(golden, list):
        assert isinstance(actual, list), f"{path}: expected a list"
        assert len(actual) == len(golden), f"{path}: length {len(actual)} != {len(golden)}"
        for index, (expected, got) in enumerate(zip(golden, actual, strict=True)):
            _project(expected, got, f"{path}[{index}]")
    else:
        assert actual == golden, f"{path}: {actual!r} != {golden!r}"


def regenerate() -> None:
    """Rewrite every golden fixture from the current tree (see module docstring)."""
    import tempfile

    FIXTURES.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            markdown, sidecar = _render(_run(case, Path(tmp)))
        (FIXTURES / f"{case}.md").write_text(markdown, encoding="utf-8")
        (FIXTURES / f"{case}.json").write_text(sidecar, encoding="utf-8")


@pytest.mark.parametrize("case", CASES)
def test_case_lands_on_its_story_type(case: str, tmp_path: Path) -> None:
    _, story_type = _CASES[case]
    assert _run(case, tmp_path).story_type == story_type.value


@pytest.mark.parametrize("case", CASES)
def test_markdown_matches_golden(case: str, tmp_path: Path) -> None:
    markdown, _ = _render(_run(case, tmp_path))
    assert markdown == (FIXTURES / f"{case}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("case", CASES)
def test_json_projects_onto_golden(case: str, tmp_path: Path) -> None:
    _, sidecar = _render(_run(case, tmp_path))
    golden = json.loads((FIXTURES / f"{case}.json").read_text(encoding="utf-8"))
    _project(golden, json.loads(sidecar))
