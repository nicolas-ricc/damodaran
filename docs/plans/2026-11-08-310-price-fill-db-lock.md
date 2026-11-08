# price_fill.sh skips with a logged line when .cache/bot.lock is held — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/price_fill.sh` takes the shared advisory lock `$REPO/.cache/bot.lock` without waiting before its DB section; when another bot run holds it, the drip logs one `skipped: DB busy` line and exits 0 without invoking `uv`.

**Architecture:** One non-blocking `flock -n` on file descriptor 9, inserted right after the `=== <date> run ===` header line, so the refresh and the MISSING query (both child processes) run under it and it is released when the script exits. Tests hold the lock from the test process with `fcntl.flock` (same `flock(2)` underneath). README Quickstart step 3 replaces the "do not run both" warning.

**Tech Stack:** bash, `flock(1)` (util-linux), pytest, `fcntl`, shellcheck (`.venv/bin/shellcheck`).

**Spec:** GitHub issue #310 (`gh issue view 310 --repo nicolas-ricc/damodaran`); story context in #108's plan comment.

## Global Constraints

- Lock file: `LOCK="$REPO/.cache/bot.lock"`; never deleted by the script.
- `flock` called by name, no fallback when missing.
- Exact shape (verbatim from the spec):
  ```bash
  LOCK="$REPO/.cache/bot.lock"
  exec 9>>"$LOCK"
  if ! flock -n 9; then
    echo "skipped: DB busy ($LOCK is held by another bot run); the next hourly run catches up" >> "$LOG"
    exit 0
  fi
  ```
  placed right after `echo "=== $(date -Is) run ===" >> "$LOG"`. Everything after it is unchanged.
- The `DONE` short-circuit and the `sync_master.sh` re-exec stay before the lock.
- No new env var (`BOT_DB_LOCK_WAIT` is the sibling #311's, not read here).
- `scripts/daily.sh` and `scripts/weekly.sh` are not touched (sibling #311); nor the README Scheduling section (#311's region).
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- **Probe for "held while uv runs".** A probe `uv` written with `_write_exe` into `tmp_path/"bin-probe"/"uv"` runs `flock -n "<lock>" true`; exit 0 → appends `lock-free <argv>` to the calls file, non-zero → `lock-held <argv>`. For `$2 = python` it then drains stdin and prints `0` (so the run completes like the recorder's). It probes both calls, so the test pins the refresh **and** the MISSING query: expected calls are `["lock-held run bot refresh --prices --only-missing", "lock-held run python -"]`. This works because `flock -n <file>` opens a new open file description, which conflicts with the one fd 9 holds even though the child inherits fd 9.
- **Lock holder in tests.** A small context-manager-free helper in the test: `(repo/".cache").mkdir()`, `fd = os.open(lock, os.O_WRONLY | os.O_CREAT)`, `fcntl.flock(fd, fcntl.LOCK_EX)`, run, `os.close(fd)` in `finally`.
- **Missing `flock(1)`** (rejected alternative: a `command -v flock` guard that fails loudly). Spec: "No fallback when it is missing; the wrappers are Linux cron jobs." Without it, `flock` exits 127, `! flock -n 9` is true, and the run logs the skip line and exits 0, with `command not found` on stderr (cron mails it). The test host has `/usr/bin/flock` (util-linux), and the issue verified the `fcntl`/`flock(1)` interplay there.
- **`exec 9>>"$LOCK"` failing** (unwritable `.cache/`). The script runs without `set -e` (`price_fill.sh:21`). By then `.cache/` is unwritable, so `$LOG` (lines 33, 40, 44) already fails to take writes. No test is added (rejected alternative: a chmod test, which passes trivially as root). Out of the spec's criteria.
- **Doc test location**: `tests/unit/test_price_fill_docs.py`, following the `tests/unit/test_*_docs.py` precedent (`test_flex_docs.py`, `test_readme_dev_docs.py`) rather than `test_scripts.py` (rejected alternative). The spec's three script tests stay in `test_scripts.py` as it requires.
- **Header comment wording**: it says `daily.sh`/`weekly.sh` share the lock. This is true once the story branch reaches `master`, because #108's children comment says `feature/108-db-lock` merges into `master` only when both #310 and #311 are closed.
- **Plan location `docs/plans/`** follows the recent issue plans (e.g. `docs/plans/2026-11-08-114-price-fill-env.md`).
- **Docs.** `docs/pipeline/` boards cite `scripts/price_fill.sh` by file only; `docs/plano/estado.html` is not a per-child concern (story #108 plan item 7 lists it as unchanged). No ADR covers the lock.

## Acceptance criteria → tests

- Lock held → exit 0, one skip line naming the lock, no `uv`, no DONE: `test_price_fill_skips_when_the_db_lock_is_held`.
- Lock free → same behaviour as today: `test_price_fill_runs_when_the_db_lock_is_free` plus every existing `price_fill` test unchanged.
- Lock held for the refresh and the MISSING query: `test_price_fill_holds_the_db_lock_while_uv_runs`.
- README sentence: `test_readme_quickstart_says_the_drip_skips_on_the_shared_lock` pins the required facts (precedent: `tests/unit/test_flex_docs.py` reads `README.md`); the wording itself is reviewed by reading the diff.
- Executable and shellcheck-clean: existing `test_script_is_executable_and_shellcheck_clean[price_fill.sh]`.

## Review Focus

1. A stale lock file left on disk by an earlier run (no holder) must not cause a skip. Pinned by `test_price_fill_runs_when_the_db_lock_is_free` (file pre-created, unlocked).
2. A skip must log exactly one skip line, under a run header, not one per call. Pinned in `test_price_fill_skips_when_the_db_lock_is_held` (`log.count("skipped: DB busy") == 1`).
3. DONE present and lock held: the drip still exits 0 silently without touching the log (short-circuit before the lock). Pinned by `test_price_fill_with_done_exits_0_without_uv` already (no holder needed: it never reaches the lock); no new test.
4. `.cache/` absent on the very first run: the script's `mkdir -p` precedes `exec 9>>`. Pinned by every existing price_fill test (they start without `.cache/`).

---

### Task 1: price_fill.sh takes .cache/bot.lock non-blocking, README says so

**Files:**
- Modify: `scripts/price_fill.sh` (header comment; insert the lock block after the run header line)
- Modify: `README.md:62-64` (Quickstart step 3, the "do not run both" sentence)
- Test: `tests/integration/test_scripts.py` (in the `# --- price_fill.sh` section, after `test_price_fill_with_no_count_logs_a_question_mark`)
- Create: `tests/unit/test_price_fill_docs.py` (README test)

**Interfaces:**
- Consumes: fixtures `repo`, `calls`, `recorder_bin`, `tmp_path`; helpers `_env`, `_run`, `_calls`, `_write_exe`, `_price_fill_log`; constant `_PRICE_FILL`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the four failing tests**
  - `test_price_fill_skips_when_the_db_lock_is_held(repo, recorder_bin, calls)`: hold the lock (see Assumptions), run `price_fill.sh` with `_env(recorder_bin)`. Assert `returncode == 0`, `_calls(calls) == []`, log contains `"skipped: DB busy"` and `".cache/bot.lock"`, `log.count("skipped: DB busy") == 1`, log contains `" run ==="`, `not (repo/".cache"/"price_fill.DONE").exists()`.
  - `test_price_fill_runs_when_the_db_lock_is_free(repo, recorder_bin, calls)`: `(repo/".cache").mkdir()`, `(repo/".cache"/"bot.lock").touch()`, run. Assert `returncode == 0`, `_calls(calls) == _PRICE_FILL`, `"skipped: DB busy" not in log` (plain `skipped` also matches sync_master's "not a git checkout, skipped").
  - `test_price_fill_holds_the_db_lock_while_uv_runs(repo, tmp_path, calls)`: probe `uv` (see Assumptions), run with `_env(probe_bin)`. Assert `returncode == 0`, `_calls(calls) == ["lock-held run bot refresh --prices --only-missing", "lock-held run python -"]`.

  - `test_readme_quickstart_says_the_drip_skips_on_the_shared_lock()`: in `tests/unit/test_price_fill_docs.py`, read `Path(__file__).resolve().parents[2]/"README.md"`, take the text between `price_fill.sh` drip is only for` and `Tiingo Power`, collapse whitespace. Assert it contains `.cache/bot.lock`, `skipped: DB busy`, `Tiingo quota`, `scripts/install_cron.sh`, `(#108)`, and does not contain `do not run both` nor `same DuckDB file`.

- [ ] **Step 2: Run, see them fail**
  Run: `uv run pytest -q tests/integration/test_scripts.py tests/unit/test_price_fill_docs.py -k "price_fill or readme"`
  Expected: `skips_when_the_db_lock_is_held` fails (uv is called), `holds_the_db_lock_while_uv_runs` fails (`lock-free`), the README test fails (`do not run both` present). `runs_when_the_db_lock_is_free` passes already (pins kept behaviour). The existing price_fill tests pass.

- [ ] **Step 3: Edit `scripts/price_fill.sh`**
  Insert the Global Constraints block after the run header. Add one header-comment paragraph before `# Requires BOT_TIINGO_API_KEY ...`: the DB section (refresh and MISSING query) runs under the shared `.cache/bot.lock` that `daily.sh`/`weekly.sh` also take; when another bot run holds it, this run logs `skipped: DB busy` and exits 0 — skipped, not failed; the next hourly run catches up (#108).

- [ ] **Step 4: Edit README Quickstart step 3**
  Replace `; do not run both, or they compete for the same hourly Tiingo quota and the same DuckDB file (#108).` so the paragraph says: the wrappers share `.cache/bot.lock`; when the drip finds it held it logs `skipped: DB busy` and the next hourly run catches up; the drip and the daily rounds still share the hourly Tiingo quota, so the drip is meant for the first fill before `scripts/install_cron.sh`. Keep `(#108)`.

- [ ] **Step 5: Verify**
  Run: `uv run pytest -q tests/integration/test_scripts.py tests/unit/test_price_fill_docs.py && uv run ruff check . && uv run mypy src`
  Expected: all pass (including shellcheck for `price_fill.sh`).

- [ ] **Step 6: Commit**
  ```bash
  git add scripts/price_fill.sh README.md tests/integration/test_scripts.py tests/unit/test_price_fill_docs.py
  git commit -m "feat(#310): price_fill.sh skips when .cache/bot.lock is held"
  ```

## Grilling

- Rounds: 1 (griller: fable). The revision was not substantial (one test moved file, assumptions added), so no second round.
- Questions: 15. Sources: ISSUE 7 (Q3, Q4, Q11, Q12, Q13, Q15, plus #108 comments), CODE 7 (Q1, Q2, Q5, Q6, Q7, Q8, Q10), NO SOURCE 3 (Q4 part, Q9, Q14), all technical assumptions.
- Assumptions added: missing `flock` gives a silent skip (spec: no fallback); an `exec 9>>` failure is not covered; the doc test lives in `tests/unit/test_price_fill_docs.py`; the header comment's claim about the shared lock holds once the story branch merges. Shellcheck acceptance of `exec 9>>`/`flock -n 9` is checked in Step 5, not assumed.
- Issues opened: none.
