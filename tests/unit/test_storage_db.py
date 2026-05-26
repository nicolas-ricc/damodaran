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
    }
    assert expected.issubset(tables)
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
