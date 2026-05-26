"""Investment bot — command-line interface."""

import typer

from bot import __version__

app = typer.Typer(
    help="Personal investment bot — value screener + portfolio monitor.",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Investment bot — value screener + portfolio monitor."""


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(__version__)
