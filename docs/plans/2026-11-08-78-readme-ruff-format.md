# README states the real lint and format policy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The README's Development section stops telling contributors to run `uv run ruff format .` and states the actual policy: lint is `ruff check` (with `--fix` allowed), formatting is not enforced, and nobody formats the whole tree.

**Architecture:** Docs only. One section of `README.md` changes (`README.md:277-284`). A new test module pins the policy: no whole-tree format command anywhere in the README, and every command CI and the `.factory` lint gate run appears in the Development section.

**Tech Stack:** Python 3.12, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #78 (`gh issue view 78 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** (the rescope) is the binding spec; the issue body's two original options are superseded by it.

## Global Constraints

- Docs only: no file under `src/` or `tests/` is reformatted or edited. The only additions are `tests/unit/test_readme_dev_docs.py` (new) and the edit to `README.md`.
- `.github/workflows/site.yml` and `.factory/config.toml` stay unchanged.
- Historical plans under `docs/superpowers/plans/` stay unchanged.
- The README contains no whole-tree `ruff format .` command, not even as an example of what not to run: the literal `ruff format .` does not appear in the file.
- Lint commands CI runs (`.github/workflows/site.yml:21-23`): `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q`. The `.factory/config.toml` lint gate: `uv run ruff check . && uv run mypy src`.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- **Exact Development section.** The section becomes (composed here; the brief gives its content, not its words):

  ````markdown
  ## Development

  ```bash
  uv run pytest -q                 # tests
  uv run ruff check .              # lint (--fix allowed)
  uv run mypy src                  # type check
  ```

  These are the commands CI runs (`.github/workflows/site.yml`); the lint gate
  is `uv run ruff check . && uv run mypy src`.

  Formatting is not enforced: neither CI nor the lint gate runs `ruff format`,
  and much of the tree is not formatted. Never run `ruff format` over the whole
  tree; it rewrites dozens of files of unrelated code. If you format at all,
  format only the files you change (`uv run ruff format path/to/file.py`), and
  keep the diff to the lines you touched.
  ````

- **`uv run pytest` becomes `uv run pytest -q`.** CI and `.factory/config.toml` run `-q`; the brief asks the README to give "the lint command CI actually runs", and aligning the test line is the same fact at no cost.
- **A new test module is not a reformat.** The AC "No source or test file is reformatted; the diff touches docs only" is read as: no existing code changes. Repo precedent pins README facts in a test module (`tests/unit/test_web_docs.py::test_readme_documents_the_site_flow`), and stage 3 of the pipeline requires executable evals. Rejected: no test at all, which leaves AC 1 and 2 unchecked.
- **"Only the files or lines you change".** `ruff format` takes paths; the README gives the per-file command and tells contributors to keep the diff to touched lines. It does not recommend `ruff format --range` (single-file, line-based) to keep the instruction simple.
- **Commands read from the CI files, not hard-coded.** The test parses `run:` lines of `site.yml` that start with `uv run ruff` or `uv run mypy` or `uv run pytest`, and the `lint` value of `.factory/config.toml` (via `tomllib`), so a later CI change that the README misses fails the test.
- **AC 3 is verified by a diff check, not a test.** `git diff --name-only origin/master...HEAD` lists only `README.md`, the new test module and this plan. A pytest test cannot see the base branch reliably in CI (shallow checkout), so this goes in the PR description as a verification step.

## Review Focus

1. A whole-tree command hidden in prose or another section (`ruff format .`, `ruff format --check .`): the test scans the whole README, not only the Development section. Pinned in Task 1 (`test_readme_has_no_whole_tree_format`).
2. A bare `uv run ruff format` with no path in a code block, which also formats the whole tree: pinned in Task 1 (same test, line-level check).
3. CI changing its commands and the README going stale: pinned in Task 1 (`test_readme_lists_ci_commands`, `test_readme_lists_lint_gate`).
4. The Development section disappearing or being renamed, making the section tests vacuous: the helper asserts the `## Development` heading exists before slicing.
5. The policy sentence lost in a rewrite: pinned by `test_readme_says_format_not_enforced` (`not enforced`, `--fix`).

## Acceptance criteria → tasks

| Issue item | Task |
|---|---|
| AC 1 (no whole-tree `ruff format .`) | Task 1 |
| AC 2 (formatting not enforced, lint command CI runs) | Task 1 |
| AC 3 (no reformat, docs only) | Task 1, step 6 (diff check) |

---

### Task 1: README Development section and its tests

**Files:**
- Modify: `README.md:277-284`
- Create: `tests/unit/test_readme_dev_docs.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_readme_dev_docs.py`, module docstring `"""The README states the real lint and format policy (issue #78)."""`, `_ROOT = Path(__file__).resolve().parents[2]` as in `test_web_docs.py`, and a typed helper `_development_section() -> str` that asserts `"\n## Development\n"` is in the README and returns the text from that heading to the next `\n## ` (or end of file).

```python
def test_readme_has_no_whole_tree_format() -> None:
    readme = (_ROOT / "README.md").read_text()
    assert "ruff format ." not in readme
    for line in readme.splitlines():
        assert line.split("#")[0].strip() != "uv run ruff format"

def test_readme_lists_ci_commands() -> None:
    # every `run: uv run (ruff|mypy|pytest) ...` line of .github/workflows/site.yml
    # appears verbatim in _development_section(); assert at least 3 such commands found

def test_readme_lists_lint_gate() -> None:
    # tomllib-load .factory/config.toml; its "lint" value appears verbatim in _development_section()

def test_readme_says_format_not_enforced() -> None:
    section = _development_section()
    assert "not enforced" in section
    assert "--fix" in section
    assert "whole tree" in section
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_readme_dev_docs.py -v`
Expected: `test_readme_has_no_whole_tree_format`, `test_readme_lists_ci_commands` (`uv run pytest -q` missing), `test_readme_lists_lint_gate` and `test_readme_says_format_not_enforced` FAIL.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/unit/test_readme_dev_docs.py
git commit -m "test(#78): evals"
```

- [ ] **Step 4: Replace `README.md:277-284`** with the exact section from Assumptions. Nothing else in the README changes.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_readme_dev_docs.py -v`
Expected: 4 passed.

- [ ] **Step 6: Docs-only check and full gate**

Run: `git diff --name-only origin/master...HEAD`
Expected: exactly `README.md`, `docs/plans/2026-11-08-78-readme-ruff-format.md`, `tests/unit/test_readme_dev_docs.py`.

Run: `uv run ruff check . && uv run mypy src && uv run pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs(#78): README states the real lint and format policy"
```
