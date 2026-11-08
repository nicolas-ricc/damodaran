# Unreadable override fails its ticker alone — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An override file that exists but cannot be read (permission denied, a directory named `TICKER.yaml`) fails only its own ticker with "cannot value", never the whole `bot analyze` / `bot screen` / portfolio-marks run.

**Architecture:** Reading the file becomes part of validating it: `load_override` wraps `override_path.read_text()` and turns any `OSError` into a `ValueError` that names the path and is chained from the `OSError`. Every caller already treats `ValueError` as "this ticker cannot be valued" (`_analyze_one` → exit 1, the screener's second pass → `margin_of_safety=None`, `mark_holdings` → an unvalued mark), so no caller changes. `conventional_override_path` keeps `exists()`: a directory named `TICKER.yaml` is passed on and refused by `load_override` as unreadable, so the mistake is reported instead of silently valuing without the user's assumptions.

**Tech Stack:** Python 3, typer, PyYAML, pytest, `typer.testing.CliRunner`.

**Spec:** GitHub issue #227 (the Agent Brief in the triage comment).

## Global Constraints

- The `ValueError` message starts with the path and says it cannot be read, in the style of the existing `override file {path} is not valid YAML: {exc}`. Exact copy: `override file {override_path} cannot be read: {exc}`.
- The `ValueError` is chained from the original `OSError` (`raise ... from exc`).
- `_analyze_one`'s contract stays: `LookupError` → 2, `ValueError` → 1, the batch goes on, the command exits with the worst per-ticker code (#180).
- Unchanged: a missing conventional file means no override; a missing or directory `--override` is refused with exit 2 before the DB opens (`--override {path}: no such file.`); malformed YAML gives exit 1.
- Tests must not rely on `chmod` (CI may run as root): simulate `PermissionError` by monkeypatching `Path.read_text` for the one path.
- `mypy --strict` and ruff stay clean.

## Decision: a directory at the conventional path

`conventional_override_path` keeps `candidate.exists()` (the brief allows either option). A directory named `AAPL.yaml` is almost certainly a mistake; refusing it as unreadable surfaces it on the ticker's line ("AAPL: cannot value — override file …/AAPL.yaml cannot be read: [Errno 21] Is a directory …") instead of quietly valuing AAPL without the assumptions the user meant to give. The PR states this choice.

## Out of scope

- Report render/write failures (#178), whether the screener's second pass should fail loudly on a bad override (#77), and the TLA+ analyze model: all excluded by the brief.
- The pipeline boards (`docs/pipeline/analyze*.d2`) list the reasons `load_override` refuses a file. Adding "cannot be read" there needs a d2 v0.9.0 re-render (not available locally; CI artifact `pipeline-render`) and is not required by any criterion. Candidate follow-up.

## Review Focus

1. A `--override` file that exists and is readable must still apply (no regression from wrapping the read) — covered by the existing `test_analyze_applies_override` and `test_analyze_explicit_override_wins_over_convention`.
2. An `OSError` raised by YAML parsing is impossible (parsing a string), but an `OSError` subclass from `read_text` other than `PermissionError` / `IsADirectoryError` (e.g. `EIO`) must also become `ValueError` — the wrap catches `OSError`, and the unit test parametrises over a generic `OSError(errno.EIO, ...)`.
3. A `UnicodeDecodeError` from a binary override file is a `ValueError` already and keeps reaching `_analyze_one` as "cannot value" — no change, not tested here.
4. The unreadable ticker writes no partial reports: AAPL has no files in the analysis dir while MSFT's three are there — asserted in the CLI tests.
5. `bot screen` with an unreadable shortlisted override keeps the ticker in the shortlist with `margin_of_safety is None` (existing fallback), and portfolio marks leave that holding unvalued — asserted in Task 2.

---

### Task 1: `load_override` refuses an unreadable file with `ValueError`

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`load_override`, ~lines 802-816; docstring of `load_override` and of `conventional_override_path`)
- Test: `tests/unit/test_valuator_assumptions.py`, `tests/unit/test_cli_analyze.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `load_override(override_path: Path | None) -> dict[str, Any]` (signature unchanged) now raises `ValueError("override file {path} cannot be read: {exc}")` chained from the `OSError` for a path that exists but cannot be read.

- [ ] **Step 1: Failing unit tests** (in `test_valuator_assumptions.py`, already committed in stage 3)

`test_load_override_unreadable_file_is_a_value_error` — parametrised over `PermissionError(errno.EACCES, "Permission denied")` and `OSError(errno.EIO, "Input/output error")`; writes `AAPL.yaml`, monkeypatches `Path.read_text` to raise that error for that path only; asserts `pytest.raises(ValueError, match=re.escape(f"override file {path} cannot be read"))` and `excinfo.value.__cause__ is the_error`.

`test_load_override_directory_is_a_value_error` — `path = tmp_path / "AAPL.yaml"; path.mkdir()`; asserts `ValueError` matching `override file {path} cannot be read` with `isinstance(__cause__, IsADirectoryError)`.

`test_conventional_override_path_passes_a_directory_on` — `(tmp_path / "AAPL.yaml").mkdir()`; `conventional_override_path(tmp_path, "AAPL") == tmp_path / "AAPL.yaml"` (pins the decision above).

- [ ] **Step 2: Failing CLI tests** (in `test_cli_analyze.py`, using the existing `_batch_env`, `_analysis_dir`, `_names`, `_MSFT_SET`)

`test_batch_unreadable_conventional_override_fails_the_ticker_alone` — `assumptions/AAPL.yaml` written, `Path.read_text` monkeypatched to raise `PermissionError(errno.EACCES, "Permission denied")` for that path; `analyze AAPL MSFT` → `exit_code == 1`, `"AAPL: cannot value"` and the path in `stderr`, `_names(...) == _MSFT_SET`, no non-`SystemExit` exception.

`test_batch_directory_conventional_override_fails_the_ticker_alone` — `assumptions/AAPL.yaml` is a directory; same assertions (exit 1 is the worst per-ticker code: AAPL 1, MSFT 0).

`test_analyze_unreadable_explicit_override_cannot_value` — `--override x/AAPL.yaml` that exists, read raises `PermissionError`; `exit_code == 1`, `"AAPL: cannot value"` and the path in `stderr`, `result.exception` is a `SystemExit`.

- [ ] **Step 3: Run them, verify they fail**

Run: `uv run pytest -q tests/unit/test_valuator_assumptions.py tests/unit/test_cli_analyze.py -k "unreadable or directory"`
Expected: the new tests FAIL with `PermissionError` / `IsADirectoryError` escaping; `test_conventional_override_path_passes_a_directory_on` and the existing #214 directory test already pass.

- [ ] **Step 4: Implement**

In `load_override`, put `override_path.read_text()` in its own `try` / `except OSError as exc: raise ValueError(f"override file {override_path} cannot be read: {exc}") from exc`, before the YAML parse (which keeps its own `yaml.YAMLError` handler). Update the docstring: an unreadable file (including a directory) is a `ValueError` too. In `conventional_override_path`'s docstring, say a non-file at the path is passed on and refused by `load_override`.

- [ ] **Step 5: Run, verify they pass; full suite**

Run: `uv run pytest -q` and `uv run ruff check . && uv run mypy src`
Expected: all green.

- [ ] **Step 6: Commit** — `fix(#227): an unreadable override fails its ticker alone`

### Task 2: the screener and portfolio marks survive an unreadable override

No production code expected: both already catch `ValueError`. These tests pin it.

**Files:**
- Test: `tests/unit/test_screener_engine.py`, `tests/unit/test_portfolio_marks.py`

**Interfaces:**
- Consumes: Task 1's `ValueError` from `load_override`.
- Produces: nothing.

- [ ] **Step 1: Failing tests** (committed in stage 3)

`test_run_screen_unreadable_override_falls_back` (screener) — seed like `test_run_screen_honours_assumptions_dir_override`; `assumptions_dir / "AAA.yaml"` is a directory; `run_screen(conn, _value_preset(), top=1, assumptions_dir=assumptions_dir)` returns without raising, `shortlist[0].ticker == "AAA"`, `shortlist[0].margin_of_safety is None`.

`test_mark_holdings_unreadable_override_leaves_the_holding_unvalued` (marks) — seed like `test_mark_holdings_stores_the_converted_price` (`_seed_valuable`, `_hold(conn, "AAPL")`), `tmp_path / "AAPL.yaml"` is a directory; `mark_holdings(conn, DAY, assumptions_dir=tmp_path)` returns one mark with `intrinsic_value is None`.

- [ ] **Step 2: Verify they fail before Task 1 and pass after it**

Run: `uv run pytest -q tests/unit/test_screener_engine.py tests/unit/test_portfolio_marks.py -k unreadable`

- [ ] **Step 3: Commit** (only if anything changed beyond stage 3).
