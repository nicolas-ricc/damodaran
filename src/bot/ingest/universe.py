"""Bulk universe ingest + incremental refresh (M2.6).

This module orchestrates importing *thousands* of tickers through a
:class:`~bot.ingest.provider.MarketDataProvider` in a single run. It is the
engine behind ``bot refresh --fmp [--universe FILE]``.

Two ideas drive the design:

* **Incremental, not full** (spec §4.4): fundamentals are invalidated *by event*
  (a new filing detected), never by a TTL. Before importing a ticker we read its
  newest ``filings_log`` date and ask the provider for the company's latest
  filing date; if it has not advanced since the last run we skip the import
  entirely. The first run (empty ``filings_log``) imports everything.
* **Resilient, not fatal**: a single ticker failing (bad symbol, FMP hiccup)
  must not abort a 500-name run. Per-ticker errors are caught, recorded, and
  reported at the end. The run's overall status is derived from the *failure
  rate*, and the CLI maps that to an exit code.

Everything here is pure in the adapter sense: functions accept a ``conn`` and an
explicit ticker list / importer callable, hold no global state, and record the
run in ``refresh_log``.
"""

from __future__ import annotations

import csv
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import partial
from importlib import resources
from pathlib import Path

import duckdb

from bot.ingest.base import IngestResult, _log_refresh, refresh_run, transaction
from bot.ingest.fmp import FmpClient, FmpRateLimitError, import_prices_from_fmp
from bot.ingest.industry_mapping import (
    IndustryMapping,
    load_industry_mapping,
    resolve_mapping_path,
)
from bot.ingest.provider import CompanyInfo, MarketDataProvider, ProviderRateLimitError
from bot.ingest.sec_edgar import (
    upsert_company,
    upsert_filings,
    upsert_financials_annual,
    upsert_financials_quarterly,
)
from bot.utils.fx import import_fx_rates
from bot.utils.logging import get_logger

log = get_logger(__name__)

# Status thresholds on the failure rate (fraction of the universe that errored).
# < 5% failed -> success, 5-25% -> partial, > 25% -> error. The CLI additionally
# exits non-zero (code 2) when the failure rate exceeds the success threshold.
SUCCESS_MAX_FAILURE_RATE = 0.05
PARTIAL_MAX_FAILURE_RATE = 0.25

# How often (in tickers processed) to emit a structlog progress line.
DEFAULT_PROGRESS_EVERY = 50

# Importer signature: (conn, *, ticker, api_key) -> IngestResult.
type Importer = Callable[..., IngestResult]


@dataclass(frozen=True)
class TickerOutcome:
    """What happened to one ticker during a universe refresh."""

    ticker: str
    # "imported": fetched + upserted. "skipped": unchanged since last run.
    # "failed": the per-ticker import raised or returned an error result.
    # "deferred": not attempted (or the run was interrupted) by an FMP rate limit.
    status: str
    rows_affected: int = 0
    error_message: str | None = None


@dataclass
class UniverseRefreshResult:
    """Aggregate outcome of a bulk universe refresh."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    status: str
    total: int
    imported: int
    skipped: int
    failed: int
    outcomes: list[TickerOutcome] = field(default_factory=list)

    @property
    def deferred(self) -> int:
        """Tickers no intentados porque la cuota diaria de FMP se agotó."""
        return sum(1 for o in self.outcomes if o.status == "deferred")

    @property
    def failure_rate(self) -> float:
        """Fracción de lo *intentado* que falló (0.0 cuando no se intentó nada)."""
        attempted = self.total - self.deferred
        return self.failed / attempted if attempted else 0.0

    @property
    def failures(self) -> list[TickerOutcome]:
        """The failed-ticker outcomes, for end-of-run reporting."""
        return [o for o in self.outcomes if o.status == "failed"]


def load_universe(path: Path) -> list[str]:
    """Read a CSV universe file and return the de-duplicated upper-cased tickers.

    The file is a CSV with a header row. The ticker is taken from a column named
    ``ticker`` (case-insensitive) when present, otherwise the first column. Blank
    lines, blank cells and rows beginning with ``#`` (comments) are ignored.
    Order is preserved; duplicates are dropped (first occurrence wins).
    """
    text = path.read_text(encoding="utf-8")
    return _parse_universe_csv(text)


def default_universe_path() -> Path:
    """Return the path to the small default universe CSV shipped with the package."""
    return Path(str(resources.files("bot.ingest").joinpath("universe_default.csv")))


def _parse_universe_csv(text: str) -> list[str]:
    rows = [
        row for row in csv.reader(text.splitlines()) if row and not row[0].strip().startswith("#")
    ]
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    ticker_idx = header.index("ticker") if "ticker" in header else 0
    # If the first row is not a header (no "ticker" column and first cell looks
    # like data), treat it as data too.
    data_rows = rows[1:] if "ticker" in header else rows
    out: list[str] = []
    seen: set[str] = set()
    for row in data_rows:
        if not row:
            continue
        cell = row[ticker_idx] if ticker_idx < len(row) else ""
        ticker = cell.strip().upper()
        if not ticker or ticker.startswith("#"):
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def latest_local_filing_date(
    conn: duckdb.DuckDBPyConnection, ticker: str, source: str = "fmp"
) -> date | None:
    """Return the newest ``filings_log`` date stored for ``ticker`` / ``source``."""
    row = conn.execute(
        "SELECT max(filing_date) FROM filings_log WHERE ticker = ? AND source = ?",
        [ticker.upper(), source],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    value = row[0]
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _resolve_status(failure_rate: float) -> str:
    if failure_rate <= SUCCESS_MAX_FAILURE_RATE:
        return "success"
    if failure_rate <= PARTIAL_MAX_FAILURE_RATE:
        return "partial"
    return "error"


def _company_row(
    ticker: str,
    info: CompanyInfo | None,
    currency: str | None,
    *,
    source: str,
    mapping: IndustryMapping,
) -> dict[str, object]:
    """Build the ``companies`` row from the provider's profile (+ parsed currency
    fallback).

    ``source`` is the owning provider's short id (``provider.name``, e.g. ``"fmp"``)
    so ``companies.source`` traces back to whichever adapter supplied the row.

    The profile's ``currency`` is preferred; the parsed statement currency is the
    fallback so a company row always carries a currency even if the profile omits
    it.

    ``industry`` keeps the provider's own label for traceability;
    ``industry_damodaran`` carries the translated label the sector-relative rules
    and the valuator key off (spec §4.3.1), or ``None`` when unmapped. An unmapped
    label is logged as a warning: it leaves every sector assumption ``unresolved``
    (so ``analyze`` raises) and ``is_financial_services`` ``False`` (so a bank
    slips past the §6.2 exclusion), and the only fix is a mapping-CSV row.
    """
    sym = ticker.upper()
    if info is None:
        return {
            "ticker": sym,
            "name": sym,
            "currency": currency,
            "source": source,
            "status": "active",
            "industry_damodaran": None,
            "ipo_date": None,
        }
    damodaran_industry = mapping.resolve(source, info.industry)
    if damodaran_industry is None and info.industry is not None:
        log.warning(
            "ingest.industry_mapping.unmapped",
            ticker=sym,
            provider=source,
            provider_industry=info.industry,
        )
    return {
        "ticker": sym,
        "name": info.name or sym,
        "country": info.country,
        "exchange": info.exchange_short_name or info.exchange,
        "industry": info.industry,
        "industry_damodaran": damodaran_industry,
        "currency": info.currency or currency,
        "status": "active" if info.is_actively_trading else "inactive",
        "source": source,
        "ipo_date": info.ipo_date,
    }


def import_company(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    provider: MarketDataProvider,
    mapping: IndustryMapping | None = None,
    mapping_path: Path | None = None,
) -> IngestResult:
    """Fetch + upsert one ticker's fundamentals through the provider port.

    Mirrors :func:`bot.ingest.sec_edgar.import_company_from_sec`: it returns the
    same :class:`IngestResult` contract and reuses the existing
    ``upsert_company`` / ``upsert_financials_*`` helpers. All writes happen in a
    single transaction; the run is recorded in ``refresh_log`` under
    ``provider.name``.

    Pass ``mapping`` to reuse an already-loaded :class:`IndustryMapping` across
    many tickers; when omitted, ``mapping_path`` (i.e.
    ``Settings.industry_mapping_path``) is loaded for this call alone, falling
    back to the packaged CSV when that file does not exist.
    """
    sym = ticker.upper()
    with refresh_run(
        conn,
        source=provider.name,
        log=log,
        error_event="ingest.import.failed",
        log_fail_event="ingest.refresh_log_insert_failed",
    ) as run:
        run.details = {"ticker": sym}
        bundle = provider.fundamentals(sym)
        currency = (
            bundle.annual.company.get("currency") or bundle.quarterly.company.get("currency")
        )
        resolved_mapping = (
            mapping
            if mapping is not None
            else load_industry_mapping(resolve_mapping_path(mapping_path))
        )
        company = _company_row(
            sym, bundle.info, currency, source=provider.name, mapping=resolved_mapping
        )
        with transaction(conn):
            upsert_company(conn, company)
            annual = upsert_financials_annual(conn, bundle.annual.annual)
            quarterly = upsert_financials_quarterly(conn, bundle.quarterly.quarterly)
            filings = upsert_filings(conn, bundle.filings)
        run.rows_affected = 1 + annual + quarterly + filings
        run.details = {
            "ticker": sym,
            "annual": annual,
            "quarterly": quarterly,
            "filings": filings,
            "currency": currency,
        }
    assert run.result is not None  # refresh_run always sets it on exit
    return run.result


def refresh_universe(
    conn: duckdb.DuckDBPyConnection,
    *,
    provider: MarketDataProvider,
    tickers: list[str],
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    mapping_path: Path | None = None,
) -> UniverseRefreshResult:
    """Bulk-import ``tickers`` through ``provider``, skipping unchanged ones.

    For each ticker:

    1. Probe the provider for the ticker's latest filing date and compare it to
       the newest ``filings_log`` date already stored. If the remote date has
       *not* advanced (and we have a local date), the ticker is **skipped**. A
       probe that errors is non-fatal — we fall through and attempt the full
       import.
    2. Otherwise import the ticker via :func:`import_company`. Any exception or
       error ``IngestResult`` is caught, recorded as a **failed** outcome, and
       the run continues.

    A :class:`~bot.ingest.provider.ProviderRateLimitError` (from either the
    probe or the import) stops the run cleanly: the remaining tickers are
    recorded as **deferred**, not failed.

    Progress is logged via structlog every ``progress_every`` tickers. The
    aggregate status is derived from the failure rate (``_resolve_status``) and a
    summary row is written to ``refresh_log`` (source ``f"{provider.name}_universe"``).

    ``mapping_path`` is the industry-mapping CSV to load for the run — the CLI
    passes ``Settings.industry_mapping_path`` so a user-edited CSV actually takes
    effect; a non-existent path falls back to the packaged copy.
    """
    # Load the mapping once for the whole bulk run instead of once per ticker
    # (import_company would otherwise re-read + re-parse the CSV every call).
    mapping = load_industry_mapping(resolve_mapping_path(mapping_path))
    return _run_bulk_refresh(
        conn,
        items=tickers,
        process=lambda ticker: _refresh_one(
            conn, ticker=ticker, provider=provider, mapping=mapping
        ),
        source=f"{provider.name}_universe",
        label="universe",
        progress_every=progress_every,
    )


@contextmanager
def _shared_fmp_client(api_key: str, *, needed: bool) -> Iterator[FmpClient | None]:
    """Yield one :class:`FmpClient` for a bulk run (or ``None`` when not needed),
    closing it on exit. Centralises the open/close lifecycle the universe / prices
    / fx orchestrators share; each still binds the client into its own importer."""
    client = FmpClient(api_key=api_key) if needed else None
    try:
        yield client
    finally:
        if client is not None:
            client.close()


def _run_bulk_refresh(
    conn: duckdb.DuckDBPyConnection,
    *,
    items: list[str],
    process: Callable[[str], TickerOutcome],
    source: str,
    label: str,
    progress_every: int,
) -> UniverseRefreshResult:
    """Drive a bulk refresh: loop ``items`` through ``process``, tally outcomes,
    log progress under ``{label}.refresh.*``, and write one ``source`` summary row
    to ``refresh_log``.

    The caller owns the :class:`FmpClient` lifecycle and binds it into ``process``;
    this driver only sequences the per-item work and aggregates the result, shared
    by the universe / prices / fx refreshes.
    """
    started = datetime.now()
    run_id = str(uuid.uuid4())
    total = len(items)
    outcomes: list[TickerOutcome] = []
    imported = skipped = failed = deferred = 0
    rate_limited = False

    log.info(f"{label}.refresh.start", run_id=run_id, total=total)
    for index, item in enumerate(items, start=1):
        if rate_limited:
            outcomes.append(TickerOutcome(ticker=item.upper(), status="deferred"))
            deferred += 1
            continue
        try:
            outcome = process(item)
        except ProviderRateLimitError as exc:
            log.warning(f"{label}.refresh.rate_limited", item=item, error=str(exc))
            rate_limited = True
            outcomes.append(TickerOutcome(ticker=item.upper(), status="deferred"))
            deferred += 1
            continue
        outcomes.append(outcome)
        if outcome.status == "imported":
            imported += 1
        elif outcome.status == "skipped":
            skipped += 1
        elif outcome.status == "deferred":
            deferred += 1
        else:
            failed += 1

        if progress_every > 0 and index % progress_every == 0:
            log.info(
                f"{label}.refresh.progress",
                run_id=run_id,
                processed=index,
                total=total,
                imported=imported,
                skipped=skipped,
                failed=failed,
                deferred=deferred,
            )

    finished = datetime.now()
    attempted = total - deferred
    failure_rate = failed / attempted if attempted else 0.0
    status = _resolve_status(failure_rate)
    result = UniverseRefreshResult(
        run_id=run_id,
        started_at=started,
        finished_at=finished,
        status=status,
        total=total,
        imported=imported,
        skipped=skipped,
        failed=failed,
        outcomes=outcomes,
    )

    if result.failures:
        log.warning(
            f"{label}.refresh.failures",
            run_id=run_id,
            failed=failed,
            failure_rate=round(failure_rate, 4),
            tickers=[f.ticker for f in result.failures],
        )

    log.info(
        f"{label}.refresh.done",
        run_id=run_id,
        status=status,
        total=total,
        imported=imported,
        skipped=skipped,
        failed=failed,
        deferred=deferred,
    )

    _log_bulk_refresh(conn, result, source=source)
    return result


def company_currency(conn: duckdb.DuckDBPyConnection, ticker: str) -> str | None:
    """The listing currency stored for ``ticker`` in ``companies`` (None if absent)."""
    row = conn.execute(
        "SELECT currency FROM companies WHERE ticker = ?", [ticker.upper()]
    ).fetchone()
    return str(row[0]) if row is not None and row[0] else None


def refresh_prices_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    *,
    api_key: str,
    tickers: list[str],
    since_date: date | None = None,
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    importer: Importer = import_prices_from_fmp,
) -> UniverseRefreshResult:
    """Bulk-refresh EOD prices for ``tickers`` from FMP (incremental per ticker).

    Shares one :class:`FmpClient` across the run; per-ticker errors are isolated
    into a failed outcome; a ``fmp_prices_universe`` summary row is written to
    ``refresh_log``. Each ticker's currency is read from ``companies.currency`` and
    passed through so ``prices_daily.currency`` is set for the screener's USD
    market-cap conversion. ``importer`` is injectable for tests.
    """
    needs_client = importer is import_prices_from_fmp
    with _shared_fmp_client(api_key, needed=needs_client) as shared_client:
        active = importer
        if importer is import_prices_from_fmp and shared_client is not None:
            active = partial(import_prices_from_fmp, client=shared_client)

        return _run_bulk_refresh(
            conn,
            items=tickers,
            process=lambda ticker: _refresh_one_price(
                conn, ticker=ticker, api_key=api_key, since_date=since_date, importer=active
            ),
            source="fmp_prices_universe",
            label="prices",
            progress_every=progress_every,
        )


def _refresh_one_price(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    api_key: str,
    since_date: date | None,
    importer: Importer,
) -> TickerOutcome:
    """Refresh one ticker's prices, never raising. Returns its outcome."""
    sym = ticker.upper()
    try:
        currency = company_currency(conn, sym)
        result = importer(
            conn, ticker=sym, api_key=api_key, since_date=since_date, currency=currency
        )
        if result.is_success():
            return TickerOutcome(ticker=sym, status="imported", rows_affected=result.rows_affected)
        return TickerOutcome(
            ticker=sym,
            status="failed",
            error_message=result.error_message or "import returned non-success",
        )
    except FmpRateLimitError:
        raise
    except Exception as exc:
        log.warning("prices.refresh.ticker_failed", ticker=sym, error=str(exc))
        return TickerOutcome(ticker=sym, status="failed", error_message=str(exc))


def distinct_non_usd_currencies(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """The distinct non-USD listing currencies present in ``companies`` (USD needs
    no FX rate — it is the numeraire)."""
    rows = conn.execute(
        "SELECT DISTINCT currency FROM companies "
        "WHERE currency IS NOT NULL AND upper(currency) <> 'USD' "
        "ORDER BY currency"
    ).fetchall()
    return [str(r[0]).upper() for r in rows]


def refresh_fx_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    *,
    api_key: str,
    start: date | None = None,
    end: date | None = None,
    currencies: list[str] | None = None,
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    importer: Importer = import_fx_rates,
) -> UniverseRefreshResult:
    """Bulk-refresh FX rates for the currencies held in ``companies`` (or an
    explicit ``currencies`` list).

    Shares one :class:`FmpClient` across the run; per-currency errors are isolated;
    a ``fmp_fx_universe`` summary row is written to ``refresh_log``. An all-USD
    universe yields an empty currency set → ``total=0``, status ``success``, no FMP
    calls. ``importer`` is injectable for tests.
    """
    items = currencies if currencies is not None else distinct_non_usd_currencies(conn)
    # No client needed for an all-USD universe (empty set → no FMP calls).
    needs_client = importer is import_fx_rates and bool(items)
    with _shared_fmp_client(api_key, needed=needs_client) as shared_client:
        active = importer
        if importer is import_fx_rates and shared_client is not None:
            active = partial(import_fx_rates, client=shared_client)

        return _run_bulk_refresh(
            conn,
            items=items,
            process=lambda currency: _refresh_one_currency(
                conn, currency=currency, api_key=api_key, start=start, end=end, importer=active
            ),
            source="fmp_fx_universe",
            label="fx",
            progress_every=progress_every,
        )


def _refresh_one_currency(
    conn: duckdb.DuckDBPyConnection,
    *,
    currency: str,
    api_key: str,
    start: date | None,
    end: date | None,
    importer: Importer,
) -> TickerOutcome:
    """Refresh one currency's FX rates, never raising. Returns its outcome (the
    ``ticker`` field carries the currency code)."""
    ccy = currency.upper()
    try:
        result = importer(conn, currency=ccy, api_key=api_key, start=start, end=end)
        if result.is_success():
            return TickerOutcome(ticker=ccy, status="imported", rows_affected=result.rows_affected)
        return TickerOutcome(
            ticker=ccy,
            status="failed",
            error_message=result.error_message or "import returned non-success",
        )
    except FmpRateLimitError:
        raise
    except Exception as exc:
        log.warning("fx.refresh.currency_failed", currency=ccy, error=str(exc))
        return TickerOutcome(ticker=ccy, status="failed", error_message=str(exc))


def _refresh_one(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    provider: MarketDataProvider,
    mapping: IndustryMapping,
) -> TickerOutcome:
    """Refresh a single ticker, never raising. Returns its outcome."""
    sym = ticker.upper()
    try:
        local_latest = latest_local_filing_date(conn, sym)
        if local_latest is not None and _should_skip(sym, local_latest, provider):
            log.info("universe.refresh.skip", ticker=sym, latest_filing=local_latest)
            return TickerOutcome(ticker=sym, status="skipped")

        result = import_company(conn, ticker=sym, provider=provider, mapping=mapping)
        if result.is_success():
            return TickerOutcome(ticker=sym, status="imported", rows_affected=result.rows_affected)
        return TickerOutcome(
            ticker=sym,
            status="failed",
            error_message=result.error_message or "import returned non-success",
        )
    except ProviderRateLimitError:
        raise
    except Exception as exc:
        log.warning("universe.refresh.ticker_failed", ticker=sym, error=str(exc))
        return TickerOutcome(ticker=sym, status="failed", error_message=str(exc))


def _should_skip(ticker: str, local_latest: date, provider: MarketDataProvider) -> bool:
    """Return True when the remote latest filing date has not advanced.

    A probe error is swallowed (returns False) so a transient lookup failure
    triggers a full import rather than a silent skip of stale data.
    """
    try:
        remote_latest = provider.latest_filing_date(ticker)
    except ProviderRateLimitError:
        raise
    except Exception as exc:
        log.warning("universe.refresh.probe_failed", ticker=ticker, error=str(exc))
        return False
    if remote_latest is None:
        return False
    return remote_latest <= local_latest


def _log_bulk_refresh(
    conn: duckdb.DuckDBPyConnection, result: UniverseRefreshResult, *, source: str
) -> None:
    """Write the run summary to ``refresh_log`` under ``source`` (e.g. ``fmp_universe``)."""
    error_message = None
    if result.failures:
        sample = ", ".join(f.ticker for f in result.failures[:10])
        error_message = f"{result.failed}/{result.total} failed: {sample}"
    if result.deferred:
        deferred_note = f"rate limited: {result.deferred} deferred"
        error_message = f"{error_message}; {deferred_note}" if error_message else deferred_note
    summary = IngestResult(
        source=source,
        started_at=result.started_at,
        finished_at=result.finished_at,
        status=result.status,  # type: ignore[arg-type]
        rows_affected=result.imported,
        error_message=error_message,
    )
    try:
        _log_refresh(conn, summary, run_id=result.run_id)
    except Exception as log_err:
        log.exception("refresh_log_insert_failed", source=source, error=str(log_err))
