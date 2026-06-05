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

## Portfolio sync — Interactive Brokers (M5)

The bot reads your IBKR portfolio over the **TWS API** (local socket) using a
**read-only** client (`bot.ingest.ibkr.IbkrClient`). It never places, modifies or
cancels orders.

### Prerequisites

1. **Trader Workstation (TWS)** or **IB Gateway** installed, **running and
   logged in**. Auth is entirely the desktop login — there is no OAuth, no REST
   gateway and no Docker container.
2. In TWS: **File → Global Configuration → API → Settings**, tick **"Enable
   ActiveX and Socket Clients"** and add `127.0.0.1` to **Trusted IPs**.
3. **Recommended (belt-and-braces):** also tick **"Read-Only API"** in the same
   panel so the desktop refuses any write even if a client tried.

### Configuration

Host, port and client id are configurable via environment (`.env`) — never
hard-coded. Defaults target **live TWS**:

```bash
BOT_IBKR_HOST=127.0.0.1   # default
BOT_IBKR_PORT=7496        # default; live TWS. 7497 = paper TWS, 4001/4002 = IB Gateway live/paper
BOT_IBKR_CLIENT_ID=1      # default; each concurrent client needs a distinct id
```

### Manual smoke test (human, not CI)

CI never opens a real socket — the mapping logic is unit-tested against mocked
`ib_async` responses. To verify the live round-trip yourself, with TWS running
and logged in:

```bash
uv run python -c "from bot.config import load_settings; from bot.ingest.ibkr import IbkrClient; \
print(IbkrClient.from_settings(load_settings()).accounts())"
```

It should print your real managed account id(s) (e.g. `['U1234567']`).

## Development

```bash
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type check
```
