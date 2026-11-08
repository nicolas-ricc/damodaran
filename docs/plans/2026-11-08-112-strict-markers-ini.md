# Unregistered pytest markers fail collection under pytest 9 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plain `uv run pytest`, with no extra flags, fails at collection when a test uses a marker that `[tool.pytest.ini_options].markers` does not list.

**Architecture:** Config only. `pyproject.toml` drops the ineffective `--strict-markers` from `addopts` and sets the pytest 9 ini key `strict_markers = true`. A new `pytester` test runs the repo's real `pyproject.toml` against a throwaway test that uses an unregistered marker, and asserts the collection error. The `test_live_marker.py` sandbox ini, which copies the same ineffective flag, switches to the ini key too.

**Tech Stack:** Python 3.12, pytest 9.0.3 (locked in `uv.lock`), `pytester`, `tomllib`, ruff, mypy --strict.

**Spec:** GitHub issue #112 (`gh issue view 112 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec.

## Global Constraints

- Use the ini key `strict_markers = true` under `[tool.pytest.ini_options]`. Do not rely on `-o strict_markers=true`.
- Do not use pytest 9's umbrella `strict = true` (out of scope: it turns on other strictness modes).
- Do not change which markers are registered (`integration`, `live` stay exactly as they are).
- No dead or ineffective strict-marker flag remains in `addopts`. `-v` stays.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` stay green.

## Assumptions (declared)

- **Root cause.** In pytest 9.0.3 `--strict-markers` is an `OverrideIniAction` that sets the `strict_markers` ini key (`_pytest/main.py:84-90`), and `MarkGenerator.__getattr__` reads only `getini("strict_markers")`, falling back to `getini("strict")` (`_pytest/mark/structures.py:588-591`). When the flag comes from `addopts`, the override does not reach `getini`, so the run only warns. Setting the ini key directly is what `MarkGenerator` reads. Reproduced on this checkout: `1 passed, 1 warning`.
- **The test uses the real `pyproject.toml`, verbatim.** `pytester.makepyprojecttoml(<repo pyproject.toml text>)` copies the whole file into the sandbox, so the test checks the configuration a developer actually runs, not a hand-written copy that could drift. The sandbox run passes the test file path explicitly (`runpytest("test_bogus.py")`), so `testpaths = ["tests"]` is ignored there (pytest uses `testpaths` only without positional args). The path is anchored on the test file (`Path(__file__).resolve().parents[2] / "pyproject.toml"`), as in `tests/unit/test_mos_thresholds.py` and the #291 fixture-path fix.
- **In-process `runpytest`.** `tests/unit/test_live_marker.py` already uses in-process `pytester.runpytest` with `pytest_plugins = ["pytester"]`. The new module follows the same pattern. Before the fix, this in-process run reproduces the bug: the bogus test passes.
- **The `test_live_marker.py` sandbox ini changes too.** Its `addopts = --strict-markers` (line 25) copies the repo flag and is just as ineffective. Switching it to `strict_markers = true` keeps the sandbox matching the repo config. The edit doesn't change those tests' assertions: `live` is registered there.
- **Historical plans are not edited.** `docs/plans/2026-10-12-51-*.md`, `docs/plans/2026-11-08-100-*.md` and `docs/superpowers/plans/2026-05-25-m1-*.md` quote the old `addopts`. They record what was planned at the time, so they stay as written.
- **Plan location `docs/plans/`.** Recent issue plans live there.

## Review Focus

1. A registered marker that strict mode breaks by accident: `test_registered_marker_still_collects` runs an `@pytest.mark.integration` test under the same config and expects `passed=1`.
2. Someone later re-adds `--strict-markers` to `addopts` thinking it does the job: `test_addopts_has_no_strict_marker_flag` fails on it.
3. Someone "simplifies" to `strict = true`: `test_strict_markers_ini_key_is_set` asserts `strict_markers is True` and `"strict" not in ini_options`.
4. The sandbox does not pick up the repo config (a wrong path or a sandbox `pytest.ini` shadowing it): the bogus test asserts the exact error text `'bogus' not found in `markers` configuration option`, which only the strict path prints.
5. None further: the change has no runtime code path.

## Acceptance criteria → tasks

| Issue item | Task |
|---|---|
| AC 1 (throwaway unregistered-marker test fails collection, proven by `pytester`) | Task 1 |
| AC 2 (full suite, ruff, mypy green) | Task 1, step 6 |
| AC 3 (no dead strict-marker flag in `addopts`) | Task 1 |

---

### Task 1: `strict_markers = true` in pyproject, proven by a pytester test

**Files:**
- Create: `tests/unit/test_strict_markers.py`
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`, lines 76-82)
- Modify: `tests/unit/test_live_marker.py:25`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_strict_markers.py`

Module docstring: one line saying unregistered markers fail collection under the repo's pytest config (#112). `pytest_plugins = ["pytester"]`. `_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"`. A helper `_ini_options() -> dict[str, Any]` returns `tomllib.loads(_PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]`. A helper `_run(pytester, marker: str) -> pytest.RunResult` writes `_PYPROJECT.read_text()` with `pytester.makepyprojecttoml`, writes `test_bogus.py` with a test marked `@pytest.mark.<marker>`, and returns `pytester.runpytest("test_bogus.py")`.

```python
def test_unregistered_marker_fails_collection(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "bogus")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*'bogus' not found in `markers` configuration option*"])

def test_registered_marker_still_collects(pytester: pytest.Pytester) -> None:
    _run(pytester, "integration").assert_outcomes(passed=1)

def test_strict_markers_ini_key_is_set() -> None:
    options = _ini_options()
    assert options["strict_markers"] is True
    assert "strict" not in options

def test_addopts_has_no_strict_marker_flag() -> None:
    assert "--strict" not in _ini_options()["addopts"]
```

(`"--strict" not in addopts` covers `--strict-markers` and `--strict` at once.)

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/unit/test_strict_markers.py -q`
Expected: `test_unregistered_marker_fails_collection` FAILS (the sandbox reports `passed=1`), `test_strict_markers_ini_key_is_set` FAILS with `KeyError: 'strict_markers'`, `test_addopts_has_no_strict_marker_flag` FAILS, `test_registered_marker_still_collects` PASSES.

- [ ] **Step 3: Commit the red evals**

`git add tests/unit/test_strict_markers.py && git commit -m "test(#112): evals"`

- [ ] **Step 4: Fix the config**

In `pyproject.toml` `[tool.pytest.ini_options]`: `addopts = "-v"`, and a new line `strict_markers = true` with a one-line `#` comment above it: pytest 9 reads the ini key, and `--strict-markers` in `addopts` only warned (#112). In `tests/unit/test_live_marker.py:25` replace `addopts = --strict-markers\n` with `strict_markers = true\n` in the `makeini` string.

- [ ] **Step 5: Run the new tests and the live-marker tests**

Run: `uv run pytest tests/unit/test_strict_markers.py tests/unit/test_live_marker.py -q`
Expected: 7 passed.

- [ ] **Step 6: Full gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: all green. If any existing test uses an unregistered marker it now errors at collection. Report it instead of registering a new marker (out of scope).

- [ ] **Step 7: Commit**

`git add pyproject.toml tests/unit/test_live_marker.py && git commit -m "fix(#112): strict_markers ini key replaces the ineffective addopts flag"`
