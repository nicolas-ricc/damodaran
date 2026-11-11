# Idempotent portfolio events per snapshot day Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Running `bot portfolio` twice on the same snapshot day leaves `events_log` with one row per distinct event of that day and writes the same `alerts.md` both times, while an event that is really new on the rerun is still logged and alerted once.

**Architecture:** `persist_events` stops appending blindly. It reads the rows already logged for the snapshot dates in its batch and inserts only events whose identity is not among them. A new reader, `load_events(conn, snapshot_date)`, returns the day's logged events in insertion order. `run_portfolio` renders `alerts.md` from that reader instead of from the events it just computed, so the day's alerts are "already logged ∪ newly detected". This keeps the `new_filing` events that `compute_events` suppresses on a rerun because they are already in `events_log`. No schema change and no migration.

**Tech Stack:** Python 3, DuckDB, Jinja2 (`alerts.md.j2`), pytest, mypy --strict, ruff, d2 v0.9.0 (pipeline boards).

**Spec:** GitHub issue #83 (nicolas-ricc/damodaran), "bot portfolio: a same-day rerun appends duplicate rows to events_log", with the triage comment's Agent Brief, which records the decision that a rerun is idempotent.

## Global Constraints

- A rerun is idempotent: after N runs on the same day, `events_log` holds exactly one row per distinct event for that `curr_snapshot_date`.
- `alerts.md` after the second run has the same content as after the first, including `new_filing` events.
- An event that is new on a rerun (for example a filing ingested between runs) is logged and alerted once.
- Events on other snapshot dates are untouched: no deletes, ever.
- `persist_events(conn, events) -> int` keeps its signature and returns only the rows actually inserted.
- Out of scope: detection thresholds and the set of event types, notifier delivery (`bot.notifier`, which still sends the day's `alerts.md` on every run), and cleaning duplicates already present in existing databases.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits use Conventional Commits scoped `(#83)`.

## Review Focus

1. **The rerun after a `new_filing` day.** `compute_events` suppresses the filing on the rerun because it is already in `events_log`. `alerts.md` must still list it. Pinned in Task 2 by `test_rerun_keeps_new_filing_in_alerts`.
2. **The same event twice in one batch** (two identical `Event`s passed to one `persist_events` call). One row. Pinned in Task 1 by `test_persist_events_dedupes_within_batch`.
3. **`details` key order and float values after a JSON round trip through DuckDB.** The rerun must match the stored row, and the rendered alert must show the same `k=v` order and values. Pinned in Task 1 by `test_load_events_round_trips_details` and in Task 2 by the byte-for-byte `alerts.md` comparison.
4. **Two distinct events sharing type, ticker and date** (two filings, two red flags of one holding). Both stay, because `details` differ. Pinned in Task 1 by `test_persist_events_keeps_events_differing_only_in_details`.
5. **A rerun whose inputs changed between runs** (a mark moved, so the IV-cross details differ). It is logged as a distinct event; see Assumptions. Pinned in Task 1 by the same test as item 4.

---

## Assumptions

- **Event identity** is `(event_type, ticker, prev_snapshot_date, curr_snapshot_date, details)`, where `details` is compared as canonical JSON (`json.dumps(..., sort_keys=True)` on both the new dict and the stored text after `json.loads`). `source` and `detected_at` are not part of it. Rejected: `(event_type, ticker, curr_snapshot_date)` alone, which would merge two filings or two red flags of the same holding on one day into one row.
- **Skip, not replace.** The rerun never deletes. A logged event that a rerun no longer detects (its inputs changed) stays logged and stays in that day's `alerts.md`. Rejected: delete-then-insert for the day, which would drop the `new_filing` events of the first run (the issue's caveat).
- **`PortfolioRunResult.events`** becomes the number of events in the day's `alerts.md` (the logged events of the snapshot date after this run), so the CLI line `→ N event(s)` matches the file. The `portfolio_report_written` log line gets `events_logged=<rows inserted by this run>`.
- **Order of the alerts** is insertion order, `ORDER BY rowid`, so a rerun renders the first run's events in the first run's order, followed by the newly logged ones.
- **`load_events` collapses identical rows** (same identity, first one kept), so a database that already holds duplicates for the day from before this fix renders each event once. The duplicate rows themselves stay (cleaning them is out of scope). Rejected: rendering raw rows, which would list a pre-existing duplicate twice.
- **No unique index, no explicit transaction.** `details` is free-form JSON, so it cannot be a clean unique key. Two `bot portfolio` processes cannot write the same file at once, because `bot.storage.db.connect` opens the file read-write and DuckDB holds an exclusive per-process file lock. Rejected: a `UNIQUE` constraint on a canonicalised details column, which would need a schema migration.
- **An `event_type` string unknown to `EventType`** makes `load_events` raise `ValueError`. Only `persist_events` writes `events_log`, always as `str(EventType)`, and no member has been removed. Rejected: silently skipping such rows.

### Task 1: `persist_events` skips logged events; `load_events` reads a day back

**Files:**
- Modify: `src/bot/portfolio/events.py` (`persist_events`, new `load_events`, and the module docstring line that says the caller persists events)
- Modify: `src/bot/storage/schema.sql` (the `events_log` comment: still append-only, but one row per distinct event per snapshot day, deduplicated by `persist_events`)
- Test: `tests/integration/test_portfolio_events.py`

**Interfaces:**
- Consumes: `Event`, `EventType` (same module).
- Produces:
  - `persist_events(conn: duckdb.DuckDBPyConnection, events: list[Event]) -> int`: inserts each event whose identity (see Assumptions) is neither in `events_log` nor earlier in the same batch; returns the number of rows inserted.
  - `load_events(conn: duckdb.DuckDBPyConnection, snapshot_date: date) -> list[Event]`: every `events_log` row with `curr_snapshot_date = snapshot_date`, `ORDER BY rowid`, identical rows collapsed to the first, as `Event` with `event_type=EventType(row)`, `details=json.loads(row)` (an empty dict for NULL).

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_portfolio_events.py` (use the module's `conn` fixture and its `PREV`/`CURR` dates)

  - `test_persist_events_twice_writes_once_for_every_event_type`: build one `Event(t, "AAA", CURR, PREV, {"k": 1.5, "a": "x"})` per member of `EventType` (all twelve). Assert `persist_events(conn, evs) == 12`, then `persist_events(conn, evs) == 0`, and `SELECT COUNT(*) FROM events_log` is `12`.
  - `test_persist_events_dedupes_within_batch`: `persist_events(conn, [e, e]) == 1` and the count is 1.
  - `test_persist_events_keeps_events_differing_only_in_details`: two `NEW_FILING` events for `"AAA"` on `CURR` with `details={"filing_type": "10-K", ...}` and `{"filing_type": "8-K", ...}` give `2`; then persisting the first one again with an extra key (`{"filing_type": "10-K", "x": 1}`) gives `1`, for a count of 3.
  - `test_persist_events_ignores_details_key_order`: persist `{"a": 1, "b": 2}`, then the same event with `{"b": 2, "a": 1}`: the second call returns `0`.
  - `test_persist_events_other_dates_unaffected`: persist an event on `PREV`, then the same type, ticker and details on `CURR`: both calls return `1`, and `load_events(conn, PREV)` still has exactly the first one.
  - `test_load_events_round_trips_details`: persist `[e1, e2]` with `e1.details == {"z": 0.123456789, "a": None, "m": "s"}`. Assert `load_events(conn, CURR) == [e1, e2]` and `list(load_events(conn, CURR)[0].details) == ["z", "a", "m"]` (key order kept).
  - `test_load_events_empty_day`: `load_events(conn, CURR) == []`.
  - `test_persist_events_empty_batch`: `persist_events(conn, []) == 0`.
  - `test_load_events_collapses_preexisting_duplicates`: insert the same event row twice with a raw `INSERT INTO events_log` (as the old append did), then assert `load_events(conn, CURR) == [e]`.
  - Keep `test_new_filing_reported_once` as it is (it must still pass).

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `uv run pytest -q tests/integration/test_portfolio_events.py`
  Expected: an ImportError on `load_events`. Once it is stubbed, the `persist_events` twice/dedupe tests fail (the second call returns 12, not 0).

- [ ] **Step 3: Implement** `persist_events` and `load_events` in `src/bot/portfolio/events.py`

  `persist_events` returns 0 on an empty batch before any query (as today), then selects `event_type, ticker, prev_snapshot_date, curr_snapshot_date, details` from `events_log` for the distinct `curr_snapshot_date`s of the batch, builds a set of identity keys, then walks the batch in order. It keeps an event whose key is unseen, adds the key, and `executemany`-inserts the kept ones exactly as today (`json.dumps(e.details)`, insertion order of keys preserved). It returns `len(kept)`. Update its docstring.

- [ ] **Step 4: Run the tests and confirm they pass**

  Run: `uv run pytest -q tests/integration/test_portfolio_events.py && uv run mypy src && uv run ruff check .`
  Expected: PASS.

- [ ] **Step 5: Commit**: `fix(#83): persist_events skips events already logged for the day`

### Task 2: `run_portfolio` renders the day's logged events; docs follow

**Files:**
- Modify: `src/bot/portfolio/command.py` (step 4/5 of `run_portfolio`, the module docstring's step 4 to say the events are persisted idempotently and `alerts.md` lists the day's logged events, `PortfolioRunResult.events` semantics, the log line)
- Modify: `docs/pipeline/portfolio.d2`: the `reruns` note under `events.persist` and the `persist` label ("append the events not yet logged for the day …"); `docs/pipeline/portfolio-alerts.d2`: the `logged` state's second line ("a same-day re-run logs only events not logged yet"), and the second line of the `filings_checked -> logged` edge; `docs/pipeline/portfolio-events.d2`: the second line of the `filings_checked -> logged` edge. Keep every first line (model state and step labels) unchanged, because `tests/unit/test_pipeline_models.py` matches them. Keep "a same-day re-run sends the same alerts again" (notifier, out of scope). Then run `docs/pipeline/build.sh` and `python3 docs/pipeline/check.py`.
- Modify: `docs/plano/estado.py`: in the `ev-cruce` entry, drop "Ver también #83 (repetir la corrida el mismo día duplica eventos) y" and keep the #84 reference. Do not change `AUDITADO_EN`.
- Test: `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `persist_events`, `load_events` (Task 1); `render_alerts(events, snapshot_date, *, generated_on)` unchanged.
- Produces: `run_portfolio` unchanged in signature. `PortfolioRunResult.events` is now `len(load_events(conn, snapshot_date))`.

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_portfolio_command.py` (reuse `_client`, `_valued_at`, `_ToggleGate`, `_no_analyze`; add a helper `_count(conn, day) -> int`, a `SELECT COUNT(*)` on `events_log` for `curr_snapshot_date = day`, and `_insert_filing(conn, ticker, filing_type, filing_date, fetched_at)` inserting into `filings_log` with `source='sec'`)

  - `test_same_day_rerun_is_idempotent`: run day1 (`_client(day1)`, `_valued_at(90.0)`, gate passing), then day2 with `_client(day2, actions=[a dividend for MSFT effective day2])`, `_valued_at(120.0)` and `gate.fail = True`, plus a filing for AAPL ingested on day2. Record `_count(conn, day2)` and the bytes of `reports/<day2>/alerts.md`. Run day2 again with identical arguments. Assert the count is unchanged and greater than 0, the `alerts.md` bytes are identical, the second result's `events` equals the first's, and the `event_type`s logged for day2 include `intrinsic_value_crossed_price`, `below_quality_gate`, `dividend`, `new_filing` and `concentration`.
  - `test_rerun_keeps_new_filing_in_alerts`: day1 run; filing for AAPL ingested on day2; run day2 twice. Assert `"new_filing"` is in the second `alerts.md`, and that `new_filing` rows for day2 number 1.
  - `test_rerun_logs_and_alerts_a_filing_that_arrived_between_runs`: day1 run, day2 run, then insert a filing for MSFT ingested on day2, then run day2 again. Assert there is exactly one `new_filing` MSFT row for day2, the second `alerts.md` contains both `| new_filing | MSFT |` and the first run's rows, and `_count` grew by exactly 1.
  - `test_rerun_leaves_other_days_untouched`: run day1, then day2 twice. Assert `_count(conn, day1)` is unchanged by the day2 runs and `reports/<day1>/alerts.md` is unchanged.

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `uv run pytest -q tests/integration/test_portfolio_command.py`
  Expected: `test_rerun_keeps_new_filing_in_alerts` fails (the second `alerts.md` lacks `new_filing`), and the byte comparison in `test_same_day_rerun_is_idempotent` fails.

- [ ] **Step 3: Implement** in `run_portfolio`: `logged = persist_events(conn, events)`, then `day_events = load_events(conn, snapshot_date)`. Render `alerts.md` from `day_events`, set `PortfolioRunResult.events=len(day_events)`, and log `events=len(day_events), events_logged=logged`. Update the docstrings and the docs listed above.

- [ ] **Step 4: Run the full checks**

  Run: `uv run pytest -q && uv run ruff check . && uv run mypy src && python3 docs/pipeline/check.py`
  Expected: all PASS (this includes `tests/unit/test_cli_portfolio.py` and `tests/unit/test_pipeline_*.py`).

- [ ] **Step 5: Commit**: `fix(#83): same-day rerun of bot portfolio is idempotent`

## Grilling

- Rounds: 1 (the revision added tests and assumptions on the same seam, so no second round).
- Questions: 18. Sources: CODE 12 (Q1, Q3, Q4, Q5, Q6, Q9, Q10, Q13, Q14, Q15, Q16, Q17), ISSUE 3 (Q2, Q8, Q12), DOC 1 (Q18), NO SOURCE → technical assumption 2 (Q7, Q11). No spec ambiguity.
- Assumptions added: `load_events` collapses identical rows; no unique index or explicit transaction (the DuckDB file lock serialises processes); an unknown `event_type` raises.
- Issues opened: none. Notifier re-sends and pre-existing duplicate rows are already out of scope in the issue's Agent Brief.
