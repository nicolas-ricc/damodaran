"""JSON sidecar for an :class:`Analysis`, read by the static web viewer (#92).

Since #219, ``sanity_check.implied_pe`` is the DCF's multiple (intrinsic value
per share / EPS) and the market P/E is ``sanity_check.market_pe``. Sidecars
written before carry the market P/E under ``implied_pe`` and no ``market_pe``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date

from bot.reporting.analysis_report import margin_verdict
from bot.valuator.analysis import Analysis

SCHEMA_VERSION = 1


def _json_default(value: object) -> str:
    """Serialise ``date``; refuse everything else rather than stringify it."""
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def render_analysis_json(analysis: Analysis, *, generated_on: date) -> str:
    """Render ``analysis`` as the versioned JSON sidecar document."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_on": generated_on.isoformat(),
        "verdict": margin_verdict(analysis.margin_of_safety),
        "analysis": dataclasses.asdict(analysis),
    }
    return json.dumps(payload, default=_json_default, indent=2, allow_nan=False) + "\n"
