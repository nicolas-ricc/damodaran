# Holding marks priced on or before the snapshot date — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A holding mark's price is the newest close **on or before the snapshot date**, converted into the valuation currency with the rates on or before that close's date, so the mark and `portfolio_snapshots` read the same day's market.

**Architecture:** `analyze` and both valuator loaders (`load_valuation_input`, `bulk_load_valuation_inputs`) take an optional keyword `price_as_of: date | None = None`. When set, the close query adds `date <= price_as_of`; the #222 FX rates are already looked up on or before the loaded close's date, so they follow without change. `ValuationInput` carries the loaded close (not the bound). `AnalyzeFn` gains the keyword, and `mark_holdings` calls `analyze_fn(ticker, conn, price_as_of=snapshot_date)`. `bot analyze` and the screener pass nothing, so they keep the newest close.

**Tech Stack:** Python 3.12, DuckDB 1.5, pytest, d2 v0.9.0 and TLC (both in CI only).

**Spec:** issue #225 and its "Agent Brief" comment (maintainer decision of 2026-11-05: an optional price date bound on `analyze`, which the portfolio sets to the snapshot date).

## Global Constraints

- Signature: `analyze(..., price_as_of: date | None = None)`, keyword-only. The same keyword on `load_valuation_input` and `bulk_load_valuation_inputs`. `None` = no bound = today's behaviour (newest non-null close).
- Bound semantics: `prices_daily.date <= price_as_of` (inclusive), same as `sync._load_latest_prices` (`src/bot/portfolio/sync.py:194-217`).
- FX: unchanged rule from #222. Rates are on or before the **loaded close's** date (`LatestClose.date`), not on or before `price_as_of`.
- The per-ticker and bulk loaders return equal `ValuationInput`s for the same bound.
- `bot analyze` (`src/bot/cli.py:379`) and the screener (`src/bot/screener/engine.py:94,144`) are not edited and pass no bound.
- Out of scope: reading the price from `portfolio_snapshots`; same-day reruns (#83).
- `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` pass. TLC on `portfolio.cfg` runs in CI (`pipeline-diagram` / `models`).
- Never edit an SVG or `docs/pipeline/rendered.sha256` by hand: d2 is not on `PATH` here. The render comes from the `pipeline-render` artifact of the `pipeline-diagram` workflow after a push (as in #222).

## Decisions taken here

1. **`ValuationInput` carries the loaded close, not the bound.** `latest_close` already holds the close, its currency and its date, and `close_rates` are keyed on that date. A bound field would be a second source of truth. The brief allows either option ("carry the bound, or the loaded close").
2. **`analyze(company=..., price_as_of=...)`:** `price_as_of` is ignored when `company` is supplied, the way `currencies` and `warned` already are. The bundle was loaded with its own bound. The docstring says so.
3. **No close on or before the bound** → `latest_close=None` → `current_price=None`, margin of safety `None`. This is the existing no-price path, not a `LookupError`, so the mark keeps its intrinsic value and red flags and only `price` is unknown.
4. **`AnalyzeFn`:** `def __call__(self, ticker: str, conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None) -> Analysis: ...`. `mark_holdings` always passes `price_as_of=snapshot_date`. Test doubles accept the keyword.
5. **Bulk loader:** the bound goes in the existing `closes` query's `WHERE` clause (`AND (?::DATE IS NULL OR date <= ?::DATE)`, or a branch on `price_as_of is None` that adds the predicate). The query count stays the same.

## Review Focus

1. **A holding with no close on or before the snapshot date, only later ones** (prices fetched after a backdated snapshot): the mark's price is `None` and the intrinsic value is still stored. It must not fall back to the later close. Test in Task 2 (`test_mark_holdings_no_close_before_snapshot_has_no_price`).
2. **A close dated exactly on the snapshot date** is included (an inclusive bound, like sync). Test in Task 1 (`test_load_valuation_input_bound_is_inclusive`).
3. **An EUR reporter whose rate moved between the bounded close and today:** the rate on or before the bounded close's date applies, not today's. Test in Task 1 (`test_analyze_price_as_of_converts_with_the_rate_of_the_bounded_close`) and Task 2 (AC4).
4. **The screener's bulk path with no bound** returns exactly what it did before. Covered by the existing `tests/fixtures/screener/second_pass_shortlist.golden` and the bulk/per-ticker agreement tests, which must pass unedited.
5. **An injected `analyze_fn` that does not accept `price_as_of`** (old-style double) fails loudly with `TypeError`, not as a silent "cannot value". `mark_holdings` only catches `LookupError`/`ValueError`, so this already holds. Task 2 updates every double in the repo.

---

### Task 1: Valuator loaders and `analyze` take `price_as_of`

**Files:**
- Modify: `src/bot/valuator/analysis.py` (`_load_latest_close` ~292-300, `load_valuation_input` ~452-500, `bulk_load_valuation_inputs` ~503-560 `closes` query, `analyze` ~791-870 signature, docstring and its `load_valuation_input` call)
- Test: `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Produces: `_load_latest_close(conn, ticker, price_as_of: date | None = None) -> LatestClose | None`; `load_valuation_input(conn, ticker, *, currencies=None, warned=None, price_as_of: date | None = None) -> ValuationInput`; `bulk_load_valuation_inputs(conn, tickers, *, currencies=None, warned=None, price_as_of: date | None = None) -> dict[str, ValuationInput]`; `analyze(ticker, conn, override_path=None, *, ..., price_as_of: date | None = None) -> Analysis`.

Fixture for the tests below: `_seed(conn)`, then replace AAPL's prices with two rows, `2026-05-31` close 100.0 and `2026-06-02` close 120.0 (USD). `D = date(2026, 6, 1)`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_valuator_analysis.py`:
  - `test_load_valuation_input_price_as_of_bounds_the_close`: `load_valuation_input(conn, "AAPL", price_as_of=D).latest_close == LatestClose(100.0, "USD", date(2026, 5, 31))`.
  - `test_load_valuation_input_bound_is_inclusive`: `price_as_of=date(2026, 6, 2)` gives close 120.0.
  - `test_load_valuation_input_no_close_before_bound`: `price_as_of=date(2026, 5, 1)` gives `latest_close is None`.
  - `test_bulk_loader_price_as_of_matches_per_ticker`: for `price_as_of` in `(None, D, date(2026, 5, 1))`, `bulk_load_valuation_inputs(conn, ["AAPL"], price_as_of=b)["AAPL"] == load_valuation_input(conn, "AAPL", price_as_of=b)`.
  - `test_analyze_price_as_of_uses_the_bounded_close`: `analyze("AAPL", conn, price_as_of=D).current_price == pytest.approx(100.0)`.
  - `test_analyze_without_bound_uses_newest_close` (AC3): `analyze("AAPL", conn).current_price == pytest.approx(120.0)`.
  - `test_analyze_price_as_of_converts_with_the_rate_of_the_bounded_close` (AC4): set `financials_annual.currency = 'EUR'`, closes 110.0 on 2026-05-31 and 132.0 on 2026-06-02 (USD). `currencies` EUR rows: 1.10 on 2026-05-31, 1.20 on 2026-06-02. `analyze(..., price_as_of=D)` gives `current_price ≈ 100.0`, `fx_rate ≈ 1/1.10`, `price_date == date(2026, 5, 31)`. Without a bound: `current_price ≈ 110.0` (132/1.20).
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_valuator_analysis.py -k "price_as_of or bound or newest_close"`. Expected: FAIL (`TypeError: unexpected keyword argument 'price_as_of'`), except `test_analyze_without_bound_uses_newest_close`, which already passes (a regression guard).
- [ ] **Step 3: Implement.** Add the keyword to the four functions above. The SQL predicate is `AND date <= ?` only when the bound is set (Decision 5). `analyze` forwards `price_as_of` to `load_valuation_input`. Docstrings: `price_as_of` is "newest close on or before this date; `None` = newest close", and `analyze`'s says it is ignored with `company` (Decision 2). Update the `ValuationInput.latest_close` and `Analysis.current_price`/`price_date` docstrings from "newest close" to "newest close (on or before `price_as_of` when set)".
- [ ] **Step 4: Run** the same tests, then `uv run pytest -q`. Expected: PASS, the screener golden untouched.
- [ ] **Step 5: Commit** `feat(#225): analyze takes an optional price date bound`.

### Task 2: Marks price on or before the snapshot date

**Files:**
- Modify: `src/bot/portfolio/marks.py` (`AnalyzeFn` ~51-52, `analyze_fn_default` ~133-140, the call ~151)
- Test: `tests/unit/test_portfolio_marks.py`, `tests/integration/test_portfolio_command.py` (doubles `_no_analyze` ~125 and `_valued_at` ~319)

**Interfaces:**
- Consumes: `analyze(..., price_as_of=...)` from Task 1.
- Produces: `AnalyzeFn.__call__(self, ticker: str, conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None) -> Analysis`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_portfolio_marks.py`. Fixture for the default-valuator tests: `_seed_valuable(conn)`, then replace AAPL's `prices_daily` with closes on 2026-05-31 (100.0) and 2026-06-02 (120.0). `DAY = 2026-06-01`.
  - `test_mark_holdings_prices_on_or_before_the_snapshot_date` (AC1): `_hold(conn, "AAPL")`; `mark_holdings(conn, DAY, assumptions_dir=tmp_path)[0].price == pytest.approx(100.0)`, and the same from `load_marks(conn, DAY)`.
  - `test_mark_holdings_rerun_of_an_old_snapshot_uses_that_dates_close` (AC2): add a close of 90.0 on 2026-05-01. Insert a `portfolio_snapshots` row dated `OLD = date(2026, 5, 4)` (same columns as `_hold`). `mark_holdings(conn, OLD, ...)` stores price 90.0.
  - `test_mark_holdings_no_close_before_snapshot_has_no_price` (Review Focus 1): only the 2026-06-02 close. The mark for `DAY` has `price is None` and `intrinsic_value is not None`.
  - `test_mark_holdings_converts_the_bounded_close` (AC4): the EUR setup of Task 1's AC4 test. The mark for `DAY` has price ≈ 100.0.
  - `test_mark_holdings_passes_the_snapshot_date`: a double that records its `price_as_of` keyword. After `mark_holdings(conn, DAY, analyze_fn=double)` with one holding, the recorded value is `DAY`.
  - Update `_analyze_with`'s inner `fn` to accept `*, price_as_of: date | None = None`. The existing `test_mark_holdings_stores_the_converted_price` must pass unedited (its only close, 2026-05-29, is before `DAY`).
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_portfolio_marks.py`. Expected: the AC1, AC2, AC4 and passes-the-date tests FAIL (120.0 stored, or `TypeError`). The no-close test also fails (120.0 instead of `None`).
- [ ] **Step 3: Implement.** Protocol as in Interfaces. `analyze_fn_default(ticker, conn, *, price_as_of=None)` forwards `price_as_of=price_as_of` to `valuator.analyze`. The loop calls `analyze_fn(ticker, conn, price_as_of=snapshot_date)`. Update the `mark_holdings` docstring: "the mark's price is the newest close on or before `snapshot_date`, the quote sync values the position with". In `tests/integration/test_portfolio_command.py`, give `_no_analyze` and `_valued_at`'s `fn` the keyword `*, price_as_of: date | None = None`.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_portfolio_marks.py tests/integration/test_portfolio_command.py`, then `uv run pytest -q` and `uv run ruff check . && uv run mypy src`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(#225): holding marks price the snapshot date's close`.

### Task 3: Atlas and context say "on or before the snapshot date"

**Files:**
- Modify: `docs/pipeline/portfolio.d2` (`marks.valuation` label line 74 "latest close" → "newest close on or before the snapshot date"; edge line 176 `duckdb.prices_daily -> marks.valuation: "latest close"` → `"newest close on or before the snapshot date"`)
- Modify: `docs/pipeline/portfolio-marks.d2` (lines 42-43, the second label line "intrinsic value per share, latest close, red narrative flags" → "intrinsic value per share, newest close on or before the snapshot date, red narrative flags". Only the second line changes: the first line is the model `steps` label that `tests/unit/test_pipeline_models.py` matches)
- Modify: `docs/pipeline/models/portfolio.tla` (the comments above `TheValuatorValuesItWithARedFlag` / `...NoRedFlag`: "`analyze_fn` gives ..." → "`analyze_fn(..., price_as_of=snapshot_date)` gives ..."; comments only, no TLA+ logic)
- Modify: `CONTEXT.md` (Margin of safety: append "A holding mark uses the newest close on or before the snapshot date.")
- Test: `tests/unit/test_pipeline_diagram.py`, `tests/unit/test_pipeline_subboards.py`, `tests/unit/test_pipeline_models.py`, `docs/pipeline/check.py`

- [ ] **Step 1: Edit** the files above.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py` and `python3 docs/leccion/check.py`. Expected: PASS. `python3 docs/pipeline/check.py` fails only on the stale `rendered.sha256`.
- [ ] **Step 3: Commit** `docs(#225): the atlas says a mark's close is on or before the snapshot date`.
- [ ] **Step 4 (orchestrator, after push):** download the `pipeline-render` artifact of the push's `pipeline-diagram` run (`gh run download <id> -n pipeline-render`). Copy the SVGs and `rendered.sha256` into `docs/pipeline/` and run `python3 docs/pipeline/check.py` (PASS). Commit `docs(#225): render`, naming the run id. Check that the same run's `models` job (TLC, `portfolio.cfg` included) is green.
