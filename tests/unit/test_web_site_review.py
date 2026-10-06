"""Review follow-ups for the static viewer (issue #92, stage 6)."""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.reporting.analysis_json import render_analysis_json
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import analyze
from bot.web.site import MARKER, build
from bot.web.svg import scenario_grid_svg, tornado_svg
from bot.web.views import ScenarioGrid, TornadoBar, Verdict
from tests.unit.test_reporting_analysis import _seed
from tests.web_sidecars import make_sidecar, write_sidecar


def test_incomplete_sidecar_is_skipped_not_fatal(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    write_sidecar(reports, "2026-10-01", make_sidecar("AAA"))
    write_sidecar(
        reports,
        "2026-10-01",
        {"schema_version": 1, "verdict": "n/a", "analysis": {"ticker": "EEE"}},
    )
    with capture_logs() as logs:
        assert build(reports, tmp_path / "site", "/") == 1
    assert not (tmp_path / "site" / "c" / "EEE.html").exists()
    assert any(
        log["event"] == "web.sidecar_skipped" and log.get("ticker") == "EEE" for log in logs
    )


def test_incomplete_older_analysis_keeps_the_company(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    write_sidecar(reports, "2026-10-01", make_sidecar("AAA"))
    broken = make_sidecar("AAA")
    del broken["analysis"]["dcf_result"]
    write_sidecar(reports, "2026-09-01", broken)
    out = tmp_path / "site"
    assert build(reports, out, "/") == 1
    assert (out / "c" / "AAA.html").is_file()
    assert not (out / "c" / "AAA" / "2026-09-01.html").exists()
    assert "2026-09-01" not in (out / "f" / "AAA.html").read_text()


def test_count_reads_n_of_total(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    write_sidecar(reports, "2026-10-01", make_sidecar("AAA", mos=1.5))
    write_sidecar(reports, "2026-10-01", make_sidecar("BBB", mos=0.5))
    out = tmp_path / "site"
    build(reports, out, "/")
    assert "1 of 2" in (out / "rows" / "undervalued-mos-desc.html").read_text()
    assert "2 of 2" in (out / "index.html").read_text()


def test_marker_is_deleted_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports = tmp_path / "reports"
    write_sidecar(reports, "2026-10-01", make_sidecar("AAA"))
    out = tmp_path / "site"
    build(reports, out, "/")
    removed: list[str] = []
    real_unlink = Path.unlink

    def tracking_unlink(self: Path, missing_ok: bool = False) -> None:
        removed.append(self.name)
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", tracking_unlink)
    build(reports, out, "/")
    assert MARKER in removed
    assert removed[-1] == MARKER


def test_charts_have_accessible_names() -> None:
    labels = ("-20%", "-10%", "+0%", "+10%", "+20%")
    grid = ScenarioGrid(
        axis_a="a",
        axis_b="b",
        row_labels=labels,
        col_labels=labels,
        cells=tuple(tuple(Verdict.FAIR for _ in range(5)) for _ in range(5)),
        matching=25,
        total=25,
    )
    assert 'aria-label="Scenarios 25/25"' in str(scenario_grid_svg(grid, seed=1))
    bars = [TornadoBar("tax_rate", 1.0, 2.0)]
    assert 'aria-label="Drivers"' in str(tornado_svg(bars, price=1.5, seed=1))


def test_non_finite_numbers_fail_at_write_time() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    analysis = analyze("AAPL", conn)
    broken = dataclasses.replace(analysis, margin_of_safety=float("nan"))
    with pytest.raises(ValueError):
        render_analysis_json(broken, generated_on=date(2026, 10, 1))
