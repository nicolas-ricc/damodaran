# investment-bot

Personal investment bot: value screener (Damodaran-style) + portfolio monitor for Interactive Brokers UK.

CLI-only. Local. No real-time data, no execution.

See `docs/superpowers/specs/2026-05-25-investment-bot-design.md` for the full design.

## Quickstart (US-only, free data stack)

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

1. `uv sync` — install dependencies.
2. `scripts/bootstrap.sh` — first-run setup. Creates `.env` from `.env.example` and asks for
   the two required keys, `BOT_SEC_USER_AGENT` (your name + email) and `BOT_TIINGO_API_KEY` (a
   free token from [tiingo.com](https://www.tiingo.com/)); keys already set are never asked
   again. Then loads Damodaran's US sector benchmarks (`bot refresh --damodaran`), prints the
   TWS checklist for `bot portfolio`, and runs `bot doctor` — its exit code is bootstrap's (a
   failed Damodaran download stops bootstrap first, with that code). Safe to re-run. `--yes`
   never prompts and takes the keys from the environment (exit 1 naming any that is missing);
   `--skip-damodaran` skips the download. The default provider is
   `edgar-tiingo` — SEC EDGAR for fundamentals (no key) + Tiingo for EOD prices. See
   [ADR 0007](docs/adr/0007-free-data-stack-edgar-stooq.md).

   <details>
   <summary>By hand</summary>

   1. `cp .env.example .env` and fill in `BOT_SEC_USER_AGENT` and `BOT_TIINGO_API_KEY`.
   2. `uv run bot doctor` — verify setup.
   3. `uv run bot refresh --damodaran` — US sector benchmarks from Damodaran (once yearly).

   </details>
3. `uv run bot refresh --fundamentals && uv run bot refresh --prices` — load the universe.
   Fundamentals come from EDGAR (no key; its own throttling defers, not skips — the next run
   resumes). Prices come from Tiingo. `bot refresh --fundamentals --force` re-imports every
   ticker even if its filing date has not advanced (e.g. after a parser fix).

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

   A plain `uv run bot refresh --prices` also advances: it skips tickers that are already
   up to date (no request spent) and refreshes the rest stalest-first, so re-running it walks
   through the universe. `scripts/daily.sh` therefore repeats the price refresh (up to
   `BOT_PRICE_ROUNDS`, default 10, pausing `BOT_PRICE_RETRY_PAUSE` seconds, default 3600,
   between rounds) until no tickers are deferred. Once the universe is filled, the plain run
   does cheap daily incremental updates (one bar/ticker). The `price_fill.sh` drip is only for
   a first fill before `scripts/install_cron.sh`; do not run both, or they compete for the
   same hourly Tiingo quota and the same DuckDB file (#108).
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
4. `uv run bot screen --preset damodaran_value --top 10` — mechanical shortlist (§6).
5. `uv run bot analyze --from-screen` — DCF and report (§7.7) for each candidate.

6. Publish the read-only viewer: commit `reports/*/analysis/*.json` (the JSON sidecars `bot analyze`
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
Its test cassettes under `tests/fixtures/cassettes/{fmp,universe}/` are synthetic (listed in
`tests/fixtures/cassettes/SYNTHETIC.txt`); the suite only replays them. Re-record against the live
API with a real key via `uv run pytest -m integration --vcr-record=all` (recording rewrites each
file, dropping its `# SYNTHETIC` header), then remove its entry from `SYNTHETIC.txt`.

Other useful commands:

```bash
uv run bot --help                # see available commands
uv run bot show AAPL             # show a US company's fundamentals (M1)
```

## Scheduling

`scripts/install_cron.sh` adds two jobs to your crontab:

```
0 9  * * 1-5  <repo>/scripts/daily.sh   # bot-daily
0 10 * * 6    <repo>/scripts/weekly.sh  # bot-weekly
```

- **Daily** (weekdays 09:00): `bot refresh --prices --fx && bot portfolio`. Fundamentals are
  quarterly and are not refreshed daily. `bot portfolio` fails while TWS is not running and
  logged in; that is logged, not a bug.
- **Weekly** (Saturday 10:00): `bot refresh --all && bot screen --preset damodaran_value &&
  bot analyze --from-screen && scripts/publish_site.sh`. The last step commits only the
  `reports/*/analysis/*.json` sidecars and pushes them to `master`, which redeploys the
  viewer ([ADR 0008](docs/adr/0008-read-only-web-viewer.md)). It works through a detached
  worktree in `.cache/site-publish`, so your checked-out branch and uncommitted changes are
  never touched. cron has no ssh-agent:
  the push needs an SSH key that works without a passphrase (a deploy key with write access
  is fine). Everything the screen shortlists becomes public once pushed.

Each run appends to `.cache/daily.log` / `.cache/weekly.log` under a `=== <timestamp> run ===`
header; the job's exit code is the bot's. Running the installer again adds nothing; lines are
found by their `# bot-daily` / `# bot-weekly` markers, and every other crontab line is kept.
`scripts/install_cron.sh --remove` drops just those two lines. The hourly `price_fill.sh` drip is
separate (Quickstart step 3).

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

### Corporate actions via Flex Web Service

Written from IBKR's documentation; the parser is validated against a real statement
captured with the command below. Known corrections are tracked in #111.

The TWS socket does not report dividends or splits, so `bot portfolio` pulls them
from IBKR's **Flex Web Service** (`bot.ingest.ibkr_flex`) before computing the day's
events. Without the two settings below the import is skipped with one INFO line;
any failure during it is logged as a WARNING and the run carries on.

1. In Client Portal, **Performance & Reports → Flex Queries → Activity Flex Query**,
   create a query with:
   - **Corporate Actions**: accountId, currency, assetCategory, symbol, description,
     conid, isin, reportDate, dateTime, actionID, type, quantity, amount, proceeds,
     value, code.
   - **Cash Transactions**: accountId, currency, assetCategory, symbol, description,
     conid, isin, dateTime, settleDate, reportDate, amount, type, transactionID, code.
   - Period **Last 30 Calendar Days**, format **XML**, default date (`yyyyMMdd`) and
     time (`HHmmss`) formats with the `;` separator, all accounts.
   Note the query id.
2. **Settings → Reporting → Flex Web Service**: generate a token and note its expiry.
3. Put both in `.env` (never commit them):

   ```bash
   BOT_IBKR_FLEX_TOKEN=...      # Flex Web Service token
   BOT_IBKR_FLEX_QUERY_ID=...   # the Activity Flex Query id
   ```
4. **Validate against the live account.** From the repo root run:

   ```bash
   uv run bot flex-capture
   ```

   It fetches your real statement and writes three files:
   - `tests/fixtures/cassettes/ibkr_flex/statement_real.yaml`: the recorded HTTP
     exchanges with the Flex token scrubbed and the statement redacted.
   - `tests/fixtures/ibkr_flex/statement_real_redacted.xml`: the statement with
     account ids replaced and amounts and quantities faked; symbols, conids, isins,
     ids, dates, types and descriptions stay real.
   - `tests/fixtures/ibkr_flex/statement_real_summary.json`: counts of accounts, date
     range, rows, corporate-action and cash-transaction types, and what the parser
     parsed or skipped.

   The cassette and the redacted XML are safe to commit: the token is scrubbed and
   account ids and amounts are redacted. They still show which symbols you held and
   their corporate actions over the window. The JSON summary is also printed; paste it
   into the #111 findings. The raw statement is never written. The command exits 2
   when `BOT_IBKR_FLEX_TOKEN` or `BOT_IBKR_FLEX_QUERY_ID` is missing, and 1 when the
   Flex service fails or the token would leak into the cassette. In both cases
   nothing is written.

Dividends and payments in lieu become `DIVIDEND` events, forward and reverse
splits become `SPLIT` events, for tickers held on the day. Other corporate
actions are stored with IBKR's type code, lowercased, but raise no event yet.

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
