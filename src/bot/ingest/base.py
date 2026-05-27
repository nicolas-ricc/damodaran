"""Shared types for ingest adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

IngestStatus = Literal["success", "partial", "error"]


@dataclass
class IngestResult:
    source: str
    started_at: datetime
    finished_at: datetime
    status: IngestStatus
    rows_affected: int = 0
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def is_success(self) -> bool:
        return self.status == "success"


@dataclass
class ParsedCompanyData:
    """Normalized output from any fundamentals parser (SEC EDGAR, FMP, …)."""

    company: dict[str, Any]
    annual: list[dict[str, Any]] = field(default_factory=list)
    quarterly: list[dict[str, Any]] = field(default_factory=list)
    filings: list[dict[str, Any]] = field(default_factory=list)
