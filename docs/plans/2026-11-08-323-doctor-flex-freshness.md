# bot doctor reports the Flex settings and the portfolio snapshot age — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (`.agents/skills/subagent-driven-development/SKILL.md`) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot doctor` prints `BOT_IBKR_FLEX_TOKEN` and `BOT_IBKR_FLEX_QUERY_ID` as `set`/`MISSING` (never their values) and, when both are set, FAILs when the latest `portfolio_snapshots.snapshot_date` is more than 2 business days old or the table is empty.

**Architecture:** A new pure module `src/bot/portfolio/freshness.py` holds the business-day arithmetic and the `MAX(snapshot_date)` query. `doctor()` in `src/bot/cli.py` gains a Flex block after the data-provider block and a freshness check inside its existing DB `try`, reusing the open `conn` and the existing `issues` list. README gets one paragraph.

**Tech Stack:** Python 3, typer (`CliRunner`), DuckDB, pydantic-settings, pytest, mypy strict, ruff.

**Spec:** GitHub issue #323 (`gh api repos/nicolas-ricc/damodaran/issues/323`). Parent story #118; its planner comment holds the shared design (decisions 3, 4, 6). The issue's "Design decisions (inherited, do not reopen)" section is binding, and every output string below is exact copy from it.

## Global Constraints

- `MAX_SNAPSHOT_AGE_BUSINESS_DAYS: int = 2` in `src/bot/portfolio/freshness.py`.
- `business_days_between(start: date, end: date) -> int`: count of Monday–Friday dates `d` with `start < d <= end`; 0 when `end <= start`.
- `latest_snapshot_date(conn: duckdb.DuckDBPyConnection) -> date | None`: `SELECT MAX(snapshot_date) FROM portfolio_snapshots`.
- Doctor labels are padded to an 18-char column: `Flex token:       `, `Flex query id:    `, `Portfolio sync:   `, `Latest snapshot:  `.
- Setting values are never printed. A setting is "set" when `.strip()` is non-empty (same test as the FMP key).
- No `--today` option. `today = date.today()` inside `doctor()`.
- Do not reuse `_last_weekday_before` from `src/bot/ingest/universe.py`.
- Every existing test in `tests/unit/test_cli_doctor.py` and `tests/integration/test_scripts.py` stays unchanged and green.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- `Latest snapshot:  YYYY-MM-DD (N business day(s) old, OK)` is printed with the literal text `day(s)`, as the issue writes it.
- The `Portfolio sync:   not configured (...)` line is printed right after the two Flex lines, still before the DB block. The `Latest snapshot:` line is printed inside the DB `try`, after `DB tables:`.
- The test helper `_business_days_ago(n)` walks back one calendar day at a time from today and counts each Monday–Friday date it leaves behind, stopping after `n`. So `business_days_between(_business_days_ago(n), date.today()) == n` on every day of the week, weekends included. (A naive "n-th previous weekday" gives n-1 on a Saturday or Sunday, and this plan is written on a Sunday.)
- `_business_days_ago(n)` exact loop: `d = date.today(); left = n; while left > 0: if d.weekday() < 5: left -= 1; d -= timedelta(days=1)` — the counted date is the one being departed. On a Saturday with n=3 it returns Tuesday (age 3). (Grilling Q9.)
- A test run straddling midnight between the helper's and `doctor()`'s `date.today()` can see an age one higher. Accepted: the issue forbids `--today` and pins "today" to `date.today()`; the 2-day OK test has one day of margin only on the stale side, and the window is milliseconds. Rejected alternative: monkeypatching `bot.cli.date`, which the issue does not ask for and which would also patch every other `date` use in `cli.py`. (Grilling Q10.)
- Market holidays are not business days in the issue's definition ("number of Monday–Friday dates"), so a holiday can make doctor FAIL one day early. That is the issue's fixed design, not reopened here. (Grilling Q6.)
- If `latest_snapshot_date` raises, the existing `except Exception as e: issues.append(f"DB error — {e}")` reports it and the connection is not closed, exactly like a failing table count today (`src/bot/cli.py:743-759`). Not changed. (Grilling Q7.)
- Tests with Flex unset `chdir` into `tmp_path` and `delenv` both Flex variables, so a developer's `.env` or shell cannot leak a token in.

## Review Focus

1. The token value leaking into any output, including a FAIL message or an exception text. Pinned by asserting `secret-token-value` absent from stdout and stderr in every Flex-set doctor test (Task 2).
2. A whitespace-only token (`"   "`) must count as MISSING, not set, so doctor does not FAIL a user who has not configured Flex. Pinned by `test_doctor_blank_flex_token_is_not_configured` (Task 2).
3. Running doctor on a Saturday or Sunday: a Friday snapshot must be 0–2 business days old, never FAIL. Pinned by the weekend pairs in the `business_days_between` table (Task 1) and by the weekend-safe test helper (Task 2).
4. Only one of the two settings set (token without query id): not configured, exit 0, no freshness check even on an empty table. Pinned by `test_doctor_flex_half_configured_is_not_configured` (Task 2).
5. A snapshot dated after today (clock skew): age 0, OK, not an error. Pinned by the `(Tue, Mon) → 0` row in Task 1's table.

---

### Task 1: `freshness.py` — business-day age and latest snapshot date

**Files:**
- Create: `src/bot/portfolio/freshness.py`
- Test: `tests/unit/test_portfolio_freshness.py`

**Interfaces:**
- Consumes: `apply_schema(conn)` from `bot.storage.db`; tests open `duckdb.connect(":memory:")` as `tests/unit/test_portfolio_marks.py` does.
- Produces: `MAX_SNAPSHOT_AGE_BUSINESS_DAYS: int`, `business_days_between(start: date, end: date) -> int`, `latest_snapshot_date(conn: duckdb.DuckDBPyConnection) -> date | None`.

- [ ] **Step 1: Write the failing tests**

`test_business_days_between` parametrised over (2026-11-06 is a Friday):

| start | end | expected |
|---|---|---|
| Fri 2026-11-06 | Mon 2026-11-09 | 1 |
| Fri 2026-11-06 | Tue 2026-11-10 | 2 |
| Fri 2026-11-06 | Wed 2026-11-11 | 3 |
| Sat 2026-11-07 | Sun 2026-11-08 | 0 |
| Wed 2026-11-11 | Wed 2026-11-11 | 0 |
| Fri 2026-11-06 | Mon 2026-11-16 (two weekends) | 6 |
| Tue 2026-11-10 | Mon 2026-11-09 (end before start) | 0 |
| Fri 2026-11-06 | Sun 2026-11-08 | 0 |

`test_max_snapshot_age_is_two`: `MAX_SNAPSHOT_AGE_BUSINESS_DAYS == 2`.

`test_latest_snapshot_date_empty_table_is_none`: in-memory DB with schema → `None`.

`test_latest_snapshot_date_returns_the_newest`: insert rows dated 2026-11-04 and 2026-11-06 (two tickers on the 6th) with the column list from `tests/unit/test_portfolio_marks.py::_hold` → `date(2026, 11, 6)`, and `isinstance(result, date)`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/unit/test_portfolio_freshness.py`
Expected: collection error, `ModuleNotFoundError: No module named 'bot.portfolio.freshness'`.

- [ ] **Step 3: Implement the module**

Module docstring names the purpose (doctor's portfolio-sync freshness check, #118). `business_days_between` returns 0 when `end <= start`, otherwise counts weekdays in `(start, end]` (a day loop is fine; spans are a few days). `latest_snapshot_date` returns the scalar of `MAX(snapshot_date)`, `None` when the row or value is `None`. Fully typed for mypy strict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_portfolio_freshness.py && uv run mypy src && uv run ruff check .`
Expected: all pass.

- [ ] **Step 5: Commit**

`git commit -m "feat(#323): freshness module counts business days and reads the latest snapshot"`

### Task 2: doctor's Flex block and snapshot freshness check, README

**Files:**
- Modify: `src/bot/cli.py` (`doctor()`, ~line 700–775)
- Modify: `README.md` (`### Portfolio sync via Flex Web Service`, after step 3's env block and its existing paragraph)
- Test: `tests/unit/test_cli_doctor.py` (append only)

**Interfaces:**
- Consumes: `MAX_SNAPSHOT_AGE_BUSINESS_DAYS`, `business_days_between`, `latest_snapshot_date` from `bot.portfolio.freshness` (Task 1).
- Produces: nothing new for other tasks.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_doctor.py`)

Helpers in the test file:
- `_business_days_ago(n: int) -> date` as described in Assumptions.
- `_flex_env(tmp_path, monkeypatch)` sets `BOT_DB_PATH`, `BOT_SEC_USER_AGENT`, `BOT_REPORTS_DIR` like the existing tests, `BOT_IBKR_FLEX_TOKEN=secret-token-value`, `BOT_IBKR_FLEX_QUERY_ID=123456`.
- `_seed_snapshot(db_path, day)` opens the DB with `connect` + `apply_schema`, inserts one `portfolio_snapshots` row dated `day`, closes.
- `_assert_no_secret(result)`: `secret-token-value` not in `result.stdout` nor `result.stderr`.

Tests (each Flex-set test calls `_assert_no_secret`):
- `test_doctor_flex_snapshot_today_is_ok`: snapshot `_business_days_ago(0)` → exit 0; `Flex token:       set` and `Flex query id:    set` in stdout; `Latest snapshot:  <iso> (0 business day(s) old, OK)` in stdout.
- `test_doctor_flex_snapshot_two_business_days_old_is_ok`: `_business_days_ago(2)` → exit 0, `Latest snapshot:` line with `2 business day(s) old, OK`.
- `test_doctor_flex_snapshot_three_business_days_old_fails`: `_business_days_ago(3)` → exit 1; stderr has `FAIL:`, the snapshot iso date and `business days`.
- `test_doctor_flex_set_with_empty_snapshots_fails`: no seed → exit 1; stderr has `FAIL:` and `portfolio_snapshots is empty`.
- `test_doctor_flex_unset_is_not_configured`: `chdir(tmp_path)`, `delenv` both Flex vars, fresh DB → exit 0; stdout has `Flex token:       MISSING`, `Flex query id:    MISSING`, `not configured`; no `Latest snapshot:`.
- `test_doctor_blank_flex_token_is_not_configured`: token `"   "`, query id set, empty DB → exit 0, `Flex token:       MISSING`, `not configured`.
- `test_doctor_flex_half_configured_is_not_configured`: token `secret-token-value`, query id unset (delenv + chdir), empty DB → exit 0, `not configured`, `_assert_no_secret`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/unit/test_cli_doctor.py`
Expected: the new tests fail (no `Flex token:` line / exit 0 on stale snapshot); the existing eight pass.

- [ ] **Step 3: Implement in `doctor()`**

After the data-provider `if/elif` block, before the DB `try`:
- `flex_configured = bool(settings.ibkr_flex_token.strip()) and bool(settings.ibkr_flex_query_id.strip())`.
- Print `Flex token:       set|MISSING` and `Flex query id:    set|MISSING`.
- When not configured: print `Portfolio sync:   not configured (needs BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID)`.

Inside the DB `try`, after the table-count check and before `conn.close()`, only when `flex_configured`:
- `latest = latest_snapshot_date(conn)`; `today = date.today()`.
- `None` → issue `Flex is configured but portfolio_snapshots is empty — run bot portfolio, or check .cache/daily.log`.
- `age = business_days_between(latest, today)`; `age <= MAX_SNAPSHOT_AGE_BUSINESS_DAYS` → print `Latest snapshot:  {latest.isoformat()} ({age} business day(s) old, OK)`.
- else → issue `Latest portfolio snapshot {latest.isoformat()} is {age} business days old (limit {MAX_SNAPSHOT_AGE_BUSINESS_DAYS}) — the daily sync has stopped; check .cache/daily.log and the Flex token`.

`date` is already imported in `cli.py`.

- [ ] **Step 4: README paragraph**

In `### Portfolio sync via Flex Web Service`, after step 3's env block and its `BOT_IBKR_FLEX_TZ` paragraph (still inside step 3's indentation), one short paragraph: `bot doctor` reports both settings as set or MISSING and fails when the latest snapshot is more than 2 business days old; IBKR's T+1 statement lag leaves one day of slack.

- [ ] **Step 5: Run the issue's test commands**

Run: `uv run pytest -q tests/unit/test_cli_doctor.py tests/unit/test_portfolio_freshness.py tests/integration/test_scripts.py && uv run ruff check . && uv run mypy src`
Expected: all pass.

- [ ] **Step 6: Commit**

`git commit -m "feat(#323): bot doctor reports the Flex settings and fails on a stale portfolio snapshot"`

## Grilling

- Rounds: 1 (the revision added assumptions only; no step added or removed, same seam, so no second round).
- Questions: 15. Sources: ISSUE 7 (Q4 partly, Q5, Q6, Q11 partly, Q13, Q14, Q10 partly), CODE 10 (Q1, Q2, Q3, Q4, Q7, Q8, Q11, Q12, Q15 partly, Q9), DOC 1 (Q15: AGENTS.md). Several answers cite more than one source.
- NO SOURCE → technical assumption: Q9 (exact helper loop), Q10 (midnight race accepted), Q7 (DB-error path left as is). Recorded under Assumptions.
- Spec ambiguities: none. Out-of-scope issues opened: none.
