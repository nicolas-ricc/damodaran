# daily.sh failure message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When any step of `scripts/daily.sh` fails, the run pipes exactly one plain-text message (failed steps, exit codes, last 20 lines of `.cache/daily.log`) into `uv run bot notify`, without changing the run's exit code.

**Architecture:** The step sequence moves from the `{ ... } >> "$LOG" 2>&1` block into a function `run_steps` that records every failing step as `<command> (exit N)` in a bash array and returns the run's exit code exactly as today. The script calls it with the same redirection, and on a non-zero status it builds the whole message into a variable first (so the log tail is read before anything else is appended), pipes it into `uv run bot notify` with its output appended to the log, then exits with the saved status. The test recorder `uv` learns to capture `bot notify`'s stdin.

**Tech Stack:** bash (`set -uo pipefail`, shellcheck clean), pytest driving the script through a fake `uv` (`tests/integration/test_scripts.py`).

**Spec:** GitHub issue #322 (nicolas-ricc/damodaran), "feat(#118): daily.sh sends one notifier message per failed run with the failed step, exit code and log tail". Story context: the planner's comment on parent #118. `bot notify` itself is #321 (already on the base branch, `src/bot/cli.py` `notify()`).

## Global Constraints

- One message per failed run, sent after the last step that runs and before `exit`, through `uv run bot notify` (stdin = message), with notify's stdout/stderr appended to `$LOG`. Not under `locked` (no DB).
- The notify call's exit code never changes the run's exit code: worst of prices/FX, else portfolio's, 75 after a lock timeout, exactly as today.
- No notify call on a successful run.
- Message, verbatim layout (first line is the email subject):
  ```
  # daily.sh failed: <step> (exit N)[, <step> (exit N)]

  <date -Is> on <host>, run exit code <N>
  Last 20 lines of .cache/daily.log:

  <tail -n 20 "$LOG", read before the notify output is appended>
  ```
- Step names exactly: `bot refresh --prices`, `bot refresh --fx`, `bot portfolio`, in run order.
- Every behaviour existing tests assert stays: round loop, pause, FX after failed prices, portfolio only when prices and FX both succeeded, `locked` per command, `=== <date> run ===` header.
- `weekly.sh` is not changed.
- `scripts/daily.sh` passes shellcheck; its header comment mentions the failure message.
- README `## Scheduling` gets one bullet: the failure message, that it goes through `bot notify`, and that a `BOT_NOTIFIER=none` setup only logs it.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green. Commits are Conventional Commits scoped `(#322)`.

## Review Focus

1. **A log longer than 20 lines** (deferred price rounds, earlier runs appended): the message carries exactly the last 20 lines as they were before notify ran. Pinned in Task 1 by `test_daily_failure_message_carries_exactly_the_last_20_log_lines`.
2. **Log lines with `%`, backslashes or a leading `-`** (provider errors, tracebacks): they reach `bot notify` verbatim, never interpreted as a format string or an option. Pinned in Task 1 by `test_daily_failure_message_keeps_log_lines_verbatim`, which pre-seeds the log.
3. **`bot notify` itself failing or missing** (`FAKE_NOTIFY_EXIT=1`): run exit code unchanged and notify's output in the log. Pinned by `test_daily_failing_notify_keeps_the_run_exit_code`.
4. **Lock timeout on every step**: both refresh steps show `(exit 75)`, the run still exits 75, and the notify call itself is not blocked by the held lock. Pinned by the updated `test_wrapper_times_out_when_the_db_lock_stays_held`.
5. **Prices and FX both failing**: one call, both steps on the subject line, no `bot portfolio`. Pinned by `test_daily_failing_prices_and_fx_send_one_message_listing_both`.

## Assumptions

- **Host name is bash's `${HOSTNAME:-unknown}`**, not the `hostname` binary, which minimal images (Fedora, Debian slim containers) do not ship. The `:-unknown` fallback keeps `on <host>,` well-formed if bash could not resolve a name. Rejected: `$(hostname)`, which would print `command not found` into the message.
- **The message is built into a variable, then piped.** That makes "tail read before notify output is appended" hold by construction. Rejected: `{ ...; tail; } | uv run bot notify >> "$LOG"`, where `tail` races with notify's own output.
- **The tail is of the whole `$LOG` file**, so it can include lines of a previous run when this run wrote fewer than 20. The issue specifies `tail -n 20 of $LOG`.
- **Join of `FAILED`**: `printf '%s, ' "${FAILED[@]}"` captured, then `${steps%, }`. Exercised with one step (portfolio test) and two (prices+FX test). Rejected: `IFS`, which only joins on one character.
- **Trailing blank lines of the log tail are dropped** by `$(tail ...)`. Every step writes a non-blank last line (`fake uv: ...`, bot output, `lock timeout: ...`), so the 20-line comparison test splits the message after line 5 with `splitlines()` and compares to the log's last 20 lines. Rejected: preserving trailing newlines with a sentinel, which nobody reads in a notification.
- **Tests come first, in pipeline stage 3** (`test(#322): evals`, after this plan's review); each task's Step 1 refers to them. Rejected: implementers writing their own tests from scratch.
- **`sync_master.sh` output is not a step.** It is logged before the re-exec, and its failure is already non-fatal by design.

---

### Task 1: daily.sh sends the failure message

**Files:**
- Modify: `scripts/daily.sh` (header comment and the final `{ ... } >> "$LOG" 2>&1` block)
- Modify: `tests/integration/test_scripts.py` (`_UV_RECORDER`, the failing-run assertions, new tests)

**Interfaces:**
- Consumes: `uv run bot notify` (stdin = message; exit 0/1/2; #321).
- Produces: nothing other code calls. Test helper `_notify_message(calls: Path) -> str` reads `f"{calls}.notify"`.

- [ ] **Step 1: Tests (written and committed before implementation as the stage-3 evals, `test(#322): evals`)**

Recorder: right after `echo "fake uv: $*"`, add `if [ "$3" = notify ]; then cat > "{calls}.notify"; fi`. Constant `_NOTIFY = "run bot notify"`.

Updated (failing runs now end with `_NOTIFY`): `_AFTER_FAILING_REFRESH["daily.sh"]`, `test_daily_exits_with_portfolio_failure_and_logs_it`, `test_daily_failing_price_round_stops_the_loop_still_refreshes_fx_skips_portfolio`, `test_daily_exits_with_the_worst_of_prices_and_fx`, and `test_wrapper_times_out_when_the_db_lock_stays_held` (`daily.sh` expects `[_NOTIFY]` and the first message line `# daily.sh failed: bot refresh --prices (exit 75), bot refresh --fx (exit 75)`; `weekly.sh` still `[]`). Successful-run assertions are unchanged.

New:
- `test_daily_failing_portfolio_sends_one_failure_message`: `FAKE_PORTFOLIO_EXIT=1` → rc 1, calls `== _WRAPPERS["daily.sh"] + [_NOTIFY]`, line 1 `== "# daily.sh failed: bot portfolio (exit 1)"`, line 2 `== ""`, line 3 matches `^\d{4}-\d{2}-\d{2}T\S+ on \S+, run exit code 1$`, line 4 `== "Last 20 lines of .cache/daily.log:"`, `"fake uv: run bot portfolio"` in it, `"fake uv: run bot notify"` not in it.
- `test_daily_failing_prices_and_fx_send_one_message_listing_both`: `FAKE_PRICES_EXIT=1`, `FAKE_REFRESH_EXIT=2` → rc 2, calls `== _WRAPPERS["daily.sh"][:2] + [_NOTIFY]`, line 1 `== "# daily.sh failed: bot refresh --prices (exit 1), bot refresh --fx (exit 2)"`, `"run exit code 2"` in it.
- `test_daily_successful_run_sends_no_message`: success → calls `== _WRAPPERS["daily.sh"]` and no `.notify` file.
- `test_daily_failing_notify_keeps_the_run_exit_code`: `FAKE_PORTFOLIO_EXIT=1`, `FAKE_NOTIFY_EXIT=1` → rc 1, `"fake uv: run bot notify"` in `daily.log`.
- `test_daily_failure_message_carries_exactly_the_last_20_log_lines`: `FAKE_DEFERRED_ROUNDS=30`, `BOT_PRICE_ROUNDS=30`, no pause, `FAKE_PORTFOLIO_EXIT=1` → the message lines after line 5 `==` the last 20 lines of `daily.log` with the trailing `fake uv: run bot notify` line removed.
- `test_daily_failure_message_keeps_log_lines_verbatim`: pre-seed `daily.log` with `-n 100% done \\t %s` then `FAKE_PORTFOLIO_EXIT=1` → that exact line is in the message.

- [ ] **Step 2: Run them, verify they fail**

Run: `uv run pytest -q tests/integration/test_scripts.py -k "daily or wrapper"`
Expected: the new and updated `daily.sh` tests FAIL (no `run bot notify` call / no `.notify` file); `weekly.sh` cases pass.

- [ ] **Step 3: Implement in `scripts/daily.sh`**

- `FAILED=()` and a function `run_steps` holding today's sequence (header echo, `refresh_prices`, `locked uv run bot refresh --fx`, worst-of, `locked uv run bot portfolio`). After each step, a non-zero status appends `"bot refresh --prices (exit $prices)"` / `"bot refresh --fx (exit $fx)"` / `"bot portfolio (exit $status)"` to `FAILED`. It returns the worst of prices/FX when non-zero, else portfolio's status (replaces today's `exit "$worst"`).
- A function `notify_failure <status>` that joins `FAILED` with `", "`, builds the message with `printf '%s\n'` (never the log text as a format string) into a local variable, using `$(date -Is)`, `${HOSTNAME:-unknown}` and `$(tail -n 20 "$LOG")`, then `printf '%s\n' "$message" | uv run bot notify`.
- Main: `run_steps >> "$LOG" 2>&1` (a function, not a subshell, so `FAILED` survives), `status=$?`, `((status == 0)) || notify_failure "$status" >> "$LOG" 2>&1`, `exit "$status"`.
- Header comment: the paragraph on output/exit code gains one sentence: a failed run sends one message (failed steps, exit codes, last 20 log lines) through `bot notify`, which never changes the exit code.

- [ ] **Step 4: Verify**

Run: `uv run pytest -q tests/integration/test_scripts.py`
Expected: all pass, including `test_script_is_executable_and_shellcheck_clean[daily.sh]`.

- [ ] **Step 5: Commit** `feat(#322): daily.sh sends one notifier message per failed run`

### Task 2: README Scheduling bullet

**Files:**
- Modify: `README.md` (`## Scheduling`, new bullet after **Daily**)
- Test: `tests/integration/test_scripts.py` (new `test_readme_scheduling_documents_the_failure_message`, committed with the stage-3 evals)

**Interfaces:**
- Consumes: Task 1's message format.
- Produces: nothing.

- [ ] **Step 1: Test (committed with the stage-3 evals)**: the whitespace-collapsed `## Scheduling` section (same slicing as `test_readme_scheduling_documents_the_shared_db_lock`) contains `daily.sh failed:`, `bot notify`, `20 lines`, `BOT_NOTIFIER=none` and `exit code`.
- [ ] **Step 2: Run it, verify it fails**: `uv run pytest -q tests/integration/test_scripts.py -k readme` → FAIL on `daily.sh failed:`.
- [ ] **Step 3: Write the bullet** `**Failure message**`: when any `daily.sh` step fails, the run pipes one message into `bot notify`: subject `# daily.sh failed: <step> (exit N), ...`, then time, host, the run's exit code and the last 20 lines of `.cache/daily.log`. The notify result is logged and never changes the job's exit code; with `BOT_NOTIFIER=none` it only logs the "nothing sent" line. A successful run sends nothing.
- [ ] **Step 4: Verify**: `uv run pytest -q tests/integration/test_scripts.py -k readme` → PASS.
- [ ] **Step 5: Commit** `docs(#322): README Scheduling describes the daily failure message`

## Grilling

- Rounds: 1 (revisions were wording and assumptions only, no new step or seam, so no second round). Griller model: fable.
- Questions: 15. Sources: ISSUE 5 (Q4, Q5, Q6, Q11, Q15), CODE 7 (Q1 `scripts/daily.sh:47-51,70,87`, Q3 `scripts/daily.sh:47` vs `scripts/weekly.sh:41` with no sourcing, Q7 `scripts/daily.sh:29-30,35,88`, Q9 `_UV_RECORDER`, Q13 `scripts/daily.sh:86`, Q14 `scripts/daily.sh:33-36` `exec`, Q5 `src/bot/notifier/email.py:67-71`, `src/bot/cli.py:680-708`), NO SOURCE 4, all technical assumptions (Q2, Q8, Q10, Q12).
- Assumptions added: the `${HOSTNAME:-unknown}` fallback, the join construct, trailing blank lines of the tail being dropped, the tests coming from stage 3.
- Spec ambiguities: none. Out-of-scope issues opened: none.
