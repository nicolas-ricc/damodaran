"""Sidecar fixtures for the web viewer tests (issue #92).

Every sidecar starts from a real :class:`Analysis` (the seeded AAPL fixture run
through :func:`analyze` and :func:`render_analysis_json`), so the viewer is tested
against the exact shape ``bot analyze`` writes, then edited per test.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import analyze
from tests.unit.test_reporting_analysis import _seed


@lru_cache(maxsize=1)
def _real_sidecar_text() -> str:
    from bot.reporting.analysis_json import render_analysis_json

    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    return render_analysis_json(analyze("AAPL", conn), generated_on=date(2026, 10, 1))


def real_sidecar() -> dict[str, Any]:
    """A fresh copy of the seeded AAPL sidecar."""
    payload: dict[str, Any] = json.loads(_real_sidecar_text())
    return payload


def make_sidecar(
    ticker: str,
    *,
    name: str | None = None,
    mos: float | None = 1.5,
    red_flag: bool = False,
) -> dict[str, Any]:
    """The seeded sidecar re-labelled as ``ticker`` with the given margin of safety.

    ``mos=None`` drops the price (and the grid's reference price), which is how
    ``bot analyze`` stores a company without a quote.
    """
    from bot.reporting.analysis_report import margin_verdict

    payload = copy.deepcopy(real_sidecar())
    analysis = payload["analysis"]
    analysis["ticker"] = ticker
    analysis["name"] = name if name is not None else f"{ticker} Inc"
    intrinsic = analysis["dcf_result"]["intrinsic_value"]
    if mos is None:
        analysis["current_price"] = None
        analysis["margin_of_safety"] = None
        analysis["grid"]["reference_price"] = None
        for row in analysis["grid"]["cells"]:
            for cell in row:
                cell["margin_of_safety"] = None
    else:
        analysis["current_price"] = intrinsic / mos
        analysis["margin_of_safety"] = mos
    if red_flag:
        analysis["narrative_flags"][0]["color"] = "red"
    payload["verdict"] = margin_verdict(analysis["margin_of_safety"])
    return payload


def write_sidecar(reports_dir: Path, day: str, payload: dict[str, Any]) -> Path:
    """Write ``payload`` where ``bot analyze`` would: ``<reports>/<day>/analysis/<T>.json``."""
    out = reports_dir / day / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{payload['analysis']['ticker']}.json"
    path.write_text(json.dumps(payload))
    return path
