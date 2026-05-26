"""Investment bot — command-line interface."""

from __future__ import annotations

from pathlib import Path

import duckdb
import typer

from bot import __version__
from bot.config import Settings, load_settings
from bot.ingest.damodaran import import_damodaran
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
