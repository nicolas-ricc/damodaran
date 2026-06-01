"""Bulk universe ingest + incremental refresh (M2.6).

This module orchestrates importing *thousands* of tickers from FMP in a single
run. It is the engine behind ``bot refresh --fmp [--universe FILE]``.

Two ideas drive the design:

* **Incremental, not full** (spec §4.4): fundamentals are invalidated *by event*
  (a new filing detected), never by a TTL. Before importing a ticker we read its
  newest ``filings_log`` date and ask FMP for the company's latest filing date;
  if it has not advanced since the last run we skip the import entirely. The
  first run (empty ``filings_log``) imports everything.
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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import partial
from importlib import resources
from pathlib import Path

import duckdb

from bot.ingest.base import IngestResult, _log_refresh
from bot.ingest.fmp import FmpClient, import_company_from_fmp, import_prices_from_fmp
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
# Latest-filing probe signature: (ticker) -> date | None.
type LatestFilingProbe = Callable[[str], date | None]


@dataclass(frozen=True)
class TickerOutcome:
    """What happened to one ticker during a universe refresh."""

    ticker: str
    # "imported": fetched + upserted. "skipped": unchanged since last run.
    # "failed": the per-ticker import raised or returned an error result.
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
    def failure_rate(self) -> float:
        """Fraction of the universe whose import failed (0.0 when empty)."""
        return self.failed / self.total if self.total else 0.0

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


def make_fmp_latest_filing_probe(
    api_key: str, client: FmpClient | None = None
) -> LatestFilingProbe:
    """Build a probe that returns a ticker's newest filing date from FMP.

    Uses the lightweight annual income-statement endpoint (``limit=1``) and reads
    its ``fillingDate`` (FMP's spelling). Returns ``None`` when FMP has nothing —
    in which case the caller imports the ticker (better to try than to skip).

    Pass ``client`` to reuse an open :class:`FmpClient` across probes (the bulk
    refresh shares one for the whole run); otherwise each probe opens its own.
    """

    def probe(ticker: str) -> date | None:
        if client is not None:
            rows = client.income_statement(ticker, period="annual", limit=1)
        else:
            with FmpClient(api_key=api_key) as own:
                rows = own.income_statement(ticker, period="annual", limit=1)
        return _latest_filing_from_statements(rows)

    return probe


def _latest_filing_from_statements(rows: Iterable[dict[str, object]]) -> date | None:
    latest: date | None = None
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        filed_raw = entry.get("fillingDate") or entry.get("acceptedDate")
        if not filed_raw:
            continue
        try:
            filed = date.fromisoformat(str(filed_raw)[:10])
        except ValueError:
            continue
        if latest is None or filed > latest:
            latest = filed
    return latest


def _resolve_status(failure_rate: float) -> str:
    if failure_rate <= SUCCESS_MAX_FAILURE_RATE:
        return "success"
    if failure_rate <= PARTIAL_MAX_FAILURE_RATE:
        return "partial"
    return "error"


def refresh_universe_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    *,
    api_key: str,
    tickers: list[str],
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    importer: Importer = import_company_from_fmp,
    latest_filing_probe: LatestFilingProbe | None = None,
) -> UniverseRefreshResult:
    """Bulk-import ``tickers`` from FMP, skipping those unchanged since last run.

    For each ticker:

    1. Probe FMP for the ticker's latest filing date and compare it to the newest
       ``filings_log`` date already stored. If the remote date has *not* advanced
       (and we have a local date), the ticker is **skipped**. A probe that errors
       is non-fatal — we fall through and attempt the full import.
    2. Otherwise import the ticker via ``importer`` (the M2.3 single-ticker
       importer by default). Any exception or error ``IngestResult`` is caught,
       recorded as a **failed** outcome, and the run continues.

    Progress is logged via structlog every ``progress_every`` tickers. The
    aggregate status is derived from the failure rate (``_resolve_status``) and a
    summary row is written to ``refresh_log`` (source ``fmp_universe``). ``importer``
    and ``latest_filing_probe`` are injectable to keep the orchestrator testable
    without live HTTP.
    """
    # Open one FmpClient (one connection pool) for the whole run and share it
    # across the probe and the default importer, instead of constructing a fresh
    # client — and TLS handshake — per ticker on each. Only the real FMP path
    # needs it: a fully-injected importer + probe (tests) makes no live calls.
    needs_client = importer is import_company_from_fmp or latest_filing_probe is None
    shared_client = FmpClient(api_key=api_key) if needs_client else None
    try:
        probe = latest_filing_probe or make_fmp_latest_filing_probe(api_key, client=shared_client)
        active_importer = importer
        if importer is import_company_from_fmp and shared_client is not None:
            active_importer = partial(import_company_from_fmp, client=shared_client)

        return _run_bulk_refresh(
            conn,
            items=tickers,
            process=lambda ticker: _refresh_one(
                conn, ticker=ticker, api_key=api_key, importer=active_importer, probe=probe
            ),
            source="fmp_universe",
            label="universe",
            progress_every=progress_every,
        )
    finally:
        if shared_client is not None:
            shared_client.close()


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
    imported = skipped = failed = 0

    log.info(f"{label}.refresh.start", run_id=run_id, total=total)
    for index, item in enumerate(items, start=1):
        outcome = process(item)
        outcomes.append(outcome)
        if outcome.status == "imported":
            imported += 1
        elif outcome.status == "skipped":
            skipped += 1
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
            )

    finished = datetime.now()
    failure_rate = failed / total if total else 0.0
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
    shared_client = FmpClient(api_key=api_key) if needs_client else None
    try:
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
    finally:
        if shared_client is not None:
            shared_client.close()


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
    except Exception as exc:
        log.warning("prices.refresh.ticker_failed", ticker=sym, error=str(exc))
        return TickerOutcome(ticker=sym, status="failed", error_message=str(exc))


def _refresh_one(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    api_key: str,
    importer: Importer,
    probe: LatestFilingProbe,
) -> TickerOutcome:
    """Refresh a single ticker, never raising. Returns its outcome."""
    sym = ticker.upper()
    try:
        local_latest = latest_local_filing_date(conn, sym)
        if local_latest is not None and _should_skip(sym, local_latest, probe):
            log.info("universe.refresh.skip", ticker=sym, latest_filing=local_latest)
            return TickerOutcome(ticker=sym, status="skipped")

        result = importer(conn, ticker=sym, api_key=api_key)
        if result.is_success():
            return TickerOutcome(ticker=sym, status="imported", rows_affected=result.rows_affected)
        return TickerOutcome(
            ticker=sym,
            status="failed",
            error_message=result.error_message or "import returned non-success",
        )
    except Exception as exc:
        log.warning("universe.refresh.ticker_failed", ticker=sym, error=str(exc))
        return TickerOutcome(ticker=sym, status="failed", error_message=str(exc))


def _should_skip(ticker: str, local_latest: date, probe: LatestFilingProbe) -> bool:
    """Return True when the remote latest filing date has not advanced.

    A probe error is swallowed (returns False) so a transient lookup failure
    triggers a full import rather than a silent skip of stale data.
    """
    try:
        remote_latest = probe(ticker)
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
