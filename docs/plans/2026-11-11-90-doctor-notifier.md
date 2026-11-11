# bot doctor reports notifier misconfiguration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot doctor` prints a `Notifier:` line with the configured channel and turns a `NotifierConfigError` from `build_notifier(settings)` into a doctor issue, so a bad notifier setup fails `bot doctor` (exit 1) instead of the morning cron run.

**Architecture:** One new block in `doctor()` (`src/bot/cli.py`), placed right after the Flex block and before the DB block. It calls the existing `bot.notifier.build_notifier`, which only constructs a notifier object (no network). The notifier package itself is untouched.

**Tech Stack:** Python 3.12, Typer, pydantic-settings, pytest + `typer.testing.CliRunner`, mypy --strict, ruff.

**Spec:** GitHub issue #90 (nicolas-ricc/damodaran), "bot doctor: report notifier misconfiguration", the triage Agent Brief comment in particular.

## Global Constraints

- `doctor` calls `build_notifier(settings)` and nothing else from the notifier: no `send`, no network call.
- `build_notifier` validation rules and `bot portfolio` / `bot notify` behaviour stay unchanged.
- A `NotifierConfigError` goes into `issues`, so `doctor` exits with code 1 and prints `FAIL: ...` on stderr, like the missing FMP key.
- The values of `BOT_SMTP_PASSWORD` and `BOT_TELEGRAM_BOT_TOKEN` never appear in doctor output (the issue: "Secrets (SMTP password, Telegram token) are never printed").
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits use Conventional Commits with the `(#90)` scope.

## Exact output

The label is padded to column 18, like the other doctor lines (`"Notifier:" + 9 spaces`):

| Situation | stdout line | issue appended |
|---|---|---|
| `BOT_NOTIFIER=none` (or blank) | `Notifier:         none (no alerts are pushed)` | none |
| `email` / `telegram`, `build_notifier` returns | `Notifier:         <channel> (OK)` | none |
| `email` / `telegram`, `NotifierConfigError(exc)` | `Notifier:         <channel>` | `f"Notifier misconfigured (BOT_NOTIFIER={settings.notifier}): {exc}"` |

The issue wording is the same one `bot portfolio` and `bot notify` already print (`cli.py` ~635, ~697), so a user who searches for it finds both.

## Review Focus

1. A developer `.env` that sets `BOT_NOTIFIER=email` would leak into the existing `test_doctor_ok`-style tests. A conftest autouse fixture pins `BOT_NOTIFIER=none`, and each new test sets the channel and its variables explicitly. Covered in Task 1 Step 1.
2. Telegram with the token set but the chat id missing: the issue names `BOT_TELEGRAM_CHAT_ID`, and the token value is absent from stdout and stderr. Test `test_doctor_telegram_missing_chat_id_fails_without_leaking_token`.
3. Email with a username and password but `BOT_SMTP_SECURITY=none` (the cleartext rule): it fails, and the password value does not appear in the output. Test `test_doctor_email_cleartext_credentials_fail_without_leaking_password`.
4. A valid email configuration with a password: exit 0 and the password is not printed. Test `test_doctor_email_valid_passes`.
5. Several missing SMTP variables at once: one issue line that names all of them (the `_require` message). Test `test_doctor_email_missing_host_fails` asserts that `BOT_SMTP_HOST` is named. The multi-variable case is `_require`'s, which is already tested in the notifier tests.

## Assumptions

- The `none` wording is `none (no alerts are pushed)`. The brief asks for the channel to be printed "as none" and for it to report no notifier configured; this wording does both on one line.
- Only `NotifierConfigError` is caught. Its messages name env vars only, never values (`bot/notifier/__init__.py` `_require` and the cleartext message). `build_notifier` raises nothing else (pure construction), and catching broadly would hide bugs.
- The block goes before the DB block, so the notifier line sits with the other configuration lines.
- README: one sentence in the "Notifications" section saying that `bot doctor` checks these settings. `docs/plano/estado.py`'s doctor row cites stale line numbers from before this change and is left alone, because its audit is a separate hand-curated pass (CONTEXT.md).

---

### Task 1: notifier check in `bot doctor`

**Files:**
- Modify: `src/bot/cli.py` (`doctor()`, between the Flex block that ends with `Portfolio sync: not configured` and the `try: conn = connect(...)` DB block)
- Modify: `README.md` ("Notifications" section, after the failure-mode list)
- Modify: `tests/conftest.py` (new autouse fixture `_no_notifier`, next to `_no_flex_settings`)
- Test: `tests/unit/test_cli_doctor.py` (append)

**Interfaces:**
- Consumes: `build_notifier(settings: Settings) -> Notifier | None` and `NotifierConfigError` (already imported in `cli.py`); `Settings.notifier: Literal["email", "telegram", "none"]`.
- Produces: nothing new for other code.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_cli_doctor.py`. Each test sets `BOT_DB_PATH`, `BOT_SEC_USER_AGENT` and `BOT_REPORTS_DIR` like the existing ones, plus `BOT_NOTIFIER` and the channel's variables. `out = result.stdout + result.stderr`.
  - `test_doctor_notifier_none_passes`, parametrised over `BOT_NOTIFIER` = `none` and `""` (blank is coerced to `none` by `Settings._blank_notifier_is_none`): exit 0; `"Notifier:         none"` in stdout; `"Notifier misconfigured"` not in out.
  - `test_doctor_email_valid_passes`: email with host `smtp.example.com`, from `bot@example.com`, to `me@example.com`, username `user`, password `SECRET`, security `starttls` → exit 0; `"Notifier:         email (OK)"` in stdout; `SECRET` not in out.
  - `test_doctor_email_missing_host_fails`: as above but `BOT_SMTP_HOST=""` → exit 1; `"Notifier misconfigured (BOT_NOTIFIER=email)"` and `"BOT_SMTP_HOST"` in stderr; `SECRET` not in out.
  - `test_doctor_email_cleartext_credentials_fail_without_leaking_password`: valid email plus `BOT_SMTP_SECURITY=none` → exit 1; `"BOT_SMTP_SECURITY=none"` in stderr; `SECRET` not in out.
  - `test_doctor_telegram_valid_passes`: token `SECRET`, chat id `12345` → exit 0; `"Notifier:         telegram (OK)"` in stdout; `SECRET` not in out.
  - `test_doctor_telegram_missing_token_fails`: token `""`, chat id `12345` → exit 1; `"BOT_TELEGRAM_BOT_TOKEN"` in stderr.
  - `test_doctor_telegram_missing_chat_id_fails_without_leaking_token`: token `SECRET`, chat id `""` → exit 1; `"BOT_TELEGRAM_CHAT_ID"` in stderr; `SECRET` not in out.
  - `test_doctor_reports_notifier_and_fmp_issues_together`: `BOT_DATA_PROVIDER=fmp`, `BOT_FMP_API_KEY=""`, `BOT_NOTIFIER=telegram`, no token/chat id → exit 1; stderr has two `FAIL:` lines, one naming FMP, one `Notifier misconfigured`.
  - `test_doctor_rejects_unknown_notifier`: `BOT_NOTIFIER=slack` → exit 1; `"FAIL: Settings invalid"` in stderr (existing path, `cli.py` ~744-748; pinned so the new block never masks it).
  - In `tests/conftest.py`, add an autouse fixture `_no_notifier` that sets `BOT_NOTIFIER=none`, with a docstring mirroring `_no_flex_settings`: a notifier in a developer's `.env` would otherwise fail `bot doctor` tests (`Settings` reads `.env`, `config.py` `env_file=".env"`; real env vars win over it). Tests that need a channel set it themselves.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_cli_doctor.py` and expect the new tests to FAIL: there is no `Notifier:` line yet, and the misconfigured cases exit 0.
- [ ] **Step 3: Implement** the block in `doctor()` following the "Exact output" table: `try: notifier = build_notifier(settings)`, then `except NotifierConfigError as exc:` echoes the bare channel line and appends the issue; otherwise it echoes `none (no alerts are pushed)` when `notifier is None`, else `<channel> (OK)`.
- [ ] **Step 4: Add the README sentence** in "Notifications", after the failure-mode list: `` `bot doctor` prints the configured channel and fails (exit 1) when these settings are missing or unsafe, without sending anything. ``
- [ ] **Step 5: Run** `uv run pytest -q && uv run ruff check . && uv run mypy src` and expect PASS.
- [ ] **Step 6: Commit** `feat(#90): bot doctor reports notifier misconfiguration`.

## Grilling

- Rounds: 1 (the revision added tests and a conftest fixture, but the seam did not change, so no second round). Griller model: fable.
- Questions: 15. Sources: CODE 9, ISSUE 1, DOC 2, NO SOURCE 3, all technical assumptions: the README sentence, the conftest `_no_notifier` fixture, and the `try`/`except`/`else` structure (mypy is fine with it).
- Plan changes: the secret list now follows the issue (password and token; the username is not a secret); added the blank-`BOT_NOTIFIER` case, the multi-issue test, the unknown-channel test, and the conftest fixture.
- Spec ambiguities: none. Follow-up issues opened: none.
