# BOT_IBKR_FLEX_TOKEN_EXPIRES — doctor warns 14 days before the Flex token expires and fails after: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (`.agents/skills/subagent-driven-development/SKILL.md`) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new optional setting `BOT_IBKR_FLEX_TOKEN_EXPIRES` (ISO date). `bot doctor` reports it, prints a `WARN:` line when the date is 0–14 days away, and FAILs once it has passed.

**Architecture:** `Settings` gains `ibkr_flex_token_expires: date | None` with a blank-is-unset before-validator. `src/bot/portfolio/freshness.py` gains `TOKEN_EXPIRY_WARN_DAYS = 14`. `doctor()` in `src/bot/cli.py` prints one expiry line (or a `WARN:` line, or adds a FAIL issue) right after `Flex query id:`. `.env.example` and the README Flex section document the setting.

**Tech Stack:** Python 3, pydantic-settings, typer (`CliRunner`), pytest, mypy strict, ruff.

**Spec:** GitHub issue #324 (`gh issue view 324 --repo nicolas-ricc/damodaran`). Parent story #118; its planner comment holds the shared design (decisions 5 and 6). The issue's "Design decisions (inherited, do not reopen)" section is binding, and every output string below is exact copy from it.

## Global Constraints

- Field: `ibkr_flex_token_expires: date | None = Field(default=None, description=...)`, env `BOT_IBKR_FLEX_TOKEN_EXPIRES`.
- Blank or whitespace-only value → `None` (a `mode="before"` validator, same pattern as `_blank_path_is_unset`). Any other non-ISO-date value → pydantic `ValidationError`.
- `TOKEN_EXPIRY_WARN_DAYS: int = 14` in `src/bot/portfolio/freshness.py`.
- `days_left = (expires - date.today()).days`, computed in `doctor()`. No `--today` option.
- The expiry output comes right after the `Flex query id:` line, whether or not the token or query id are set.
- Exact copy (`YYYY-MM-DD` = `expires.isoformat()`, `N` = `days_left`):
  - unset → stdout `Flex token expiry: not set (BOT_IBKR_FLEX_TOKEN_EXPIRES)`
  - `days_left < 0` → issue `Flex token expired on YYYY-MM-DD (BOT_IBKR_FLEX_TOKEN_EXPIRES) — generate a new one in Client Portal → Settings → Reporting → Flex Web Service and update .env` (printed as `FAIL: ...` on stderr by the existing loop, exit 1)
  - `0 <= days_left <= 14` → stdout `WARN: Flex token expires in N day(s) (YYYY-MM-DD) — renew it in Client Portal → Settings → Reporting → Flex Web Service`; exit code unaffected
  - `days_left > 14` → stdout `Flex token expiry: YYYY-MM-DD (N days left)`
- `WARN:` lines go to stdout and never change the exit code. Nothing is written to `alerts.md` or sent to the notifier.
- `.env.example` line, verbatim: `# BOT_IBKR_FLEX_TOKEN_EXPIRES=""   # optional ISO date; bot doctor warns 14 days before, fails after`. It must not contain `BOT_IBKR_FLEX_QUERY_ID` (`tests/unit/test_flex_docs.py::test_env_example_points_at_flex_capture`).
- All existing tests pass unchanged. `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- The label `Flex token expiry:` is exactly 18 characters, so it fills the 18-char column and is followed by one space, as the issue's copy shows.
- The validator strips nothing from non-blank values: `" 2027-03-01 "` goes to pydantic as is, and pydantic rejects it (`date_from_datetime_parsing`). The issue asks only that blank and whitespace map to `None`. Pydantic's lax date parsing decides the rest, which is the existing behaviour for every typed setting. Checked against the installed pydantic: `2027-03-01T00:00:00` is accepted as 2027-03-01, while `20270301`, `2027-03-01T10:00:00` and `next-year` are rejected. Rejected alternative: stripping first, which the issue does not ask for. (Grilling Q15.)
- The field description hard-codes "14 days" while the number lives in `TOKEN_EXPIRY_WARN_DAYS`. `bot.config` does not import from `bot.portfolio`, and adding that dependency for a help string isn't worth it. No test ties the two together. (Grilling Q16.)
- Both tasks land in one PR, squash-merged: the pipeline opens one PR per issue. Task 1 alone would document a doctor behaviour that does not exist yet, so it never ships alone. (Grilling Q17.)
- `days_left == 0` is a WARN, as the issue's `0 <= days_left <= 14` fixes. Whether IBKR invalidates the token at the start or the end of that date is not stated anywhere, and the issue's design is not reopened. (Grilling Q3.)
- `N day(s)` is printed literally with `day(s)`, as in the issue. `N days left` appears only when N > 14, so it is always plural.
- If settings fail to load, doctor exits before any Flex line through its existing `FAIL: Settings invalid — ...` path. No new code handles a bad date.
- The doctor tests `chdir` into `tmp_path` and `delenv` `BOT_IBKR_FLEX_TOKEN` and `BOT_IBKR_FLEX_QUERY_ID`, so neither a developer's `.env` nor their shell can leak a token in. That also keeps the empty-snapshot FAIL from #323 out of the exit code.
- A test run that straddles midnight between the test's `date.today()` and doctor's could be off by one day. The same window was accepted in #323, and the issue forbids `--today`.

## Review Focus

1. The boundaries: `days_left == 14` must WARN (not the info line) and `days_left == 15` must print `15 days left`. `days_left == 0` (expires today) must WARN, not FAIL. Pinned by the today+14, today+15 and today+0 doctor tests (Task 2).
2. The expiry line must appear when Flex is not configured at all. Every Task 2 test runs without `BOT_IBKR_FLEX_TOKEN`.
3. A WARN must not turn a passing doctor into exit 1, and it must stay on stdout: the today+14 and today+0 tests assert exit 0, assert the `WARN:` line is in `result.stdout`, and assert `All checks OK.` is still printed.
4. `BOT_IBKR_FLEX_TOKEN_EXPIRES="   "` (whitespace) must be unset, not a validation error. Pinned in Task 1 and, end to end, by `test_doctor_flex_token_expiry_blank_is_not_set` (Task 2).
5. Expired and the token unset at the same time: the FAIL still fires (the check doesn't depend on Flex being configured). This is the today−1 test, which runs without a token.

---

### Task 1: the `ibkr_flex_token_expires` setting and `.env.example`

**Files:**
- Modify: `src/bot/config.py` (field after `ibkr_flex_tz`, validator next to `_blank_path_is_unset`, `from datetime import date`)
- Modify: `.env.example` (new line right after `# BOT_IBKR_FLEX_TZ=...`)
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.ibkr_flex_token_expires: date | None`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_config.py`. Each sets `BOT_SEC_USER_AGENT` and builds `Settings(_env_file=None)` like the neighbouring Flex tests.
  - `test_flex_token_expires_defaults_to_none`: `delenv("BOT_IBKR_FLEX_TOKEN_EXPIRES", raising=False)` → `s.ibkr_flex_token_expires is None`.
  - `test_blank_flex_token_expires_is_unset`, parametrised over `""` and `"  "`: setenv → `is None`.
  - `test_flex_token_expires_parses_iso_date`: `"2027-03-01"` → `== date(2027, 3, 1)`.
  - `test_invalid_flex_token_expires_is_rejected`: `"next-year"` → `pytest.raises(ValidationError, match="ibkr_flex_token_expires")`.
  - Extend `test_env_example_documents_flex_settings`: it also asserts the exact `.env.example` line from Global Constraints is one of `text.splitlines()`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_config.py`. Expected: the new tests fail (`AttributeError` / no `ValidationError` / line missing).
- [ ] **Step 3: Implement.** Add the field with a description naming doctor's 14-day warning and post-expiry FAIL. Add a `@field_validator("ibkr_flex_token_expires", mode="before")` classmethod `_blank_expiry_is_unset(cls, value: object) -> object` with the same body as `_blank_path_is_unset`. Add the `.env.example` line.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_config.py tests/unit/test_flex_docs.py && uv run mypy src && uv run ruff check .`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(#324): BOT_IBKR_FLEX_TOKEN_EXPIRES setting`.

### Task 2: doctor's token-expiry line, and the README

**Files:**
- Modify: `src/bot/portfolio/freshness.py` (add `TOKEN_EXPIRY_WARN_DAYS: int = 14`; one docstring line that the module also holds the token-expiry threshold)
- Modify: `src/bot/cli.py` (`doctor()`, right after the `Flex query id:` echo; import `TOKEN_EXPIRY_WARN_DAYS` in the existing `bot.portfolio.freshness` import)
- Modify: `README.md` (`### Portfolio sync via Flex Web Service`, steps 2 and 3)
- Test: `tests/unit/test_cli_doctor.py` (append only)

**Interfaces:**
- Consumes: `Settings.ibkr_flex_token_expires` (Task 1).
- Produces: `TOKEN_EXPIRY_WARN_DAYS: int` in `bot.portfolio.freshness`.

- [ ] **Step 1: Write the failing tests.** Add a helper `_expiry_env(tmp_path, monkeypatch, value: str | None)`: `chdir(tmp_path)`, set `BOT_DB_PATH`, `BOT_SEC_USER_AGENT` and `BOT_REPORTS_DIR` like the other tests, `delenv` both `BOT_IBKR_FLEX_TOKEN` and `BOT_IBKR_FLEX_QUERY_ID`, then set `BOT_IBKR_FLEX_TOKEN_EXPIRES` to `value`, or `delenv` it when `value is None`. Tests (`d(n) = (date.today() + timedelta(days=n)).isoformat()`):
  - `test_doctor_flex_token_expiry_far_is_info`: `d(30)` → exit 0; `f"Flex token expiry: {d(30)} (30 days left)"` in stdout; no `WARN:` in stdout.
  - `test_doctor_flex_token_expiry_just_outside_window_is_info`: `d(15)` → exit 0; `(15 days left)` in stdout; no `WARN:`.
  - `test_doctor_flex_token_expiry_within_window_warns`, parametrised over 14 and 0: exit 0; `f"WARN: Flex token expires in {n} day(s) ({d(n)})"` in stdout; `WARN:` not in stderr; `All checks OK.` in stdout.
  - `test_doctor_flex_token_expired_fails`: `d(-1)` → exit 1; a stderr line starts with `f"FAIL: Flex token expired on {d(-1)} (BOT_IBKR_FLEX_TOKEN_EXPIRES)"`.
  - `test_doctor_flex_token_expiry_unset`: `None` → exit 0; `Flex token expiry: not set (BOT_IBKR_FLEX_TOKEN_EXPIRES)` in stdout.
  - `test_doctor_flex_token_expiry_blank_is_not_set`: `"  "` → exit 0; `Flex token expiry: not set` in stdout.
  - `test_doctor_flex_token_expiry_garbage_is_settings_invalid`: `"garbage"` → exit 1; `Settings invalid` in stderr.
  - `test_doctor_flex_token_expiry_follows_query_id_line`: `d(30)`. In `result.stdout.splitlines()`, the line after the one starting `Flex query id:` starts with `Flex token expiry:`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_cli_doctor.py`. Expected: the new tests fail, except `garbage`, which already passes once Task 1 is in. Before Task 1, `extra="ignore"` drops the unknown variable and doctor exits 0, so it fails too. The existing tests pass.
- [ ] **Step 3: Implement** in `doctor()`, right after the `Flex query id:` echo and before the `if not flex_configured:` block: read `expires = settings.ibkr_flex_token_expires`. When `None`, print the unset line. Otherwise compute `days_left` and branch on `< 0` (append the issue), `<= TOKEN_EXPIRY_WARN_DAYS` (echo `WARN:` to stdout) and otherwise (echo the info line). Use the exact copy from Global Constraints. Add the constant to `freshness.py`.
- [ ] **Step 4: README.** Step 2 keeps "generate a token. It expires at most yearly" and replaces "so note its expiry" with: put its expiry date in `BOT_IBKR_FLEX_TOKEN_EXPIRES` (ISO, `YYYY-MM-DD`); `bot doctor` prints a warning from 14 days before that date and fails once it has passed. Step 3's `.env` block gains `BOT_IBKR_FLEX_TOKEN_EXPIRES=2027-03-01   # optional; the token's expiry date, bot doctor warns 14 days before` after the `BOT_IBKR_FLEX_TZ` line. Keep "Put both in `.env`" (the tz line is already a third), and keep every string `tests/unit/test_flex_docs.py` asserts.
- [ ] **Step 5: Run** `uv run pytest -q tests/unit/test_config.py tests/unit/test_cli_doctor.py tests/unit/test_flex_docs.py && uv run ruff check . && uv run mypy src`. Expected: all pass.
- [ ] **Step 6: Commit** `feat(#324): bot doctor warns before the Flex token expires and fails after`.

## Grilling

- Rounds: 1. The revision added assumptions only: no step was added or removed and the seam is the same, so there was no second round.
- Questions: 18. Sources: ISSUE 9 (Q1, Q2, Q3, Q4, Q9, Q10, Q14 partly, Q15 partly, Q11 partly), CODE 11 (Q5 `cli.py:741,785-787,840-844`; Q6 `config.py:147-158`; Q7 `cli.py:743-747`; Q8 `config.py:14-19`; Q9 `freshness.py`; Q10 the `freshness.py` docstring; Q11 `cli.py:785-786` hand-padded literals; Q12 `test_flex_docs.py:56-59`, `test_config.py:95-97`; Q13 `test_flex_docs.py:17-29`; Q14 `cli.py:807`), DOC 1 (Q18 `CONTEXT.md` "Commits: Conventional Commits"). Several answers cite more than one source.
- NO SOURCE → technical assumption: Q15 (lax pydantic parsing, checked empirically), Q16 (hard-coded 14 in the description), Q17 (one PR), Q3 (the IBKR cut-off time inside the expiry day). All are recorded under Assumptions.
- Spec ambiguities: none. Out-of-scope issues opened: none.
