from pathlib import Path

import pytest

from bot.ingest.damodaran import (
    DEFAULT_COUNTRY_COLUMN_MAP,
    DEFAULT_INDUSTRY_COLUMN_MAP,
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
        column_map=DEFAULT_INDUSTRY_COLUMN_MAP,
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
def test_country_parse_stops_at_the_second_table() -> None:
    """The ERPs-by-country sheet holds two differently-shaped tables.

    Rows after the second table's header carry PRS scores where the first table
    has regions, and the Default Spread column where it has the ERP — so reading
    them with the first table's column positions stored a wrong ERP for 21
    countries. Parsing must stop at the boundary.
    """
    rows = parse_country_xls(
        FIXTURES / "ctryprem_sample.xls",
        year=2026,
        column_map=DEFAULT_COUNTRY_COLUMN_MAP,
    )
    assert len(rows) == 158, "only the Moody's-rated first table"

    countries = {r["country"] for r in rows}
    assert "United States" in countries
    assert "Abu Dhabi" in countries
    # Second-table countries must be absent rather than present with wrong figures.
    for absent in ("Algeria", "Brunei", "Gambia", "Guinea"):
        assert absent not in countries, absent

    # No region may be a number: that was the PRS score bleeding through.
    for row in rows:
        region = row.get("region")
        if region is None:
            continue
        assert isinstance(region, str)
        with pytest.raises(ValueError):
            float(region)


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
