"""Financial Modeling Prep (FMP) adapter — HTTP client + auth + ticker lookup.

Thin client over the FMP REST API. Plays the same role as ``SecEdgarClient`` but
for global coverage (international fundamentals + EOD prices). The API key is read
from ``BOT_FMP_API_KEY`` (see :class:`bot.config.Settings`) and passed to FMP as
the ``apikey`` query parameter on every request.

Only the ticker lookup and exchange/country listing endpoints are implemented
here (M2.1). Fundamentals ingestion lands in a later slice.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import httpx

from bot.ingest.base import coerce_date
from bot.ingest.provider import (
    CompanyInfo,
    FundamentalsBundle,
    FxRate,
    ParsedCompanyData,
    PriceBar,
    ProviderRateLimitError,
)
from bot.utils.logging import get_logger

log = get_logger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"


class FmpRateLimitError(ProviderRateLimitError):
    """FMP devolvió HTTP 429: se agotó la cuota diaria del API key.

    No es una falla del ticker ni un error de datos: la corrida debe cortar y
    el resto del universo queda diferido para la próxima corrida (el refresh es
    incremental, así que retomarlo es gratis).
    """


class FmpClient:
    """Thin HTTP client for Financial Modeling Prep public endpoints.

    FMP authenticates via an ``apikey`` query parameter on every request. The key
    is required — there is no anonymous access — so construction fails fast on an
    empty key.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("FMP API key is required. Set BOT_FMP_API_KEY (no default).")
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=BASE_URL,
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

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` with the API key injected. Returns parsed JSON."""
        query: dict[str, Any] = dict(params or {})
        query["apikey"] = self._api_key
        r = self._client.get(path, params=query)
        if r.status_code == 429:
            raise FmpRateLimitError(
                "FMP rate limit (HTTP 429): cuota diaria agotada; reintentá mañana"
            )
        r.raise_for_status()
        return r.json()

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        """Return normalized basic info for ``ticker``, or None if not found.

        FMP's ``/profile/{ticker}`` endpoint returns a JSON array: a single
        profile object for a known symbol, or an empty array for an unknown one.
        """
        data = self._get(f"/profile/{ticker.upper()}")
        if not isinstance(data, list) or not data:
            log.info("fmp.lookup_company.not_found", ticker=ticker)
            return None
        profile = data[0]
        info = CompanyInfo(
            ticker=str(profile.get("symbol", ticker)).upper(),
            name=str(profile.get("companyName", "")),
            exchange=_str_or_none(profile.get("exchange")),
            exchange_short_name=_str_or_none(profile.get("exchangeShortName")),
            country=_str_or_none(profile.get("country")),
            currency=_str_or_none(profile.get("currency")),
            sector=_str_or_none(profile.get("sector")),
            industry=_str_or_none(profile.get("industry")),
            is_actively_trading=bool(profile.get("isActivelyTrading", False)),
            ipo_date=coerce_date(profile.get("ipoDate")),
        )
        log.info("fmp.lookup_company.found", ticker=info.ticker, country=info.country)
        return info

    def available_exchanges(self) -> list[dict[str, Any]]:
        """Return FMP's list of available exchanges (for sanity checks)."""
        data = self._get("/available-exchanges")
        if not isinstance(data, list):
            return []
        return [e for e in data if isinstance(e, dict)]

    def historical_fx(
        self,
        currency: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return daily {currency}/USD rates as ``[{"date", "rate_to_usd"}, ...]``.

        Uses FMP's ``/historical-price-full/{PAIR}`` endpoint for the forex pair
        ``{CURRENCY}USD`` (e.g. ``EURUSD``). The daily ``close`` is taken as the
        rate that converts one unit of ``currency`` into USD. USD itself needs no
        request — it is the numeraire — so it returns an empty list.
        """
        ccy = currency.upper()
        if ccy == "USD":
            return []
        params: dict[str, Any] = {}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()
        data = self._get(f"/historical-price-full/{ccy}USD", params=params)
        historical = data.get("historical") if isinstance(data, dict) else None
        if not isinstance(historical, list):
            log.info("fmp.historical_fx.empty", currency=ccy)
            return []
        out: list[dict[str, Any]] = []
        for entry in historical:
            if not isinstance(entry, dict):
                continue
            d = entry.get("date")
            close = entry.get("close")
            if d is None or close is None:
                continue
            # FMP returns datetime-ish strings ("2023-12-29" or "2023-12-29 00:00:00").
            out.append({"date": str(d)[:10], "rate_to_usd": float(close)})
        log.info("fmp.historical_fx.fetched", currency=ccy, rows=len(out))
        return out

    def historical_prices(
        self,
        ticker: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return daily EOD price rows for ``ticker`` as a list of dicts.

        Uses FMP's ``/historical-price-full/{TICKER}`` endpoint. Each returned
        dict carries ``date`` (``YYYY-MM-DD``), ``close``, ``volume`` and
        ``market_cap`` (the last derived from FMP's ``marketCap`` field when
        present, else ``None``). ``start``/``end`` are passed as FMP's
        ``from``/``to`` query parameters to bound the fetched window — used by
        :meth:`FmpProvider.daily_prices` for incremental fetches.
        """
        sym = ticker.upper()
        params: dict[str, Any] = {}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()
        data = self._get(f"/historical-price-full/{sym}", params=params)
        historical = data.get("historical") if isinstance(data, dict) else None
        if not isinstance(historical, list):
            log.info("fmp.historical_prices.empty", ticker=sym)
            return []
        out: list[dict[str, Any]] = []
        for entry in historical:
            if not isinstance(entry, dict):
                continue
            d = entry.get("date")
            if d is None:
                continue
            out.append(
                {
                    "date": str(d)[:10],
                    "close": _float_or_none(entry.get("close")),
                    "volume": _float_or_none(entry.get("volume")),
                    "market_cap": _float_or_none(entry.get("marketCap")),
                }
            )
        log.info("fmp.historical_prices.fetched", ticker=sym, rows=len(out))
        return out

    def _statement(
        self, kind: str, ticker: str, *, period: str, limit: int
    ) -> list[dict[str, Any]]:
        """Fetch one statement array (``kind``) for ``ticker`` from FMP.

        ``kind`` is the endpoint segment (``income-statement``,
        ``balance-sheet-statement`` or ``cash-flow-statement``). ``period`` is
        FMP's ``annual`` or ``quarter`` query parameter. Returns the raw JSON
        array (one object per fiscal period), or ``[]`` for an unknown symbol.
        """
        data = self._get(
            f"/{kind}/{ticker.upper()}",
            params={"period": period, "limit": limit},
        )
        if not isinstance(data, list):
            return []
        return [e for e in data if isinstance(e, dict)]

    def income_statement(
        self, ticker: str, *, period: str = "annual", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return the income-statement array for ``ticker`` (``annual``/``quarter``)."""
        return self._statement("income-statement", ticker, period=period, limit=limit)

    def balance_sheet(
        self, ticker: str, *, period: str = "annual", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return the balance-sheet array for ``ticker`` (``annual``/``quarter``)."""
        return self._statement("balance-sheet-statement", ticker, period=period, limit=limit)

    def cash_flow(
        self, ticker: str, *, period: str = "annual", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return the cash-flow array for ``ticker`` (``annual``/``quarter``)."""
        return self._statement("cash-flow-statement", ticker, period=period, limit=limit)


class FmpProvider:
    """The FMP adapter behind :class:`bot.ingest.provider.MarketDataProvider`.

    One instance owns one :class:`FmpClient` (one connection pool) for its
    lifetime — construct per bulk run, close when done (context manager).
    Everything FMP-specific — endpoints, JSON shapes, parsing — stays inside.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: FmpClient | None = None

    @property
    def name(self) -> str:
        return "fmp"

    def _fmp(self) -> FmpClient:
        if self._client is None:
            self._client = FmpClient(api_key=self._api_key, timeout=self._timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> FmpProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        return self._fmp().lookup_company(ticker)

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        sym = ticker.upper()
        fmp = self._fmp()
        info = fmp.lookup_company(sym)
        inc_a = fmp.income_statement(sym, period="annual")
        bal_a = fmp.balance_sheet(sym, period="annual")
        cf_a = fmp.cash_flow(sym, period="annual")
        inc_q = fmp.income_statement(sym, period="quarter")
        bal_q = fmp.balance_sheet(sym, period="quarter")
        cf_q = fmp.cash_flow(sym, period="quarter")
        return FundamentalsBundle(
            info=info,
            annual=parse_fmp_fundamentals(sym, inc_a, bal_a, cf_a),
            quarterly=parse_fmp_fundamentals(sym, inc_q, bal_q, cf_q),
            filings=_collect_fmp_filings(sym, inc_a, inc_q),
        )

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        rows = self._fmp().historical_prices(ticker.upper(), start=since, end=None)
        return [
            PriceBar(
                date=_as_date(r["date"]),
                close=_float_or_none(r.get("close")),
                volume=_float_or_none(r.get("volume")),
                market_cap=_float_or_none(r.get("market_cap")),
            )
            for r in rows
        ]

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        rows = self._fmp().historical_fx(currency.upper(), start=since, end=None)
        return [
            FxRate(date=_as_date(r["date"]), rate_to_usd=float(r["rate_to_usd"]))
            for r in rows
        ]

    def latest_filing_date(self, ticker: str) -> date | None:
        sym = ticker.upper()
        rows = self._fmp().income_statement(sym, period="annual", limit=1)
        return _latest_filing_from_rows(rows)


def _as_date(value: Any) -> date:
    parsed = coerce_date(value)
    if parsed is None:
        raise ValueError(f"FMP row has no usable date: {value!r}")
    return parsed


def _latest_filing_from_rows(rows: Iterable[dict[str, object]]) -> date | None:
    """Return the newest ``fillingDate``/``acceptedDate`` across FMP statement rows.

    Backs :meth:`FmpProvider.latest_filing_date` — adapter-internal since it reads
    FMP's own statement JSON shape.
    """
    latest: date | None = None
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        filed_raw = entry.get("fillingDate") or entry.get("acceptedDate")
        if not filed_raw:
            continue
        filed = coerce_date(filed_raw)
        if filed is None:
            continue
        if latest is None or filed > latest:
            latest = filed
    return latest


def _str_or_none(value: Any) -> str | None:
    """Coerce to a non-empty string, mapping empty/None to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    """Coerce to ``float``, mapping None/non-numeric to None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------- Fundamentals parser (M2.2) ----------
#
# FMP returns one JSON object per fiscal period for each statement type
# (income / balance sheet / cash flow). Keys are camelCase. Amounts are in the
# company's local currency (``reportedCurrency``); USD conversion happens
# elsewhere (M2.5 / valuator). This parser is PURE: it accepts the already-fetched
# JSON arrays and joins them per fiscal period into the row shape that
# ``upsert_financials_annual`` / ``upsert_financials_quarterly`` consume.

# FMP income-statement field -> our DB column.
_INCOME_FIELD_MAP: dict[str, str] = {
    "revenue": "revenue",
    "costOfRevenue": "cogs",
    "grossProfit": "gross_profit",
    "operatingExpenses": "operating_expenses",
    "operatingIncome": "ebit",
    "ebitda": "ebitda",
    "interestExpense": "interest_expense",
    "incomeTaxExpense": "tax_expense",
    "netIncome": "net_income",
    "weightedAverageShsDilOut": "shares_diluted",
    "depreciationAndAmortization": "depreciation",
}

# FMP balance-sheet field -> our DB column.
_BALANCE_FIELD_MAP: dict[str, str] = {
    "totalAssets": "total_assets",
    "totalDebt": "total_debt",
    "cashAndCashEquivalents": "cash",
    "totalStockholdersEquity": "total_equity",
    "goodwill": "goodwill",
}

# FMP cash-flow field -> our DB column.
_CASHFLOW_FIELD_MAP: dict[str, str] = {
    "operatingCashFlow": "operating_cashflow",
    "freeCashFlow": "free_cashflow",
    "dividendsPaid": "dividends_paid",
}


def parse_fmp_fundamentals(
    ticker: str,
    income_json: list[dict[str, Any]],
    balance_json: list[dict[str, Any]],
    cashflow_json: list[dict[str, Any]],
) -> ParsedCompanyData:
    """Normalize FMP statement JSON into our ``financials_*`` row shape.

    ``income_json``, ``balance_json`` and ``cashflow_json`` are the raw arrays
    returned by FMP's ``/income-statement``, ``/balance-sheet-statement`` and
    ``/cash-flow-statement`` endpoints (annual *or* quarterly — pass one period
    granularity per call). Each statement is joined per fiscal period (keyed on
    ``date``, the period-end). Rows whose ``period`` is ``FY`` land in ``annual``;
    quarterly rows (``Q1``..``Q4``) land in ``quarterly``.

    Currency is taken from the source ``reportedCurrency`` (no conversion here).
    EBITDA and free cash flow are derived when FMP omits them. A fiscal period
    seen in more than one filing is flagged ``is_restated`` (latest filing wins).
    """
    ticker = ticker.upper()

    currency = _first_currency(income_json, balance_json, cashflow_json)
    company: dict[str, Any] = {
        "ticker": ticker,
        "name": ticker,
        "currency": currency,
        "source": "fmp",
        "status": "active",
    }

    # period_end (date string) -> merged column dict
    periods: dict[str, dict[str, Any]] = {}
    # period_end -> True if any single statement reported it in >1 filing
    restated: dict[str, bool] = {}

    _merge_statement(periods, restated, income_json, _INCOME_FIELD_MAP)
    _merge_statement(periods, restated, balance_json, _BALANCE_FIELD_MAP)
    _merge_statement(periods, restated, cashflow_json, _CASHFLOW_FIELD_MAP)

    annual: list[dict[str, Any]] = []
    quarterly: list[dict[str, Any]] = []

    for period_end, cols in periods.items():
        fiscal_year = cols.pop("_fiscal_year", None)
        period = cols.pop("_period", None)
        if fiscal_year is None or period is None:
            continue

        row: dict[str, Any] = {
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "period_end_date": period_end,
            "currency": cols.pop("_currency", currency),
            "source": "fmp",
            "is_restated": restated.get(period_end, False),
        }
        row.update(cols)

        raw = _collect_raw(income_json, balance_json, cashflow_json, period_end)
        capex_signed = _capex_signed(raw)

        # capex: FMP reports capitalExpenditure as a negative magnitude. Store the
        # positive amount (matching the SEC adapter, where capex is a cash outflow
        # expressed as a positive number).
        if capex_signed is not None:
            row["capex"] = abs(capex_signed)

        # working_capital = total current assets - total current liabilities.
        wc = _working_capital(raw)
        if wc is not None:
            row["working_capital"] = wc

        # Derived EBITDA = EBIT + D&A when FMP omits ebitda.
        if row.get("ebitda") is None:
            ebit = row.get("ebit")
            dep = row.get("depreciation")
            if ebit is not None and dep is not None:
                row["ebitda"] = ebit + dep

        # Derived FCF = OCF + capitalExpenditure (capex is negative in FMP).
        if row.get("free_cashflow") is None:
            ocf = row.get("operating_cashflow")
            if ocf is not None and capex_signed is not None:
                row["free_cashflow"] = ocf + capex_signed

        if _is_annual(period):
            annual.append(row)
        else:
            q = _quarter_number(period)
            if q is None:
                continue
            row["fiscal_quarter"] = q
            quarterly.append(row)

    log.info(
        "fmp.parse_fundamentals",
        ticker=ticker,
        currency=currency,
        annual=len(annual),
        quarterly=len(quarterly),
    )
    return ParsedCompanyData(company=company, annual=annual, quarterly=quarterly)


def _merge_statement(
    periods: dict[str, dict[str, Any]],
    restated: dict[str, bool],
    statement: list[dict[str, Any]],
    field_map: dict[str, str],
) -> None:
    """Merge one statement's entries into ``periods`` (latest filing wins).

    Entries are keyed on ``date`` (the period-end). The first time a period is
    seen we record its fiscal year / period / currency. When the same period
    appears more than once *within this statement* — i.e. FMP returned two
    filings for the same fiscal period — the later one overwrites the earlier
    values and the period is flagged as restated. Comparison is scoped to a
    single statement so that the same period appearing once in each of the three
    statement types is not mistaken for a restatement.
    """
    # period_end -> latest filing date seen in THIS statement
    latest_filed: dict[str, str] = {}

    for entry in statement:
        if not isinstance(entry, dict):
            continue
        raw_period_end = entry.get("date")
        if not raw_period_end:
            continue
        period_end = str(raw_period_end)[:10]

        filed_raw = entry.get("fillingDate") or entry.get("acceptedDate") or raw_period_end
        filed = str(filed_raw)[:10]
        if period_end in latest_filed:
            # Same period reported twice within this statement -> restatement.
            restated[period_end] = True
            # Keep the values from the most recently filed version.
            if filed < latest_filed[period_end]:
                continue
        latest_filed[period_end] = filed
        restated.setdefault(period_end, False)

        slot = periods.setdefault(period_end, {})
        slot.setdefault("_fiscal_year", _fiscal_year(entry))
        slot.setdefault("_period", _str_or_none(entry.get("period")))
        slot.setdefault("_currency", _str_or_none(entry.get("reportedCurrency")))

        for fmp_key, db_col in field_map.items():
            if fmp_key in entry and entry[fmp_key] is not None:
                slot[db_col] = entry[fmp_key]


def _collect_raw(
    income_json: list[dict[str, Any]],
    balance_json: list[dict[str, Any]],
    cashflow_json: list[dict[str, Any]],
    period_end: str,
) -> dict[str, Any]:
    """Return the merged raw FMP fields across statements for a period-end.

    Used for derivations that need fields we do not store as DB columns
    (e.g. ``capitalExpenditure``, ``totalCurrentAssets``).
    """
    merged: dict[str, Any] = {}
    for statement in (income_json, balance_json, cashflow_json):
        for entry in statement:
            if isinstance(entry, dict) and str(entry.get("date", ""))[:10] == period_end:
                merged.update({k: v for k, v in entry.items() if v is not None})
    return merged


def _capex_signed(raw: dict[str, Any]) -> float | None:
    """Return ``capitalExpenditure`` with FMP's native sign (negative outflow)."""
    value = raw.get("capitalExpenditure")
    return float(value) if value is not None else None


def _working_capital(raw: dict[str, Any]) -> float | None:
    """Compute current assets - current liabilities when both are present."""
    ca = raw.get("totalCurrentAssets")
    cl = raw.get("totalCurrentLiabilities")
    if ca is None or cl is None:
        return None
    return float(ca) - float(cl)


def _fiscal_year(entry: dict[str, Any]) -> int | None:
    """Resolve the fiscal year from ``calendarYear`` or the ``date`` year."""
    cal = entry.get("calendarYear")
    if cal is not None:
        try:
            return int(cal)
        except (TypeError, ValueError):
            pass
    raw_date = entry.get("date")
    if raw_date:
        try:
            return int(str(raw_date)[:4])
        except (TypeError, ValueError):
            return None
    return None


def _first_currency(*statements: list[dict[str, Any]]) -> str | None:
    """Return the first ``reportedCurrency`` found across the statements."""
    for statement in statements:
        for entry in statement:
            if isinstance(entry, dict):
                ccy = _str_or_none(entry.get("reportedCurrency"))
                if ccy is not None:
                    return ccy
    return None


def _is_annual(period: str) -> bool:
    return period.upper() == "FY"


def _quarter_number(period: str) -> int | None:
    """Map an FMP ``period`` label (``Q1``..``Q4``) to an int."""
    p = period.upper()
    if p.startswith("Q"):
        try:
            q = int(p[1:])
        except ValueError:
            return None
        return q if 1 <= q <= 4 else None
    return None


# ---------- Fundamentals importer (M2.3) ----------


def _collect_fmp_filings(
    ticker: str,
    *statements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract ``filings_log`` rows from FMP statement arrays.

    FMP carries a ``fillingDate`` (sic) and ``acceptedDate`` on each statement
    object. We key one filing per ``(period_label, filing_date)`` pair so the
    bulk universe refresh (M2.6) can read the *latest* filing date for a ticker
    and skip re-importing companies whose newest filing has not advanced since
    the previous run. ``filing_type`` is the FMP period label (``FY`` for annual,
    ``Q1``..``Q4`` for quarterly), and ``source`` is ``fmp``.
    """
    sym = ticker.upper()
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for statement in statements:
        for entry in statement:
            if not isinstance(entry, dict):
                continue
            filed_raw = entry.get("fillingDate") or entry.get("acceptedDate")
            period = _str_or_none(entry.get("period"))
            if not filed_raw or period is None:
                continue
            filing_date = str(filed_raw)[:10]
            filing_type = period.upper()
            key = (filing_type, filing_date)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "ticker": sym,
                    "filing_type": filing_type,
                    "filing_date": filing_date,
                    "accession_number": None,
                    "source": "fmp",
                }
            )
    return out

