"""Damodaran datasets — parser (Capa A).

Column headers reflect the January 2026 Damodaran release.  If headers drift in
a future release, update ``DEFAULT_INDUSTRY_COLUMN_MAP`` and
``DEFAULT_COUNTRY_COLUMN_MAP`` to match the new strings; no other code change is
required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Column maps — db_column_name -> xls_header_string
# Inspected from Damodaran Jan-2026 files:
#   wacc.xls      sheet "Industry Averages"   header row 18
#   ctryprem.xls  sheet "ERPs by country"     header row 7
# ---------------------------------------------------------------------------

DEFAULT_INDUSTRY_COLUMN_MAP: dict[str, str] = {
    "industry": "Industry Name",
    "beta_levered": "Beta",
    "cost_of_equity": "Cost of Equity",
    "cost_of_debt": "Cost of Debt",
    "tax_rate": "Tax Rate",
    # "Cost of Capital" is labelled "WACC" in the DB schema
    "wacc": "Cost of Capital",
}

DEFAULT_COUNTRY_COLUMN_MAP: dict[str, str] = {
    "country": "Country",
    # The region column header is literally "Africa" in the file (column B),
    # but the values are regional groupings such as "Middle East", "Western
    # Europe", etc.  We capture it under "region" in the DB.
    "region": "Africa",
    "rating": "Moody's rating",
    "erp": "Total Equity Risk Premium",
    "country_risk_premium": "Country Risk Premium",
}

INDUSTRY_WACC_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/wacc.xls"
COUNTRY_RISK_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xls"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Keywords checked in priority order (most-specific first).
# For country files, "erps by" matches "ERPs by country" before the more
# generic "country" keyword would pick up "Country Lookup".
_INDUSTRY_KEYWORDS = ("industry",)
_COUNTRY_KEYWORDS = ("erps by", "erp by", "erp")
_AVERAGE_KEYWORDS = ("average",)


def _find_header_row(rows: list[list[Any]]) -> int:
    """Return the index of the best column-header row in the first 25 rows.

    The strategy is to find the row that is:
    1. Entirely composed of string values (no numerics in non-empty cells), AND
    2. Has the most non-empty cells — the widest all-string row is the header.

    Damodaran sheets typically have a few preamble rows with 2-3 string cells
    followed by the true header which spans all columns.  Choosing the widest
    all-string row reliably picks the real header over preamble rows.
    """
    best_idx = 0
    best_count = 0
    for i, r in enumerate(rows[:25]):
        non_empty = [c for c in r if c is not None and str(c).strip() != ""]
        if len(non_empty) < 3:
            continue
        numeric_cells = [c for c in non_empty if isinstance(c, (int, float))]
        string_cells = [c for c in non_empty if isinstance(c, str)]
        # Only consider rows that are entirely strings (no numerics).
        if len(numeric_cells) == 0 and len(string_cells) > best_count:
            best_count = len(string_cells)
            best_idx = i
    return best_idx


def _pick_sheet(names: list[str], keywords: tuple[str, ...]) -> str:
    """Return the best-matching sheet name from *names* using *keywords*.

    Keywords are checked in priority order: the first keyword that matches any
    sheet wins, and among sheets matching that keyword the first one is returned.
    Falls back to the first sheet if nothing matches.
    """
    lower_names = [n.lower() for n in names]
    for kw in keywords:
        for i, lower in enumerate(lower_names):
            if kw in lower:
                return names[i]
    return names[0]


def _load_rows(path: Path, sheet_name: str | None) -> tuple[list[list[Any]], str]:
    """Load all cell values from *path*, returning (rows, picked_sheet_name).

    Tries openpyxl first (xlsx), then falls back to xlrd (legacy xls).
    """
    try:
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        names: list[str] = list(wb.sheetnames)
        if sheet_name is not None:
            if sheet_name not in names:
                raise ValueError(f"Sheet {sheet_name!r} not found in {path}. Available: {names}")
            picked = sheet_name
        else:
            picked = _pick_sheet(names, _INDUSTRY_KEYWORDS + _COUNTRY_KEYWORDS + _AVERAGE_KEYWORDS)
        ws = wb[picked]
        rows: list[list[Any]] = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows, picked
    except Exception as exc:
        log.info(
            "damodaran.openpyxl_failed_falling_back_to_xlrd",
            path=str(path),
            error=str(exc),
        )

    import xlrd  # type: ignore[import-untyped]

    book = xlrd.open_workbook(str(path))
    names_xlrd: list[str] = book.sheet_names()
    if sheet_name is not None:
        if sheet_name not in names_xlrd:
            raise ValueError(f"Sheet {sheet_name!r} not found in {path}. Available: {names_xlrd}")
        picked_xlrd = sheet_name
    else:
        picked_xlrd = _pick_sheet(
            names_xlrd, _INDUSTRY_KEYWORDS + _COUNTRY_KEYWORDS + _AVERAGE_KEYWORDS
        )
    ws_xlrd = book.sheet_by_name(picked_xlrd)
    xlrd_rows: list[list[Any]] = [ws_xlrd.row_values(r) for r in range(ws_xlrd.nrows)]
    return xlrd_rows, picked_xlrd


def _load_to_records(path: Path, sheet_name: str | None) -> list[dict[str, Any]]:
    """Read xls/xlsx, detect the header row, and return a list of row dicts.

    Using raw dicts instead of a Polars DataFrame avoids type-inference issues
    with Damodaran sheets that mix strings, floats, and ``None`` in the same
    column.
    """
    rows, picked = _load_rows(path, sheet_name)
    log.debug("damodaran.sheet_picked", path=str(path), sheet=picked)

    if not rows:
        return []

    header_idx = _find_header_row(rows)
    header_raw = rows[header_idx]

    # Deduplicate and sanitize column names.
    seen: dict[str, int] = {}
    header: list[str] = []
    for i, h in enumerate(header_raw):
        name = str(h).strip() if h is not None and str(h).strip() else f"col_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        header.append(name)

    records: list[dict[str, Any]] = []
    for r in rows[header_idx + 1 :]:
        records.append({h: (r[i] if i < len(r) else None) for i, h in enumerate(header)})
    return records


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _coerce_value(value: Any) -> Any:
    """Coerce a single cell value: strip strings, parse percentage strings."""
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
        if value.endswith("%"):
            try:
                return float(value[:-1]) / 100.0
            except ValueError:
                pass
    return value


def _to_normalized_rows(
    records: list[dict[str, Any]],
    column_map: dict[str, str],
    constants: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply *column_map*, attach *constants*, drop blank-PK rows.

    The first key in *column_map* is treated as the primary-key field; any
    row whose PK value is blank/None is dropped.
    """
    pk_field = next(iter(column_map))
    out: list[dict[str, Any]] = []

    for record in records:
        normalized: dict[str, Any] = dict(constants)
        for db_col, xls_col in column_map.items():
            if xls_col not in record:
                continue
            normalized[db_col] = _coerce_value(record[xls_col])

        pk_val = normalized.get(pk_field)
        if pk_val is None or (isinstance(pk_val, str) and pk_val == ""):
            continue
        out.append(normalized)

    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_industry_xls(
    path: Path,
    *,
    region: str,
    year: int,
    column_map: dict[str, str],
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a Damodaran industry-level xls into normalized rows.

    Args:
        path: Path to the ``.xls`` / ``.xlsx`` file.
        region: Region tag injected into every row (e.g. ``"US"``).
        year: Data year injected into every row.
        column_map: Mapping ``db_column_name -> xls_header_string``.
        sheet_name: Explicit sheet to open; auto-detected when *None*.

    Returns:
        List of dicts ready for DB upsert.
    """
    records = _load_to_records(path, sheet_name)
    if not records:
        log.warning("damodaran.industry.empty_file", path=str(path))
        return []
    return _to_normalized_rows(records, column_map, {"region": region, "year": year})


def parse_country_xls(
    path: Path,
    *,
    year: int,
    column_map: dict[str, str],
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a Damodaran country-level xls into normalized rows.

    Args:
        path: Path to the ``.xls`` / ``.xlsx`` file.
        year: Data year injected into every row.
        column_map: Mapping ``db_column_name -> xls_header_string``.
        sheet_name: Explicit sheet to open; auto-detected when *None*.

    Returns:
        List of dicts ready for DB upsert.
    """
    records = _load_to_records(path, sheet_name)
    if not records:
        log.warning("damodaran.country.empty_file", path=str(path))
        return []
    return _to_normalized_rows(records, column_map, {"year": year})
