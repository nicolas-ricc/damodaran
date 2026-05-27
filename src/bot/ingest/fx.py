"""ECB Statistical Data Warehouse — FX rate ingest adapter.

FX rates are fetched from the ECB SDW REST API (data-api.ecb.europa.eu/service/data/EXR).
ECB publishes rates as units of the quoted currency per 1 EUR.  To obtain rate_to_usd
(1 unit of currency X = ? USD) we use EUR as the cross:

    rate_to_usd[EUR] = ECB rate for D.USD.EUR.SP00.A  (USD per 1 EUR)
    rate_to_usd[X]   = ECB_USD_EUR / ECB_X_EUR        (USD per 1 X, for any other X)
    rate_to_usd[USD] = 1.0 (by definition, stored for completeness)

See docs/adr/0004-fx-source-ecb.md for the rationale for ECB over FMP.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

import duckdb
import httpx

from bot.ingest.base import IngestResult
from bot.utils.logging import get_logger

log = get_logger(__name__)

ECB_API_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"


def _ecb_url(currency: str, start: date, end: date) -> str:
    key = f"D.{currency.upper()}.EUR.SP00.A"
    return (
        f"{ECB_API_BASE}/{key}"
        f"?startPeriod={start.isoformat()}&endPeriod={end.isoformat()}&format=jsondata"
    )


def _parse_ecb_response(body: dict[str, Any]) -> dict[str, float]:
    """Return {date_str: rate} from an ECB SDMX-JSON response."""
    try:
        obs_dims = body["structure"]["dimensions"]["observation"]
        time_dim = next(d for d in obs_dims if d["id"] == "TIME_PERIOD")
        date_values: list[str] = [v["id"] for v in time_dim["values"]]

        series_data: dict[str, Any] = body["dataSets"][0]["series"]
        observations: dict[str, list[Any]] = next(iter(series_data.values()))["observations"]

        result: dict[str, float] = {}
        for idx_str, obs_vals in observations.items():
            idx = int(idx_str)
            val = obs_vals[0]
            if val is not None and idx < len(date_values):
                result[date_values[idx]] = float(val)
        return result
    except (KeyError, StopIteration, IndexError, TypeError) as exc:
        log.warning("ecb.parse_failed", error=str(exc))
        return {}


def fetch_ecb_rates(
    currency: str,
    start: date,
    end: date,
    *,
    client: httpx.Client,
) -> dict[str, float]:
    """Return {date_str: rate} for `currency` quoted as units-per-EUR from ECB."""
    url = _ecb_url(currency, start, end)
    log.info("ecb.fetch", currency=currency, start=str(start), end=str(end))
    resp = client.get(url)
    if resp.status_code == 404:
        log.warning("ecb.not_found", currency=currency, url=url)
        return {}
    resp.raise_for_status()
    return _parse_ecb_response(resp.json())


def upsert_fx_rows(
    conn: duckdb.DuckDBPyConnection,
    rows: list[dict[str, Any]],
) -> int:
    """Delete-then-insert FX rows into currencies. Returns number of rows written."""
    if not rows:
        return 0
    for r in rows:
        conn.execute(
            "DELETE FROM currencies WHERE currency = ? AND date = ?",
            [r["currency"], r["date"]],
        )
        conn.execute(
            "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES (?, ?, ?, ?)",
            [r["currency"], r["date"], r["rate_to_usd"], r["source"]],
        )
    return len(rows)


def _log_refresh(
    conn: duckdb.DuckDBPyConnection, result: IngestResult, run_id: str
) -> None:
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


def import_fx_rates(
    conn: duckdb.DuckDBPyConnection,
    *,
    currencies: list[str],
    start: date,
    end: date,
    timeout: float = 30.0,
) -> IngestResult:
    """Download and upsert ECB FX rates for the given currency list and date range.

    Args:
        conn: Open DuckDB connection with schema already applied.
        currencies: ISO 4217 codes to import (e.g. ["EUR", "GBP"]).  USD is
            handled as a special case (rate_to_usd = 1.0 for every trading day
            in the range, derived from the USD/EUR series already fetched).
        start: First date (inclusive).
        end: Last date (inclusive).
        timeout: HTTP timeout in seconds.
    """
    started = datetime.now()
    run_id = str(uuid.uuid4())
    total_rows = 0
    errors: list[str] = []

    try:
        with httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        ) as client:
            usd_per_eur = fetch_ecb_rates("USD", start, end, client=client)

            for currency in currencies:
                ccy = currency.upper()
                try:
                    rows_to_insert: list[dict[str, Any]] = []

                    if ccy == "USD":
                        for d in usd_per_eur:
                            rows_to_insert.append(
                                {"currency": "USD", "date": d, "rate_to_usd": 1.0, "source": "ecb"}
                            )
                    elif ccy == "EUR":
                        for d, rate in usd_per_eur.items():
                            rows_to_insert.append(
                                {"currency": "EUR", "date": d, "rate_to_usd": rate, "source": "ecb"}
                            )
                    else:
                        ccy_rates = fetch_ecb_rates(ccy, start, end, client=client)
                        for d, ccy_per_eur in ccy_rates.items():
                            if d not in usd_per_eur or ccy_per_eur == 0.0:
                                continue
                            rows_to_insert.append(
                                {
                                    "currency": ccy,
                                    "date": d,
                                    "rate_to_usd": usd_per_eur[d] / ccy_per_eur,
                                    "source": "ecb",
                                }
                            )

                    conn.execute("BEGIN TRANSACTION")
                    try:
                        n = upsert_fx_rows(conn, rows_to_insert)
                        conn.execute("COMMIT")
                    except Exception:
                        conn.execute("ROLLBACK")
                        raise

                    total_rows += n
                    log.info("ecb.imported", currency=ccy, rows=n)

                except Exception as exc:
                    log.exception("ecb.import_currency_failed", currency=ccy, error=str(exc))
                    errors.append(f"{ccy}: {exc}")

    except Exception as exc:
        log.exception("ecb.import_failed", error=str(exc))
        result = IngestResult(
            source="fx_rates",
            started_at=started,
            finished_at=datetime.now(),
            status="error",
            error_message=str(exc),
        )
        _log_refresh(conn, result, run_id)
        return result

    if errors and total_rows == 0:
        status: str = "error"
        error_msg: str | None = "; ".join(errors)
    elif errors:
        status = "partial"
        error_msg = "; ".join(errors)
    else:
        status = "success"
        error_msg = None

    result = IngestResult(
        source="fx_rates",
        started_at=started,
        finished_at=datetime.now(),
        status=status,  # type: ignore[arg-type]
        rows_affected=total_rows,
        error_message=error_msg,
    )
    _log_refresh(conn, result, run_id)
    return result
