"""Investment bot — command-line interface."""

from __future__ import annotations

from pathlib import Path

import duckdb
import typer

from bot import __version__
from bot.config import Settings, load_settings
from bot.ingest.damodaran import import_damodaran
from bot.ingest.sec_edgar import import_company_from_sec
from bot.reporting.show import format_company_summary
from bot.storage.db import apply_schema, connect
from bot.utils.logging import configure_logging, get_logger

app = typer.Typer(
    help="Personal investment bot — value screener + portfolio monitor.",
    no_args_is_help=True,
)
log = get_logger(__name__)


@app.callback()
def _root() -> None:
    """Investment bot — value screener + portfolio monitor."""


def _open_db() -> tuple[duckdb.DuckDBPyConnection, Settings]:
    settings = load_settings()
    configure_logging(level=settings.log_level, json_output=False)
    conn = connect(settings.db_path)
    apply_schema(conn)
    return conn, settings


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(__version__)


@app.command()
def refresh(
    damodaran: bool = typer.Option(False, "--damodaran", help="Refresh Damodaran datasets."),
    region: str = typer.Option("US", "--region", help="Damodaran region (US, Europe, EM, ...)."),
    year: int | None = typer.Option(
        None, "--year", help="Damodaran dataset year (defaults to current)."
    ),
    download_dir: Path = typer.Option(  # noqa: B008
        Path("./.cache/damodaran"),
        "--download-dir",
        help="Where to cache downloaded Damodaran files.",
    ),
) -> None:
    """Refresh data from external sources."""
    if not damodaran:
        typer.echo(
            "Specify what to refresh. Available flags: --damodaran",
            err=True,
        )
        raise typer.Exit(code=2)

    conn, _ = _open_db()
    typer.echo(f"Importing Damodaran datasets (region={region}, year={year or 'current'})...")
    result = import_damodaran(conn, download_dir=download_dir, region=region, year=year)
    if result.is_success():
        typer.echo(
            f"OK — imported {result.rows_affected} rows in {result.duration_seconds():.1f}s "
            f"(industry={result.details.get('industry_rows')}, "
            f"country={result.details.get('country_rows')})"
        )
        raise typer.Exit(code=0)
    typer.echo(f"FAILED — {result.error_message}", err=True)
    raise typer.Exit(code=1)


@app.command()
def show(
    ticker: str = typer.Argument(..., help="Company ticker (e.g. AAPL)."),
    fetch_if_missing: bool = typer.Option(
        True,
        "--fetch/--no-fetch",
        help="If the ticker isn't in the DB, fetch it from SEC EDGAR first.",
    ),
) -> None:
    """Show a company's basic info and last 5 years of financials."""
    conn, settings = _open_db()
    ticker = ticker.upper()

    row = conn.execute(
        "SELECT ticker, name, cik, country, currency FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()

    if row is None:
        if not fetch_if_missing:
            typer.echo(f"{ticker} not in DB (use --fetch to import from SEC).", err=True)
            raise typer.Exit(code=2)
        typer.echo(f"{ticker} not in DB — fetching from SEC EDGAR...")
        result = import_company_from_sec(conn, ticker=ticker, user_agent=settings.sec_user_agent)
        if not result.is_success():
            typer.echo(f"Failed to import {ticker}: {result.error_message}", err=True)
            raise typer.Exit(code=1)
        row = conn.execute(
            "SELECT ticker, name, cik, country, currency FROM companies WHERE ticker = ?",
            [ticker],
        ).fetchone()

    if row is None:
        typer.echo(f"{ticker} still not in DB after import — aborting.", err=True)
        raise typer.Exit(code=1)

    company = dict(zip(["ticker", "name", "cik", "country", "currency"], row, strict=False))
    annual_cursor = conn.execute(
        """
        SELECT *
        FROM financials_annual
        WHERE ticker = ?
        ORDER BY fiscal_year DESC
        LIMIT 5
        """,
        [ticker],
    )
    columns = [d[0] for d in annual_cursor.description]
    annual_rows = [dict(zip(columns, r, strict=False)) for r in annual_cursor.fetchall()]

    typer.echo(format_company_summary(company, annual_rows))


@app.command()
def doctor() -> None:
    """Run health checks and report what's broken (if anything)."""
    issues: list[str] = []

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"FAIL: Settings invalid — {e}", err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"DB path:          {settings.db_path}")
    typer.echo(f"Reports dir:      {settings.reports_dir}")
    typer.echo(f"SEC user agent:   {settings.sec_user_agent}")
    typer.echo(f"FMP API key:      {'set' if settings.fmp_api_key else 'MISSING'}")
    typer.echo(f"Log level:        {settings.log_level}")

    try:
        conn = connect(settings.db_path)
        apply_schema(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()
        tables = row[0] if row is not None else 0
        if tables < 8:
            issues.append(f"DB has only {tables} tables — schema may be incomplete.")
        else:
            typer.echo(f"DB tables:        {tables} (OK)")
        conn.close()
    except Exception as e:
        issues.append(f"DB error — {e}")

    try:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.reports_dir / ".doctor_probe"
        probe.write_text("x")
        probe.unlink()
        typer.echo("Reports dir:      writable (OK)")
    except Exception as e:
        issues.append(f"Reports dir not writable — {e}")

    if issues:
        typer.echo("", err=True)
        for issue in issues:
            typer.echo(f"FAIL: {issue}", err=True)
        raise typer.Exit(code=1)
    typer.echo("\nAll checks OK.")


@app.command()
def status() -> None:
    """Show the most recent refresh result per data source."""
    conn, _ = _open_db()
    rows = conn.execute(
        """
        SELECT source, MAX(finished_at) AS last_finished, status, rows_affected
        FROM refresh_log
        GROUP BY source, status, rows_affected
        QUALIFY ROW_NUMBER() OVER (PARTITION BY source ORDER BY last_finished DESC) = 1
        ORDER BY source
        """
    ).fetchall()
    if not rows:
        typer.echo("No refresh history yet — run `bot refresh --damodaran` first.")
        return
    typer.echo(f"{'Source':<14}{'Last run':<22}{'Status':<10}{'Rows':>8}")
    typer.echo("-" * 54)
    for source, last_finished, status_str, rows_affected in rows:
        typer.echo(
            f"{source:<14}{last_finished.strftime('%Y-%m-%d %H:%M:%S'):<22}{status_str:<10}{rows_affected:>8}"
        )
