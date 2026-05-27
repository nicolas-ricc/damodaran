"""Financial Modeling Prep (FMP) adapter — company lookup and fundamentals parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from bot.ingest.base import ParsedCompanyData
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


# ---------- Fundamentals Parser ----------

_QUARTERLY_PERIODS = {"Q1", "Q2", "Q3", "Q4"}

# Columns present in the financials_quarterly schema (schema.sql).
# _build_financials_row returns additional annual-only columns that are stripped
# before quarterly rows are appended.
_QUARTERLY_COLUMNS: frozenset[str] = frozenset({
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
})


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


def _filling_sort_key(e: dict[str, Any]) -> tuple[int, str]:
    """Push None/missing fillingDate to the bottom (oldest) in sort order."""
    v = e.get("fillingDate")
    return (1, str(v)) if v is not None else (0, "")


def _index_statements(
    entries: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return a {(calendarYear, period): entry} index keeping the latest fillingDate."""
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for e in entries:
        key = _period_key(e)
        existing = idx.get(key)
        if existing is None or _filling_sort_key(e) > _filling_sort_key(existing):
            idx[key] = e
    return idx


def _build_filing_index(
    entries: list[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Index by (calendarYear, period, fillingDate) for snapshot-aware restatement joins."""
    idx: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in entries:
        raw = e.get("fillingDate")
        filing_date = str(raw) if raw is not None else ""
        key = (str(e.get("calendarYear", "")), str(e.get("period", "")), filing_date)
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
        groups[key].sort(key=_filling_sort_key)
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
    # For EBITDA derivation use income-statement D&A (operating-only).
    # Cashflow D&A may include capex-related amortization and would overstate EBITDA.
    ebitda_da = _num(inc, "depreciationAndAmortization")
    depreciation = _num(cf, "depreciationAndAmortization") or _num(inc, "depreciationAndAmortization")
    ebitda = _num(inc, "ebitda")
    if ebitda is None and ebit is not None and ebitda_da is not None:
        ebitda = ebit + ebitda_da

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

    Restatement handling: each restated income entry is matched to its contemporaneous
    balance/cashflow snapshot by fillingDate. If FMP does not preserve historical
    balance/cf snapshots for a given restated income entry (no entry with a matching
    fillingDate is found), that restated row is dropped rather than emitted with
    mismatched current balance/cf figures. The latest (current) income entry is
    always emitted using the latest available balance/cf for that period.
    """
    ticker = ticker.upper()

    bal_idx = _index_statements(balance_json)
    cf_idx = _index_statements(cashflow_json)
    bal_by_filing = _build_filing_index(balance_json)
    cf_by_filing = _build_filing_index(cashflow_json)
    income_groups = _group_statements(income_json)

    annual: list[dict[str, Any]] = []
    quarterly: list[dict[str, Any]] = []

    for (cal_year, period), entries in income_groups.items():
        if not cal_year.isdigit():
            log.warning(
                "fmp.invalid_calendar_year.skipped",
                ticker=ticker,
                year=cal_year,
                period=period,
            )
            continue

        period_key = (cal_year, period)
        n = len(entries)

        for i, inc in enumerate(entries):
            is_restated = i < n - 1
            raw_date = inc.get("fillingDate")
            filling_date = str(raw_date) if raw_date is not None else ""
            filing_key = (cal_year, period, filling_date)

            # For restated income entries, require a contemporaneous balance/cf snapshot
            # by fillingDate. When FMP stores only the latest version (no historical
            # snapshots), skip rather than pair stale income with current balance/cf.
            if is_restated and bal_by_filing.get(filing_key) is None and cf_by_filing.get(filing_key) is None:
                log.debug(
                    "fmp.restatement.no_snapshot_skipped",
                    ticker=ticker,
                    year=cal_year,
                    period=period,
                    filling_date=filling_date,
                )
                continue

            bal_snapshot = bal_by_filing.get(filing_key)
            cf_snapshot = cf_by_filing.get(filing_key)
            bal = bal_snapshot if bal_snapshot is not None else bal_idx.get(period_key, {})
            cf = cf_snapshot if cf_snapshot is not None else cf_idx.get(period_key, {})
            row = _build_financials_row(ticker, inc, bal, cf, is_restated=is_restated)

            if period == "FY":
                annual.append(row)
            elif period in _QUARTERLY_PERIODS:
                quarterly_row: dict[str, Any] = {
                    k: val for k, val in row.items() if k in _QUARTERLY_COLUMNS
                }
                quarterly_row["fiscal_quarter"] = int(period[1])
                quarterly.append(quarterly_row)
            # Unknown period strings are silently ignored.

    # Derive a minimal company stub from the first income entry.
    # The `name` field defaults to ticker as a placeholder; the M2.3 importer
    # overwrites it with the full company name from the FMP /profile endpoint.
    first = income_json[0] if income_json else {}
    cik_raw = first.get("cik")
    cik: str | None = str(cik_raw).strip().zfill(10) if cik_raw and str(cik_raw).strip() else None
    company: dict[str, Any] = {
        "ticker": ticker,
        "name": ticker,
        "cik": cik,
        "currency": first.get("reportedCurrency") or None,
        "source": "fmp",
        "status": "active",
    }

    return ParsedCompanyData(company=company, annual=annual, quarterly=quarterly)
