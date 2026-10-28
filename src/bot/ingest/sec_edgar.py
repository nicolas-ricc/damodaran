"""SEC EDGAR adapter — fetch + parse + import US company fundamentals."""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import date
from statistics import median
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

# Accepted duration spans in days. Annual covers 52/53-week years (363 to 371) and
# rejects transition periods and year-to-date spans; quarterly rejects the same.
ANNUAL_SPAN_DAYS: tuple[int, int] = (350, 380)
QUARTERLY_SPAN_DAYS: tuple[int, int] = (80, 100)
_QUARTER_DAYS = 91.3
# Factors tried in order when an annual share count is a whole scale off its peers.
_SHARE_SCALE_FACTORS = (1_000_000, 1_000)
_MIN_SHARE_COMPARATORS = 3
_SHARE_SCALE_TOLERANCE = 2.0

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
    provider-industry key into ``industry_mapping.csv``, looked up under the
    ``edgar`` taxonomy key shared by every EDGAR-based provider
    (``EdgarPricedProvider.industry_mapping_key``). EDGAR has no IPO date and
    no sector taxonomy, so those stay ``None`` (ADR 0007).
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
# parser resolves each period end separately: the first concept in list order with an
# accepted fact for that period wins it; later concepts only fill periods still unfilled.
ANNUAL_CONCEPT_MAP: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": ["OperatingExpenses"],
    "ebit": ["OperatingIncomeLoss"],
    # FASB's 2024 taxonomy deprecated InterestExpense; filers moved to the
    # Nonoperating / Debt / Operating variants, so a FY2025 10-K carries the old
    # concept only on its comparatives. Income-statement concepts first; the
    # cash-flow interest paid is a last resort when none is tagged.
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestExpenseOperating",
        "InterestPaidNet",
        "InterestPaid",
    ],
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
    annual_by_end = _collect_period_rows(
        ticker, us_gaap, span_days=ANNUAL_SPAN_DAYS, allowed_forms={"10-K", "10-K/A"}
    )
    # Every accepted annual end, also one an annual fiscal-year collision drops.
    annual_ends = list(annual_by_end)
    annual_rows = _label_rows(
        ticker,
        annual_by_end,
        lambda end, _row: (end.year,),
        fields=("fiscal_year",),
        collision_event="sec_edgar.fiscal_year_collision",
    )
    quarterly_rows = _label_rows(
        ticker,
        _collect_period_rows(
            ticker,
            us_gaap,
            span_days=QUARTERLY_SPAN_DAYS,
            allowed_forms={"10-Q", "10-Q/A"},
            row_cols=FINANCIALS_QUARTERLY_COLS,
        ),
        lambda end, row: _fiscal_quarter_key(end, annual_ends, row["_first_fy_fp"]),
        fields=("fiscal_year", "fiscal_quarter"),
        collision_event="sec_edgar.fiscal_quarter_collision",
    )
    filings = _collect_filings(ticker, us_gaap)
    shares_rescaled = _rescale_shares_diluted(ticker, annual_rows)

    return ParsedCompanyData(
        company=company,
        annual=annual_rows,
        quarterly=quarterly_rows,
        filings=filings,
        shares_rescaled=shares_rescaled,
    )


def _rescale_shares_diluted(ticker: str, rows: list[dict[str, Any]]) -> int:
    """Fix annual ``shares_diluted`` reported in millions or thousands; return the count.

    Each value is compared with the median of the other positive annual values
    (all taken from the original parse). Needs at least three comparators.
    """
    original = [row.get("shares_diluted") for row in rows]
    corrected = 0
    for i, row in enumerate(rows):
        value = original[i]
        if value is None or value <= 0:
            continue
        others = [v for j, v in enumerate(original) if j != i and v is not None and v > 0]
        if len(others) < _MIN_SHARE_COMPARATORS:
            continue
        ratio = median(others) / value
        for factor in _SHARE_SCALE_FACTORS:
            if factor / _SHARE_SCALE_TOLERANCE <= ratio <= factor * _SHARE_SCALE_TOLERANCE:
                row["shares_diluted"] = value * factor
                corrected += 1
                log.warning(
                    "sec_edgar.shares_rescaled",
                    ticker=ticker,
                    fiscal_year=row.get("fiscal_year"),
                    original=value,
                    factor=factor,
                )
                break
    return corrected


def _label_rows(
    ticker: str,
    rows: dict[date, dict[str, Any]],
    label: Callable[[date, dict[str, Any]], tuple[int, ...] | None],
    *,
    fields: tuple[str, ...],
    collision_event: str,
) -> list[dict[str, Any]]:
    """Stamp each row with its ``label`` under ``fields``; on a clash keep the later end.

    ``label`` returning None drops the row.
    """
    by_key: dict[tuple[int, ...], date] = {}
    for end in sorted(rows):
        key = label(end, rows[end])
        if key is None:
            continue
        if key in by_key:
            log.warning(
                collision_event,
                ticker=ticker,
                **dict(zip(fields, key, strict=True)),
                kept=end.isoformat(),
                dropped=by_key[key].isoformat(),
            )
        by_key[key] = end
    out: list[dict[str, Any]] = []
    for key, end in by_key.items():
        row = rows[end]
        row.pop("_first_fy_fp", None)
        row.update(zip(fields, key, strict=True))
        out.append(row)
    return out


def _fiscal_quarter_key(
    quarter_end: date, annual_ends: list[date], fallback: tuple[int, int] | None
) -> tuple[int, int] | None:
    """``(fiscal_year, fiscal_quarter)`` of a quarter, counted from the nearest annual end.

    Counts back from the next annual end within a year, else forward from the
    previous one. Without a usable annual end (or an ordinal outside 1..4) it
    returns ``fallback``, the first-reporting filing's label; ``None`` drops the row.
    """
    max_gap = ANNUAL_SPAN_DAYS[1]
    following = [e for e in annual_ends if 0 <= (e - quarter_end).days <= max_gap]
    if following:
        end = min(following)
        key = (end.year, 4 - round((end - quarter_end).days / _QUARTER_DAYS))
    else:
        preceding = [e for e in annual_ends if 0 < (quarter_end - e).days <= max_gap]
        if not preceding:
            return fallback
        end = max(preceding)
        key = (end.year + 1, round((quarter_end - end).days / _QUARTER_DAYS))
    return key if 1 <= key[1] <= 4 else fallback


def _accepted_entries(
    entries: list[dict[str, Any]], allowed_forms: set[str]
) -> list[tuple[date | None, date, dict[str, Any]]]:
    """(start, end, entry) for well-formed entries on an allowed form, oldest filing first.

    ``start`` is None for instant facts. Entries with no value, an unparsable
    ``end``, or a present-but-unparsable ``start`` are skipped. Sorting by
    (filed, accn) makes "later write wins" independent of the API's list order.
    """
    out: list[tuple[date | None, date, dict[str, Any]]] = []
    for e in sorted(entries, key=lambda x: (x.get("filed") or "", x.get("accn") or "")):
        if e.get("form", "") not in allowed_forms or e.get("val") is None:
            continue
        end = coerce_date(e.get("end"))
        if end is None:
            continue
        start = None
        if e.get("start") is not None:
            start = coerce_date(e["start"])
            if start is None:
                continue
        out.append((start, end, e))
    return out


def _collect_period_rows(
    ticker: str,
    us_gaap: dict[str, Any],
    *,
    span_days: tuple[int, int],
    allowed_forms: set[str],
    row_cols: Collection[str] | None = None,
) -> dict[date, dict[str, Any]]:
    """Build rows keyed by period ``end`` from facts attributed by their own start/end.

    ``fy``/``fp`` describe the filing, not the fact, so they never pick the
    period. A row exists only when an accepted duration fact (span inside
    ``span_days``) ends on that date; instant facts (no ``start``) attach to the
    row with the same ``end`` and are dropped otherwise. With ``row_cols``, only
    a duration fact of one of those columns creates a row (others still fill it).
    Concepts resolve per period end, not per column: for each column the first
    concept in list order with an accepted fact for an end wins that end, and later
    concepts only fill ends still unfilled. ``is_restated`` and ``_first_fy_fp``
    come from the winning concept's facts only. Facts for one ``end`` share a slot
    whatever their ``start``: one row per period end. Each row carries
    ``_first_fy_fp``: the (fy, quarter number) of the earliest-filed accepted duration fact
    ending there whose fp is Q1-Q4 and fy an int (else None), the fallback label
    for quarters with no annual end to count from.
    """
    lo, hi = span_days
    # values: end -> db_col -> val. Later (filed, accn) overwrites earlier.
    values: dict[date, dict[str, Any]] = {}
    # forms_seen: forms of every fact used per end, so is_restated survives a later
    # plain filing
    forms_seen: dict[date, set[str]] = {}
    first_seen: dict[date, tuple[str, str, int, str]] = {}
    duration_cols: set[str] = set()
    row_ends: set[date] = set()

    def entries_of(concept: str) -> list[dict[str, Any]]:
        unit_map = us_gaap.get(concept, {}).get("units", {})
        entries: list[dict[str, Any]] = unit_map.get("USD") or unit_map.get("shares") or []
        return entries

    # Phase a: duration facts decide which period ends have a row. Per column, an
    # earlier concept wins every end it has an accepted fact for.
    for db_col, concepts in ANNUAL_CONCEPT_MAP.items():
        resolved: set[date] = set()
        for concept in concepts:
            accepted = [
                (end, e)
                for start, end, e in _accepted_entries(entries_of(concept), allowed_forms)
                if start is not None and lo <= (end - start).days <= hi and end not in resolved
            ]
            if not accepted:
                continue
            for end, e in accepted:
                values.setdefault(end, {})[db_col] = e["val"]
                if row_cols is None or db_col in row_cols:
                    row_ends.add(end)
                forms_seen.setdefault(end, set()).add(e["form"])
                order = (e.get("filed") or "", e.get("accn") or "")
                fy, fp = e.get("fy"), e.get("fp")
                if (
                    isinstance(fy, int)
                    and fp in {"Q1", "Q2", "Q3", "Q4"}
                    and (end not in first_seen or order < first_seen[end][:2])
                ):
                    first_seen[end] = (*order, fy, fp)
            resolved.update(end for end, _ in accepted)
            duration_cols.add(db_col)

    # Phase b: instant facts attach to existing period ends only; same per-period
    # concept order, so a concept whose instants all miss leaves the ends to the next.
    for db_col, concepts in ANNUAL_CONCEPT_MAP.items():
        if db_col in duration_cols:
            continue
        resolved_instants: set[date] = set()
        for concept in concepts:
            matched = [
                (end, e)
                for start, end, e in _accepted_entries(entries_of(concept), allowed_forms)
                if start is None and end in row_ends and end not in resolved_instants
            ]
            for end, e in matched:
                values[end][db_col] = e["val"]
                forms_seen[end].add(e["form"])
            resolved_instants.update(end for end, _ in matched)

    out: dict[date, dict[str, Any]] = {}
    for end in row_ends:
        cols = values[end]
        row: dict[str, Any] = {
            "ticker": ticker,
            "currency": "USD",
            "source": "sec_edgar",
            "is_restated": any(f.endswith("/A") for f in forms_seen[end]),
            "period_end_date": end.isoformat(),
            **cols,
        }
        _derive_financial_fields(row)
        row["_first_fy_fp"] = (
            (first_seen[end][2], int(first_seen[end][3][1:])) if end in first_seen else None
        )
        out[end] = row
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
    """Upsert filings_log entries on PK match. Returns row count.

    Conflicts update only the accession number: ``fetched_at`` must keep the
    first-ingestion time, since new-filing events are keyed off it.
    """
    if not filings:
        return 0
    cols = ["ticker", "filing_type", "filing_date", "accession_number", "source"]
    placeholders = ", ".join(["?"] * len(cols))
    for f in filings:
        conn.execute(
            f"INSERT INTO filings_log ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (ticker, filing_type, filing_date, source) "
            f"DO UPDATE SET accession_number = excluded.accession_number",
            [f.get(c) for c in cols],
        )
    return len(filings)


def count_null_revenue(rows: list[dict[str, Any]]) -> int:
    """Number of annual rows whose ``revenue`` is missing (NULL after resolution)."""
    return sum(1 for r in rows if r.get("revenue") is None)


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
        null_revenue = count_null_revenue(parsed.annual)
        log.info(
            "ingest.annual_revenue_null",
            ticker=ticker,
            source="sec_edgar",
            annual_revenue_null=null_revenue,
            annual=annual,
        )
        run.details = {
            "ticker": ticker,
            "annual": annual,
            "quarterly": quarterly,
            "shares_rescaled": parsed.shares_rescaled,
            "filings": filings,
            "annual_revenue_null": null_revenue,
        }
    assert run.result is not None  # refresh_run always sets it on exit
    return run.result
