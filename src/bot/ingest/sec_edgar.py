"""SEC EDGAR adapter — fetch + parse + import US company fundamentals."""

from __future__ import annotations

from datetime import date
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult, coerce_date, refresh_run, transaction
from bot.ingest.provider import CompanyInfo, ParsedCompanyData, ProviderRateLimitError
from bot.utils.logging import get_logger

log = get_logger(__name__)

TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_CONCEPT_URL_TEMPLATE = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/dei/"
    "EntityCommonStockSharesOutstanding.json"
)

_FINANCIAL_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A"}


class EdgarRateLimitError(ProviderRateLimitError):
    """EDGAR throttled us (429, or the 403 it serves for abusive traffic)."""


class SecEdgarClient:
    """Thin HTTP client for SEC EDGAR public endpoints.

    SEC requires every request to carry a User-Agent identifying the requester
    (per https://www.sec.gov/os/accessing-edgar-data).
    """

    def __init__(
        self,
        user_agent: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent identifying you. Format: 'Your Name email@example.com'"
            )
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
            transport=transport,
        )
        self._ticker_table: dict[str, str] | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _checked(self, r: httpx.Response) -> httpx.Response:
        if r.status_code in (403, 429):
            raise EdgarRateLimitError(f"EDGAR throttled: HTTP {r.status_code} for {r.url}")
        r.raise_for_status()
        return r

    def _load_ticker_table(self) -> dict[str, str]:
        if self._ticker_table is not None:
            return self._ticker_table
        r = self._checked(self._client.get(TICKER_LOOKUP_URL))
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
        r = self._checked(self._client.get(url))
        result: dict[str, Any] = r.json()
        return result

    def fetch_submissions(self, cik: str) -> dict[str, Any]:
        """Fetch the submissions JSON (profile + recent filings) for a CIK."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        r = self._checked(self._client.get(SUBMISSIONS_URL_TEMPLATE.format(cik=cik)))
        result: dict[str, Any] = r.json()
        return result

    def shares_outstanding(self, cik: str) -> float | None:
        """Newest reported common shares outstanding (dei), or None."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        r = self._client.get(COMPANY_CONCEPT_URL_TEMPLATE.format(cik=cik))
        if r.status_code == 404:
            return None
        r = self._checked(r)
        entries = r.json().get("units", {}).get("shares", [])
        newest_val: float | None = None
        newest_end: date | None = None
        for entry in entries:
            end = coerce_date(entry.get("end"))
            val = entry.get("val")
            if end is None or val is None:
                continue
            if newest_end is None or end > newest_end:
                newest_end, newest_val = end, float(val)
        return newest_val


def parse_submissions_info(ticker: str, submissions: dict[str, Any]) -> CompanyInfo:
    """Map an EDGAR submissions payload to :class:`CompanyInfo`.

    ``industry`` carries ``sicDescription`` verbatim — that string is the
    provider-industry key into ``industry_mapping.csv``, looked up under
    ``edgar_stooq``, the provider name of the adapter that serves it. EDGAR
    has no IPO date and no sector taxonomy, so those stay ``None`` (ADR 0007).
    """
    exchanges = submissions.get("exchanges") or []
    exchange = str(exchanges[0]) if exchanges else None
    sic_description = str(submissions.get("sicDescription") or "").strip() or None
    return CompanyInfo(
        ticker=ticker.upper(),
        name=str(submissions.get("name") or ticker.upper()),
        exchange=exchange,
        exchange_short_name=exchange,
        country="US",
        currency="USD",
        sector=None,
        industry=sic_description,
        is_actively_trading=True,
        ipo_date=None,
    )


def latest_filing_date_from_submissions(submissions: dict[str, Any]) -> date | None:
    """Newest 10-K/10-Q filing date in ``filings.recent`` (parallel arrays)."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    latest: date | None = None
    for form, filed_raw in zip(forms, dates, strict=False):
        if form not in _FINANCIAL_FORMS:
            continue
        filed = coerce_date(filed_raw)
        if filed is None:
            continue
        if latest is None or filed > latest:
            latest = filed
    return latest


# ---------- Parser ----------


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
    "_current_assets": ["AssetsCurrent"],
    "_current_liabilities": ["LiabilitiesCurrent"],
}


def _derive_financial_fields(row: dict[str, Any]) -> None:
    """Fill ebitda / free_cashflow / working_capital when their inputs exist.

    EDGAR facts report the components, not the aggregates FMP pre-computed.
    Derivations only fill gaps — a reported aggregate is never overwritten —
    and missing inputs leave ``None`` (graceful degradation, spec §13.2).
    """
    ebit, dep = row.get("ebit"), row.get("depreciation")
    if row.get("ebitda") is None:
        row["ebitda"] = ebit + dep if ebit is not None and dep is not None else None
    ocf, capex = row.get("operating_cashflow"), row.get("capex")
    if row.get("free_cashflow") is None:
        row["free_cashflow"] = ocf - capex if ocf is not None and capex is not None else None
    ca = row.pop("_current_assets", None)
    cl = row.pop("_current_liabilities", None)
    if row.get("working_capital") is None:
        row["working_capital"] = ca - cl if ca is not None and cl is not None else None


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
        _derive_financial_fields(row)
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
    """Merge-replace the company row by ticker. Assumes called within a transaction.

    A raw DELETE + INSERT with only the provider's columns would wipe out
    what that provider doesn't carry: the SEC row doesn't load industry, so
    a ``bot show --fetch`` would drop a ticker mapped by FMP out of the
    screener's universe. Columns the new row doesn't carry (or carries as
    ``None``) keep the value already stored.
    """
    existing_row = conn.execute(
        "SELECT * FROM companies WHERE ticker = ?", [company["ticker"]]
    ).fetchone()
    merged = dict(company)
    if existing_row is not None:
        columns = [d[0] for d in conn.description]
        existing = dict(zip(columns, existing_row, strict=True))
        for col, value in existing.items():
            if merged.get(col) is None and value is not None:
                merged[col] = value
    merged.pop("last_updated_at", None)  # let the DEFAULT re-stamp it
    cols = sorted(merged.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    conn.execute("DELETE FROM companies WHERE ticker = ?", [company["ticker"]])
    conn.execute(
        f"INSERT INTO companies ({col_list}) VALUES ({placeholders})",
        [merged[c] for c in cols],
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
