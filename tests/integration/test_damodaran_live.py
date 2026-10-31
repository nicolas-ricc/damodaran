"""Live shape check of the published Damodaran files (opt-in, ``BOT_LIVE_TESTS=1``).

Run after a new Damodaran release: ``BOT_LIVE_TESTS=1 uv run pytest -m live``.
Asserts shape only, never exact numbers, so a routine release does not break it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.ingest.damodaran import (
    COUNTRY_RISK_URL,
    INDUSTRY_WACC_URL,
    download_dataset,
    import_damodaran_from_files,
)
from bot.storage.db import apply_schema, connect

_UNAVAILABLE_EVENTS = {
    "damodaran.country_tax_sheet.unavailable",
}


@pytest.mark.live
def test_published_files_still_carry_country_tax_rates(tmp_path: Path) -> None:
    industry_path = download_dataset(INDUSTRY_WACC_URL, tmp_path / "wacc.xls")
    country_path = download_dataset(COUNTRY_RISK_URL, tmp_path / "ctryprem.xls")
    conn = connect(":memory:")
    apply_schema(conn)

    with capture_logs() as logs:
        result = import_damodaran_from_files(
            conn,
            industry_path=industry_path,
            country_path=country_path,
            region="US",
            year=date.today().year,
        )

    assert result.is_success(), result.error_message
    assert not _UNAVAILABLE_EVENTS & {entry["event"] for entry in logs}
    us = conn.execute(
        "SELECT tax_rate FROM damodaran_country WHERE country = 'United States'"
    ).fetchone()
    assert us is not None
    (tax_rate,) = us
    assert tax_rate is not None and 0 < tax_rate < 1
    counts = conn.execute("SELECT COUNT(*), COUNT(tax_rate) FROM damodaran_country").fetchone()
    assert counts is not None
    total, with_tax = counts
    assert with_tax / total >= 0.95
    conn.close()
