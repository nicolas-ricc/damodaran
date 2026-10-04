# investment-bot

Personal investment bot: value screener (Damodaran-style) + portfolio monitor for Interactive Brokers UK.

CLI-only. Local. No real-time data, no execution.

See `docs/superpowers/specs/2026-05-25-investment-bot-design.md` for the full design.

## Quickstart (US-only, free data stack)

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

1. `uv sync` — install dependencies.
2. `cp .env.example .env` and fill in `BOT_SEC_USER_AGENT` (your name + email) and
   `BOT_TIINGO_API_KEY` (a free token from [tiingo.com](https://www.tiingo.com/)). The default
   provider is `edgar-tiingo` — SEC EDGAR for fundamentals (no key) + Tiingo for EOD prices.
   See [ADR 0007](docs/adr/0007-free-data-stack-edgar-stooq.md).
3. `uv run bot doctor` — verify setup.
4. `uv run bot refresh --damodaran` — US sector benchmarks from Damodaran (once yearly).
5. `uv run bot refresh --fundamentals && uv run bot refresh --prices` — load the universe.
   Fundamentals come from EDGAR (no key; its own throttling defers, not skips — the next run
   resumes). Prices come from Tiingo.

   **Tiingo's free tier is rate-capped** (a few hundred requests per hourly window, 500 unique
   symbols/month), so the shipped universe is trimmed to 498 names to fit the monthly cap, and a
   full first fill may take one or two windows. Use **`--only-missing`** so each run skips
   tickers that already have prices (no request spent) and advances through the unpriced
   remainder:

   ```bash
   uv run bot refresh --prices --only-missing   # fills the unpriced remainder; re-run per window
   ```

   `scripts/price_fill.sh` automates the drip — it runs `--only-missing`, logs to
   `.cache/price_fill.log`, and stops once every ticker is priced. Arm it hourly (from your
   checkout root):

   ```bash
   ( crontab -l 2>/dev/null; echo "7 * * * * $(pwd)/scripts/price_fill.sh # bot-price-fill" ) | crontab -
   # remove when done:  crontab -l | grep -v 'bot-price-fill' | crontab -
   ```

   Once the universe is filled, plain `uv run bot refresh --prices` does cheap daily
   incremental updates (one bar/ticker).
   For the full S&P 500 priced daily without the drip, Tiingo Power (~$30/mo) lifts the caps —
   same `edgar-tiingo` provider, just a paid key, and re-add the trimmed names.

   **Alternative price source — `edgar-stooq`.** Set `BOT_DATA_PROVIDER=edgar-stooq` to read
   Stooq CSVs instead of Tiingo. Stooq's HTTP endpoint is behind a JavaScript anti-bot wall
   (observed 2026-09-09) and its `db/` bulk archives require a paid subscription, so the only
   free route is harvesting per-ticker CSVs through a real browser
   ([agent-browser](https://www.npmjs.com/package/agent-browser) required) — slow and
   daily-limited even when logged in, so `edgar-tiingo` is preferred:

   ```bash
   agent-browser open "https://stooq.com/q/d/?s=aapl.us" && agent-browser wait --load networkidle
   node scripts/stooq_browser_fetch.mjs --universe src/bot/ingest/universe_default.csv
   BOT_DATA_PROVIDER=edgar-stooq BOT_STOOQ_DIR=.cache/stooq uv run bot refresh --prices
   ```

   With `BOT_STOOQ_DIR` set, `refresh --prices` reads `<TICKER>.csv` files from that
   directory; a ticker with no file fails individually with a message naming the recipe, and
   the rest continue. Background in the "Real run (Task 8)" section of
   `docs/superpowers/plans/2026-09-09-free-data-stack-edgar-stooq.md`. Under either provider,
   SEC EDGAR's own throttling can
   still cut a fundamentals run short, in which case the remaining tickers are deferred, not
   skipped, and the next day's run continues from where it left off.
   Use `--limit N` to cap a run at the first N universe tickers — useful for a first-day sanity
   check, not for daily use (it always re-probes the same alphabetical head of the ticker list,
   so it won't help you progress through the universe day over day).

   **Alternative price source — `edgar-stooq`.** Set `BOT_DATA_PROVIDER=edgar-stooq` to read
   Stooq CSVs instead of Tiingo. Stooq's HTTP endpoint is behind a JavaScript anti-bot wall
   (observed 2026-09-09) and its `db/` bulk archives require a paid subscription, so the only
   free route is harvesting per-ticker CSVs through a real browser
   ([agent-browser](https://www.npmjs.com/package/agent-browser) required) — slow and
   daily-limited even when logged in, so `edgar-tiingo` is preferred:

   ```bash
   agent-browser open "https://stooq.com/q/d/?s=aapl.us" && agent-browser wait --load networkidle
   node scripts/stooq_browser_fetch.mjs --universe src/bot/ingest/universe_default.csv
   BOT_DATA_PROVIDER=edgar-stooq BOT_STOOQ_DIR=.cache/stooq uv run bot refresh --prices
   ```

   With `BOT_STOOQ_DIR` set, `refresh --prices` reads `<TICKER>.csv` files from that
   directory; a ticker with no file fails individually with a message naming the recipe, and
   the rest continue. Background in the "Real run (Task 8)" section of
   `docs/superpowers/plans/2026-09-09-free-data-stack-edgar-stooq.md`. Under either provider,
   SEC EDGAR's own throttling can
   still cut a fundamentals run short, in which case the remaining tickers are deferred, not
   skipped, and the next day's run continues from where it left off.
   Use `--limit N` to cap a run at the first N universe tickers — useful for a first-day sanity
   check, not for daily use (it always re-probes the same alphabetical head of the ticker list,
   so it won't help you progress through the universe day over day).
6. `uv run bot screen --preset damodaran_value --top 10` — mechanical shortlist (§6).
7. `uv run bot analyze --from-screen` — DCF and report (§7.7) for each candidate.

8. Publish the read-only viewer: commit `reports/*/analysis/*.json` (the JSON sidecars `bot analyze`
   writes; `.gitignore` lets only those through) and push to `master`. `.github/workflows/site.yml`
   runs ruff, mypy and pytest, builds the site with `bot site` and deploys it to GitHub Pages. One-time
   setup: Settings -> Pages -> Source = GitHub Actions. See [ADR 0008](docs/adr/0008-read-only-web-viewer.md).

   Local preview, no env vars needed:

   ```bash
   uv run bot site --out site --reports-dir reports --base-url /
   python -m http.server -d site
   ```

The paid Financial Modeling Prep adapter is still available for the eventual non-US reopening —
set `BOT_DATA_PROVIDER=fmp` and `BOT_FMP_API_KEY` (see `.env.example`).

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

### Notifications

`bot portfolio` can forward the day's `alerts.md` by email or Telegram. Set
`BOT_NOTIFIER=email` or `BOT_NOTIFIER=telegram` (default `none`). The message is
the contents of `alerts.md` as plain text; on a quiet day the file is empty and
nothing is sent. On success the command prints `Sent alerts via <channel>`.

```bash
BOT_NOTIFIER=email
BOT_SMTP_HOST=smtp.example.com   # required
BOT_SMTP_PORT=587                # default; 465 with BOT_SMTP_SECURITY=ssl
BOT_SMTP_SECURITY=starttls       # default; or ssl, none
BOT_SMTP_USERNAME=""
BOT_SMTP_PASSWORD=""
BOT_SMTP_FROM=bot@example.com    # required
BOT_SMTP_TO=me@example.com       # required; comma-separated

BOT_NOTIFIER=telegram
BOT_TELEGRAM_BOT_TOKEN=""        # required (from @BotFather)
BOT_TELEGRAM_CHAT_ID=""          # required
```

`BOT_SMTP_SECURITY=none` is rejected when a username is set, because the
password would travel in cleartext. Telegram messages longer than 4096 UTF-16
units are split into several messages.

Failure modes:

- Missing or unsafe notifier settings: `Notifier misconfigured`, exit code 2,
  before any sync or report work starts.
- Send failure: `Alerts not sent`, exit code 1. The reports have already been
  written by then.

There is no automatic retry. Re-running `bot portfolio` the same day re-renders
and re-sends that day's alerts.

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
