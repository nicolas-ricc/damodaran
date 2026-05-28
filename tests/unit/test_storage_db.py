from bot.storage.db import apply_schema, connect


def test_connect_creates_file(tmp_path: object) -> None:
    assert isinstance(tmp_path, __import__("pathlib").Path)
    db_file = tmp_path / "x.duckdb"
    conn = connect(db_file)
    assert db_file.exists()
    result = conn.execute("SELECT 1 AS x").fetchone()
    assert result == (1,)
    conn.close()


def test_apply_schema_creates_all_tables(tmp_path: object) -> None:
    assert isinstance(tmp_path, __import__("pathlib").Path)
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    expected = {
        "damodaran_industry",
        "damodaran_country",
        "companies",
        "financials_annual",
        "financials_quarterly",
        "filings_log",
        "refresh_log",
        "screener_candidates",
    }
    assert expected.issubset(tables)
    conn.close()


def test_screener_candidates_table_exists(tmp_path: object) -> None:
    """M3.1 acceptance: screener_candidates table is created by apply_schema."""
    assert isinstance(tmp_path, __import__("pathlib").Path)
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert "screener_candidates" in tables

    # Verify all expected columns exist
    cols = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'screener_candidates' AND table_schema = 'main'"
        ).fetchall()
    }
    expected_cols = {
        "run_id",
        "preset",
        "ticker",
        "rank",
        "score",
        "score_value",
        "score_quality",
        "score_growth",
        "score_mos",
        "passed_gates",
        "failed_gates",
        "created_at",
    }
    assert expected_cols.issubset(cols)
    conn.close()


def test_apply_schema_is_idempotent(tmp_path: object) -> None:
    assert isinstance(tmp_path, __import__("pathlib").Path)
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    apply_schema(conn)
    conn.close()


def test_connect_in_memory() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    result = conn.execute("SELECT COUNT(*) FROM companies").fetchone()
    assert result == (0,)
    conn.close()


def test_table_count_at_least_eight(tmp_path: object) -> None:
    """M3.1 acceptance: bot doctor should see >= 8 tables."""
    assert isinstance(tmp_path, __import__("pathlib").Path)
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    count = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchone()[0]
    assert count >= 8
    conn.close()
