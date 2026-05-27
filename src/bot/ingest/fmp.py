"""Financial Modeling Prep (FMP) adapter — company lookup, fundamentals parser, and importer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult, ParsedCompanyData
from bot.ingest.sec_edgar import upsert_company
from bot.utils.logging import get_logger

log = get_logger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


@dataclass
class CompanyInfo:
    """Normalized company data returned by FmpClient.lookup_company."""

    ticker: str
    name: str
    currency: str | None
    country: str | None
    exchange: str | None
    industry: str | None
    isin: str | None
    cik: str | None
    is_actively_trading: bool
    source: str = "fmp"

    @property
    def status(self) -> str:
        return "active" if self.is_actively_trading else "delisted"


class FmpClient:
    """Thin HTTP client over the Financial Modeling Prep v3 REST API.

    Authentication is via ``apikey`` query parameter on every request.
    API key is read from the ``api_key`` constructor argument; the caller
    should pass ``Settings().fmp_api_key``.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("FMP API key must not be empty")
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=FMP_BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FmpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, **params: Any) -> Any:
        response = self._client.get(path, params={"apikey": self._api_key, **params})
        response.raise_for_status()
        return response.json()

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        """Return normalized company info for *ticker*, or ``None`` if FMP has no profile.

        Works for US (e.g. ``AAPL``), Swiss (``NESN.SW``), and Japanese (``7203.T``)
        tickers — any symbol accepted by the FMP ``/profile/{symbol}`` endpoint.
        """
        ticker = ticker.upper()
        data: Any = self._get(f"/profile/{ticker}")
        if not data:
            log.info("fmp.lookup_company.not_found", ticker=ticker)
            return None
        profile: dict[str, Any] = data[0]
        cik_raw = profile.get("cik")
        # Only US companies have a CIK; zero-pad to 10 digits when present.
        cik: str | None = None
        if cik_raw and str(cik_raw).strip():
            cik = str(cik_raw).strip().zfill(10)
        return CompanyInfo(
            ticker=ticker,
            name=profile.get("companyName") or ticker,
            currency=profile.get("currency") or None,
            country=profile.get("country") or None,
            exchange=profile.get("exchangeShortName") or None,
            industry=profile.get("industry") or None,
            isin=profile.get("isin") or None,
            cik=cik,
            is_actively_trading=bool(profile.get("isActivelyTrading", True)),
        )

    def fetch_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch income statement rows. period='annual' or 'quarter'."""
        ticker = ticker.upper()
        data: Any = self._get(f"/income-statement/{ticker}", period=period, limit=limit)
        return list(data) if data else []

    def fetch_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch balance sheet rows. period='annual' or 'quarter'."""
        ticker = ticker.upper()
        data: Any = self._get(f"/balance-sheet-statement/{ticker}", period=period, limit=limit)
        return list(data) if data else []

    def fetch_cashflow(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch cash flow statement rows. period='annual' or 'quarter'."""
        ticker = ticker.upper()
        data: Any = self._get(f"/cash-flow-statement/{ticker}", period=period, limit=limit)
        return list(data) if data else []


# ---------- Fundamentals Parser ----------

_QUARTERLY_PERIODS = {"Q1", "Q2", "Q3", "Q4"}


def _num(d: dict[str, Any], key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _period_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (str(entry.get("calendarYear", "")), str(entry.get("period", "")))


def _index_statements(
    entries: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return a {(calendarYear, period): entry} index keeping the latest fillingDate."""
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for e in entries:
        key = _period_key(e)
        existing = idx.get(key)
        if existing is None or str(e.get("fillingDate", "")) > str(existing.get("fillingDate", "")):
            idx[key] = e
    return idx


def _group_statements(
    entries: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group entries by (calendarYear, period), sorted by fillingDate ascending."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for e in entries:
        key = _period_key(e)
        groups.setdefault(key, []).append(e)
    for key in groups:
        groups[key].sort(key=lambda e: str(e.get("fillingDate", "")))
    return groups


def _build_financials_row(
    ticker: str,
    inc: dict[str, Any],
    bal: dict[str, Any],
    cf: dict[str, Any],
    *,
    is_restated: bool,
) -> dict[str, Any]:
    currency = (
        inc.get("reportedCurrency")
        or bal.get("reportedCurrency")
        or cf.get("reportedCurrency")
        or None
    )
    period_end = inc.get("date") or bal.get("date") or cf.get("date") or None
    cal_year = str(inc.get("calendarYear") or bal.get("calendarYear") or cf.get("calendarYear") or "")
    fiscal_year = int(cal_year) if cal_year.isdigit() else 0

    ebit = _num(inc, "operatingIncome")
    # FMP provides D&A in both income and cashflow; prefer cashflow for consistency.
    depreciation = _num(cf, "depreciationAndAmortization") or _num(inc, "depreciationAndAmortization")
    ebitda = _num(inc, "ebitda")
    if ebitda is None and ebit is not None and depreciation is not None:
        ebitda = ebit + depreciation

    operating_cashflow = _num(cf, "operatingCashFlow") or _num(
        cf, "netCashProvidedByOperatingActivities"
    )
    capex_signed = _num(cf, "capitalExpenditure")
    # Capex from FMP cashflow is negative; store as positive absolute value.
    capex = abs(capex_signed) if capex_signed is not None else None
    free_cashflow = _num(cf, "freeCashFlow")
    if free_cashflow is None and operating_cashflow is not None and capex is not None:
        free_cashflow = operating_cashflow - capex

    dividends_signed = _num(cf, "dividendsPaid")
    dividends_paid = abs(dividends_signed) if dividends_signed is not None else None

    total_equity = _num(bal, "totalStockholdersEquity") or _num(bal, "totalEquity")

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "period_end_date": period_end,
        "currency": currency,
        "revenue": _num(inc, "revenue"),
        "cogs": _num(inc, "costOfRevenue"),
        "gross_profit": _num(inc, "grossProfit"),
        "operating_expenses": _num(inc, "operatingExpenses"),
        "ebit": ebit,
        "ebitda": ebitda,
        "interest_expense": _num(inc, "interestExpense"),
        "tax_expense": _num(inc, "incomeTaxExpense"),
        "net_income": _num(inc, "netIncome"),
        "total_assets": _num(bal, "totalAssets"),
        "total_debt": _num(bal, "totalDebt"),
        "cash": _num(bal, "cashAndCashEquivalents"),
        "total_equity": total_equity,
        "goodwill": _num(bal, "goodwill"),
        "capex": capex,
        "depreciation": depreciation,
        "operating_cashflow": operating_cashflow,
        "free_cashflow": free_cashflow,
        "dividends_paid": dividends_paid,
        "shares_diluted": _num(inc, "weightedAverageShsOutDil"),
        "is_restated": is_restated,
        "source": "fmp",
    }


def parse_fmp_fundamentals(
    ticker: str,
    income_json: list[dict[str, Any]],
    balance_json: list[dict[str, Any]],
    cashflow_json: list[dict[str, Any]],
) -> ParsedCompanyData:
    """Parse FMP statement arrays into normalized DB rows.

    Joins income / balance / cashflow per (calendarYear, period), derives EBITDA
    and FCF when FMP omits them, and detects restatements when duplicate periods
    appear with different fillingDates.
    """
    ticker = ticker.upper()

    bal_idx = _index_statements(balance_json)
    cf_idx = _index_statements(cashflow_json)
    income_groups = _group_statements(income_json)

    annual: list[dict[str, Any]] = []
    quarterly: list[dict[str, Any]] = []

    for (cal_year, period), entries in income_groups.items():
        key = (cal_year, period)
        bal = bal_idx.get(key, {})
        cf = cf_idx.get(key, {})
        n = len(entries)
        for i, inc in enumerate(entries):
            # All but the last (most recent) filing are superseded — mark as restated.
            is_restated = i < n - 1
            row = _build_financials_row(ticker, inc, bal, cf, is_restated=is_restated)
            if period == "FY":
                annual.append(row)
            elif period in _QUARTERLY_PERIODS:
                row["fiscal_quarter"] = int(period[1])
                quarterly.append(row)
            # Unknown period strings are silently ignored.

    # Derive a minimal company stub from the first income entry (profile comes from M2.3).
    first = income_json[0] if income_json else {}
    cik_raw = first.get("cik")
    cik: str | None = str(cik_raw).strip().zfill(10) if cik_raw and str(cik_raw).strip() else None
    company: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "currency": first.get("reportedCurrency") or None,
        "source": "fmp",
        "status": "active",
    }

    return ParsedCompanyData(company=company, annual=annual, quarterly=quarterly)


# ---------- Importer ----------

def _upsert_financials_in_txn(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    rows: list[dict[str, Any]],
) -> int:
    """DELETE + INSERT *rows* into *table* within the caller's active transaction.

    Does NOT call BEGIN/COMMIT — the caller owns the transaction boundary.
    *table* must be one of the known financials tables; never user-supplied.
    """
    if not rows:
        return 0
    all_cols: set[str] = set()
    for r in rows:
        all_cols.update(r.keys())
    cols = sorted(all_cols)
    for t in {r["ticker"] for r in rows}:
        conn.execute(f"DELETE FROM {table} WHERE ticker = ?", [t])
    ph = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    for r in rows:
        conn.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({ph})",
            [r.get(c) for c in cols],
        )
    return len(rows)


# Columns present in financials_quarterly (subset of financials_annual).
_QUARTERLY_COLS = frozenset({
    "ticker", "fiscal_year", "fiscal_quarter", "period_end_date", "currency",
    "revenue", "ebit", "ebitda", "net_income",
    "operating_cashflow", "free_cashflow", "total_debt", "cash",
    "is_restated", "source",
})


def import_company_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    api_key: str,
    annual_limit: int = 20,
    quarters_limit: int = 40,
) -> IngestResult:
    """Fetch + parse + upsert one ticker from FMP.

    Mirrors ``import_company_from_sec``: returns an ``IngestResult`` and always
    writes a row to ``refresh_log`` regardless of success or failure.

    All three upserts (company, annual, quarterly) run inside a single transaction;
    any failure rolls back all three, so ``rows_affected`` is 0 on error.

    *Currency and CIK precedence*: statement-level ``reportedCurrency`` and ``cik``
    from the income statement (via ``parsed.company``) take precedence over the
    ``/profile`` endpoint; the profile supplies name, country, exchange, industry,
    and isin which are absent from statement data.

    Args:
        annual_limit: Annual periods to fetch (default 20 ≈ 20 years).
        quarters_limit: Quarterly periods to fetch (default 40 ≈ 10 years).
    """
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    result: IngestResult

    try:
        with FmpClient(api_key=api_key) as client:
            info = client.lookup_company(ticker)
            if info is None:
                raise ValueError(f"Ticker {ticker!r} not found in FMP")

            income = (
                client.fetch_income_statement(ticker, period="annual", limit=annual_limit)
                + client.fetch_income_statement(ticker, period="quarter", limit=quarters_limit)
            )
            balance = (
                client.fetch_balance_sheet(ticker, period="annual", limit=annual_limit)
                + client.fetch_balance_sheet(ticker, period="quarter", limit=quarters_limit)
            )
            cashflow = (
                client.fetch_cashflow(ticker, period="annual", limit=annual_limit)
                + client.fetch_cashflow(ticker, period="quarter", limit=quarters_limit)
            )

        parsed = parse_fmp_fundamentals(ticker, income, balance, cashflow)

        # Statement-level currency/cik supersede /profile; profile fills the rest.
        company: dict[str, Any] = {
            "ticker": info.ticker,
            "cik": parsed.company.get("cik") or info.cik,
            "name": info.name,
            "country": info.country,
            "exchange": info.exchange,
            "industry": info.industry,
            "isin": info.isin,
            "currency": parsed.company.get("currency") or info.currency,
            "status": info.status,
            "source": "fmp",
        }

        quarterly_rows = [{k: v for k, v in r.items() if k in _QUARTERLY_COLS} for r in parsed.quarterly]

        conn.begin()
        try:
            upsert_company(conn, company)
            annual_count = _upsert_financials_in_txn(conn, "financials_annual", parsed.annual)
            quarterly_count = _upsert_financials_in_txn(conn, "financials_quarterly", quarterly_rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        total = 1 + annual_count + quarterly_count

        result = IngestResult(
            source="fmp",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="success",
            rows_affected=total,
            details={
                "ticker": ticker,
                "annual": annual_count,
                "quarterly": quarterly_count,
            },
        )

    except Exception as e:
        log.exception("fmp.import.failed", ticker=ticker, error=str(e))
        result = IngestResult(
            source="fmp",
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
