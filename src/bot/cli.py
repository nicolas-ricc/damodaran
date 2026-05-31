"""Investment bot — command-line interface."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import typer

from bot import __version__
from bot.config import Settings, load_settings
from bot.ingest.damodaran import import_damodaran
from bot.ingest.sec_edgar import import_company_from_sec
from bot.ingest.universe import (
    UniverseRefreshResult,
    default_universe_path,
    load_universe,
    refresh_universe_from_fmp,
)
from bot.reporting.analysis_report import render_analysis
from bot.reporting.html import render_analysis_html
from bot.reporting.screen_report import render_csv, render_markdown
from bot.reporting.show import format_company_summary
from bot.screener.config import load_screener_config
from bot.screener.engine import run_screen
from bot.screener.persist import persist_candidates
from bot.storage.db import apply_schema, connect
from bot.utils.logging import configure_logging, get_logger
from bot.valuator.analysis import analyze as run_analysis

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
    fmp: bool = typer.Option(
        False, "--fmp", help="Bulk-refresh a universe of tickers from FMP (incremental)."
    ),
    universe: Path | None = typer.Option(  # noqa: B008
        None,
        "--universe",
        help="CSV of tickers for --fmp (defaults to the shipped global universe).",
    ),
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
    if not damodaran and not fmp:
        typer.echo(
            "Specify what to refresh. Available flags: --damodaran, --fmp",
            err=True,
        )
        raise typer.Exit(code=2)

    if fmp:
        _refresh_fmp_universe(universe)
        return

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


def _refresh_fmp_universe(universe: Path | None) -> None:
    """Run a bulk FMP universe refresh and map its outcome to an exit code.

    Exit codes follow the spec convention (§9.2) and the M2.6 brief: ``0`` when at
    most 5% of the universe failed, ``2`` (data error) when more than 5% failed.
    Per-ticker failures are summarised on stderr; they never abort the run.
    """
    conn, settings = _open_db()
    path = universe or default_universe_path()
    tickers = load_universe(path)
    if not tickers:
        typer.echo(f"Universe file {path} has no tickers.", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Refreshing {len(tickers)} tickers from FMP (universe={path})...")
    result = refresh_universe_from_fmp(
        conn, api_key=settings.fmp_api_key, tickers=tickers
    )
    _report_universe_refresh(result)

    # > 5% failed (i.e. status is not 'success') is a data error.
    raise typer.Exit(code=0 if result.status == "success" else 2)


def _report_universe_refresh(result: UniverseRefreshResult) -> None:
    typer.echo(
        f"{result.status.upper()} — {result.total} tickers: "
        f"{result.imported} imported, {result.skipped} skipped, "
        f"{result.failed} failed "
        f"({result.failure_rate * 100:.1f}% failure) "
        f"in {(result.finished_at - result.started_at).total_seconds():.1f}s"
    )
    if result.failures:
        typer.echo("Failures:", err=True)
        for outcome in result.failures:
            typer.echo(f"  {outcome.ticker}: {outcome.error_message}", err=True)


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

    def _load_company_row(
        conn: duckdb.DuckDBPyConnection, ticker: str
    ) -> tuple[object, ...] | None:
        return conn.execute(
            "SELECT ticker, name, cik, country, currency FROM companies WHERE ticker = ?",
            [ticker],
        ).fetchone()

    row = _load_company_row(conn, ticker)

    if row is None:
        if not fetch_if_missing:
            typer.echo(f"{ticker} not in DB (use --fetch to import from SEC).", err=True)
            raise typer.Exit(code=2)
        typer.echo(f"{ticker} not in DB — fetching from SEC EDGAR...")
        result = import_company_from_sec(conn, ticker=ticker, user_agent=settings.sec_user_agent)
        if not result.is_success():
            typer.echo(f"Failed to import {ticker}: {result.error_message}", err=True)
            raise typer.Exit(code=1)
        row = _load_company_row(conn, ticker)

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
def analyze(
    ticker: str = typer.Argument(..., help="Company ticker (e.g. AAPL)."),
    override: Path | None = typer.Option(  # noqa: B008
        None,
        "--override",
        help="Path to config/assumptions/<TICKER>.yaml with manual overrides.",
    ),
) -> None:
    """Run a Damodaran-style DCF analysis and write the §7.7 reports.

    Produces ``<reports_dir>/YYYY-MM-DD/analysis/<TICKER>.md`` with the executive
    summary, story type, assumptions (with source), year-by-year DCF, sensitivity
    (tornado + 2-D grid), narrative flags, manual overrides, and the sanity check
    versus sector multiples. A self-contained ``<TICKER>.html`` (M6.1) is written
    alongside it: the same report rendered to HTML with a base64-inlined
    Matplotlib tornado chart, openable in a browser with no external assets.
    """
    conn, settings = _open_db()
    ticker = ticker.upper()

    try:
        analysis = run_analysis(ticker, conn, override_path=override)
    except LookupError as exc:
        typer.echo(f"{ticker}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(f"{ticker}: cannot value — {exc}", err=True)
        raise typer.Exit(code=1) from exc

    today = date.today()
    report_md = render_analysis(analysis, generated_on=today)
    report_html = render_analysis_html(analysis, generated_on=today)
    out_dir = settings.reports_dir / today.isoformat() / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{ticker}.md"
    html_path = out_dir / f"{ticker}.html"
    out_path.write_text(report_md)
    html_path.write_text(report_html)

    typer.echo(f"Wrote {out_path}")
    typer.echo(f"Wrote {html_path}")
    if analysis.margin_of_safety is not None:
        typer.echo(
            f"Intrinsic {analysis.dcf_result.intrinsic_value:,.2f} "
            f"vs price {analysis.current_price:,.2f} → "
            f"margin of safety {analysis.margin_of_safety:.2f}x"
        )


@app.command()
def screen(
    preset: str = typer.Option(
        "damodaran_value",
        "--preset",
        help="Named screener preset under the presets dir (config/presets/<name>.yaml).",
    ),
    config: Path | None = typer.Option(  # noqa: B008
        None,
        "--config",
        help="Explicit screener YAML path (overrides --preset).",
    ),
    top: int | None = typer.Option(
        None, "--top", help="Keep only the best N candidates in the shortlist."
    ),
) -> None:
    """Run the mechanical screener and write the §6.1 shortlist (Markdown + CSV).

    Loads the preset (or ``--config``), iterates the DB universe, applies the
    three eliminatory layers (§6.2/§6.3/§6.4), ranks the survivors (§6.5),
    persists the top-N to ``screener_candidates`` under a fresh run id, and writes
    ``<reports_dir>/YYYY-MM-DD/screen/<preset>.{md,csv}``.
    """
    conn, settings = _open_db()

    config_path = config if config is not None else settings.presets_dir / f"{preset}.yaml"
    if not config_path.exists():
        typer.echo(f"Screener config not found: {config_path}", err=True)
        raise typer.Exit(code=2)
    screener_config = load_screener_config(config_path)

    result = run_screen(conn, screener_config, top=top)
    run_id = persist_candidates(conn, result)

    today = date.today()
    out_dir = settings.reports_dir / today.isoformat() / "screen"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{screener_config.name}.md"
    csv_path = out_dir / f"{screener_config.name}.csv"
    md_path.write_text(render_markdown(result, generated_on=today))
    csv_path.write_text(render_csv(result))

    typer.echo(
        f"Screened {result.screened} companies → {len(result.shortlist)} candidates "
        f"(run {run_id})"
    )
    typer.echo(f"Wrote {md_path}")
    typer.echo(f"Wrote {csv_path}")


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
