# price_fill.sh resolves its environment like the cron wrappers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/price_fill.sh` resolves its repo root to the physical path and appends the cron fallbacks to `PATH`, calling `uv` by name, exactly as `scripts/daily.sh` and `scripts/weekly.sh` do; and it comes under `tests/integration/test_scripts.py` like they are.

**Architecture:** Two edits to one script (the root line and the `PATH`/`UV` lines) plus tests in the existing script harness. The harness's fake `uv` recorder learns to answer the script's `uv run python -` missing-count query, so the count is driven by an env var.

**Tech Stack:** bash, pytest, `subprocess`, shellcheck (from the test venv, `.venv/bin/shellcheck`).

**Spec:** GitHub issue #114 (`gh issue view 114 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec.

## Global Constraints

- Behaviour stays the same: the `.cache/price_fill.DONE` short-circuit (checked before the sync), the `sync_master.sh` re-exec guarded by `BOT_SYNCED`, `uv run bot refresh --prices --only-missing`, the `missing=<n>` log line (`missing=?` when the query prints nothing), and `touch DONE` plus the `FILLED` line when the count is exactly `0`.
- Root: `SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"`, the same line as `scripts/daily.sh:18`.
- PATH: `export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"`, with the same two-line comment as `scripts/daily.sh:22-24`. The `UV=` variable goes away, and every `"$UV" run` becomes `uv run`.
- Out of scope (brief): locking (#108), adding `price_fill.sh` to `install_cron.sh`, changing what the script refreshes or the SQL.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- **How the fake `uv` gets red on today's script.** Today's script prepends `$HOME/.local/bin:/usr/local/bin:/usr/bin`. The PATH test sets `HOME` to a temp dir holding a decoy `$HOME/.local/bin/uv` that writes a marker file and exits 97. With the prepend, the decoy runs; with the append, the recorder that is first on `PATH` runs. This does not depend on where the machine's real `uv` lives. On this machine it is `/usr/local/bin/uv`, which today's script would also pick ahead of the fake.
- **The missing-count query in the recorder.** `_UV_RECORDER` gets a branch at the top: when `$2` is `python`, it appends `$*` to the calls file, discards stdin, prints `${FAKE_MISSING-0}` alone on stdout (no `fake uv:` line, which would pollute `MISSING`), and exits 0. The existing scripts never call `uv run python`, so their tests are unaffected.
- **Logical vs physical root cannot be told apart from the filesystem.** Both name the same `.cache/`. The symlink AC is checked by running the script through a symlink placed in another directory, with `cwd` set elsewhere: the log lands in the real checkout's `.cache/` and nowhere else. The `pwd -P` change is for consistency with the other wrappers (the brief's first "Desired behavior" bullet). Its observable effect is already covered by `readlink -f`.
- **The test copy is not a git checkout**, so `sync_master.sh` logs "not a git checkout, skipped" and the script re-execs once. The re-exec against a real origin is pinned with the existing `behind_origin` fixture.
- **Plan location `docs/plans/`** follows recent issue plans such as `docs/plans/2026-11-08-78-readme-ruff-format.md`.
- **README/docs.** `README.md:48-53,131,150` describe the drip and sync. They do not change, because they say nothing about PATH or the root. The pipeline boards cite `scripts/price_fill.sh` by file only.

## Review Focus

1. A `uv` already on `PATH` must win over `$HOME/.local/bin/uv`. Pinned in Task 1 (`test_price_fill_uses_the_first_uv_on_path`).
2. DONE present: no `uv` call and no sync. Pinned in Task 1 (`test_price_fill_with_done_exits_0_without_uv`).
3. A non-zero missing count must not write DONE. Pinned in Task 1 (`test_price_fill_with_tickers_missing_keeps_going`).
4. The re-exec must not loop. A run that completes and calls `refresh` exactly once proves it. Pinned in Task 1 (`test_price_fill_pulls_origin_master_before_running`).

---

### Task 1: Align price_fill.sh and bring it under the script tests

**Files:**
- Modify: `scripts/price_fill.sh` (root line, PATH/UV block, the two `"$UV" run` calls, and the header comment if it mentions the prepend)
- Test: `tests/integration/test_scripts.py`

**Interfaces:**
- Consumes: the existing fixtures `repo`, `calls`, `recorder_bin`, `behind_origin`, `tmp_path`, and the helpers `_env`, `_run`, `_calls`, `_write_exe`, `_GIT_ENV`.
- Produces: `FAKE_MISSING` env var for the recorder, plus a module constant `_PRICE_FILL = ["run bot refresh --prices --only-missing", "run python -"]` (the calls one full run makes).

- [ ] **Step 1: Write the failing tests**

  - Add `"price_fill.sh"` to `SCRIPTS`.
  - Add the `$2 = python` branch to `_UV_RECORDER` (see Assumptions).
  - Tests. All of them run `repo / "scripts" / "price_fill.sh"`, and the log is `repo / ".cache" / "price_fill.log"`:
    - `test_price_fill_uses_the_first_uv_on_path`: decoy at `tmp_path/"home"/".local"/"bin"/"uv"` touches `tmp_path/"decoy-ran"` and exits 97. Run with `_env(recorder_bin, HOME=str(tmp_path / "home"))`. Assert `returncode == 0`, `_calls(calls) == _PRICE_FILL`, and that `decoy-ran` does not exist.
    - `test_price_fill_through_a_symlink_logs_in_the_real_checkout`: `tmp_path/"elsewhere"/"price_fill.sh"` is a symlink to the repo script. Run it via `subprocess.run` with `cwd=tmp_path`. Assert `returncode == 0`, `repo/.cache/price_fill.log` exists and holds `" run ==="`, and neither `tmp_path/".cache"` nor `tmp_path/"elsewhere"/".cache"` exists.
    - `test_price_fill_run_from_another_directory_logs_in_the_checkout`: the same, without the symlink (the real path, `cwd=tmp_path`).
    - `test_price_fill_with_done_exits_0_without_uv`: create `repo/.cache/price_fill.DONE` first. Assert `returncode == 0`, `_calls(calls) == []`, and that the log does not exist (the short-circuit runs before the sync).
    - `test_price_fill_writes_done_when_nothing_is_missing`: `FAKE_MISSING="0"`. Assert `returncode == 0`, `_calls(calls) == _PRICE_FILL`, that DONE exists, and that the log holds `"missing=0\n"` and `"FILLED"`.
    - `test_price_fill_with_tickers_missing_keeps_going`: `FAKE_MISSING="12"`. Assert that DONE does not exist, the log holds `"missing=12\n"`, and the log does not hold `"FILLED"`.
    - `test_price_fill_pulls_origin_master_before_running(behind_origin, recorder_bin, calls)`: run with `_env(recorder_bin, **_GIT_ENV)`. Assert `returncode == 0`, `(repo/"NEW").read_text() == "from origin\n"`, `_calls(calls) == _PRICE_FILL`, that `" sync ==="` comes before `" run ==="` in the log, and that the log holds `"sync_master: master "`.

- [ ] **Step 2: Run them, see the expected failures**

  Run: `uv run pytest -q tests/integration/test_scripts.py -k price_fill`
  Expected: the tests that call `uv` fail. The decoy or the machine's real `uv` runs instead of the recorder, so `_calls(calls)` is empty or the decoy marker exists. The DONE and shellcheck tests may already pass, because they pin behaviour that is kept.

- [ ] **Step 3: Edit `scripts/price_fill.sh`**

  Root line → `pwd -P`. PATH → append, with the daily.sh comment. Delete `UV=`. `"$UV" run` → `uv run` (two places). Nothing else moves.

- [ ] **Step 4: Run the script tests, shellcheck and the suite**

  Run: `uv run pytest -q tests/integration/test_scripts.py && uv run ruff check . && uv run mypy src && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/price_fill.sh tests/integration/test_scripts.py
  git commit -m "fix(#114): price_fill.sh resolves its root and PATH like the cron wrappers"
  ```
