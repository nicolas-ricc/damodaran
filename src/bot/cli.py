"""CLI entry point for the investment bot."""

from __future__ import annotations

import csv
from pathlib import Path

import typer

from bot.config import load_settings
from bot.ingest.refresh import refresh_universe
from bot.storage.db import apply_schema, connect
from bot.utils.logging import configure_logging, get_logger

app = typer.Typer(name="bot", add_completion=False, no_args_is_help=True)
log = get_logger(__name__)

_DEFAULT_UNIVERSE: Path = Path(__file__).parent / "data" / "universe.csv"


def _load_tickers(universe_path: Path) -> list[str]:
    tickers: list[str] = []
    with universe_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if ticker:
                tickers.append(ticker)
    return tickers


@app.command()
def refresh(
    fmp: bool = typer.Option(False, "--fmp", is_flag=True, help="Refresh from Financial Modeling Prep"),
    universe: Path | None = typer.Option(  # noqa: B008
        None, "--universe", help="CSV file of tickers (must have a 'ticker' column)"
    ),
) -> None:
    """Bulk-import / incremental refresh of a ticker universe."""
    if not fmp:
        typer.echo("Error: at least one source flag is required (e.g. --fmp)", err=True)
        raise typer.Exit(code=1)

    settings = load_settings()
    configure_logging(settings.log_level)

    universe_path = universe or _DEFAULT_UNIVERSE
    if not universe_path.exists():
        log.error("refresh.universe_not_found", path=str(universe_path))
        raise typer.Exit(code=1)

    tickers = _load_tickers(universe_path)
    if not tickers:
        log.error("refresh.no_tickers", path=str(universe_path))
        raise typer.Exit(code=1)

    log.info(
        "refresh.start",
        source="fmp",
        universe=str(universe_path),
        ticker_count=len(tickers),
    )

    conn = connect(settings.db_path)
    apply_schema(conn)

    stats = refresh_universe(conn, tickers, api_key=settings.fmp_api_key)

    if stats.fail_rate > 0.05:
        raise typer.Exit(code=2)
