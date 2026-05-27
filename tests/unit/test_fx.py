"""Unit tests for FX rate helpers (bot.utils.fx) and the FX ingest parser."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from bot.ingest.fx import _parse_ecb_response, upsert_fx_rows
from bot.storage.db import apply_schema, connect
from bot.utils.fx import get_fx_rate, to_usd


@pytest.fixture()
def db() -> Any:
    conn = connect(":memory:")
    apply_schema(conn)
    yield conn
    conn.close()


# ---------- get_fx_rate ----------


def test_get_fx_rate_returns_exact_date(db: Any) -> None:
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('EUR', '2024-01-02', 1.0960, 'ecb')"
    )
    rate = get_fx_rate(db, "EUR", date(2024, 1, 2))
    assert rate == pytest.approx(1.0960)


def test_get_fx_rate_nearest_prior(db: Any) -> None:
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('EUR', '2024-01-02', 1.0960, 'ecb')"
    )
    # 2024-01-05 is not in the DB; should fall back to 2024-01-02
    rate = get_fx_rate(db, "EUR", date(2024, 1, 5))
    assert rate == pytest.approx(1.0960)


def test_get_fx_rate_no_prior_returns_none(db: Any) -> None:
    rate = get_fx_rate(db, "EUR", date(2024, 1, 2))
    assert rate is None


def test_get_fx_rate_usd_always_one(db: Any) -> None:
    rate = get_fx_rate(db, "USD", date(2024, 1, 2))
    assert rate == 1.0


def test_get_fx_rate_case_insensitive(db: Any) -> None:
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('GBP', '2024-01-02', 1.2700, 'ecb')"
    )
    assert get_fx_rate(db, "gbp", date(2024, 1, 2)) == pytest.approx(1.2700)
    assert get_fx_rate(db, "GBP", date(2024, 1, 2)) == pytest.approx(1.2700)


def test_get_fx_rate_picks_closest_prior(db: Any) -> None:
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('EUR', '2024-01-02', 1.0960, 'ecb')"
    )
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('EUR', '2024-01-04', 1.0950, 'ecb')"
    )
    # 2024-01-03 is between the two; nearest prior is 2024-01-02
    rate = get_fx_rate(db, "EUR", date(2024, 1, 3))
    assert rate == pytest.approx(1.0960)
    # 2024-01-05 is after both; nearest prior is 2024-01-04
    rate2 = get_fx_rate(db, "EUR", date(2024, 1, 5))
    assert rate2 == pytest.approx(1.0950)


# ---------- to_usd ----------


def test_to_usd_converts_correctly(db: Any) -> None:
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('EUR', '2024-01-02', 1.0960, 'ecb')"
    )
    usd = to_usd(db, 100.0, "EUR", date(2024, 1, 2))
    assert usd == pytest.approx(109.60)


def test_to_usd_no_rate_returns_none(db: Any) -> None:
    usd = to_usd(db, 100.0, "EUR", date(2024, 1, 2))
    assert usd is None


def test_to_usd_usd_passthrough(db: Any) -> None:
    usd = to_usd(db, 250.0, "USD", date(2024, 1, 2))
    assert usd == pytest.approx(250.0)


# ---------- upsert_fx_rows ----------


def test_upsert_fx_rows_inserts(db: Any) -> None:
    rows = [{"currency": "EUR", "date": "2024-01-02", "rate_to_usd": 1.0960, "source": "ecb"}]
    n = upsert_fx_rows(db, rows)
    assert n == 1
    row = db.execute(
        "SELECT rate_to_usd FROM currencies WHERE currency = 'EUR' AND date = '2024-01-02'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(1.0960)


def test_upsert_fx_rows_replaces_existing(db: Any) -> None:
    db.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES ('EUR', '2024-01-02', 1.0900, 'ecb')"
    )
    upsert_fx_rows(
        db, [{"currency": "EUR", "date": "2024-01-02", "rate_to_usd": 1.0960, "source": "ecb"}]
    )
    row = db.execute(
        "SELECT rate_to_usd FROM currencies WHERE currency = 'EUR' AND date = '2024-01-02'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(1.0960)


def test_upsert_fx_rows_empty_is_noop(db: Any) -> None:
    n = upsert_fx_rows(db, [])
    assert n == 0


# ---------- _parse_ecb_response ----------


def test_parse_ecb_response_returns_date_map() -> None:
    fake_response: dict[str, Any] = {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0:0": {
                        "observations": {
                            "0": [1.0960, 0, 0],
                        }
                    }
                }
            }
        ],
        "structure": {
            "dimensions": {
                "observation": [
                    {
                        "id": "TIME_PERIOD",
                        "values": [{"id": "2024-01-02"}],
                    }
                ]
            }
        },
    }
    result = _parse_ecb_response(fake_response)
    assert result == {"2024-01-02": pytest.approx(1.0960)}


def test_parse_ecb_response_bad_body_returns_empty() -> None:
    result = _parse_ecb_response({})
    assert result == {}
