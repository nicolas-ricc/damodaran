# investment-bot

Personal investment bot: value screener (Damodaran-style) + portfolio monitor for Interactive Brokers UK.

CLI-only. Local. No real-time data, no execution.

See `docs/superpowers/specs/2026-05-25-investment-bot-design.md` for the full design.

## Quickstart (US-only, FMP tier gratis)

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

1. `uv sync` — install dependencies.
2. `cp .env.example .env` and fill in `BOT_SEC_USER_AGENT` (your name + email) and your FMP API
   key.
3. `uv run bot doctor` — verify setup.
4. `uv run bot refresh --damodaran` — US sector benchmarks from Damodaran (once yearly).
5. `uv run bot refresh --fmp && uv run bot refresh --prices` — load the S&P 500 universe. On the
   free FMP tier (~250 requests/day) a single run won't cover the whole universe: it stops
   cleanly once the daily quota is exhausted (the remaining tickers are deferred, not skipped),
   and the next day's run re-probes the tickers already loaded and continues from where it left
   off. Full universe loads over ~2 weeks of daily refreshes.
   Use `--limit N` to cap a run at the first N universe tickers — useful for a first-day sanity
   check, not for daily use (it always re-probes the same alphabetical head of the ticker list,
   so it won't help you progress through the universe day over day).
6. `uv run bot screen --preset damodaran_value --top 10` — mechanical shortlist (§6).
7. `uv run bot analyze --from-screen` — DCF and report (§7.7) for each candidate.

Other useful commands:

```bash
uv run bot --help                # see available commands
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
