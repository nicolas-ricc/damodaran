# currency_changed per (account, ticker) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `currency_changed` compares each (account, ticker)'s currency across the two snapshots, so a ticker held in a USD account and a EUR account can no longer fire a spurious event because `ANY_VALUE(currency)` picked a different row each day.

**Architecture:** `detect_currency_changes` keeps its place among the pure detectors in `src/bot/portfolio/events.py`. It stops taking `Position` and takes per-account rows instead (a new frozen dataclass `AccountCurrency`). A new loader, `_load_account_currencies`, reads those rows straight from `portfolio_snapshots`. `compute_events` feeds the detector from that loader. `_load_positions`, `Position` and every other detector keep aggregating per ticker. Two board labels change text, and the SVGs come from CI because d2 is not on `PATH` here.

**Tech Stack:** Python 3, DuckDB, pytest; d2 v0.9.0 (CI render); TLC (CI `models` job).

**Spec:** issue #223 and its Agent Brief comment. Board conventions are in `docs/pipeline/README.md`.

## Global Constraints

- `mypy --strict` and `ruff` stay clean (`uv run ruff check . && uv run mypy src`).
- `details` = `{"account": ..., "from": ..., "to": ...}`; `ticker` upper-cased (brief).
- No event on the first run (unchanged): `compute_events` keeps calling the detector only when `prev_snapshot_date is not None`.
- `Position`, `_load_positions` and the other detectors are not changed. `ANY_VALUE(currency)` stays in `_load_positions` for `Position.currency`.
- Out of scope: same-day reruns (#83), symbol mapping (#84).
- Never edit an SVG or `rendered.sha256` by hand (`docs/pipeline/README.md`).

## Decisions taken here

1. **New input type.** `AccountCurrency(account: str, ticker: str, currency: str | None)`, a frozen dataclass next to `Position`. It is one row of `portfolio_snapshots`.
2. **Detector signature.** `detect_currency_changes(prev: Sequence[AccountCurrency], curr: Sequence[AccountCurrency], *, snapshot_date: date, prev_date: date | None) -> list[Event]`. It stays pure.
3. **Several rows for one (account, ticker).** The primary key of `portfolio_snapshots` is `(snapshot_date, account, ticker, con_id)` (`src/bot/db/schema.sql:191`). One account can therefore hold one ticker under two `con_id`s, for example two listings. The detector collapses rows by `(account, ticker.upper())`. The key's currency is known only when its rows carry exactly one distinct currency and none of them is NULL. Otherwise it is treated as unknown, and an unknown currency fires nothing, as today. This makes the result deterministic and order-independent, and it can never produce the issue's false positive inside a single account.
4. **Event order.** Events are sorted by `(ticker, account)`, so the stream is the same whatever order the rows come in.
5. **Loader.** `_load_account_currencies(conn, snapshot_date) -> list[AccountCurrency]` runs `SELECT account, ticker, currency FROM portfolio_snapshots WHERE snapshot_date = ?`. It does no aggregation, because the rule lives in the pure detector, where it can be unit-tested.
6. **Atlas copy.** `portfolio.d2` `events.currency_changed`, replacing the line `held in several accounts: any one account's currency`:
   `compared per (account, ticker): one event per account whose currency changed;\nan account holding it on one side only: nothing`.
   `portfolio-events.d2`, the `CurrencyChangedFires` edge label (line 49), replacing `; held in several accounts: any one account's currency`:
   `, compared per (account, ticker), one event per account`.
   The model (`models/portfolio.tla`, `portfolio.view.js`) carries no such text, so it is unchanged. The brief asks for a change there only "if they carry that text".

## Review Focus

- One account holds the ticker under two `con_id`s with different currencies → no event, and no crash (Task 1 test `test_currency_ambiguous_within_account_is_unknown`).
- The ticker moves from account A on the previous day to account B today → no event (Task 1 test `test_currency_account_on_one_side_only_no_event`).
- The currency is NULL on one side → no event (Task 1 test `test_currency_unknown_side_no_event`).
- A lower-case ticker in one snapshot and an upper-case one in the other → matched, and the event's ticker is upper-cased (Task 1 test `test_currency_ticker_case_insensitive`).
- Rows supplied in any order → the same events in the same order (Task 1 tests run both orders).

---

### Task 1: Per-account currency detector, loader, wiring

**Files:**
- Modify: `src/bot/portfolio/events.py` (add `AccountCurrency` after `Position`; rewrite `detect_currency_changes` at lines 188-214; add `_load_account_currencies` after `_load_positions`; `compute_events` passes the loader's output)
- Test: `tests/unit/test_portfolio_events.py` (currency section), `tests/integration/test_portfolio_events.py`

**Interfaces:**
- Produces: `AccountCurrency`, `detect_currency_changes` (Decision 2), `_load_account_currencies` (Decision 5).

- [ ] **Step 1: Failing unit tests** in the currency section. Use a helper `_acc(account, ticker, ccy)` that returns an `AccountCurrency`. Adapt the two existing tests to the new input; `test_currency_change_fires` now expects `details == {"account": "U1", "from": "GBP", "to": "USD"}`. New tests:
  - `test_currency_same_ticker_two_accounts_unchanged_no_event`: parametrised over both row orders. prev = [U1 AAPL USD, U2 AAPL EUR], curr = the same rows in the given order (and prev in the reverse order) → `[]`.
  - `test_currency_one_account_switches`: prev [A USD, B EUR], curr [A EUR, B EUR], both orders → exactly one event, with `ticker == "AAPL"` and `details == {"account": "A", "from": "USD", "to": "EUR"}`.
  - `test_currency_account_on_one_side_only_no_event`: prev [A AAPL USD], curr [B AAPL EUR] → `[]`.
  - `test_currency_unknown_side_no_event`: a NULL currency on either side → `[]`.
  - `test_currency_ambiguous_within_account_is_unknown`: prev [A AAPL USD], curr [A AAPL USD, A AAPL EUR] → `[]`. prev [A AAPL USD, A AAPL NULL], curr [A AAPL EUR] → `[]`.
  - `test_currency_ticker_case_insensitive`: prev [A "bp" GBP], curr [A "BP" USD] → one event, ticker `"BP"`.
- [ ] **Step 2: Failing integration tests** in `tests/integration/test_portfolio_events.py`. Add a helper that inserts rows with an explicit account, `_insert_account_rows(conn, date, [(account, ticker, qty, mv, ccy)])`. The existing end-to-end test's AAPL USD→EUR event now also carries `"account": "DU1"`, so assert that. New tests:
  - `test_currency_two_accounts_unchanged_no_event`: parametrised over the two insertion orders of the accounts on each day (USD-first yesterday with EUR-first today, and the reverse). `compute_events` → no `CURRENCY_CHANGED`.
  - `test_currency_one_account_switches_logs_account`: account A USD→EUR, B EUR unchanged → exactly one `CURRENCY_CHANGED`. After `persist_events`, `json_extract_string(details, '$.account')` from `events_log` is `'A'`.
- [ ] **Step 3: Run** `uv run pytest -q tests/unit/test_portfolio_events.py tests/integration/test_portfolio_events.py`. Expected: the new and adapted tests FAIL (TypeError or ImportError on `AccountCurrency`, or a missing `account` key).
- [ ] **Step 4: Implement** Decisions 1-5. Update the docstring of `detect_currency_changes` to state the per-account rule and the ambiguity rule. In `compute_events`, load `_load_account_currencies` for both dates inside the existing `if prev_snapshot_date is not None:` block.
- [ ] **Step 5: Run** the same tests, then `uv run pytest -q` and lint. Expected: PASS.
- [ ] **Step 6: Commit** `fix(#223): currency_changed per (account, ticker)`.

### Task 2: Atlas text

**Files:**
- Modify: `docs/pipeline/portfolio.d2:101`, `docs/pipeline/portfolio-events.d2:49`
- Test: `tests/unit/test_pipeline_diagram.py` (`_PORTFOLIO_TEXT["events.currency_changed"]`), `tests/unit/test_pipeline_subboards.py` (`_PORTFOLIO_TEXT["portfolio-events"]`)

- [ ] **Step 1: Failing tests.** Add `"per (account, ticker)"` and `"one event per account"` to `_PORTFOLIO_TEXT["events.currency_changed"]` (keep `"listing currency"` and `"not on the first run"`). Add `"compared per (account, ticker), one event per account"` to `_PORTFOLIO_TEXT["portfolio-events"]`. Add a test in `test_pipeline_subboards.py`, `test_no_board_says_any_one_accounts_currency`: no `docs/pipeline/*.d2` contains `any one account's currency`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py`. Expected: the new entries FAIL.
- [ ] **Step 3: Edit the two labels** with the Decision 6 copy. Edge and node counts are unchanged.
- [ ] **Step 4: Run** the same tests (PASS) and `python3 docs/pipeline/check.py`. Expected: the only failure is the stale `rendered.sha256` (fixed in Task 3).
- [ ] **Step 5: Commit** `docs(#223): per-account currency rule on the portfolio boards`.

### Task 3: Render (orchestrator, needs a push)

- [ ] Push the branch and wait for the `pipeline-diagram` run on its head (`gh run list --branch <b> --workflow pipeline-diagram`, then `gh run watch <id>`). Download `pipeline-render` (`gh run download <id> -n pipeline-render`). Copy `portfolio.svg`, `portfolio-events.svg` and `rendered.sha256` into `docs/pipeline/`, plus any other SVG that d2 renders differently. The same run's `models` job is the TLC check on `portfolio.cfg`, and it must be green. Run `python3 docs/pipeline/check.py` (expected: pass) and the full suite. Commit `docs(#223): render`.
