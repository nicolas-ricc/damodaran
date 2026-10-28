# Stale-first price refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the daily price refresh advance through the whole universe under Tiingo's hourly cap instead of re-importing the same first 50 tickers every day.

**Architecture:** `refresh_prices` in `src/bot/ingest/universe.py` reorders its ticker list stale-first (never priced, then oldest newest-stored-date, ties in CSV order) with one `GROUP BY` query before handing it to `_run_bulk_refresh`, so every rate-limited run spends its quota where it is most needed. `scripts/daily.sh` then re-runs `bot refresh --prices` with a pause between rounds while the bot reports deferred tickers, up to a bounded number of rounds, each round a separate process so the DuckDB file is not held between rounds (#108); FX and the portfolio sync run once after the loop.

**Tech Stack:** Python 3, duckdb, typer, pytest, mypy --strict, ruff, bash 4+ (shellcheck in the suite).

**Spec:** GitHub issue #136 (nicolas-ricc/damodaran), "Daily price refresh never advances past the first 50 tickers under Tiingo's hourly limit".

## Global Constraints

- Ordering: never-priced tickers first, then by newest stored `prices_daily.date` ascending (oldest first); ties keep the input (CSV) order. Ticker matching is case-insensitive (`prices_daily.ticker` is stored upper-case).
- One query for the newest dates of the whole list (`SELECT ticker, max(date) FROM prices_daily GROUP BY ticker`), not one query per ticker.
- Place `_stale_first` *below* `refresh_prices` in `universe.py`: `docs/leccion/index.html` cites `refresh_prices` at `src/bot/ingest/universe.py:521`, and `docs/leccion/check.py` warns when a cited line moves. If the line still moves, update the citation.
- `--only-missing` keeps its meaning (drops any ticker with a stored price); ordering applies to whatever survives it.
- Do not change the monthly 500-symbol cap handling (ADR 0007) nor the universe CSV.
- Deferred tickers are still not failures: a rate-limited run keeps exit code 0 when nothing failed.
- `daily.sh` round pause and round cap are env-overridable: `BOT_PRICE_RETRY_PAUSE` (seconds, default `3600`) and `BOT_PRICE_ROUNDS` (default `10`). 10 rounds × 50 requests covers 498 tickers in one day and stays under Tiingo's 1000 requests/day.
- The loop's "more to do" signal is the CLI's existing deferred line, `NOTE — <n> tickers deferred (provider rate limit)`; the shell greps for `tickers deferred`.
- Type hints everywhere; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- Commits: Conventional Commits with `(#136)` scope.

## Review Focus

1. A ticker whose provider never returns bars (PSKY, WBD: absent from EDGAR/Tiingo) stays never-priced and is attempted first every run; it must cost one request per run, not block the others. Test in Task 1 (`test_unpriceable_ticker_does_not_starve_the_rest`).
2. Mixed-case tickers in the input list (`"aapl"`) must match the upper-case `prices_daily` rows, otherwise a priced ticker is mistaken for never-priced. Test in Task 1.
3. A refresh that fails (non-zero exit) inside the loop must stop the loop and skip FX/portfolio, like today's `&&` chain. Test in Task 2.
4. A run that still has deferred tickers after the last round must not sleep again and must not fail the script: FX and portfolio still run. Test in Task 2.
5. The CLI's deferred hint must no longer tell the operator `--only-missing` is needed to advance (it now advances on its own); the `tickers deferred` phrase the loop greps for must stay. Test in Task 2.

## Assumptions

- Stale-first ordering lives in `refresh_prices`, not in `_run_bulk_refresh` (shared with fundamentals and FX, which the issue does not touch).
- The daily loop lives in `scripts/daily.sh` (issue option 2a), not in a `--wait-for-quota` CLI flag (option 2b): a sleeping Python process would hold the DuckDB write lock for hours, which is exactly the #108 hazard; separate processes release it between rounds.
- `scripts/price_fill.sh` and its `--only-missing` drip are left as they are; README is updated to say the plain daily run now advances by itself.
- Live-DB acceptance (every ticker priced within 3 trading days; `min_market_cap` failures drop) cannot run in CI and is manual verification in the PR.

---

### Task 1: Stale-first ordering in `refresh_prices`

**Files:**
- Modify: `tests/fake_provider.py` (`FakeProvider`)
- Modify: `src/bot/ingest/universe.py` (`refresh_prices`, new `_stale_first`)
- Test: `tests/unit/test_prices_refresh.py`

**Interfaces:**
- Produces: `FakeProvider(..., prices_rate_limit_after: int | None = None)` — `daily_prices` records the call, then raises `ProviderRateLimitError("fake quota exhausted")` once it has already served `prices_rate_limit_after` calls (own counter, independent of the fundamentals `rate_limit_after`).
- Produces: `_stale_first(conn: duckdb.DuckDBPyConnection, tickers: list[str]) -> list[str]` — returns the same tickers (original spelling) reordered per Global Constraints.
- `refresh_prices` applies `_stale_first` after the `only_missing` filter.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_prices_refresh.py` (seed prices with a helper inserting `prices_daily(ticker, date, close, source)` rows):
  - `test_two_rate_limited_runs_import_distinct_tickers`: tickers `T1..T6`, every one with a bar; run `refresh_prices` twice, each with a fresh `FakeProvider(prices=..., prices_rate_limit_after=2)`, bar date `date.today()`. Assert each result has `imported == 2`, `deferred == 4`, and the union of imported tickers across both runs has 4 distinct names (`{"T1","T2","T3","T4"}`).
  - `test_never_priced_before_stale_before_fresh`: tickers `["FRESH", "STALE", "NEW"]`; FRESH seeded at `date.today()`, STALE at `date(2026, 9, 17)`, NEW unseeded. Assert `[t for _, t in provider.calls if _ == "daily_prices"] == ["NEW", "STALE", "FRESH"]`.
  - `test_stale_first_orders_oldest_first_and_keeps_csv_order_on_ties`: `["B", "A", "D", "C"]` with B and A both seeded `2026-09-17`, D `2026-10-01`, C `2026-08-01` → call order `["C", "B", "A", "D"]`; and two never-priced `["Y", "X"]` appended → they come first as `["Y", "X", ...]`.
  - `test_stale_first_matches_tickers_case_insensitively`: input `["aapl", "MSFT"]`, AAPL seeded today, MSFT unseeded → call order `["MSFT", "AAPL"]`.
  - `test_unpriceable_ticker_does_not_starve_the_rest`: `["GONE", "A", "B", "C"]`, `GONE` has no bars in the fake, `prices_rate_limit_after=2`; two runs (fresh provider each) → second run's daily_prices calls start `["GONE", "B"]`… i.e. GONE is retried and still only one of the two budgeted calls; union of tickers with a stored price after both runs is `{"A", "B"}`.
  - `test_only_missing_still_drops_priced_tickers`: existing behaviour pinned with ordering — `["P", "N1", "N2"]`, P seeded, `only_missing=True` → calls `["N1", "N2"]`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_prices_refresh.py -q`
Expected: FAIL (`prices_rate_limit_after` unknown keyword; CSV-order calls).

- [ ] **Step 3: Implement** `prices_rate_limit_after` in `FakeProvider` and `_stale_first` in `universe.py`. Sort with a stable `sorted` on key `(newest is not None, newest or date.min)` where `newest` comes from a dict built by the one `GROUP BY` query (keys upper-cased, values through `coerce_date`). Update the `refresh_prices` docstring: ordering, and why (a rate-limited run spends its quota on the stalest tickers, so consecutive runs cover the universe).

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_prices_refresh.py tests/unit/test_cli_refresh.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `feat(#136): refresh prices stale-first`

### Task 2: Daily script keeps refreshing prices until nothing is deferred

**Files:**
- Modify: `scripts/daily.sh`
- Modify: `src/bot/cli.py` (`_report_universe_refresh` deferred NOTE)
- Modify: `README.md` (Tiingo paragraph: daily run now advances stale-first and loops)
- Test: `tests/integration/test_scripts.py`, `tests/unit/test_cli_refresh.py`

**Interfaces:**
- Consumes: Task 1's ordering (a plain re-run advances; no `--only-missing` needed).
- `daily.sh` invocation sequence: `uv run bot refresh --prices` once per round, then `uv run bot refresh --fx`, then `uv run bot portfolio`, all `&&`-chained after the loop; the loop returns the failing round's exit code on a non-zero refresh.

- [ ] **Step 1: Write the failing tests.**
  - In `test_scripts.py`, extend `_UV_RECORDER` so that when `FAKE_DEFERRED_ROUNDS=<k>` is set, the first `k` `refresh --prices` calls also print `NOTE — 5 tickers deferred (provider rate limit); re-run the same command to continue.` (counter kept in a file next to `{calls}`). Change `_WRAPPERS["daily.sh"]` to `["run bot refresh --prices", "run bot refresh --fx", "run bot portfolio"]`, and make the generic wrapper tests' `[1]`/`[:1]` indices still mean "second call"/"first call only". Pass `BOT_PRICE_RETRY_PAUSE=0` in `_env` (or the daily tests) so no test sleeps.
  - `test_daily_repeats_price_refresh_while_tickers_are_deferred`: `FAKE_DEFERRED_ROUNDS=2` → calls are three `run bot refresh --prices` then `--fx` then `portfolio`; exit 0.
  - `test_daily_stops_after_max_rounds_and_still_runs_fx_and_portfolio`: `FAKE_DEFERRED_ROUNDS=99`, `BOT_PRICE_ROUNDS=3` → exactly three price calls, then fx and portfolio; exit 0.
  - `test_daily_failing_price_round_stops_everything`: `FAKE_DEFERRED_ROUNDS=1`, `FAKE_REFRESH_EXIT=3` → one price call only, exit 3 (covered by the generic failing-refresh test once indices are right; keep it explicit for daily).
  - In `test_cli_refresh.py`, `test_deferred_note_no_longer_requires_only_missing`: a prices refresh rate-limited by the fake prints a line containing `tickers deferred` and does not contain `--only-missing`. Follow `test_refresh_prices_invokes_price_orchestrator`: patch `bot.cli.refresh_prices` to return a `UniverseRefreshResult` whose `outcomes` hold two `TickerOutcome(status="deferred")`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/integration/test_scripts.py tests/unit/test_cli_refresh.py -q`
Expected: FAIL (daily.sh still runs `refresh --prices --fx` once; NOTE mentions `--only-missing`).

- [ ] **Step 3: Implement.** In `daily.sh`, a `refresh_prices` shell function: loop rounds `1..BOT_PRICE_ROUNDS`; capture `uv run bot refresh --prices 2>&1` and its status, print the output (it goes to the log); non-zero status → return it; no `tickers deferred` in the output → return 0; last round → return 0; else `sleep "$BOT_PRICE_RETRY_PAUSE"`. Header comment explains why (Tiingo 50/hour, stale-first, separate processes so the DB lock is released between rounds, #108). Change the NOTE to `NOTE — {n} tickers deferred (provider rate limit); re-run to continue with the stalest tickers.` Update README accordingly. Must pass `shellcheck` (the suite runs it).

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/integration/test_scripts.py tests/unit/test_cli_refresh.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite and lint** — `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

- [ ] **Step 6: Commit** — `feat(#136): daily script loops price refresh until nothing is deferred`
