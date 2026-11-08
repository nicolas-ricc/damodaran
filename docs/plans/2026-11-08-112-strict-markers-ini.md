# Unregistered pytest markers fail collection under pytest 9 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plain `uv run pytest`, with no extra flags, fails at collection when a test uses a marker that `[tool.pytest.ini_options].markers` does not list.

**Architecture:** Config only. `pyproject.toml` drops the ineffective `--strict-markers` from `addopts`, sets the pytest 9 ini key `strict_markers = true`, and raises the dev floor to `pytest>=9.0` so the key always exists. A new `pytester` test runs the repo's real `pyproject.toml` against a throwaway test that uses an unregistered marker, and asserts the collection error. The `test_live_marker.py` sandbox ini, which copies the same ineffective flag, switches to the ini key too.

**Tech Stack:** Python 3.12, pytest 9.0.3 (locked in `uv.lock`), `pytester`, `tomllib`, ruff, mypy --strict.

**Spec:** GitHub issue #112 (`gh issue view 112 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec.

## Global Constraints

- Use the ini key `strict_markers = true` under `[tool.pytest.ini_options]`. Do not rely on `-o strict_markers=true`.
- Do not use pytest 9's umbrella `strict = true` (out of scope: it turns on other strictness modes).
- Do not change which markers are registered (`integration`, `live` stay exactly as they are).
- No dead or ineffective strict-marker flag remains in `addopts`. `-v` stays.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` stay green.

## Assumptions (declared)

- **Root cause.** In pytest 9.0.3 `--strict-markers` is an `OverrideIniAction`: it appends `strict_markers=true` to `override_ini` (`_pytest/main.py:84-90`, `_pytest/config/argparsing.py:577`). `MarkGenerator.__getattr__` reads only `getini("strict_markers")`, falling back to `getini("strict")` (`_pytest/mark/structures.py:588-591`). `Config.parse` builds the ini config with `determine_setup(override_ini=ns.override_ini, ...)` from the command-line args alone (`_pytest/config/__init__.py:1500-1506`). Only afterwards does it prepend `getini("addopts")` to the args (`:1527-1530`). So an override that comes from `addopts` never reaches `inicfg`, and the run only warns. Setting the ini key directly is what `MarkGenerator` reads. Reproduced with `uv run pytest tests/unit/test_zz_bogus.py -q`: `1 passed, 1 warning`.
- **The test uses the real `pyproject.toml`, verbatim.** `pytester.makepyprojecttoml(<repo pyproject.toml text>)` copies the whole file into the sandbox, so the test checks the configuration a developer actually runs, not a hand-written copy that could drift. The sandbox run passes the test file path explicitly (`runpytest("test_bogus.py")`), so `testpaths = ["tests"]` is ignored there (pytest uses `testpaths` only without positional args). The path is anchored on the test file (`Path(__file__).resolve().parents[2] / "pyproject.toml"`), as in `tests/unit/test_mos_thresholds.py` and the #291 fixture-path fix.
- **In-process `runpytest`.** `tests/unit/test_live_marker.py:9,27` already uses in-process `pytester.runpytest` with `pytest_plugins = ["pytester"]`. The new module follows the same pattern. `Pytester.__init__` chdirs into its tmp path (`_pytest/pytester.py:698,748-753`), and with a positional arg the rootdir search starts at that arg. The sandbox `pyproject.toml` is therefore the config file. Observed with a prototype: `rootdir: /tmp/pytest-of-root/.../test_p0`, `configfile: pyproject.toml`. Before the fix the prototype gave `1 passed, 1 warning`. With `addopts = "-v"` + `strict_markers = true` it gave `'bogus' not found in `markers` configuration option` (emitted at `_pytest/mark/structures.py:593`).
- **Pytest floor raised to `>=9.0`.** `pyproject.toml` declares `"pytest>=8.2"` in `[dependency-groups].dev`. `strict_markers` is a pytest 9 ini key, so under pytest 8 it would be unknown and strictness would silently vanish. The lock already resolves 9.0.3, and `uv lock` after the bump changes only the `requires-dev` specifier line in `uv.lock` (verified). Rejected: keeping both `addopts --strict-markers` and the ini key for pytest 8 compatibility, because AC 3 forbids the dead flag.
- **Current markers are all registered.** `grep -rhoE "pytest\.mark\.[a-z_]+" tests` finds `integration`, `live` (registered in `pyproject.toml`), `vcr` (registered by `pytest_vcr.py:37-38` through `addinivalue_line('markers', ...)`), and the builtins `parametrize`, `skip`, `skipif`, `usefixtures`. The one `add_marker` call adds `skip`.
- **`addopts` is checked token by token.** `addopts` is a TOML string today (`pyproject.toml:78`). The test normalises a string with `shlex.split` and a list as is, then asserts that neither `--strict-markers` nor `--strict` is a token. That covers a later list form and does not ban an unrelated `--strict-config`.
- **No other document needs the change.** `grep -rn "strict.markers\|strict_markers"` over `*.md *.py *.toml *.yml *.cfg *.ini` (outside `.venv`) hits only `pyproject.toml:78`, `tests/unit/test_live_marker.py:25` and three historical plans. CI runs `uv run pytest -q` (`.github/workflows/site.yml:23`).
- **The floor test reads the specifier, not the string.** It uses `packaging.requirements.Requirement` (`packaging` 26.2 is installed as a pytest dependency). So `pytest>=9`, `pytest>=9.0,<10` and `pytest~=9.0` all pass. Rejected: a literal string match, which breaks on any equivalent spelling.
- **`uv.lock` must be regenerated.** CI and `.factory/setup.sh` both run `uv sync --frozen` (`.github/workflows/site.yml:20`, `.factory/setup.sh:10`), which installs from the lock without re-resolving. The floor bump is at `pyproject.toml:31`. No other file pins pytest. `uv lock` ran in this environment without error and changed one line. If it fails, Step 7 has not committed yet, and `git checkout pyproject.toml uv.lock` restores the tree.
- **The ban on the flag in `addopts` is AC 3, verbatim:** "No dead or ineffective strict-marker flag remains in `addopts`". With `strict_markers = true` set, the flag would be redundant even if a later pytest honoured it again.
- **The sandbox config is the deciding one.** `pytester` builds a fresh `Config` per `runpytest`. Entry-point plugins load there too (`pytest_vcr` registers only `vcr`), but the repo's `tests/conftest.py` is outside the sandbox. The prototype shows the sandbox config deciding the outcome both ways: the bogus test passed without the ini key and failed with it, with `Interrupted: 1 error during collection` (exit code 2 = `ExitCode.INTERRUPTED`). The repo's `[tool.pytest.ini_options]` holds only `testpaths`, `addopts`, `markers` (`pyproject.toml:76-82`): no `filterwarnings`, `-m`, `-p` or `pythonpath` that could change the sandbox run.
- **Ini-format booleans.** `_getini_ini` parses `type="bool"` with `_strtobool` (`_pytest/config/__init__.py:1758`), so `strict_markers = true` in the `test_live_marker.py` tox-style ini is a real boolean.
- **The green control test in the red commit.** `test_registered_marker_still_collects` is a guard against over-strictness, not an eval of the bug, so it is green before the fix by design. Repo precedent puts the whole eval module in `test(#N): evals`.
- **Style.** Ruff applies `E,F,W,I,N,B,UP,RUF,SIM,TID` everywhere (`pyproject.toml:59`). There are no `D`/`ANN` rules, so `dict[str, Any]` and test functions without docstrings pass, as in `test_live_marker.py`. Comments in `pyproject.toml` cite issue numbers in parentheses (`pyproject.toml:61`, "(#217)"), so the new comment ends with "(#112)".
- **A red-evals commit that stalls.** If Step 6 finds a problem, the branch stays unmerged with the red commit, and the stall is reported on the issue (pipeline rule). Nothing reaches `master` red.
- **The `test_live_marker.py` sandbox ini changes too.** Its `addopts = --strict-markers` (line 25) copies the repo flag and is just as ineffective. Switching it to `strict_markers = true` keeps the sandbox matching the repo config. The edit doesn't change those tests' assertions: `live` is registered there.
- **Historical plans are not edited.** `docs/plans/2026-10-12-51-*.md`, `docs/plans/2026-11-08-100-*.md` and `docs/superpowers/plans/2026-05-25-m1-*.md` quote the old `addopts`. They record what was planned at the time, so they stay as written.
- **Plan location `docs/plans/`.** Recent issue plans live there.

## Review Focus

1. A registered marker that strict mode breaks by accident: `test_registered_marker_still_collects` runs an `@pytest.mark.integration` test under the same config, expects `passed=1`, and expects no `PytestUnknownMarkWarning`. A run that ignored the sandbox config would print that warning.
2. Someone later re-adds `--strict-markers` to `addopts` thinking it does the job: `test_addopts_has_no_strict_marker_flag` fails on it.
3. Someone "simplifies" to `strict = true` (out of scope per the Agent Brief): `test_strict_markers_ini_key_is_set` asserts `strict_markers is True` and `"strict" not in ini_options`.
4. Someone installs pytest 8, where `strict_markers` is unknown: `test_pytest_floor_is_9` asserts that the dev pytest specifier rejects 8.4.2 and accepts the locked 9.0.3.
5. The sandbox does not pick up the repo config (a wrong path or a sandbox `pytest.ini` shadowing it): the bogus test asserts the exact error text `'bogus' not found in `markers` configuration option`, which only the strict path prints.
6. None further: the change has no runtime code path.

## Acceptance criteria → tasks

| Issue item | Task |
|---|---|
| AC 1 (throwaway unregistered-marker test fails collection, proven by `pytester`) | Task 1 |
| AC 2 (full suite, ruff, mypy green) | Task 1, step 6 |
| AC 3 (no dead strict-marker flag in `addopts`) | Task 1 |
| Not in the ACs: the `test_live_marker.py:25` sandbox ini, the `strict` ban, the pytest floor | Task 1. All three are declared in Assumptions and Review Focus: they keep AC 1 true over time. |

---

### Task 1: `strict_markers = true` in pyproject, proven by a pytester test

**Files:**
- Create: `tests/unit/test_strict_markers.py` (imports `shlex`, `tomllib`, `Path`, `Any`, `pytest`, `packaging.requirements.Requirement`)
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`, lines 76-82: `testpaths`, `addopts`, `markers`; and `"pytest>=8.2"` in `[dependency-groups].dev`)
- Modify: `uv.lock` (regenerated by `uv lock`; only the `requires-dev` pytest specifier changes)
- Modify: `tests/unit/test_live_marker.py:25`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_strict_markers.py`

Module docstring: one line saying unregistered markers fail collection under the repo's pytest config (#112). `pytest_plugins = ["pytester"]`. `_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"`. A helper `_pyproject() -> dict[str, Any]` returns `tomllib.loads(_PYPROJECT.read_text())`. A second helper `_ini_options()` returns its `["tool"]["pytest"]["ini_options"]`. A helper `_run(pytester, marker: str) -> pytest.RunResult` writes `_PYPROJECT.read_text()` with `pytester.makepyprojecttoml`, writes `test_bogus.py` with a test marked `@pytest.mark.<marker>`, and returns `pytester.runpytest("test_bogus.py")`.

```python
def test_unregistered_marker_fails_collection(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "bogus")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*'bogus' not found in `markers` configuration option*"])

def test_registered_marker_still_collects(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "integration")
    result.assert_outcomes(passed=1)
    assert "PytestUnknownMarkWarning" not in result.stdout.str()

def test_strict_markers_ini_key_is_set() -> None:
    options = _ini_options()
    assert options["strict_markers"] is True
    assert "strict" not in options

def test_addopts_has_no_strict_marker_flag() -> None:
    addopts = _ini_options()["addopts"]
    tokens = shlex.split(addopts) if isinstance(addopts, str) else addopts
    assert "--strict-markers" not in tokens
    assert "--strict" not in tokens

def test_pytest_floor_is_9() -> None:
    (spec,) = [Requirement(r) for r in _pyproject()["dependency-groups"]["dev"] if Requirement(r).name == "pytest"]
    assert not spec.specifier.contains("8.4.2")
    assert spec.specifier.contains("9.0.3")
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/unit/test_strict_markers.py -q`
Expected: `test_unregistered_marker_fails_collection` FAILS (the sandbox reports `passed=1`), `test_strict_markers_ini_key_is_set` FAILS with `KeyError: 'strict_markers'`, `test_addopts_has_no_strict_marker_flag` FAILS, `test_pytest_floor_is_9` FAILS, `test_registered_marker_still_collects` PASSES.

- [ ] **Step 3: Commit the red evals**

`git add tests/unit/test_strict_markers.py && git commit -m "test(#112): evals"`

- [ ] **Step 4: Fix the config**

In `pyproject.toml` `[tool.pytest.ini_options]`: `addopts = "-v"`, and a new line `strict_markers = true` with a one-line `#` comment above it: pytest 9 reads the ini key, and `--strict-markers` in `addopts` only warned (#112). In `[dependency-groups].dev` replace `"pytest>=8.2"` with `"pytest>=9.0"`, then run `uv lock`. `uv.lock` changes by one line. In `tests/unit/test_live_marker.py:25` replace `addopts = --strict-markers\n` with `strict_markers = true\n` in the `makeini` string.

- [ ] **Step 5: Run the new tests and the live-marker tests**

Run: `uv run pytest tests/unit/test_strict_markers.py tests/unit/test_live_marker.py -q`
Expected: 8 passed (5 new + the 3 in `test_live_marker.py`: `test_live_tests_are_skipped_by_default`, `test_live_tests_run_when_opted_in`, `test_live_marker_is_registered`. None of them asserts warn-only behaviour).

- [ ] **Step 6: Full gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: all green. If any existing test uses an unregistered marker it now errors at collection. Report it instead of registering a new marker (out of scope).

- [ ] **Step 7: Commit**

`git add pyproject.toml uv.lock tests/unit/test_live_marker.py && git commit -m "fix(#112): strict_markers ini key replaces the ineffective addopts flag"`

## Grilling

- Two rounds (griller model: fable). Round 1: 15 questions. Round 2: 14 questions.
- Sources, round 1: CODE 13 (pytest 9.0.3 source, `pyproject.toml`, `tests/`, a prototype run), DOC 1 (AGENTS.md skill paths), NO SOURCE 1 (red commit rollback → technical assumption).
- Sources, round 2: CODE 11, ISSUE 1 (AC 3 quoted for the flag ban), NO SOURCE 2 (floor-test form; green control test in the red commit → technical assumptions).
- Assumptions added: the pytest floor `>=9.0` with `uv lock`; the `addopts` token check; the no-warning assertion on the registered-marker test; the floor test reading the specifier; the root cause cited to `Config.parse`; the sandbox config being the deciding one; ini-format booleans; style.
- Spec ambiguities: none. Out of scope: none. No follow-up issues opened.
- Result: `ok`.
