"""Shared types for ingest adapters."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import duckdb

IngestStatus = Literal["success", "partial", "error"]


@dataclass
class IngestResult:
    """Outcome of a single ingest run, written to refresh_log."""

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


def _log_refresh(
    conn: duckdb.DuckDBPyConnection, result: IngestResult, run_id: str
) -> None:
    conn.execute(
        """
        INSERT INTO refresh_log
            (source, run_id, started_at, finished_at, status, rows_affected, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            result.source,
            run_id,
            result.started_at,
            result.finished_at,
            result.status,
            result.rows_affected,
            result.error_message,
        ],
    )


@contextmanager
def transaction(conn: duckdb.DuckDBPyConnection) -> Iterator[None]:
    """Run the wrapped block inside a DuckDB transaction.

    Commits on success; rolls back and re-raises on any exception.
    """
    conn.execute("BEGIN TRANSACTION")
    try:
        yield
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


@dataclass
class RefreshOutcome:
    """Mutable box a :func:`refresh_run` body fills in while it works.

    The body sets ``rows_affected`` and ``details`` (and optionally the status /
    error overrides for a partial run). ``result`` is assigned by the context
    manager on exit so the caller can ``return run.result``.
    """

    source: str
    run_id: str
    started_at: datetime
    rows_affected: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    status_override: IngestStatus | None = None
    error_message_override: str | None = None
    result: IngestResult | None = None


@contextmanager
def refresh_run(
    conn: duckdb.DuckDBPyConnection,
    *,
    source: str,
    log: Any,
    error_event: str,
    log_fail_event: str,
) -> Iterator[RefreshOutcome]:
    """Wrap a single-shot ingest run: timing, result building and refresh_log.

    Stamps ``started_at`` / ``run_id``, yields a mutable :class:`RefreshOutcome`
    box for the body to populate, then builds the success / error
    :class:`IngestResult` and always records it in ``refresh_log`` (a logging
    failure is caught and logged, never propagated). ``box.result`` is assigned
    on both branches so the caller can ``return run.result``.
    """
    started = datetime.now()
    run_id = str(uuid.uuid4())
    box = RefreshOutcome(source=source, run_id=run_id, started_at=started)
    try:
        yield box
        box.result = IngestResult(
            source=source,
            started_at=started,
            finished_at=datetime.now(),
            status=box.status_override or "success",
            rows_affected=box.rows_affected,
            error_message=box.error_message_override,
            details=box.details,
        )
    except Exception as e:
        # Fold the box's early-set context (e.g. {"ticker": sym}) into the
        # failure event so it keeps the structured fields the inline importers
        # used to log directly.
        log.exception(error_event, error=str(e), **box.details)
        box.result = IngestResult(
            source=source,
            started_at=started,
            finished_at=datetime.now(),
            status="error",
            error_message=str(e),
            details=box.details,
        )
    try:
        _log_refresh(conn, box.result, run_id)
    except Exception as log_err:
        log.exception(log_fail_event, error=str(log_err))
