from pathlib import Path

import pytest

from bot.ingest.damodaran import import_damodaran_from_files
from bot.storage.db import apply_schema, connect

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"


@pytest.mark.integration
@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran fixtures not downloaded; run Task 7.",
)
def test_import_damodaran_from_files_populates_db():
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )

    assert result.is_success()
    assert result.rows_affected > 0

    industry_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]
    country_count = conn.execute("SELECT COUNT(*) FROM damodaran_country").fetchone()[0]
    assert industry_count > 50
    assert country_count > 100

    refresh_rows = conn.execute(
        "SELECT source, status, rows_affected FROM refresh_log WHERE source = 'damodaran'"
    ).fetchall()
    assert len(refresh_rows) == 1
    assert refresh_rows[0][1] == "success"

    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran fixtures not downloaded; run Task 7.",
)
def test_import_damodaran_is_idempotent():
    conn = connect(":memory:")
    apply_schema(conn)

    import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    first_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]

    import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    second_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]

    assert first_count == second_count
    conn.close()
