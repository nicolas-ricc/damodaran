# CLI commands close their DuckDB connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every CLI command that opens the DuckDB database (`refresh`, `show`, `analyze`, `screen`, `portfolio`, `status`, and `doctor`) closes that connection however it finishes: a normal return, an early `typer.Exit`, or an exception. Output and exit codes do not change.

**Architecture:** `_open_db` in `src/bot/cli.py` becomes a `contextlib.contextmanager` that yields `(conn, settings)` and closes `conn` in a `finally`. It keeps its name, because `docs/pipeline/models/portfolio.tla` and older plans cite `_open_db`. Each of the six commands wraps everything after the open in `with _open_db() as (conn, settings):`. This is a re-indent only, with no logic change. `doctor` opens its own connection through `connect` (it must not use `_open_db`, which reconfigures logging and could raise outside doctor's `try`), so it switches to `with closing(connect(settings.db_path)) as conn:`, matching the `closing` idiom the module already uses for providers.

**Tech Stack:** Python 3, Typer (`CliRunner` in tests), DuckDB, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #87 (nicolas-ricc/damodaran), "CLI commands leave their DuckDB connection open", with the triage comment's Agent Brief, which holds the acceptance criteria.

## Global Constraints

- Commands covered: `refresh`, `show`, `analyze`, `screen`, `portfolio`, `status`, and `doctor` (the brief says to keep `doctor` "consistent with the chosen approach").
- The connection is closed after a normal run, after an early `typer.Exit`, and when the command raises.
- No change to command output, options, or exit codes. Existing CLI tests stay green and unmodified.
- Out of scope: connection pooling, any change to `bot.storage.db.connect` / `apply_schema`, and connections opened outside `src/bot/cli.py`.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits use Conventional Commits scoped `(#87)`.

## Review Focus

1. **`apply_schema` raising inside `_open_db`** (for example a locked or corrupt file, or a migration error). The connection that was already opened must still be closed. Pinned in Task 1 by `test_open_db_closes_when_apply_schema_raises`.
2. **An exception from the command body that is not `typer.Exit`** (a provider error, a bug). The connection is closed and the exception still propagates unchanged (CliRunner's `result.exception` is the original). Pinned by the stage-3 `*_raises` tests in `tests/unit/test_cli_closes_db.py`.
3. **`doctor`'s DB probe failing halfway** (a query raises after `connect`). Today `conn.close()` is skipped. It must be closed, and doctor still reports `DB error — ...` and exits 1. Pinned in Task 2 by `test_doctor_closes_db_when_probe_raises`.
4. **`status` with no history**, which leaves through a bare `return` rather than `typer.Exit`. Pinned by the stage-3 `test_status_closes_db_on_early_return`.
5. **`portfolio` loads settings before opening the DB**, so a misconfiguration exits before `_open_db` and no connection is ever opened. That must stay true (`docs/pipeline/models/portfolio.tla:36`), and it is covered by the unchanged `test_cli_portfolio_flex.py`.

## Assumptions

- **Context manager over `with closing(conn)` at each call site.** Both re-indent each command body. The context manager also closes the connection when `apply_schema` raises (Review Focus 1), and it leaves exactly one place that owns the lifetime. Rejected: registering `conn.close` with `click.get_current_context().call_on_close`, which needs no re-indent but hides the lifetime from the reader and does nothing when a command is called outside Click.
- **Keep the name `_open_db`.** Renaming it would break doc citations and buy nothing.
- **The final `raise typer.Exit(code=exit_code)` in `refresh` and `analyze` stays inside the `with`.** The `finally` closes the connection before the exit propagates.

---

## Evals (stage 3, written before Task 1)

`tests/unit/test_cli_closes_db.py` has a fixture `opened` that monkeypatches `bot.cli.connect` with a wrapper. The wrapper calls the real `bot.storage.db.connect`, appends the returned connection to a list, and returns it. A helper `_assert_all_closed(conns)` asserts that the list is non-empty and that `conn.execute("SELECT 1")` raises `duckdb.ConnectionException` for each connection. Environment setup: `BOT_DB_PATH` (tmp), `BOT_REPORTS_DIR` (tmp), `BOT_SEC_USER_AGENT`, and `BOT_PRESETS_DIR` pointing at the repo's `config/presets`. Tests, each through `CliRunner().invoke(app, [...])`, assert the exit code or exception shown here and then `_assert_all_closed`:

| Test | Setup / patch | Expect |
|---|---|---|
| `test_refresh_closes_db` | `bot.cli._refresh_fx` → returns 0; `refresh --fx` | exit 0 |
| `test_refresh_closes_db_when_it_raises` | `_refresh_fx` raises `RuntimeError("boom")` | `isinstance(result.exception, RuntimeError)` |
| `test_show_closes_db` | company row `AAA` inserted beforehand; `show AAA --no-fetch` | exit 0 |
| `test_show_closes_db_on_early_exit` | `show ZZZZ --no-fetch` | exit 2 |
| `test_analyze_closes_db` | `bot.cli._analyze_one` → returns 0; `analyze AAA` | exit 0 |
| `test_analyze_closes_db_on_early_exit` | empty DB; `analyze --from-screen` | exit 2 |
| `test_analyze_closes_db_when_it_raises` | `_analyze_one` raises `RuntimeError` | RuntimeError |
| `test_screen_closes_db` | `bot.cli.run_screen` / `persist_candidates` stubbed if a real empty-DB screen is not cheap; `screen` | exit 0 |
| `test_screen_closes_db_on_early_exit` | `screen --config <tmp>/missing.yaml` | exit 2 |
| `test_portfolio_closes_db_on_flex_failure` | token `tok`, query id `123`; `bot.cli.FlexPortfolioClient.from_settings` stubbed; `bot.cli.run_portfolio` raises `FlexError("x")` | exit 1 |
| `test_portfolio_closes_db_when_it_raises` | same, `run_portfolio` raises `RuntimeError` | RuntimeError |
| `test_status_closes_db` | one `refresh_log` row inserted beforehand | exit 0 |
| `test_status_closes_db_on_early_return` | empty DB | exit 0 |

The DB is seeded beforehand with the real `connect`/`apply_schema`, and that connection is closed before the fixture patches `bot.cli.connect`, so only the command's connections are recorded. All of these tests fail on `master`.

---

### Task 1: `_open_db` as a context manager; the six commands use it

**Files:**
- Modify: `src/bot/cli.py` (`_open_db` at ~75, and `refresh` ~200, `show` ~342, `analyze` ~445, `screen` ~569, `portfolio` ~649, `status` ~870)
- Test: `tests/unit/test_cli_closes_db.py`

**Interfaces:**
- Produces: `_open_db() -> Iterator[tuple[duckdb.DuckDBPyConnection, Settings]]`, decorated with `@contextmanager` (imported from `contextlib`, as `closing` is; `Iterator` comes from `collections.abc`). It runs `load_settings`, `configure_logging`, then `connect`. Everything after `connect` (including `apply_schema` and the `yield`) sits in a `try` whose `finally` calls `conn.close()`.

- [ ] **Step 1: Write the failing tests**, added to `tests/unit/test_cli_closes_db.py`:
  - `test_open_db_closes_after_block`: `with bot.cli._open_db() as (conn, settings): conn.execute("SELECT 1")`; afterwards `conn` is closed and `settings.db_path` equals the env path.
  - `test_open_db_closes_when_body_raises`: `pytest.raises(RuntimeError)` around a `with` that raises; `conn` is closed.
  - `test_open_db_closes_when_apply_schema_raises`: monkeypatch `bot.cli.apply_schema` to raise `RuntimeError`; entering the `with` raises `RuntimeError`, and the one connection recorded by `opened` is closed.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_cli_closes_db.py -q`. Expected: FAIL (`_open_db()` returns a tuple, not a context manager), along with the stage-3 command tests.
- [ ] **Step 3: Implement** `_open_db` as above. In each of the six commands, replace `conn, settings = _open_db()` (or `conn, _ = ...`) with `with _open_db() as (conn, settings):` (or `(conn, _)`), and indent the rest of the body under it. In `show`, the nested `_load_company_row` helper moves inside too. Change nothing else.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_cli_closes_db.py tests/unit/test_cli*.py tests/integration/test_screen_cli.py -q`. Expected: all pass except `test_doctor_closes_db_when_probe_raises` (Task 2). Then run `uv run ruff check . && uv run mypy src`, which must be clean.
- [ ] **Step 5: Commit** `fix(#87): CLI commands close their DuckDB connection`.

### Task 2: `doctor` closes its connection on every path

**Files:**
- Modify: `src/bot/cli.py` (`doctor`, the `try` block at ~812–848)
- Test: `tests/unit/test_cli_closes_db.py`

**Interfaces:**
- Consumes: the `opened` fixture and `_assert_all_closed` from the test module.

- [ ] **Step 1: Write the failing test** `test_doctor_closes_db_when_probe_raises`: env as in the evals, with `BOT_REPORTS_DIR` writable; monkeypatch `bot.cli.schema_table_count` to raise `RuntimeError("probe")`; `doctor` exits 1, `"DB error" in result.output`, and `_assert_all_closed(opened)` holds.
- [ ] **Step 2: Run it.** Expected: FAIL (the connection is still open).
- [ ] **Step 3: Implement.** Inside doctor's existing `try`, replace `conn = connect(...)` … `conn.close()` with `with closing(connect(settings.db_path)) as conn:` around the same statements, and drop the explicit `close()`. The `except Exception` stays where it is.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check . && uv run mypy src`. Expected: everything passes.
- [ ] **Step 5: Commit** `fix(#87): doctor closes its DB connection on error`.
