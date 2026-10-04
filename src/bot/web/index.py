"""Scan ``reports/*/analysis/*.json`` sidecars into companies (issue #92)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import structlog

from bot.reporting.analysis_json import SCHEMA_VERSION

log = structlog.get_logger(__name__)

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")


@dataclass(frozen=True)
class AnalysisRef:
    """One analysis of one ticker on one day."""

    ticker: str
    date: date
    data: Mapping[str, Any]


@dataclass(frozen=True)
class CompanyEntry:
    """A ticker with every analysis found for it, newest first."""

    ticker: str
    history: tuple[AnalysisRef, ...]

    @property
    def latest(self) -> AnalysisRef:
        return self.history[0]


def _skip(path: Path, reason: str) -> None:
    log.warning("web.sidecar_skipped", path=str(path), reason=reason)


def read_sidecar(path: Path) -> Mapping[str, Any] | None:
    """Parse a sidecar; return ``None`` (after a warning) if unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _skip(path, f"unreadable: {exc}")
        return None
    if not isinstance(data, dict):
        _skip(path, "not a JSON object")
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        _skip(path, f"unsupported schema_version {data.get('schema_version')!r}")
        return None
    return data


def scan(reports_dir: Path) -> list[CompanyEntry]:
    """Collect all valid sidecars under ``reports_dir``, sorted by ticker."""
    if not reports_dir.is_dir():
        return []
    by_ticker: dict[str, list[AnalysisRef]] = {}
    for path in sorted(reports_dir.glob("*/analysis/*.json")):
        folder = path.parent.parent.name
        try:
            day = date.fromisoformat(folder)
        except ValueError:
            day = None
        if day is None or day.isoformat() != folder:
            _skip(path, "folder name is not an ISO date")
            continue
        ticker = path.stem
        if not TICKER_RE.fullmatch(ticker):
            _skip(path, "file stem is not a valid ticker")
            continue
        data = read_sidecar(path)
        if data is None:
            continue
        analysis = data.get("analysis")
        if not isinstance(analysis, dict) or analysis.get("ticker") != ticker:
            _skip(path, "analysis.ticker does not match file name")
            continue
        by_ticker.setdefault(ticker, []).append(AnalysisRef(ticker, day, data))
    return [
        CompanyEntry(t, tuple(sorted(refs, key=lambda r: r.date, reverse=True)))
        for t, refs in sorted(by_ticker.items())
    ]
