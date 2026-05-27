"""Financial Modeling Prep (FMP) adapter — company lookup and price ingest."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult
from bot.utils.logging import get_logger

log = get_logger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


@dataclass
class PricePoint:
    """One day of price data returned by FmpClient.fetch_historical_prices."""

    date: str  # ISO "YYYY-MM-DD"
    close: float
    volume: int | None
    market_cap: float | None = None


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

        FMP's ``from`` parameter is inclusive; callers that want strictly-newer
        rows must filter the result themselves.
        """
        ticker = ticker.upper()
        params: dict[str, Any] = {}
        if since_date is not None:
            params["from"] = since_date.isoformat()
        data: Any = self._get(f"/historical-price-full/{ticker}", **params)
        historical: list[dict[str, Any]] = (
            data.get("historical", []) if isinstance(data, dict) else []
        )
        return [
            PricePoint(
                date=str(entry["date"]),
                close=float(entry["close"]),
                volume=int(entry["volume"]) if entry.get("volume") is not None else None,
            )
            for entry in historical
        ]


def import_prices_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    since_date: date | None = None,
    *,
    api_key: str,
) -> IngestResult:
    """Fetch daily prices from FMP and upsert into ``prices_daily``.

    Incremental by default: queries ``MAX(date)`` for *ticker* and only fetches
    rows newer than that.  Pass *since_date* to override the automatic cutoff.

    The second call with the same *ticker* and no new data upstream inserts
    zero rows (idempotent).
    """
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    ticker = ticker.upper()

    try:
        row = conn.execute(
            "SELECT MAX(date) FROM prices_daily WHERE ticker = ?", [ticker]
        ).fetchone()
        db_max: date | None = row[0] if row and row[0] is not None else None

        # fetch_from: date passed to FMP's inclusive `from=` parameter
        fetch_from: date | None = since_date if since_date is not None else db_max

        with FmpClient(api_key=api_key) as client:
            company = client.lookup_company(ticker)
            currency = company.currency if company else None
            points = client.fetch_historical_prices(ticker, since_date=fetch_from)

        # When using the automatic cutoff, filter out the cutoff date itself
        # because FMP's `from=` is inclusive and we already stored that date.
        if db_max is not None and since_date is None:
            cutoff = db_max.isoformat()
            points = [p for p in points if p.date > cutoff]

        inserted = 0
        for point in points:
            conn.execute(
                "DELETE FROM prices_daily WHERE ticker = ? AND date = ?",
                [ticker, point.date],
            )
            conn.execute(
                "INSERT INTO prices_daily (ticker, date, close, volume, market_cap, currency)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [ticker, point.date, point.close, point.volume, point.market_cap, currency],
            )
            inserted += 1

        result: IngestResult = IngestResult(
            source="fmp_prices",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="success",
            rows_affected=inserted,
            details={"ticker": ticker, "currency": currency},
        )
    except Exception as e:
        log.exception("fmp.import_prices.failed", ticker=ticker, error=str(e))
        result = IngestResult(
            source="fmp_prices",
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
