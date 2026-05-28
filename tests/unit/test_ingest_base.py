from datetime import datetime

from bot.ingest.base import IngestResult


def test_ingest_result_basic() -> None:
    r = IngestResult(
        source="test",
        rows_affected=10,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
    )
    assert r.duration_seconds() == 5.0
    assert r.is_success() is True


def test_ingest_result_partial_failure() -> None:
    r = IngestResult(
        source="test",
        rows_affected=5,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="partial",
        error_message="3 of 8 records failed validation",
    )
    assert r.is_success() is False
