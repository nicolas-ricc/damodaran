"""Additional Damodaran industry datasets (margins, sales-to-capital, multiples).

wacc.xls carries only cost-of-capital columns. operating_margin and
sales_to_capital are *required* by to_dcf_assumptions, and the multiples feed the
§6.3 value indicators and the §7.7 sanity check. Each lives in its own published
file, merged here on the industry label.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb
import pytest

from bot.ingest.damodaran import (
    INDUSTRY_DATASETS,
    import_damodaran_from_files,
    merge_industry_datasets,
)
from bot.storage.db import apply_schema

_FIXTURES = Path("tests/fixtures/damodaran")
_WACC_FIXTURE = _FIXTURES / "wacc_sample.xls"
_CTRY_FIXTURE = _FIXTURES / "ctryprem_sample.xls"

#: Every registry dataset except ``wacc`` (which arrives as ``industry_path``).
_EXTRA_KEYS = tuple(d.key for d in INDUSTRY_DATASETS if d.key != "wacc")

_EXTRA_FIXTURES = {key: _FIXTURES / f"{key}_sample.xls" for key in _EXTRA_KEYS}

_ALL_FIXTURES_PRESENT = (
    _WACC_FIXTURE.exists()
    and _CTRY_FIXTURE.exists()
    and all(p.exists() for p in _EXTRA_FIXTURES.values())
)


def test_registry_covers_every_column_the_consumers_select() -> None:
    # These are the columns valuator/assumptions.py, valuator/analysis.py and
    # screener/benchmarks.py actually SELECT. Every one needs a source.
    required = {
        "op_margin",
        "net_margin",
        "sales_to_capital",
        "pe",
        "pbv",
        "ev_ebitda",
        "ev_sales",
        "roe",
        "roic",
    }
    covered: set[str] = set()
    for dataset in INDUSTRY_DATASETS:
        covered |= set(dataset.column_map) - {"industry"}
    missing = required - covered
    assert not missing, f"no dataset supplies: {sorted(missing)}"


def test_registry_keys_are_unique() -> None:
    keys = [d.key for d in INDUSTRY_DATASETS]
    assert len(keys) == len(set(keys))


def test_every_registry_column_map_starts_with_the_industry_key() -> None:
    # _to_normalized_rows treats the first key as the row's primary key.
    for dataset in INDUSTRY_DATASETS:
        assert next(iter(dataset.column_map)) == "industry", dataset.key


def test_merge_is_an_outer_join_on_industry() -> None:
    a: list[dict[str, Any]] = [
        {"industry": "Semiconductor", "wacc": 0.09},
        {"industry": "Steel", "wacc": 0.08},
    ]
    b: list[dict[str, Any]] = [
        {"industry": "Semiconductor", "op_margin": 0.25},
        {"industry": "Software (System & Application)", "op_margin": 0.18},
    ]
    merged = {row["industry"]: row for row in merge_industry_datasets([a, b])}
    assert merged["Semiconductor"]["wacc"] == pytest.approx(0.09)
    assert merged["Semiconductor"]["op_margin"] == pytest.approx(0.25)
    assert merged["Steel"]["wacc"] == pytest.approx(0.08)
    assert "op_margin" not in merged["Steel"]
    assert merged["Software (System & Application)"]["op_margin"] == pytest.approx(0.18)


def test_merge_later_dataset_does_not_overwrite_a_present_value() -> None:
    # The cost-of-capital file is authoritative for tax_rate; a later file that
    # happens to carry the same column must not clobber it.
    merged = merge_industry_datasets(
        [[{"industry": "Steel", "tax_rate": 0.25}], [{"industry": "Steel", "tax_rate": 0.99}]]
    )
    assert merged[0]["tax_rate"] == pytest.approx(0.25)


def test_merge_skips_rows_without_an_industry() -> None:
    merged = merge_industry_datasets([[{"op_margin": 0.2}, {"industry": "Steel"}]])
    assert [r["industry"] for r in merged] == ["Steel"]


def test_merge_of_nothing_is_empty() -> None:
    assert merge_industry_datasets([]) == []


def _seeded_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    return conn


def test_no_dataset_maps_a_column_the_table_does_not_have() -> None:
    """A stray column_map key would reach INSERT and fail at runtime.

    upsert_industry_rows builds its INSERT column list from the row keys, so a
    key that is not a damodaran_industry column produces a SQL error against the
    real table. Only declared parse artefacts — header strings the parser reads
    and derive_industry_columns consumes and pops before the upsert — are exempt.
    """
    #: Row fields the parser produces that are deliberately not DB columns.
    #: derive_industry_columns turns debt_weight_raw into debt_to_equity plus
    #: beta_unlevered and drops it.
    parse_artefacts = {"debt_weight_raw"}

    conn = _seeded_conn()
    real_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'damodaran_industry'"
        ).fetchall()
    }
    conn.close()
    assert real_columns, "damodaran_industry has no columns; the schema did not apply"

    for dataset in INDUSTRY_DATASETS:
        stray = set(dataset.column_map) - real_columns - parse_artefacts
        assert not stray, f"{dataset.key} maps non-columns: {sorted(stray)}"


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_real_import_fills_the_columns_the_extra_datasets_publish() -> None:
    """The end of the silent-NULL bug: every mapped column arrives populated."""
    conn = _seeded_conn()
    result = import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths=dict(_EXTRA_FIXTURES),
    )
    assert result.status == "success", result.error_message

    columns = (
        "op_margin",
        "net_margin",
        "sales_to_capital",
        "pe",
        "pbv",
        "ev_ebitda",
        "ev_sales",
        "roe",
        "roic",
    )
    counts = conn.execute(
        "SELECT " + ", ".join(f"COUNT({c})" for c in columns) + " FROM damodaran_industry"
    ).fetchone()
    assert counts is not None
    for column, count in zip(columns, counts, strict=True):
        assert count > 0, f"{column} is NULL for every industry"
    conn.close()


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_the_cost_of_capital_file_wins_the_columns_it_shares() -> None:
    """psdata.xls also publishes Net Margin; margin.xls comes first and wins."""
    conn = _seeded_conn()
    import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths={"margin": _EXTRA_FIXTURES["margin"]},
    )
    from_margin_only = conn.execute(
        "SELECT industry, net_margin FROM damodaran_industry "
        "WHERE net_margin IS NOT NULL ORDER BY industry"
    ).fetchall()

    conn2 = _seeded_conn()
    import_damodaran_from_files(
        conn2,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths={
            "margin": _EXTRA_FIXTURES["margin"],
            "psdata": _EXTRA_FIXTURES["psdata"],
        },
    )
    with_psdata = conn2.execute(
        "SELECT industry, net_margin FROM damodaran_industry "
        "WHERE net_margin IS NOT NULL ORDER BY industry"
    ).fetchall()

    assert from_margin_only == with_psdata
    conn.close()
    conn2.close()


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_a_dataset_that_fails_to_parse_degrades_to_partial(tmp_path: Path) -> None:
    """§13.2: one broken extra dataset warns and downgrades, never aborts."""
    conn = _seeded_conn()
    broken = tmp_path / "not-a-workbook.xls"
    broken.write_bytes(b"this is not a spreadsheet")

    result = import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths={"margin": _EXTRA_FIXTURES["margin"], "capex": broken},
    )

    assert result.status == "partial"
    assert result.error_message is not None and "capex" in result.error_message
    # The healthy datasets still landed.
    op_margins = conn.execute(
        "SELECT COUNT(op_margin), COUNT(sales_to_capital) FROM damodaran_industry"
    ).fetchone()
    assert op_margins is not None
    assert op_margins[0] > 0, "margin.xls must still have been imported"
    assert op_margins[1] == 0, "the broken dataset's column stays NULL"
    # Still exactly one refresh_log row.
    rows = conn.execute("SELECT COUNT(*) FROM refresh_log WHERE source = 'damodaran'").fetchone()
    assert rows is not None and rows[0] == 1
    conn.close()


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_download_of_the_full_registry_writes_one_refresh_log_row(tmp_path: Path) -> None:
    """import_damodaran downloads every registry dataset, still logging once."""
    from bot.ingest.damodaran import import_damodaran

    requested: list[str] = []
    sources = {"wacc.xls": _WACC_FIXTURE, "ctryprem.xls": _CTRY_FIXTURE} | {
        f"{key}.xls": path for key, path in _EXTRA_FIXTURES.items()
    }

    def _fake_download(url: str, dest: Path) -> Path:
        requested.append(dest.name)
        return sources[dest.name]

    conn = _seeded_conn()
    with patch("bot.ingest.damodaran.download_dataset", side_effect=_fake_download):
        result = import_damodaran(conn, download_dir=tmp_path, region="US", year=2026)

    assert result.status == "success", result.error_message
    assert sorted(requested) == sorted(sources)
    rows = conn.execute("SELECT COUNT(*) FROM refresh_log WHERE source = 'damodaran'").fetchone()
    assert rows is not None and rows[0] == 1
    conn.close()


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_an_extra_dataset_download_failure_degrades_to_partial(tmp_path: Path) -> None:
    """A 404 on one of the extra files must not lose the rest of the import."""
    from bot.ingest.damodaran import import_damodaran

    sources = {"wacc.xls": _WACC_FIXTURE, "ctryprem.xls": _CTRY_FIXTURE} | {
        f"{key}.xls": path for key, path in _EXTRA_FIXTURES.items()
    }

    def _fake_download(url: str, dest: Path) -> Path:
        if dest.name == "pbvdata.xls":
            raise OSError("404 Not Found")
        return sources[dest.name]

    conn = _seeded_conn()
    with patch("bot.ingest.damodaran.download_dataset", side_effect=_fake_download):
        result = import_damodaran(conn, download_dir=tmp_path, region="US", year=2026)

    assert result.status == "partial"
    assert result.error_message is not None and "pbvdata" in result.error_message
    counts = conn.execute(
        "SELECT COUNT(pe), COUNT(pbv) FROM damodaran_industry"
    ).fetchone()
    assert counts is not None
    assert counts[0] > 0, "pedata.xls must still have been imported"
    assert counts[1] == 0, "the file that 404'd leaves its columns NULL"
    rows = conn.execute("SELECT COUNT(*) FROM refresh_log WHERE source = 'damodaran'").fetchone()
    assert rows is not None and rows[0] == 1
    conn.close()
