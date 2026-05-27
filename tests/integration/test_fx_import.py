"""Integration test for FX rate import from ECB — uses VCR cassette.

EUR/USD on 2024-01-02 (ECB reference rate) must be within ±0.1% of the
published value of 1.0960.
"""

from __future__ import annotations

from datetime import date

import pytest

from bot.ingest.fx import import_fx_rates
from bot.storage.db import apply_schema, connect
from bot.utils.fx import get_fx_rate


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "fx")


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {"record_mode": "once"}


@pytest.mark.integration
@pytest.mark.vcr
def test_eur_usd_rate_at_known_date() -> None:
    """ECB EUR/USD on 2024-01-02 must be within ±0.1% of the known published rate."""
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_fx_rates(
        conn,
        currencies=["EUR"],
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
    )

    assert result.is_success(), f"Import failed: {result.error_message}"
    assert result.rows_affected >= 1

    rate = get_fx_rate(conn, "EUR", date(2024, 1, 2))
    assert rate is not None, "No EUR/USD rate stored for 2024-01-02"

    expected = 1.0960  # ECB published 1.09600 on 2024-01-02
    tolerance = 0.001  # 0.1%
    assert abs(rate - expected) / expected <= tolerance, (
        f"EUR/USD {rate:.5f} deviates from expected {expected:.5f} by more than ±0.1%"
    )

    conn.close()
