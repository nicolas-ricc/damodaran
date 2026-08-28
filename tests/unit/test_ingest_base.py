from datetime import date, datetime

from bot.ingest.base import IngestResult, coerce_date


def test_ingest_result_basic():
    r = IngestResult(
        source="test",
        rows_affected=10,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
    )
    assert r.duration_seconds() == 5.0
    assert r.is_success() is True


def test_ingest_result_partial_failure():
    r = IngestResult(
        source="test",
        rows_affected=5,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="partial",
        error_message="3 of 8 records failed validation",
    )
    assert r.is_success() is False


def test_coerce_date_accepts_every_shape_the_pipeline_sees() -> None:
    assert coerce_date(None) is None
    assert coerce_date("") is None
    assert coerce_date(date(2024, 1, 2)) == date(2024, 1, 2)
    assert coerce_date(datetime(2024, 1, 2, 13, 45)) == date(2024, 1, 2)
    assert coerce_date("2024-01-02") == date(2024, 1, 2)
    assert coerce_date("2024-01-02 00:00:00") == date(2024, 1, 2)
    assert coerce_date("not-a-date") is None
