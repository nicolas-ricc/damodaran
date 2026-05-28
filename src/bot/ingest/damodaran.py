"""Damodaran datasets — downloader, parser, importer (Capa A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import httpx
import polars as pl

from bot.ingest.base import IngestResult
from bot.utils.logging import get_logger

log = get_logger(__name__)

DEFAULT_INDUSTRY_COLUMN_MAP: dict[str, str] = {
    "industry": "Industry Name",
    "cost_of_equity": "Cost of Equity",
    "cost_of_debt": "Cost of Debt",
    "wacc": "Cost of Capital",
    "beta_levered": "Beta",
    "beta_unlevered": "Unlevered beta",
    "debt_to_equity": "D/E Ratio",
    "tax_rate": "Tax Rate",
}

DEFAULT_COUNTRY_COLUMN_MAP: dict[str, str] = {
    "country": "Country",
    "rating": "Moody's rating",
    "erp": "Total Equity Risk Premium",
    "country_risk_premium": "Country Risk Premium",
    "region": "Region",
}

INDUSTRY_WACC_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/wacc.xls"
COUNTRY_RISK_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xls"


def _load_workbook_to_df(path: Path, sheet_name: str | None) -> pl.DataFrame:
    """Read an xls/xlsx file into a Polars DataFrame, picking the first matching sheet."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception:
        import xlrd  # type: ignore[import-untyped]

        book = xlrd.open_workbook(str(path))
        sheets = book.sheet_names()
        if sheet_name and sheet_name in sheets:
            picked = sheet_name
        else:
            picked = next(
                (s for s in sheets if "industry" in s.lower() or "country" in s.lower()),
                sheets[0],
            )
        ws = book.sheet_by_name(picked)
        rows = [ws.row_values(r) for r in range(ws.nrows)]
        header_idx = _find_header_row(rows)
        header = rows[header_idx]
        data_rows = rows[header_idx + 1 :]
        return pl.DataFrame(
            {
                str(h): [r[i] if i < len(r) else None for r in data_rows]
                for i, h in enumerate(header)
            }
        )

    if sheet_name:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' not found. Available: {wb.sheetnames}")
        picked = sheet_name
    else:
        picked = next(
            (
                s
                for s in wb.sheetnames
                if "industry" in s.lower() or "country" in s.lower() or "average" in s.lower()
            ),
            wb.sheetnames[0],
        )
    ws = wb[picked]
    rows_raw = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows_raw:
        return pl.DataFrame()
    header_idx = _find_header_row(rows_raw)
    header = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows_raw[header_idx])]
    data_rows = rows_raw[header_idx + 1 :]
    cols: dict[str, list[Any]] = {h: [] for h in header}
    for r in data_rows:
        for i, h in enumerate(header):
            cols[h].append(r[i] if i < len(r) else None)
    return pl.DataFrame(cols)


def _find_header_row(rows: list[list[Any]]) -> int:
    """Find the row index that looks like a header (mostly non-numeric, non-empty)."""
    for i, r in enumerate(rows[:20]):
        non_empty = [c for c in r if c is not None and str(c).strip() != ""]
        if len(non_empty) >= 3 and sum(1 for c in non_empty if isinstance(c, str)) >= 2:
            return i
    return 0


def _to_normalized_rows(
    df: pl.DataFrame, column_map: dict[str, str], constants: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply column mapping; drop rows with empty primary key field; coerce numerics."""
    pk_field = next(iter(column_map))
    out: list[dict[str, Any]] = []
    for record in df.to_dicts():
        normalized: dict[str, Any] = dict(constants)
        for db_col, xls_col in column_map.items():
            if xls_col not in record:
                continue
            value = record[xls_col]
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    value = None
                elif value.endswith("%"):
                    import contextlib

                    with contextlib.suppress(ValueError):
                        value = float(value[:-1]) / 100.0
            normalized[db_col] = value
        if normalized.get(pk_field) in (None, ""):
            continue
        out.append(normalized)
    return out


def parse_industry_xls(
    path: Path,
    *,
    region: str,
    year: int,
    column_map: dict[str, str],
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a Damodaran industry-level xls into normalized rows."""
    df = _load_workbook_to_df(path, sheet_name)
    if df.is_empty():
        log.warning("damodaran.industry.empty_file", path=str(path))
        return []
    return _to_normalized_rows(df, column_map, {"region": region, "year": year})


def parse_country_xls(
    path: Path,
    *,
    year: int,
    column_map: dict[str, str],
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a Damodaran country-level xls into normalized rows."""
    df = _load_workbook_to_df(path, sheet_name)
    if df.is_empty():
        log.warning("damodaran.country.empty_file", path=str(path))
        return []
    return _to_normalized_rows(df, column_map, {"year": year})


# ---------- Downloader ----------


def download_dataset(url: str, dest: Path, timeout: float = 60.0) -> Path:
    """Download a Damodaran xls/xlsx file to `dest`. Overwrites if present."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    log.info("damodaran.download.ok", url=url, dest=str(dest), bytes=len(response.content))
    return dest


# ---------- Upsert ----------


def upsert_industry_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Upsert into damodaran_industry. Returns number of rows affected."""
    if not rows:
        return 0
    all_columns: set[str] = set()
    for r in rows:
        all_columns.update(r.keys())
    cols = sorted(all_columns)

    conn.execute("BEGIN TRANSACTION")
    try:
        pairs = {(r["region"], r["year"]) for r in rows}
        for region, year in pairs:
            conn.execute(
                "DELETE FROM damodaran_industry WHERE region = ? AND year = ?",
                [region, year],
            )
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO damodaran_industry ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def upsert_country_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Upsert into damodaran_country. Returns number of rows affected."""
    if not rows:
        return 0
    all_columns: set[str] = set()
    for r in rows:
        all_columns.update(r.keys())
    cols = sorted(all_columns)

    conn.execute("BEGIN TRANSACTION")
    try:
        years = {r["year"] for r in rows}
        for year in years:
            conn.execute("DELETE FROM damodaran_country WHERE year = ?", [year])
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO damodaran_country ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


# ---------- High-level importers ----------


def _log_refresh(conn: duckdb.DuckDBPyConnection, result: IngestResult, run_id: str) -> None:
    conn.execute(
        """
        INSERT INTO refresh_log
            (source, run_id, started_at, finished_at, status, rows_affected, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            result.source,
            run_id,
            result.started_at,
            result.finished_at,
            result.status,
            result.rows_affected,
            result.error_message,
        ],
    )


def import_damodaran_from_files(
    conn: duckdb.DuckDBPyConnection,
    *,
    industry_path: Path,
    country_path: Path,
    region: str,
    year: int,
) -> IngestResult:
    """Import already-downloaded Damodaran files into the DB."""
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    try:
        industry_rows = parse_industry_xls(
            industry_path,
            region=region,
            year=year,
            column_map=DEFAULT_INDUSTRY_COLUMN_MAP,
        )
        country_rows = parse_country_xls(
            country_path,
            year=year,
            column_map=DEFAULT_COUNTRY_COLUMN_MAP,
        )
        total = upsert_industry_rows(conn, industry_rows) + upsert_country_rows(conn, country_rows)
        result = IngestResult(
            source="damodaran",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="success",
            rows_affected=total,
            details={
                "industry_rows": len(industry_rows),
                "country_rows": len(country_rows),
                "region": region,
                "year": year,
            },
        )
    except Exception as e:
        log.exception("damodaran.import.failed", error=str(e))
        result = IngestResult(
            source="damodaran",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="error",
            error_message=str(e),
        )
    _log_refresh(conn, result, run_id)
    return result


def import_damodaran(
    conn: duckdb.DuckDBPyConnection,
    *,
    download_dir: Path,
    region: str = "US",
    year: int | None = None,
    industry_url: str = INDUSTRY_WACC_URL,
    country_url: str = COUNTRY_RISK_URL,
) -> IngestResult:
    """Download and import current-year Damodaran datasets."""
    year = year or datetime.utcnow().year
    industry_path = download_dataset(industry_url, download_dir / "wacc.xls")
    country_path = download_dataset(country_url, download_dir / "ctryprem.xls")
    return import_damodaran_from_files(
        conn,
        industry_path=industry_path,
        country_path=country_path,
        region=region,
        year=year,
    )
