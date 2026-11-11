# Invalid BOT_* settings exit cleanly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a `BOT_*` variable is invalid, every `bot` command that loads settings prints one stderr line per bad variable, naming it and what it accepts, and exits 2 with no traceback. `bot doctor` behaves the same way.

**Architecture:** A pure formatter, `settings_error_lines(exc: ValidationError) -> list[str]` in `bot.config`, turns pydantic's `errors()` into lines of the form `Invalid setting BOT_NOTIFIER: Input should be 'email', 'telegram' or 'none'`. A single CLI helper, `_load_settings() -> Settings` in `bot.cli`, wraps `load_settings()`: on `ValidationError` it echoes those lines to stderr and raises `typer.Exit(code=2)`. All five call sites (`_open_db`, `portfolio`, `notify`, `flex_capture`, `doctor`) call the helper instead of `load_settings()`. Nothing else changes in `Settings`.

**Tech Stack:** Python 3.12, pydantic v2 + pydantic-settings, Typer (`CliRunner`), pytest, mypy --strict, ruff.

**Spec:** GitHub issue #89 (nicolas-ricc/damodaran), "CLI: invalid BOT_* settings crash with a pydantic traceback", with the Agent Brief in its triage comment.

## Global Constraints

- Config error exit code: `2`, the CLI's existing code for usage/config errors (brief: "follow the CLI's existing code for usage/config errors, 2"). Not `1`.
- One stderr line per offending variable, naming it with its `BOT_` prefix (or the field's alias, when one is declared). For `Literal` fields the line lists the allowed values. No traceback.
- Handled in one place, not per command.
- `bot doctor` prints the same lines and exits with the same code.
- Out of scope: changing validation rules or adding settings; re-mapping other CLI exit codes; `ValidationError` from the screener config loader.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits are Conventional Commits scoped `(#89)`.

## Assumptions

- **Message text.** The line is `Invalid setting <VAR>: <pydantic msg>`. For a `literal_error`, pydantic's `msg` is already `Input should be 'email', 'telegram' or 'none'`, so it lists the allowed values. For a type error it is, for example, `Input should be a valid integer, unable to parse string as an integer`. The variable's value is not echoed: some `BOT_*` variables hold secrets, and pydantic's `msg` for these types does not include the input. The one exception is the `ibkr_flex_tz` validator's own message, which quotes the time zone name, which is not a secret.
- **Variable name.** pydantic puts the field name in `loc[0]`, or the alias when the field declares one. This was observed with pydantic 2.13.4 / pydantic-settings 2.14.1: an `alias="MY_NOTIFIER"` field reports `loc=('MY_NOTIFIER',)` and is read from `MY_NOTIFIER`, without the prefix. So the rule is: when `loc[0]` is a key of `Settings.model_fields`, the name is `Settings.model_config["env_prefix"] + name.upper()`; otherwise it is an alias, and the name is `str(loc[0]).upper()`. No field declares an alias today; this is the "honoring aliases" clause of the brief. Rejected: looking up `field.alias`, which is unreachable, because `loc` already carries it.
- **Missing required setting.** A missing `BOT_SEC_USER_AGENT` is also a `ValidationError` (`type="missing"`), so it gets the same treatment: `Invalid setting BOT_SEC_USER_AGENT: Field required`, exit 2. This is the same error class and the same call site, so it cannot be excluded without per-type special-casing.
- **`doctor` drops its `except Exception`.** Its only other exception sources would be an unreadable `.env` (an `OSError`, which is already a traceback for every other command) and a pydantic-settings `SettingsError` (raised only for complex JSON fields; `Settings` has none, see `src/bot/config.py:22-136`). Rejected: keeping the broad catch in `doctor` alone, which would give doctor a second, different error path. Today it catches every exception and prints `FAIL: Settings invalid — <raw pydantic text>`, exit 1. It now goes through `_load_settings()`, which catches `ValidationError` only. `Settings()` raises nothing else for the current field types. The existing test `test_doctor_flex_token_expiry_garbage_is_settings_invalid` changes to expect exit 2 and `Invalid setting BOT_IBKR_FLEX_TOKEN_EXPIRES:`.
- **Downstream callers of doctor's exit code.** `scripts/bootstrap.sh` propagates `bot doctor`'s status unchanged, so an invalid setting makes bootstrap exit 2 instead of 1. `scripts/daily.sh` only checks for non-zero. Neither needs a code change.
- **Empty `errors()`.** pydantic never raises a `ValidationError` without entries during model validation, so there is no special case: the helper prints nothing extra and still exits 2.
- **Test isolation.** The new test modules delete every `BOT_*` variable from the environment first, the same pattern as `tests/unit/test_cli_site.py:17-19`, and then `chdir(tmp_path)`. `env_file=".env"` is resolved against the CWD. The autouse conftest fixtures that set `BOT_FMP_API_KEY` and `BOT_CURRENCIES_PATH` run before this and are harmless.
- **The README sentence** sits in the troubleshooting/exit-code prose next to `bot doctor`, matching how README.md:295-310 already documents exit codes per command. No rule requires it; it is the existing pattern.
- **`bot site` and `bot version`** do not load settings and stay untouched (`tests/unit/test_cli_site.py` already pins `site`).

## Review Focus

1. **Several bad variables at once.** Each one gets its own line, in pydantic's error order, and the exit code is still 2. Pinned in Task 1 by `test_settings_error_lines_one_per_error` and in Task 2 by `test_invalid_settings_list_every_bad_variable`.
2. **A command reached through `_open_db` versus one that calls the loader directly** (`portfolio`, `notify`). All of them must take the same path. Pinned in Task 2 by the parametrised `test_invalid_notifier_exits_2_without_traceback` over every command that loads settings.
3. **`bot notify` with a bad `BOT_NOTIFIER`.** `scripts/daily.sh` uses it to report failures. It must exit 2 cleanly, not crash. Covered by item 2's parametrisation.
4. **A field validator's `ValueError`** (`BOT_IBKR_FLEX_TZ=Mars/Nowhere`). The `Value error, ...` message is kept and the variable is named. Pinned in Task 1 by `test_settings_error_lines_value_error`.
5. **Repo `.env` leaking into tests.** `env_file=".env"` is relative to the CWD. CLI tests `monkeypatch.chdir(tmp_path)`, so only the variables they set count.

---

### Task 1: `settings_error_lines` formats a settings `ValidationError`

**Files:**
- Modify: `src/bot/config.py` (new function after `load_settings`)
- Test: new `tests/unit/test_config_errors.py` (a separate module, so its import of the new name cannot break `tests/unit/test_config.py` during red)

**Interfaces:**
- Produces: `settings_error_lines(exc: pydantic.ValidationError) -> list[str]`: one `Invalid setting <VAR>: <msg>` per `exc.errors()` entry, in order.

- [ ] **Step 1: Write the failing tests.** Build the error with `pytest.raises(ValidationError)` around `load_settings()`, after `monkeypatch.chdir(tmp_path)` and setting `BOT_SEC_USER_AGENT` unless the test says otherwise.
  - `test_settings_error_lines_literal`: `BOT_NOTIFIER=slack` gives `["Invalid setting BOT_NOTIFIER: Input should be 'email', 'telegram' or 'none'"]`.
  - `test_settings_error_lines_type`: `BOT_SMTP_PORT=abc` gives one line that starts with `Invalid setting BOT_SMTP_PORT: ` and contains `valid integer`.
  - `test_settings_error_lines_value_error`: `BOT_IBKR_FLEX_TZ=Mars/Nowhere` gives one line that starts with `Invalid setting BOT_IBKR_FLEX_TZ: ` and contains `unknown time zone`.
  - `test_settings_error_lines_missing_required`: with `BOT_SEC_USER_AGENT` deleted, the result is `["Invalid setting BOT_SEC_USER_AGENT: Field required"]`.
  - `test_settings_error_lines_one_per_error`: `BOT_NOTIFIER=slack`, `BOT_SMTP_PORT=abc` and `BOT_DATA_PROVIDER=foo` give 3 lines whose variable names, as a set, are `{BOT_DATA_PROVIDER, BOT_NOTIFIER, BOT_SMTP_PORT}`. The order is not asserted. The `BOT_DATA_PROVIDER` line contains `'edgar-tiingo', 'edgar-stooq' or 'fmp'`.
  - `test_settings_error_lines_honours_alias`: a throwaway `class _Aliased(Settings)` with `notifier: Literal["none"] = Field(default="none", alias="MY_NOTIFIER")`; `MY_NOTIFIER=slack` gives one line that starts with `Invalid setting MY_NOTIFIER: `.
  - `test_settings_error_lines_do_not_echo_value`: `BOT_SMTP_PORT=s3cr3t-port` gives a line without `s3cr3t-port`.

- [ ] **Step 2:** `uv run pytest tests/unit/test_config_errors.py -q`. Expected: the new tests fail with an ImportError on `settings_error_lines`.

- [ ] **Step 3: Implement `settings_error_lines(exc: ValidationError) -> list[str]` in `src/bot/config.py`.** Resolve each `loc[0]` against `Settings.model_fields` to get the alias or `BOT_` + upper name, as described under Assumptions. Use `error["msg"]` as is.

- [ ] **Step 4:** The tests from step 2 pass. `uv run mypy src` and `uv run ruff check .` are clean.

- [ ] **Step 5: Commit** `fix(#89): format settings validation errors per variable`.

### Task 2: One CLI helper turns invalid settings into exit 2

**Files:**
- Modify: `src/bot/cli.py` (new `_load_settings` next to `_open_db`; the call sites at `_open_db`, `portfolio`, `notify`, `flex_capture` and `doctor`; the import from `bot.config`)
- Modify: `README.md` (one sentence next to the setup steps saying that an invalid `BOT_*` value prints `Invalid setting BOT_X: ...` and exits 2)
- Test: new `tests/unit/test_cli_invalid_settings.py`; modify `tests/unit/test_cli_doctor.py::test_doctor_flex_token_expiry_garbage_is_settings_invalid`

**Interfaces:**
- Consumes: `settings_error_lines` (Task 1), `load_settings`.
- Produces: `_load_settings() -> Settings` in `bot.cli`. It is the only function in `bot.cli` that calls `load_settings()`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_cli_invalid_settings.py`. A fixture `monkeypatch.chdir(tmp_path)` sets `BOT_SEC_USER_AGENT`, `BOT_DB_PATH=tmp_path/x.duckdb` and `BOT_REPORTS_DIR=tmp_path/reports`. Invoke with `CliRunner()` (click 8.4.1 is locked: `result.stderr` is stderr alone, and `result.output` interleaves both streams).
  - `test_invalid_notifier_exits_2_without_traceback`, parametrised over the argv lists `["status"]`, `["doctor"]`, `["notify"]` (with `input="hi"`), `["portfolio"]`, `["refresh", "--damodaran"]`, `["show", "AAPL"]`, `["analyze", "AAPL"]`, `["screen"]` and `["flex-capture"]`, with `BOT_NOTIFIER=slack`. Assertions: `result.exit_code == 2`, `not isinstance(result.exception, ValidationError)`, `"Traceback" not in result.output + result.stderr`, `"BOT_NOTIFIER" in result.stderr`, and `"'email', 'telegram' or 'none'" in result.stderr`.
  - `test_invalid_smtp_port_names_variable`: `["status"]` with `BOT_SMTP_PORT=abc` exits 2, and stderr has exactly one non-empty line, which starts with `Invalid setting BOT_SMTP_PORT:`.
  - `test_invalid_data_provider_names_variable`: the same for `BOT_DATA_PROVIDER=foo`. The line contains `'edgar-tiingo', 'edgar-stooq' or 'fmp'`.
  - `test_invalid_settings_list_every_bad_variable`: `["status"]` with all three bad variables gives exit 2 and 3 stderr lines.
  - `test_doctor_matches_other_commands`: with `BOT_NOTIFIER=slack`, `["doctor"]` and `["status"]` give the same `exit_code` and the same `stderr`.
  - `test_only_helper_calls_load_settings`: `inspect.getsource(bot.cli)` contains `load_settings()` exactly once. This pins the "one place" criterion.
  - Update `test_doctor_flex_token_expiry_garbage_is_settings_invalid`: `exit_code == 2` and `"Invalid setting BOT_IBKR_FLEX_TOKEN_EXPIRES:" in result.stderr`.

- [ ] **Step 2:** `uv run pytest tests/unit/test_cli_invalid_settings.py tests/unit/test_cli_doctor.py -q`. Expected: failures. Under `CliRunner`, an uncaught `ValidationError` gives `exit_code == 1` with `result.exception` set; `load_settings()` is counted 5 times.

- [ ] **Step 3: Implement `_load_settings() -> Settings` in `src/bot/cli.py`.** It catches only `ValidationError`, echoes each line from `settings_error_lines` with `err=True`, and raises `typer.Exit(code=2) from None`. Replace the 5 `load_settings()` calls with `_load_settings()`. In `doctor`, remove the `try/except Exception` block around it. Add the README sentence.

- [ ] **Step 4:** The tests from step 2 pass. Then the full `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass.

- [ ] **Step 5: Commit** `fix(#89): invalid BOT_* settings exit 2 with one line per variable`.

## Grilling

- Rounds: 1 (griller model: fable). Questions: 19.
- Sources: CODE 15 (`src/bot/cli.py`, `src/bot/config.py`, `scripts/bootstrap.sh:12,142,155`, `scripts/daily.sh:104-117`, `tests/unit/test_cli_doctor.py:330-337`, `tests/unit/test_cli_site.py:17-25`, `uv.lock`, plus pydantic behaviour observed at runtime); ISSUE 2 (triage brief, Desired behavior: "Any command with an invalid setting", and exit code 2); DOC 1 (README.md:295-310); NO SOURCE 4, all technical assumptions (missing required setting, `doctor`'s broad catch, empty `errors()`, README placement).
- The plan changed in four places: the alias resolution (`loc[0]` already holds the alias); the multi-error test asserts a set, not an order; a new test checks the value is not echoed; and the test isolation now deletes host `BOT_*` variables.
- Spec ambiguities: none. Follow-up issues opened: none.
