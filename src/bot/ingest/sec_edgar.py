"""SEC EDGAR adapter — fetch + parse + import US company fundamentals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult, refresh_run, transaction
from bot.utils.logging import get_logger

log = get_logger(__name__)

TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class SecEdgarClient:
    """Thin HTTP client for SEC EDGAR public endpoints.

    SEC requires every request to carry a User-Agent identifying the requester
    (per https://www.sec.gov/os/accessing-edgar-data).
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
        data = r.json()
        # File is { "0": {"cik_str": 320193, "ticker": "AAPL", ...}, ... }
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


@dataclass
class ParsedCompanyData:
    """Result of parsing SEC company facts JSON."""

    company: dict[str, Any]
    annual: list[dict[str, Any]] = field(default_factory=list)
    quarterly: list[dict[str, Any]] = field(default_factory=list)
    filings: list[dict[str, Any]] = field(default_factory=list)


# XBRL concept (us-gaap) -> our DB column. Multiple alternative concepts per column;
# parser uses the first one with data.
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

    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    annual_rows = _collect_period_rows(
        ticker, us_gaap, fiscal_period="FY", allowed_forms={"10-K", "10-K/A"}
    )
    quarterly_rows = _collect_period_rows(
        ticker,
        us_gaap,
        fiscal_period_set={"Q1", "Q2", "Q3", "Q4"},
        allowed_forms={"10-Q", "10-Q/A"},
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
    allowed_forms: set[str],
) -> list[dict[str, Any]]:
    """Build per-period rows from the XBRL facts. Latest filing wins per (period, column)."""
    # accum: (fy, quarter_or_None) -> { db_col -> {"val", "filed", "form", "end"} }
    accum: dict[tuple[int, int | None], dict[str, dict[str, Any]]] = {}
    # forms_seen: track ALL forms observed for each (fy, q) slot to compute is_restated correctly
    forms_seen: dict[tuple[int, int | None], set[str]] = {}

    for db_col, concepts in ANNUAL_CONCEPT_MAP.items():
        for concept in concepts:
            unit_map = us_gaap.get(concept, {}).get("units", {})
            entries = unit_map.get("USD") or unit_map.get("shares") or []
            if not entries:
                continue
            found_any = False
            for e in entries:
                fp = e.get("fp")
                form = e.get("form", "")
                if form not in allowed_forms:
                    continue
                if fiscal_period and fp != fiscal_period:
                    continue
                if fiscal_period_set and fp not in fiscal_period_set:
                    continue
                fy = e.get("fy")
                if fy is None:
                    continue
                q = None
                if fp and fp.startswith("Q"):
                    try:
                        q = int(fp[1:])
                    except ValueError:
                        q = None
                key = (fy, q)
                # Track every form seen for this period slot
                forms_seen.setdefault(key, set()).add(form)
                slot = accum.setdefault(key, {})
                existing = slot.get(db_col)
                if existing is None or e.get("filed", "") > existing.get("filed", ""):
                    slot[db_col] = {
                        "val": e.get("val"),
                        "filed": e.get("filed"),
                        "form": form,
                        "end": e.get("end"),
                    }
                    found_any = True
            if found_any:
                break  # found a concept with data — don't fall through

    out: list[dict[str, Any]] = []
    for (fy, q), cols in accum.items():
        # is_restated is True if ANY historical form for this period was an amendment (/A)
        is_restated = any(f.endswith("/A") for f in forms_seen.get((fy, q), set()))
        row: dict[str, Any] = {
            "ticker": ticker,
            "fiscal_year": fy,
            "currency": "USD",
            "source": "sec_edgar",
            "is_restated": is_restated,
        }
        if q is not None:
            row["fiscal_quarter"] = q
        end_dates: list[str] = [c["end"] for c in cols.values() if c.get("end")]
        if end_dates:
            row["period_end_date"] = max(end_dates)
        for db_col, info in cols.items():
            row[db_col] = info["val"]
        # Derived: EBITDA = EBIT + Depreciation (when both present)
        if row.get("ebit") is not None and row.get("depreciation") is not None:
            row["ebitda"] = row["ebit"] + row["depreciation"]
        # Derived: FCF = OCF - Capex
        if row.get("operating_cashflow") is not None and row.get("capex") is not None:
            row["free_cashflow"] = row["operating_cashflow"] - row["capex"]
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


# ---------- Importer + Upserts ----------


def upsert_company(conn: duckdb.DuckDBPyConnection, company: dict[str, Any]) -> None:
    """Replace the company row by ticker. Assumes called within a transaction."""
    cols = sorted(company.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    conn.execute("DELETE FROM companies WHERE ticker = ?", [company["ticker"]])
    conn.execute(
        f"INSERT INTO companies ({col_list}) VALUES ({placeholders})",
        [company[c] for c in cols],
    )


def upsert_financials_annual(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Replace all financials_annual rows for the tickers present. Returns row count."""
    if not rows:
        return 0
    all_cols: set[str] = set()
    for r in rows:
        all_cols.update(r.keys())
    cols = sorted(all_cols)

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
    return len(rows)


FINANCIALS_QUARTERLY_COLS = {
    "ticker",
    "fiscal_year",
    "fiscal_quarter",
    "period_end_date",
    "currency",
    "revenue",
    "ebit",
    "ebitda",
    "net_income",
    "operating_cashflow",
    "free_cashflow",
    "total_debt",
    "cash",
    "is_restated",
    "source",
}


def upsert_financials_quarterly(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Replace all financials_quarterly rows for the tickers present. Returns row count."""
    if not rows:
        return 0
    # Filter rows to only columns that exist in financials_quarterly and have fiscal_quarter
    filtered: list[dict[str, Any]] = []
    for r in rows:
        if r.get("fiscal_quarter") is None:
            continue
        filtered.append({k: v for k, v in r.items() if k in FINANCIALS_QUARTERLY_COLS})
    if not filtered:
        return 0

    all_cols: set[str] = set()
    for r in filtered:
        all_cols.update(r.keys())
    cols = sorted(all_cols)

    tickers = {r["ticker"] for r in filtered}
    for ticker in tickers:
        conn.execute("DELETE FROM financials_quarterly WHERE ticker = ?", [ticker])
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    for r in filtered:
        conn.execute(
            f"INSERT INTO financials_quarterly ({col_list}) VALUES ({placeholders})",
            [r.get(c) for c in cols],
        )
    return len(filtered)


def upsert_filings(conn: duckdb.DuckDBPyConnection, filings: list[dict[str, Any]]) -> int:
    """Replace filings_log entries on PK match. Returns row count."""
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
    """Fetch + parse + upsert one US ticker from SEC EDGAR. Atomic on the DB side."""
    with refresh_run(
        conn,
        source="sec_edgar",
        log=log,
        error_event="sec_edgar.import.failed",
        log_fail_event="sec_edgar.refresh_log_insert_failed",
    ) as run:
        run.details = {"ticker": ticker}

        with SecEdgarClient(user_agent=user_agent) as client:
            cik = client.lookup_cik(ticker)
            if cik is None:
                raise ValueError(f"Ticker {ticker} not found in SEC EDGAR ticker table")
            facts = client.fetch_company_facts(cik)
        parsed = parse_company_facts(ticker, facts)

        with transaction(conn):
            upsert_company(conn, parsed.company)
            annual = upsert_financials_annual(conn, parsed.annual)
            quarterly = upsert_financials_quarterly(conn, parsed.quarterly)
            filings = upsert_filings(conn, parsed.filings)

        run.rows_affected = 1 + annual + quarterly + filings
        run.details = {
            "ticker": ticker,
            "annual": annual,
            "quarterly": quarterly,
            "filings": filings,
        }
    assert run.result is not None  # refresh_run always sets it on exit
    return run.result
