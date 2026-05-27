"""Financial Modeling Prep (FMP) adapter — company lookup and price ingest."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult
from bot.utils.logging import get_logger

log = get_logger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

# Always re-fetch this many calendar days of history on every run, so that
# same-day re-runs refresh today's bar and recent data-vendor corrections are
# picked up.  ~5 trading days.  Deep historical revisions (>7 days back)
# still require an explicit since_date backfill.
_REFRESH_WINDOW_DAYS = 7

# Skip the FMP profile call when the companies row is fresher than this.
_COMPANY_CACHE_DAYS = 30


@dataclass
class PricePoint:
    """One day of price data returned by FmpClient.fetch_historical_prices."""

    date: date
    close: float
    volume: int | None
    market_cap: float | None = None
    adj_close: float | None = None


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

    def fetch_historical_prices(
        self, ticker: str, *, since_date: date | None = None
    ) -> list[PricePoint]:
        """Return daily close + volume for *ticker* from *since_date* onwards.

        FMP's ``from`` parameter is inclusive.  Rows with unparseable dates are
        logged and skipped.
        """
        ticker = ticker.upper()
        params: dict[str, Any] = {}
        if since_date is not None:
            params["from"] = since_date.isoformat()
        data: Any = self._get(f"/historical-price-full/{ticker}", **params)
        historical: list[dict[str, Any]] = (
            data.get("historical", []) if isinstance(data, dict) else []
        )
        points: list[PricePoint] = []
        for entry in historical:
            try:
                pt_date = date.fromisoformat(str(entry["date"]))
            except (ValueError, KeyError):
                log.warning("fmp.bad_date_skipped", entry=entry)
                continue
            points.append(
                PricePoint(
                    date=pt_date,
                    close=float(entry["close"]),
                    volume=(
                        int(entry["volume"]) if entry.get("volume") is not None else None
                    ),
                    adj_close=(
                        float(entry["adjClose"])
                        if entry.get("adjClose") is not None
                        else None
                    ),
                )
            )
        return points


def import_prices_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    since_date: date | None = None,
    *,
    api_key: str,
) -> IngestResult:
    """Fetch daily prices from FMP and upsert into ``prices_daily``.

    Incremental by default: re-fetches the last ``_REFRESH_WINDOW_DAYS``
    calendar days on every run, so same-day re-runs refresh today's bar and
    recent data-vendor corrections are picked up.  Pass *since_date* to
    override the fetch window start entirely.

    Deep historical revisions (more than ``_REFRESH_WINDOW_DAYS`` days back)
    still require an explicit *since_date* backfill.

    All writes are executed inside a single transaction; a mid-batch error
    rolls back the entire batch and records zero rows affected.

    The FMP company profile is skipped when a companies row newer than
    ``_COMPANY_CACHE_DAYS`` days already exists for the ticker.
    """
    started = datetime.now(UTC)
    run_id = str(uuid.uuid4())
    ticker = ticker.upper()

    try:
        row = conn.execute(
            "SELECT MAX(date) FROM prices_daily WHERE ticker = ?", [ticker]
        ).fetchone()
        db_max: date | None = row[0] if row and row[0] is not None else None

        # Determine fetch window start.  Always re-fetch the last
        # _REFRESH_WINDOW_DAYS so today's bar and recent revisions are captured.
        fetch_from: date | None
        if since_date is not None:
            fetch_from = since_date
        elif db_max is not None:
            fetch_from = db_max - timedelta(days=_REFRESH_WINDOW_DAYS)
        else:
            fetch_from = None

        # Use cached currency when the companies row is recent enough.
        company_row = conn.execute(
            "SELECT currency, last_updated_at FROM companies WHERE ticker = ?", [ticker]
        ).fetchone()
        now_naive = datetime.now(UTC).replace(tzinfo=None)
        need_lookup: bool = company_row is None or (
            now_naive - company_row[1]
        ).days > _COMPANY_CACHE_DAYS

        currency: str | None = (
            company_row[0] if not need_lookup and company_row is not None else None
        )

        with FmpClient(api_key=api_key) as client:
            if need_lookup:
                company = client.lookup_company(ticker)
                currency = company.currency if company else None
            points = client.fetch_historical_prices(ticker, since_date=fetch_from)

        inserted = 0
        conn.begin()
        try:
            for point in points:
                conn.execute(
                    "DELETE FROM prices_daily WHERE ticker = ? AND date = ?",
                    [ticker, point.date],
                )
                conn.execute(
                    "INSERT INTO prices_daily"
                    " (ticker, date, close, volume, market_cap, currency, adjusted_close)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        ticker,
                        point.date,
                        point.close,
                        point.volume,
                        point.market_cap,
                        currency,
                        point.adj_close,
                    ],
                )
                inserted += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        result: IngestResult = IngestResult(
            source="fmp_prices",
            started_at=started,
            finished_at=datetime.now(UTC),
            status="success",
            rows_affected=inserted,
            details={"ticker": ticker, "currency": currency},
        )
    except Exception as e:
        log.exception("fmp.import_prices.failed", ticker=ticker, error=str(e))
        result = IngestResult(
            source="fmp_prices",
            started_at=started,
            finished_at=datetime.now(UTC),
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
