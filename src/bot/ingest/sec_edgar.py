"""SEC EDGAR adapter — fetch + parse + import US company fundamentals."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult, ParsedCompanyData
from bot.utils.logging import get_logger

log = get_logger(__name__)

TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class SecEdgarClient:
    """Thin HTTP client for SEC EDGAR public endpoints.

    Note: SEC requires every request to carry a User-Agent identifying the requester
    (per https://www.sec.gov/os/accessing-edgar-data). Provide one explicitly.
    """

    def __init__(self, user_agent: str, timeout: float = 30.0) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent identifying you. Format: 'Your Name email@example.com'"
            )
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._ticker_table: dict[str, str] | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _load_ticker_table(self) -> dict[str, str]:
        if self._ticker_table is not None:
            return self._ticker_table
        r = self._client.get(TICKER_LOOKUP_URL)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        # The file is { "0": {"cik_str": 320193, "ticker": "AAPL", ...}, "1": {...}, ... }
        self._ticker_table = {
            entry["ticker"].upper(): str(entry["cik_str"]).zfill(10) for entry in data.values()
        }
        log.info("sec.ticker_table.loaded", count=len(self._ticker_table))
        return self._ticker_table

    def lookup_cik(self, ticker: str) -> str | None:
        """Return zero-padded 10-digit CIK for a ticker, or None if not found."""
        table = self._load_ticker_table()
        return table.get(ticker.upper())

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        """Fetch XBRL company facts JSON for the given CIK (10-digit zero-padded)."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        url = COMPANY_FACTS_URL_TEMPLATE.format(cik=cik)
        r = self._client.get(url)
        r.raise_for_status()
        result: dict[str, Any] = r.json()
        return result


# ---------- Parser ----------


# XBRL concept (us-gaap) -> our DB column for annual financials.
# Many companies use different concepts for the same thing; the parser tries
# each in order and takes the first one with data.
ANNUAL_CONCEPT_MAP: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": ["OperatingExpenses"],
    "ebit": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense"],
    "tax_expense": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
    "total_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
    "total_equity": ["StockholdersEquity"],
    "goodwill": ["Goodwill"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "depreciation": ["DepreciationDepletionAndAmortization", "Depreciation"],
    "operating_cashflow": ["NetCashProvidedByUsedInOperatingActivities"],
    "dividends_paid": ["PaymentsOfDividends"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}


def parse_company_facts(ticker: str, facts: dict[str, Any]) -> ParsedCompanyData:
    """Normalize SEC company facts JSON into our DB rows."""
    ticker = ticker.upper()
    cik_raw = facts.get("cik")
    cik = str(cik_raw).zfill(10) if cik_raw is not None else None
    name = facts.get("entityName", ticker)

    company: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "name": name,
        "country": "US",
        "currency": "USD",
        "source": "sec_edgar",
        "status": "active",
    }

    us_gaap: dict[str, Any] = facts.get("facts", {}).get("us-gaap", {})
    annual_rows = _collect_period_rows(ticker, us_gaap, fiscal_period="FY", form_prefix="10-K")
    quarterly_rows = _collect_period_rows(
        ticker, us_gaap, fiscal_period_set={"Q1", "Q2", "Q3", "Q4"}, form_prefix="10-Q"
    )
    filings = _collect_filings(ticker, us_gaap)

    return ParsedCompanyData(
        company=company,
        annual=annual_rows,
        quarterly=quarterly_rows,
        filings=filings,
    )


def _collect_period_rows(
    ticker: str,
    us_gaap: dict[str, Any],
    *,
    fiscal_period: str | None = None,
    fiscal_period_set: set[str] | None = None,
    form_prefix: str,
) -> list[dict[str, Any]]:
    """Build per-period rows from the XBRL facts."""
    # period_key -> { db_col -> {"val": ..., "filed": ..., "form": ...} }
    accum: dict[tuple[int, int | None], dict[str, dict[str, Any]]] = {}

    for db_col, concepts in ANNUAL_CONCEPT_MAP.items():
        for concept in concepts:
            entries = us_gaap.get(concept, {}).get("units", {}).get("USD") or us_gaap.get(
                concept, {}
            ).get("units", {}).get("shares")
            if not entries:
                continue
            for e in entries:
                fp = e.get("fp")
                form = e.get("form", "")
                if not form.startswith(form_prefix):
                    continue
                if fiscal_period and fp != fiscal_period:
                    continue
                if fiscal_period_set and fp not in fiscal_period_set:
                    continue
                fy = e.get("fy")
                if fy is None:
                    continue
                q: int | None = (
                    None
                    if fp == "FY"
                    else int(fp[1:])
                    if isinstance(fp, str) and fp.startswith("Q")
                    else None
                )
                key = (fy, q)
                slot = accum.setdefault(key, {})
                existing = slot.get(db_col)
                # Take the latest filing for each (period, column)
                if existing is None or e.get("filed", "") > existing.get("filed", ""):
                    slot[db_col] = {
                        "val": e.get("val"),
                        "filed": e.get("filed"),
                        "form": form,
                        "end": e.get("end"),
                    }
            if any(db_col in slot for slot in accum.values()):
                break  # found a concept with data — don't fall through to alternates

    out: list[dict[str, Any]] = []
    for (fy, q), cols in accum.items():
        is_restated = any(c["form"].endswith("/A") for c in cols.values())
        row: dict[str, Any] = {
            "ticker": ticker,
            "fiscal_year": fy,
            "currency": "USD",
            "source": "sec_edgar",
            "is_restated": is_restated,
        }
        if q is not None:
            row["fiscal_quarter"] = q
        end_dates: list[str] = [str(c["end"]) for c in cols.values() if c.get("end")]
        if end_dates:
            row["period_end_date"] = max(end_dates)
        for db_col, info in cols.items():
            row[db_col] = info["val"]
        # Derived: EBITDA = EBIT + Depreciation (if both present)
        if "ebit" in row and "depreciation" in row:
            row["ebitda"] = (row["ebit"] or 0) + (row["depreciation"] or 0)
        # Derived: FCF = OCF - Capex
        if "operating_cashflow" in row and "capex" in row:
            row["free_cashflow"] = (row["operating_cashflow"] or 0) - (row["capex"] or 0)
        out.append(row)
    return out


def _collect_filings(ticker: str, us_gaap: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract unique (form, filed_date) pairs as filings_log entries."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for concept in us_gaap.values():
        for unit_entries in concept.get("units", {}).values():
            for e in unit_entries:
                form = e.get("form")
                filed = e.get("filed")
                if not form or not filed:
                    continue
                key = (form, filed)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "ticker": ticker,
                        "filing_type": form,
                        "filing_date": filed,
                        "accession_number": e.get("accn"),
                        "source": "sec_edgar",
                    }
                )
    return out


# ---------- Importer + Upsert ----------


def upsert_company(conn: duckdb.DuckDBPyConnection, company: dict[str, Any]) -> None:
    cols = sorted(company.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    conn.execute("DELETE FROM companies WHERE ticker = ?", [company["ticker"]])
    conn.execute(
        f"INSERT INTO companies ({col_list}) VALUES ({placeholders})",
        [company[c] for c in cols],
    )


def upsert_financials_annual(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    all_cols: set[str] = set()
    for r in rows:
        all_cols.update(r.keys())
    cols = sorted(all_cols)

    conn.execute("BEGIN TRANSACTION")
    try:
        tickers = {r["ticker"] for r in rows}
        for ticker in tickers:
            conn.execute("DELETE FROM financials_annual WHERE ticker = ?", [ticker])
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO financials_annual ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def upsert_financials_quarterly(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    all_cols: set[str] = set()
    for r in rows:
        all_cols.update(r.keys())
    cols = sorted(all_cols)

    conn.execute("BEGIN TRANSACTION")
    try:
        tickers = {r["ticker"] for r in rows}
        for ticker in tickers:
            conn.execute("DELETE FROM financials_quarterly WHERE ticker = ?", [ticker])
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO financials_quarterly ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def upsert_filings(conn: duckdb.DuckDBPyConnection, filings: list[dict[str, Any]]) -> int:
    if not filings:
        return 0
    cols = ["ticker", "filing_type", "filing_date", "accession_number", "source"]
    placeholders = ", ".join(["?"] * len(cols))
    inserted = 0
    for f in filings:
        conn.execute(
            "DELETE FROM filings_log WHERE ticker = ? AND filing_type = ? AND filing_date = ? AND source = ?",
            [f["ticker"], f["filing_type"], f["filing_date"], f["source"]],
        )
        conn.execute(
            f"INSERT INTO filings_log ({', '.join(cols)}) VALUES ({placeholders})",
            [f.get(c) for c in cols],
        )
        inserted += 1
    return inserted


def import_company_from_sec(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    user_agent: str,
) -> IngestResult:
    """Fetch + parse + upsert one US ticker from SEC EDGAR."""
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    try:
        with SecEdgarClient(user_agent=user_agent) as client:
            cik = client.lookup_cik(ticker)
            if cik is None:
                raise ValueError(f"Ticker {ticker} not found in SEC EDGAR ticker table")
            facts = client.fetch_company_facts(cik)
        parsed = parse_company_facts(ticker, facts)
        upsert_company(conn, parsed.company)
        annual = upsert_financials_annual(conn, parsed.annual)
        quarterly = upsert_financials_quarterly(conn, parsed.quarterly)
        filings = upsert_filings(conn, parsed.filings)
        total = 1 + annual + quarterly + filings
        result: IngestResult = IngestResult(
            source="sec_edgar",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="success",
            rows_affected=total,
            details={
                "ticker": ticker,
                "annual": annual,
                "quarterly": quarterly,
                "filings": filings,
            },
        )
    except Exception as e:
        log.exception("sec_edgar.import.failed", ticker=ticker, error=str(e))
        result = IngestResult(
            source="sec_edgar",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="error",
            error_message=str(e),
            details={"ticker": ticker},
        )

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
    return result
