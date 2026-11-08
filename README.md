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
   Flex checklist for `bot portfolio`, and runs `bot doctor` — its exit code is bootstrap's (a
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
`tests/fixtures/cassettes/SYNTHETIC.txt`); the suite only replays them, with a dummy key. To
re-record, run `BOT_FMP_API_KEY=<real key> uv run pytest -m integration --vcr-record=all`:
with a record mode set the FMP tests use that key and fail before any request if it is missing, and a
non-2xx response is never written to a cassette (the key is scrubbed as `apikey=SCRUBBED`). Recording
rewrites each file, dropping its `# SYNTHETIC` header; then remove its entry from `SYNTHETIC.txt`.

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

- **Before each run** `daily.sh`, `weekly.sh` and `price_fill.sh` call `scripts/sync_master.sh`,
  which fast-forwards the checkout to `origin/master` (`git pull --ff-only`). It skips a checkout
  on another branch, and a failed pull is logged and the run goes ahead on the code it has.
- **Daily** (weekdays 09:00): `bot refresh --prices --fx && bot portfolio`. Fundamentals are
  quarterly and are not refreshed daily. `bot portfolio` fails (exit 1) when the Flex
  service does, and exits 2 while the Flex token or query id is unset; that is logged,
  not a bug.
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

The bot reads your IBKR portfolio from the **Flex Web Service**
(`bot.ingest.ibkr_flex.FlexPortfolioClient`), read-only. It never places, modifies or
cancels orders. There is no TWS, no gateway and no local process: `bot portfolio` runs
unattended ([ADR 0010](docs/adr/0010-flex-web-service-as-the-only-ibkr-source.md)).

### Portfolio sync via Flex Web Service

Written from IBKR's documentation; the parser is validated against a real statement
captured with the command below. Known corrections are tracked in #111.

`bot portfolio` downloads one Activity Flex Query statement per run and serves positions,
cash, trades and corporate actions from it. The snapshot and `reports/<as_of>/` carry the
statement date (the latest Open Positions `reportDate`, falling back to the statement's
`toDate`), usually the previous business day. A statement more than 5 days old logs a
warning. Snapshots stored before this change are keyed on the run day; there is no migration.

1. In Client Portal, **Performance & Reports → Flex Queries → Activity Flex Query**,
   create **one** query, format **XML**, period **Last 7 Calendar Days**, all accounts,
   with five sections:
   - **Open Positions** (level Summary): accountId, conid, symbol, assetCategory,
     currency, listingExchange, position, costBasisPrice, markPrice, reportDate.
   - **Cash Report**: accountId, currency, endingCash, levelOfDetail.
   - **Trades** (level Executions): accountId, conid, symbol, assetCategory,
     currency, buySell, quantity, tradePrice, dateTime, ibExecID, ibOrderID, levelOfDetail.
   - **Corporate Actions**: accountId, currency, assetCategory, symbol, description,
     conid, isin, reportDate, dateTime, actionID, type, quantity, amount, proceeds,
     value, code.
   - **Cash Transactions**: accountId, currency, assetCategory, symbol, description,
     conid, isin, dateTime, settleDate, reportDate, amount, type, transactionID, code.

   Keep IBKR's default date and time formats (`yyyyMMdd;HHmmss`). Note the query id.
   If you already have a corporate-actions-only query, add Open Positions, Cash Report
   and Trades to it: a statement missing any of those three fails the run.
2. **Settings → Reporting → Flex Web Service**: generate a token. It expires at most
   yearly, so note its expiry.
3. Put both in `.env` (never commit them):

   ```bash
   BOT_IBKR_FLEX_TOKEN=...      # Flex Web Service token
   BOT_IBKR_FLEX_QUERY_ID=...   # the Activity Flex Query id
   BOT_IBKR_FLEX_TZ=America/New_York   # default; the account's reporting time zone
   ```

   `BOT_IBKR_FLEX_TZ` is the time zone of the trade `dateTime` values; the bot converts
   them to UTC. `bot portfolio` exits 2 when the token or query id is missing and 1 when
   the Flex service fails; nothing is written in either case.
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
     range, rows, positions, cash rows, trades, corporate-action and cash-transaction
     types, and what the parser parsed or skipped.

   The cassette and the redacted XML are safe to commit: the token is scrubbed and
   account ids and every numeric column are redacted, and open positions and trades
   carry pseudonyms (`SYM1`, conid `1`, ...) instead of their instruments. The repository
   is public, and corporate-action and cash-transaction rows still show their real
   symbols over the window: review the redacted XML before you commit it. The JSON summary is also printed; paste it
   into the #111 findings. The raw statement is never written. The command exits 2
   when `BOT_IBKR_FLEX_TOKEN` or `BOT_IBKR_FLEX_QUERY_ID` is missing, and 1 when the
   Flex service fails, the token would leak into the cassette, the query lacks Open
   Positions, Cash Report or Trades, or a value cannot be parsed. In every case
   nothing is written.

**Historical trade backfill.** Temporarily widen the query period in IBKR, run
`bot portfolio` once, then set it back to Last 7 Calendar Days. The `exec_id` dedupe
absorbs the overlap with fills already stored.

**Gaps.** If more days pass between two runs than the query period covers (7), the fills
in between are lost. Widen the period once, as above, to recover them.

**Reruns.** `events_log` is append-only, so running `bot portfolio` again on a statement
whose date was already synced replaces that date's snapshot but repeats its events
(open issue #83).

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

## Development

```bash
uv run pytest -q                 # tests
uv run ruff check .              # lint (--fix allowed)
uv run mypy src                  # type check
```

These are the checks CI runs (`.github/workflows/site.yml`); the lint gate
is `uv run ruff check . && uv run mypy src`.

Formatting is not enforced: neither CI nor the lint gate runs `ruff format`,
and much of the tree is not formatted. Never run `ruff format` over the
whole tree; it rewrites about a hundred files of unrelated code. If you format
at all, format only the files you change (`uv run ruff format path/to/file.py`),
and keep the diff to the lines you touched.

The suite refuses non-loopback network connections through pytest-socket.
`BOT_LIVE_TESTS=1` (for `live` tests) and `--vcr-record` lift the guard.
