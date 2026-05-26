# investment-bot

Personal investment bot: value screener (Damodaran-style) + portfolio monitor for Interactive Brokers UK.

CLI-only. Local. No real-time data, no execution.

See `docs/superpowers/specs/2026-05-25-investment-bot-design.md` for the full design.

## Quickstart

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync                          # install dependencies
cp .env.example .env             # configure
$EDITOR .env                     # set BOT_SEC_USER_AGENT to your name + email

uv run bot --help                # see available commands
uv run bot doctor                # verify setup
uv run bot refresh --damodaran   # import Damodaran datasets (M1)
uv run bot show AAPL             # show a US company's fundamentals (M1)
```

## Development

```bash
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type check
```
