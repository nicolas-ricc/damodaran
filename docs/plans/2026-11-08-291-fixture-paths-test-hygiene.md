# Damodaran fixture paths and three test assertions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Damodaran dataset tests find their fixtures from any working directory and fail (never skip) when one is missing; a misnamed test is renamed; the fill-rate test and the `AssumptionSource` reachability test assert what their names claim.

**Architecture:** Test-only. Two module-level path constants are re-anchored on `__file__` and the `skipif` guards around them are deleted; one test is renamed; two test bodies are tightened. Nothing under `src/` changes.

**Tech Stack:** Python 3.12, pytest, DuckDB, ruff, mypy --strict.

**Spec:** GitHub issue #291 (`gh issue view 291 --repo nicolas-ricc/damodaran`). Its four "Decisions (taken by the planner; do not reopen)" and its six acceptance criteria are binding. Story context: #64 (plan comment, item 3 and item 5).

## Global Constraints

- No change under `src/`. Only `tests/unit/test_damodaran_datasets.py`, `tests/unit/test_damodaran_derived.py`, `tests/unit/test_valuator_assumptions.py` and `tests/conftest.py` change (the last added in execution, see Assumptions).
- Fixture root in both dataset modules: `_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "damodaran"`; every fixture path derives from it.
- `_ALL_FIXTURES_PRESENT` and every `skipif` decorator disappear from the two dataset modules (7 in `test_damodaran_datasets.py`, 3 in `test_damodaran_derived.py`).
- `tests/unit/test_ibkr_flex_capture.py:327-335` keeps its `Path("tests/fixtures/...")` spellings (cwd-relative by design).
- New test name: `test_the_margin_file_wins_the_columns_it_shares_with_psdata`; body unchanged.
- Fill-rate assertion: `count >= 0.9 * total` per column, `total = COUNT(*)` from `damodaran_industry`, message names the column and both numbers. Column list unchanged (nine columns).
- Reachability: every `AssumptionSource` member appears as `AssumptionSource.<NAME>` in the source of at least one `bot.valuator` module; the existing eight-value set assertion stays as a second assertion.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- **Which "26 passed" is meant.** The two modules collect 26 tests today (16 passed + 10 skipped from `tests/`, 26 passed from the root). The rename keeps the count; nothing is added, so 26 stays the target from both directories.
- **Stage-3 evals live outside the repo.** The issue is test-only: the committed tests *are* the deliverable, and the behaviour they cover already works, so no in-repo test can fail before the change and pass after it without being one of the deliverables. The acceptance criteria (including the two temporary mutations) become an executable script, `.scratch/evals-291.sh`, git-excluded, which fails on the base branch and must pass at the end.
- **Config defaults anchored in `tests/conftest.py` (found in Task 1 execution).** Without the guards, four tests run from `tests/` and fail with `assumption 'terminal_growth' is unresolved`: `bot.reference.currencies.DEFAULT_CURRENCIES_PATH` and `bot.reference.default_spreads.DEFAULT_SPREADS_PATH` are cwd-relative (`src/bot/reference/currencies.py:25`, `default_spreads.py:27`). Criterion 1 needs 26 passed from `tests/` and the issue forbids `src/` changes, so an autouse fixture in `tests/conftest.py`, beside `_currencies_path` (#109, same purpose for the CLI), monkeypatches both constants to `REPO_ROOT / "config" / ...`. Rejected: anchoring the constants in `src/` (forbidden by the issue; the product runs from the repo root by design), and a per-module fixture duplicated in the two dataset modules.
- **Who writes the eval script.** Pipeline stage 3, before Task 1, adds `.scratch/` to `.git/info/exclude` and writes the script; it restores both mutated files with a shell `trap ... EXIT` (`git checkout -- <file>`), and Task 3 Step 3's `git diff --stat -- src` would still catch a leftover `PROBE`.
- **Empty import guard.** The fill-rate test also asserts `total > 0` (rejected: relying on `result.status == "success"` alone, which does not prove rows were written). The issue fixes the per-column assertion; this extra line only closes the vacuous `0 >= 0` case.
- **Mutation probes are temporary.** The `0.97` threshold and the `PROBE = "probe"` member are applied, observed failing and reverted inside the eval script; neither is ever committed.
- **The scan counts `AssumptionSource.<NAME>` tokens with a regex** (`r"AssumptionSource\.([A-Z_]+)"`) over every module's source. The enum body declares members as `NAME = "value"`, never `AssumptionSource.NAME`, so no body stripping is needed (the issue allows this equivalent).

## Review Focus

- Running pytest from `tests/` or from any other directory: every dataset test runs, none skips. Pinned by the eval script, criterion 1.
- A committed fixture deleted or renamed: the test errors with a missing-file error instead of skipping. Pinned by the absence of any guard (criterion 2 grep).
- A header drift leaving one column mostly NULL: the fill-rate test fails naming the column. Pinned by the `0.97` mutation (criterion 4).
- A new `AssumptionSource` member nobody emits: the reachability test fails naming it. Pinned by the `PROBE` mutation (criterion 5).
- A `bot.valuator` submodule whose import has side effects or fails: the scan imports every submodule; today the seven submodules (`analysis`, `assumptions`, `dcf`, `hypergrowth`, `narrative_flags`, `sensitivity`, `story_types`; no subpackage) import cleanly in the unit suite, and an import error fails the test loudly, which is the wanted outcome. No extra test.

---

### Task 1: Anchor the fixture paths on the test file and drop the guards

**Files:**
- Modify: `tests/unit/test_damodaran_datasets.py:27-40` and the seven `@pytest.mark.skipif` lines (145, 201, 212, 224, 263, 294, 319)
- Modify: `tests/unit/test_damodaran_derived.py:22-36` and the three `@pytest.mark.skipif` lines (86, 96, 147)

**Interfaces:**
- Produces: `_FIXTURES`, `_WACC_FIXTURE`, `_CTRY_FIXTURE`, `_EXTRA_FIXTURES` keep their names and types (`Path`, `dict[str, Path]`) in both modules.

- [ ] **Step 1: Observe the failure.** Run `cd tests && uv run --project .. pytest -q -p no:cacheprovider unit/test_damodaran_datasets.py unit/test_damodaran_derived.py`. Expected: `16 passed, 10 skipped`.
- [ ] **Step 2: In `test_damodaran_datasets.py`,** set `_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "damodaran"`, delete `_ALL_FIXTURES_PRESENT` and the seven decorators.
- [ ] **Step 3: In `test_damodaran_derived.py`,** add the same `_FIXTURES`, derive `_WACC_FIXTURE`, `_CTRY_FIXTURE` and `_EXTRA_FIXTURES` (`_FIXTURES / f"{key}_sample.xls"`, same six keys) from it, delete `_ALL_FIXTURES_PRESENT` and the three decorators. Drop `import pytest` only if nothing else uses it (it is used by `pytest.approx`, so it stays).
- [ ] **Step 4: Verify.** The Step-1 command and `uv run pytest -q -p no:cacheprovider tests/unit/test_damodaran_datasets.py tests/unit/test_damodaran_derived.py` from the root both give `26 passed`, no skip. `grep -n 'skipif\|_ALL_FIXTURES_PRESENT\|Path("tests/' tests/unit/test_damodaran_datasets.py tests/unit/test_damodaran_derived.py` prints nothing. `uv run ruff check tests` clean.
- [ ] **Step 5: Commit** `test(#291): anchor Damodaran fixture paths on the test file, drop the skipif guards`.

### Task 2: Rename the margin-precedence test and assert a real fill rate

**Files:**
- Modify: `tests/unit/test_damodaran_datasets.py` (`test_real_import_fills_the_columns_the_extra_datasets_publish`, `test_the_cost_of_capital_file_wins_the_columns_it_shares`)

**Interfaces:**
- Consumes: Task 1's `_FIXTURES`-derived constants.

- [ ] **Step 1: Rename** `test_the_cost_of_capital_file_wins_the_columns_it_shares` to `test_the_margin_file_wins_the_columns_it_shares_with_psdata`. Body and docstring unchanged.
- [ ] **Step 2: Tighten the fill-rate test.** The query selects `COUNT(*)` first, then the nine `COUNT(col)`; the loop asserts:

```python
assert count >= 0.9 * total, f"{column}: {count} of {total} industries populated"
```

  Before the loop, `assert total > 0, "the import wrote no industry rows"`, so an empty table cannot pass `count >= 0.9 * 0` vacuously. Update the docstring to say every mapped column arrives populated for at least 90% of industries.
- [ ] **Step 3: Prove it is live.** Temporarily change `0.9` to `0.97`; the test fails on `roe` (`92 of 96`). Revert.
- [ ] **Step 4: Verify.** `uv run pytest -q tests/unit/test_damodaran_datasets.py` → 15 passed (the module's count, no skip); `uv run pytest -q tests/unit/test_damodaran_datasets.py -k cost_of_capital` selects nothing.
- [ ] **Step 5: Commit** `test(#291): rename the margin-precedence test, assert a 90% fill rate per column`.

### Task 3: Make the `AssumptionSource` reachability test real

**Files:**
- Modify: `tests/unit/test_valuator_assumptions.py:994` (`test_assumption_source_has_no_unreachable_member`)

**Interfaces:**
- Consumes: `bot.valuator` package (`__path__`, `__name__`), `bot.valuator.assumptions.AssumptionSource`.

- [ ] **Step 1: Replace the body.** Walk `pkgutil.iter_modules(bot.valuator.__path__)`, `importlib.import_module(f"bot.valuator.{info.name}")`, `inspect.getsource(module)`; collect `re.findall(r"AssumptionSource\.([A-Z_]+)", source)` into a set `referenced`. First assertion:

```python
unreachable = {member.name for member in AssumptionSource} - referenced
assert not unreachable, f"AssumptionSource members nothing emits: {sorted(unreachable)}"
```

  Second assertion: the existing eight-value set, unchanged, with its `ANALYST_CONSENSUS` comment. Docstring: the test proves every member is referenced by name somewhere in `bot.valuator` outside the enum body, and pins the member list. Imports (`importlib`, `inspect`, `pkgutil`, `re`, `bot.valuator`) go local to the test, like the existing local `AssumptionSource` import.
- [ ] **Step 2: Prove it is live.** Temporarily add `PROBE = "probe"` to `AssumptionSource` in `src/bot/valuator/assumptions.py`; the test fails on the reachability assertion naming `PROBE`. Revert (`git checkout src/bot/valuator/assumptions.py`).
- [ ] **Step 3: Verify.** `uv run pytest -q tests/unit/test_valuator_assumptions.py -k unreachable` → 1 passed; `git diff --stat origin/feature/64-remediation-follow-ups -- src` empty.
- [ ] **Step 4: Commit** `test(#291): assumption-source test checks reachability by source scan`.

### Final verification

- [ ] `.scratch/evals-291.sh` passes; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Grilling

- Rounds: 1 (revisions were local: one assertion, two clarifications; no step added or removed, no seam changed).
- Questions: 17. Sources: ISSUE 9, CODE 7, DOC 0, NO SOURCE 2 (both technical assumptions).
- Answers in brief: criteria 3 and 6 are the rename (Task 2 Step 1) and the final lint+suite (Final verification); `bot.valuator` has no subpackage and no `AssumptionSource.<NAME>` reference exists outside it (`grep -rn` over `src/`); the regex scan, comments included, is the variant the issue's decision 4 allows; 96/92 and the per-column counts are measured in the issue body (only `roe` is under 97%); line numbers are from base `bf1c94b`; no `pytest.skip`, `importorskip`, `parametrize` or other `exists()` guard is in either module (15 + 11 = 26 `def test_`); fixtures are named `<key>_sample.xls` (`ls tests/fixtures/damodaran`, keys from `INDUSTRY_DATASETS`, `src/bot/ingest/damodaran.py:109-180`); the `test_ibkr_flex_capture.py` exclusion and the `test:` commit type are quoted from the issue; ruff selects no `PLC` rule (`pyproject.toml:59`), and `test_valuator_assumptions.py:995` already imports locally; base is `feature/64-remediation-follow-ups` (issue body, `Branch:` line of #64).
- Assumptions added: the eval script's author and its `trap` restore; the `total > 0` guard.
- Issues opened: none.
