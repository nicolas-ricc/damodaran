# new_red_flag against the latest known mark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `new_red_flag` diffs a holding's current red flags against its newest *known* red-flag set (`red_flags IS NOT NULL`, any earlier snapshot), so a day without a valuation no longer makes a standing red flag fire again.

**Architecture:** A new loader in `src/bot/portfolio/marks.py` reads, in one window-function query, the newest earlier known red-flag set of every held ticker. `compute_events` passes each ticker's baseline to `detect_new_red_flags`, which stays pure and takes the baseline set and its date. It records the date in the event's `details`. The other three mark events keep diffing `prev_marks` (the previous snapshot) as they do today. Boards, model and docstrings change to say so.

**Tech Stack:** Python 3.12, DuckDB (`QUALIFY ROW_NUMBER() OVER (...)`), pytest, d2 v0.9.0 + TALA (local at `/usr/local/lib/d2/d2-v0.9.0/bin`), TLA+ (TLC in the CI `models` job; no Java here).

**Spec:** issue #224 and its Agent Brief comment (maintainer decision of 2026-11-05).

## Global Constraints

- Baseline = "the newest `holding_marks` row with `snapshot_date < current snapshot` and `red_flags IS NOT NULL`".
- With no such row, the baseline is empty: every current red flag fires, as on today's first run.
- When the current mark is unknown (`red_flags=None`), nothing fires (unchanged).
- `intrinsic_value_crossed_price`, `below_quality_gate` and `sector_recalibrated` keep diffing the previous snapshot's mark. Their code and their tests stay untouched.
- The loader runs one query for all held tickers (a window function), not one per ticker.
- `events_log.details` of `new_red_flag` gains `baseline_snapshot_date`: an ISO date string, or `null` when there is no known mark.
- `detect_new_red_flags` stays pure (no connection).
- Out of scope: same-day reruns (#83, so the bound is strictly `<`), and which flags can be red (#218).
- `mypy --strict`, ruff, and the full suite pass. `python3 docs/pipeline/check.py` passes. TLC on `portfolio.cfg` passes in CI.
- Never edit an SVG or `rendered.sha256` by hand: run `docs/pipeline/build.sh` with the pinned d2 on `PATH`.

## Decisions

1. **Loader:** `load_red_flag_baselines(conn, before: date, tickers: Collection[str]) -> dict[str, RedFlagBaseline]`, in `marks.py` beside `load_marks`. `RedFlagBaseline` is a frozen dataclass with `snapshot_date: date` and `red_flags: dict[str, str]`. A ticker with no known earlier mark is absent from the dict. An empty `tickers` returns `{}` without a query. Tickers are matched as stored: `holding_marks.ticker` is already upper-cased by `_held_tickers`, and `compute_events`' `held_tickers` is upper-cased too.
2. **Detector signature:** `detect_new_red_flags(baseline: Collection[str], curr: HoldingMark, *, baseline_date: date | None, snapshot_date: date, prev_date: date | None) -> list[Event]`. `baseline` holds the flag names red in the baseline, empty when there is none. `details` = `{"flag", "reason", "baseline_snapshot_date": baseline_date.isoformat() or None}`. `prev_snapshot_date` of the event stays the previous snapshot (`prev_date`), like every other event.
3. **The loader is called on every run, including the first** (`prev_snapshot_date is None`). There is no earlier row then, so the result matches today's behaviour, and the code needs no special case.
4. **Model (`portfolio.tla`):** in the model, `prevMark` is the *previous snapshot's* mark. With the new rule, a red flag can stay silent even when `prevMark = "absent"`, because an older known mark may hold it (a ticker sold and bought back). So:
   - the guard `valuation # "red" \/ prevMark = "present"` on `NoNewRedFlag` is dropped;
   - `NoPreviousMarkOnlyRedFlags` loses its second clause ("a red flag now does fire") and keeps only "with no previous mark, the other three never fire". Its name still reads true ("only red flags").

   The brief says "model labels", but leaving the guard in place would make the model claim the old rule. Leaving `flags_checked` already resets `valuation`, so the added states stay few.
5. **Copy (boards, view, docstrings).** The phrase is "the last known mark", meaning the newest earlier mark whose flags are known. Pinned phrases in tests change accordingly:
   - `_PORTFOLIO_TEXT["marks.persist.unknowns"]`: `"counts as empty"` becomes `"last known mark"`.
   - `events.new_red_flag`: `"not red in the previous mark"` becomes `"not red in the last known mark"`.
   - In `test_pipeline_subboards.py`, `"counts as none red"` becomes `"no known mark: every red flag is new"`.

## Review Focus

- A ticker sold and bought back months later, still red → no event (baseline = the old known mark). Task 2 test `test_rebought_holding_compares_with_old_known_mark`.
- A known *empty* set (`{}`, valued with no red flag) is a known baseline, not unknown → red later fires. The AC "green on D3, red on D4" covers it. A `json` value of `'{}'` must not be treated as NULL.
- Two held tickers with different baseline dates in one call → each gets its own (Task 1 test `test_baselines_are_per_ticker`).
- Marks of the current snapshot itself, or of later dates (a backfill), never count as the baseline: the bound is strict `<` (Task 1 test `test_baseline_ignores_current_and_later_marks`).
- The baseline date is JSON-serialisable in `events_log.details` (`persist_events` uses `json.dumps`). Task 2's integration test persists the events and reads the date back.

---

### Task 1: `load_red_flag_baselines`

**Files:**
- Modify: `src/bot/portfolio/marks.py` (module docstring; new dataclass and loader after `load_marks`)
- Test: `tests/unit/test_portfolio_marks.py`

**Interfaces:**
- Produces: `RedFlagBaseline(snapshot_date: date, red_flags: dict[str, str])` and `load_red_flag_baselines(conn: duckdb.DuckDBPyConnection, before: date, tickers: Collection[str]) -> dict[str, RedFlagBaseline]`.

- [ ] **Step 1: Failing tests.** Seed the rows with `persist_marks` on an in-memory DB with `apply_schema`. Days D1–D4 = 2026-05-01..04.
  - `test_baseline_skips_unknown_marks`: T red `{"growth_reinvestment": "r"}` on D1, `None` on D2. `load_red_flag_baselines(conn, D3, ["T"]) == {"T": RedFlagBaseline(D1, {"growth_reinvestment": "r"})}`.
  - `test_known_empty_set_is_a_baseline`: `{}` on D1. The result is `{"T": RedFlagBaseline(D1, {})}`.
  - `test_no_known_mark_no_baseline`: only `None` marks → `{}`. No rows at all → `{}`.
  - `test_baseline_ignores_current_and_later_marks`: red on D1, `{}` on D3 and D4. `before=D3` → D1.
  - `test_baselines_are_per_ticker`: A known on D2; B known on D1 and unknown on D2; C not asked for. `before=D3, tickers=["A", "B"]` → A@D2, B@D1, and no C.
  - `test_baselines_empty_tickers`: `tickers=[]` → `{}`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_portfolio_marks.py`. Expected: ImportError / FAIL.
- [ ] **Step 3: Implement.** One query: `SELECT ticker, snapshot_date, red_flags FROM holding_marks WHERE snapshot_date < ? AND red_flags IS NOT NULL AND ticker IN (<placeholders>) QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY snapshot_date DESC) = 1`. Parse `red_flags` the way `load_marks` does. Rewrite the module docstring's last two sentences: an unknown prior red-flag set is skipped, and `new_red_flag` compares with the last known mark (`load_red_flag_baselines`); an unknown prior gate set or WACC still yields no event.
- [ ] **Step 4: Run** the same tests, then `uv run mypy src`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(#224): load the last known red-flag set per holding`.

### Task 2: Detector and `compute_events`

**Files:**
- Modify: `src/bot/portfolio/events.py` (`detect_new_red_flags`, `compute_events`, module and `compute_events` docstrings)
- Test: `tests/unit/test_portfolio_events.py` (the four red-flag tests only), `tests/integration/test_portfolio_events.py`

**Interfaces:**
- Consumes: Task 1's `load_red_flag_baselines`, `RedFlagBaseline`.
- Produces: the Decision 2 signature.

- [ ] **Step 1: Failing tests.**
  - Unit (rewrite the four existing red-flag tests to the new signature):
    - newly red fires and persistent red does not (`baseline={"story_margin"}`);
    - an empty baseline with `baseline_date=None` → all red fire, `details["baseline_snapshot_date"] is None`;
    - a baseline date → `details["baseline_snapshot_date"] == "2026-05-01"`;
    - the current mark unknown → `[]`.
  - Integration (`compute_events` over `persist_marks` rows, ticker `T`, snapshots on each day). One test per AC:
    - `test_red_through_an_unknown_day_does_not_refire`: red D1, `None` D2, red D3. `compute_events(conn, D2, D3)` has no `NEW_RED_FLAG`. `load_red_flag_baselines(conn, D3, ["T"])["T"].snapshot_date == D1`.
    - `test_red_after_green_after_unknown_fires`: red D1, `None` D2, `{}` D3, red D4. `compute_events(conn, D3, D4)` has exactly one `NEW_RED_FLAG`, `baseline_snapshot_date == "2026-05-03"`.
    - `test_never_valued_holding_red_now_fires`: `None` D1, red D2. `compute_events(conn, D1, D2)` gives one event with `baseline_snapshot_date is None`. The first run, `compute_events(conn, None, D1)` with red on D1, fires too.
    - `test_unknown_now_fires_nothing`: red D1, `None` D2 → no `NEW_RED_FLAG`.
    - `test_rebought_holding_compares_with_old_known_mark`: held and red on D1, no snapshot or mark on D2, held and red on D3. `compute_events(conn, D2, D3)` → no `NEW_RED_FLAG`.
    - `test_baseline_date_survives_persist`: `persist_events` then `json_extract_string(details, '$.baseline_snapshot_date')` equals the ISO date.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_portfolio_events.py tests/integration/test_portfolio_events.py`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - Change the detector per Decision 2.
  - In `compute_events`, call `load_red_flag_baselines(conn, curr_snapshot_date, held_tickers)` once, beside `load_marks`. For each ticker, pass `set(b.red_flags)` and `b.snapshot_date`, or `set()` and `None`.
  - Leave the other three detectors' calls untouched.
  - Docstrings: the module docstring says `new_red_flag` diffs against the last known mark. `compute_events` no longer says "no baseline mark, so only red flags (all new) fire": the red flags compare with the last known mark, all new when there is none.
- [ ] **Step 4: Run** the same tests, then `uv run pytest -q`, `uv run ruff check . && uv run mypy src`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(#224): new_red_flag compares with the last known mark`.

### Task 3: Boards, model, render

**Files:**
- Modify: `docs/pipeline/portfolio.d2`:
  - the `marks.persist.unknowns` note, which says an unknown previous red-flag set is skipped and `new_red_flag` compares with the last known mark (an earlier mark whose flags are known);
  - `events.new_red_flag`, which says "one per narrative flag red now and not red in the last known mark", "unknown previous flags: the mark before is used", "no known mark: every red flag is new", and "unknown flags now: nothing";
  - the `duckdb.holding_marks -> events.new_red_flag` edge label, which becomes "current and last known marks".
- Modify: `docs/pipeline/portfolio-mark-events.d2`:
  - the two `cross_checked -> flags_checked` edges take the new step labels from `portfolio.view.js`;
  - their second lines say how, with no digits.
- Modify: `docs/pipeline/models/portfolio.tla` (Decision 4, plus the `NoNewRedFlag` and `NewRedFlagFires` cite comments naming `load_red_flag_baselines`), `docs/pipeline/models/portfolio.view.js`:
  - `NewRedFlagFires`: "new red flag fires [red now, not red in the last known mark]";
  - `NoNewRedFlag`: "no new red flag [none red now, red in the last known mark, or flags unknown]".
- Test: `tests/unit/test_pipeline_diagram.py` and `tests/unit/test_pipeline_subboards.py` (Decision 5 pins).
- Render: every `docs/pipeline/*.svg` that `build.sh` rewrites, plus `rendered.sha256`.

- [ ] **Step 1: Failing tests.** Change the Decision 5 pins. Run `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py`. Expected: the pinned-text tests FAIL.
- [ ] **Step 2: Edit** the boards, the model and the view as listed above. Keep every other pinned phrase verbatim (for example "only growth_reinvestment can fire new_red_flag"). Step labels must match `portfolio.view.js` exactly (`test_step_labels_are_drawn`).
- [ ] **Step 3: Run** the same tests. Expected: PASS.
- [ ] **Step 4: Render.** `PATH=/usr/local/lib/d2/d2-v0.9.0/bin:$PATH docs/pipeline/build.sh`, then `python3 docs/pipeline/check.py`. Expected: `0 errors`. In `git status`, only SVGs and `rendered.sha256` change besides the sources (PNGs are git-ignored).
- [ ] **Step 5: Commit** `docs(#224): boards and model say new_red_flag compares with the last known mark`.
