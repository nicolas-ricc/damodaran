import logging
from collections.abc import Iterator
from pathlib import Path

import openpyxl
import pytest
import structlog
from structlog.testing import capture_logs

from bot.ingest.damodaran import (
    DEFAULT_COUNTRY_COLUMN_MAP,
    INDUSTRY_PARSE_ARTEFACT_COLUMNS,
    WACC_COLUMN_MAP,
    parse_country_xls,
    parse_industry_xls,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"


@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran wacc fixture not downloaded; run Task 7 Step 1.",
)
def test_parse_industry_xls_returns_rows():
    rows = parse_industry_xls(
        FIXTURES / "wacc_sample.xls",
        region="US",
        year=2026,
        column_map={**WACC_COLUMN_MAP, **INDUSTRY_PARSE_ARTEFACT_COLUMNS},
    )
    assert len(rows) > 50  # Damodaran publishes ~90+ industries
    sample = rows[0]
    assert "industry" in sample
    assert sample["region"] == "US"
    assert sample["year"] == 2026
    numeric_keys = {"wacc", "cost_of_equity", "beta_levered"}
    assert any(sample.get(k) is not None for k in numeric_keys)
    # D/(D+E) is mapped as a parsing artefact so derive_industry_columns can turn it
    # into debt_to_equity; without it every equity/debt weight resolves to None.
    assert any(isinstance(r.get("debt_weight_raw"), float) for r in rows)


@pytest.mark.skipif(
    not (FIXTURES / "ctryprem_sample.xls").exists(),
    reason="Damodaran ctryprem fixture not downloaded; run Task 7 Step 1.",
)
def test_parse_country_xls_returns_rows():
    rows = parse_country_xls(
        FIXTURES / "ctryprem_sample.xls",
        year=2026,
        column_map=DEFAULT_COUNTRY_COLUMN_MAP,
    )
    assert len(rows) > 100  # ~150 countries
    sample = rows[0]
    assert "country" in sample
    assert sample["year"] == 2026
    assert any(sample.get(k) is not None for k in {"erp", "country_risk_premium"})


@pytest.mark.skipif(
    not (FIXTURES / "ctryprem_sample.xls").exists(),
    reason="Damodaran ctryprem fixture not downloaded; run Task 7 Step 1.",
)
def test_country_parse_reads_both_tables() -> None:
    """The ERPs-by-country sheet holds two differently-shaped tables.

    Below the Moody's-rated table sits a second one of unrated countries scored
    by PRS, whose columns do not line up with the first. Each table is read with
    its own columns, and ``erp_basis`` says which one a row came from.
    """
    rows = parse_country_xls(
        FIXTURES / "ctryprem_sample.xls",
        year=2026,
        column_map=DEFAULT_COUNTRY_COLUMN_MAP,
    )
    assert len(rows) == 178
    assert sum(r["erp_basis"] == "moodys_rating" for r in rows) == 157
    # Hand-read from rows 167-187 of the fixture.
    assert sorted(r["country"] for r in rows if r["erp_basis"] == "prs_score") == [
        "Algeria", "Brunei", "Gambia", "Guinea", "Guinea-Bissau", "Guyana", "Haiti",
        "Iran", "Korea, D.P.R.", "Liberia", "Libya", "Madagascar", "Malawi", "Myanmar",
        "Russia", "Sierra Leone", "Somalia", "Sudan", "Syria", "Yemen, Republic",
        "Zimbabwe",
    ]

    countries = {r["country"] for r in rows}
    assert "United States" in countries
    # The title row above the second table and its header are not countries.
    assert "Frontier Markets (no sovereign ratings)" not in countries
    assert "Country" not in countries

    # No region may be a number: that was the PRS score bleeding through.
    for row in rows:
        region = row.get("region")
        if region is None:
            continue
        assert isinstance(region, str)
        with pytest.raises(ValueError):
            float(region)

    by_country = {r["country"]: r for r in rows}
    algeria = by_country["Algeria"]
    assert algeria["erp"] == pytest.approx(0.10057659756375703)
    assert algeria["country_risk_premium"] == pytest.approx(0.058276597563757034)
    assert algeria["prs_score"] == 67.0
    assert algeria["erp_basis"] == "prs_score"
    assert algeria["region"] is None
    assert algeria["rating"] is None

    abu = by_country["Abu Dhabi"]
    assert abu["region"] == "Middle East"
    assert abu["rating"] == "Aa2"
    assert abu["erp"] == pytest.approx(0.0486906451636496)
    assert abu["erp_basis"] == "moodys_rating"
    assert abu.get("prs_score") is None


def _write_country_sheet(path: Path, rows: list[list[object]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "ERPs by country"
    for row in rows:
        ws.append(row)
    wb.save(path)


_RATED_HEADER = [
    "Country",
    "Africa",
    "Moody's rating",
    "Total Equity Risk Premium",
    "Country Risk Premium",
]
_PRS_HEADER = ["Country", "PRS Composite Risk Score", "ERP", "CRP", "Default Spread"]


@pytest.fixture
def debug_logs() -> Iterator[None]:
    """Let debug events through even after a test configured logging at INFO."""
    saved = structlog.get_config()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG))
    yield
    structlog.configure(**saved)


@pytest.mark.usefixtures("debug_logs")
def test_country_parse_two_tables_drops_title_row_and_prs_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "ctryprem.xlsx"
    _write_country_sheet(
        path,
        [
            _RATED_HEADER,
            ["United States", "North America", "Aaa", 0.05, 0.0],
            ["Brazil", "Latin America", "Ba2", 0.09, 0.04],
            ["Frontier Markets (no sovereign ratings)", None, None, None, None],
            _PRS_HEADER,
            ["Algeria", 67, 0.10, 0.058, 0.038],
            ["Brazil", 60, 0.12, 0.07, 0.05],
            [None, None, None, None, None],
            [None, "A1", 59.9, None, None],
        ],
    )

    with capture_logs() as logs:
        rows = parse_country_xls(path, year=2026, column_map=DEFAULT_COUNTRY_COLUMN_MAP)

    assert [r["country"] for r in rows] == ["United States", "Brazil", "Algeria"]
    brazil = rows[1]
    assert brazil["erp"] == pytest.approx(0.09)
    assert brazil["erp_basis"] == "moodys_rating"
    algeria = rows[2]
    assert algeria["erp_basis"] == "prs_score"
    assert algeria["prs_score"] == 67
    assert algeria["erp"] == pytest.approx(0.10)
    assert algeria["region"] is None
    assert algeria["rating"] is None
    assert "Default Spread" not in algeria

    duplicates = [e for e in logs if e["event"] == "damodaran.country.prs_duplicate"]
    assert [e["country"] for e in duplicates] == ["Brazil"]
    assert duplicates[0]["log_level"] == "warning"
    titles = [e for e in logs if e["event"] == "damodaran.country.title_row_dropped"]
    assert [(e["country"], e["log_level"]) for e in titles] == [
        ("Frontier Markets (no sovereign ratings)", "debug")
    ]
    tables = [e for e in logs if e["event"] == "damodaran.country.tables_read"]
    assert [(e["rated"], e["prs"]) for e in tables] == [(2, 1)]


def test_country_parse_single_table_sheet_has_only_rated_rows(tmp_path: Path) -> None:
    path = tmp_path / "ctryprem.xlsx"
    _write_country_sheet(
        path,
        [
            _RATED_HEADER,
            ["United States", "North America", "Aaa", 0.05, 0.0],
            ["Brazil", "Latin America", "Ba2", 0.09, 0.04],
        ],
    )

    rows = parse_country_xls(path, year=2026, column_map=DEFAULT_COUNTRY_COLUMN_MAP)

    assert [r["country"] for r in rows] == ["United States", "Brazil"]
    assert {r["erp_basis"] for r in rows} == {"moodys_rating"}


@pytest.mark.skipif(
    not (FIXTURES / "ctryprem_sample.xls").exists(),
    reason="Damodaran ctryprem fixture not downloaded; run Task 7 Step 1.",
)
def test_first_table_erp_is_the_equity_risk_premium() -> None:
    rows = {
        r["country"]: r
        for r in parse_country_xls(
            FIXTURES / "ctryprem_sample.xls",
            year=2026,
            column_map=DEFAULT_COUNTRY_COLUMN_MAP,
        )
    }
    abu = rows["Abu Dhabi"]
    assert abu["region"] == "Middle East"
    assert abu["rating"] == "Aa2"
    assert abu["erp"] == pytest.approx(0.0486906451636496)
    assert abu["country_risk_premium"] == pytest.approx(0.0063906451636495986)


def test_parse_industry_xls_skips_blank_rows(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Industry Averages"
    ws.append(["Industry Name", "Cost of Equity", "WACC"])
    ws.append(["Software", 0.10, 0.09])
    ws.append([None, None, None])
    ws.append(["Retail", 0.08, 0.07])
    path = tmp_path / "tiny.xlsx"
    wb.save(path)

    mapping = {
        "industry": "Industry Name",
        "cost_of_equity": "Cost of Equity",
        "wacc": "WACC",
    }
    rows = parse_industry_xls(
        path, region="US", year=2026, column_map=mapping, sheet_name="Industry Averages"
    )
    assert len(rows) == 2
    assert {r["industry"] for r in rows} == {"Software", "Retail"}
