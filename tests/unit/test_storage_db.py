from bot.storage.db import apply_schema, connect


def test_connect_creates_file(tmp_path):
    db_file = tmp_path / "x.duckdb"
    conn = connect(db_file)
    assert db_file.exists()
    result = conn.execute("SELECT 1 AS x").fetchone()
    assert result == (1,)
    conn.close()


def test_apply_schema_creates_all_tables(tmp_path):
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


def test_screener_candidates_table_has_expected_columns(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = 'screener_candidates'"
        ).fetchall()
    }
    expected = {
        "run_id",
        "preset",
        "ticker",
        "rank",
        "score",
        "value_score",
        "quality_score",
        "growth_score",
        "mos_score",
        "passed_gates",
        "failed_gates",
        "created_at",
    }
    assert expected.issubset(columns)
    conn.close()


def test_screener_candidates_round_trips_a_row(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        """
        INSERT INTO screener_candidates
            (run_id, preset, ticker, rank, score,
             value_score, quality_score, growth_score, mos_score,
             passed_gates, failed_gates)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "run-1",
            "damodaran_value",
            "AAPL",
            1,
            0.87,
            0.9,
            0.8,
            0.7,
            0.6,
            ["market_cap", "interest_coverage"],
            ["roic_vs_wacc"],
        ],
    )
    row = conn.execute(
        "SELECT preset, ticker, rank, passed_gates, failed_gates "
        "FROM screener_candidates WHERE run_id = ?",
        ["run-1"],
    ).fetchone()
    assert row is not None
    preset, ticker, rank, passed, failed = row
    assert (preset, ticker, rank) == ("damodaran_value", "AAPL", 1)
    assert list(passed) == ["market_cap", "interest_coverage"]
    assert list(failed) == ["roic_vs_wacc"]
    conn.close()


def test_apply_schema_is_idempotent(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    apply_schema(conn)  # must not raise
    conn.close()


def test_connect_in_memory():
    conn = connect(":memory:")
    apply_schema(conn)
    result = conn.execute("SELECT COUNT(*) FROM companies").fetchone()
    assert result == (0,)
    conn.close()
