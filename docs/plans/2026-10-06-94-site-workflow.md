# Add the GitHub Pages workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `feature/92-static-analysis-viewer` carries `.github/workflows/site.yml`, and the three tests in `tests/unit/test_site_workflow.py` run and pass instead of skipping.

**Architecture:** One file is added verbatim from issue #94, which reproduces the Task 7 YAML of `docs/superpowers/plans/2026-10-04-web-viewer.md`. The `pytest.skip` guard that #93 put in `_load()` is removed, so that a missing or renamed workflow fails the suite again (comment of 2026-10-04 on #94). The Pages source is already GitHub Actions (`GET /repos/nicolas-ricc/damodaran/pages` → `build_type: workflow`), so no repository setting changes.

**Tech Stack:** GitHub Actions, uv, Python 3.12, pytest, PyYAML.

**Spec:** GitHub issue nicolas-ricc/damodaran#94 (parent story #92).

## Global Constraints

- File name: exactly `.github/workflows/site.yml`. Under any other name, the tests would point at nothing.
- File content: byte-for-byte the YAML block in #94's "What to do" step 1, including `cancel-in-progress: true`, `actions/checkout@v4`, `astral-sh/setup-uv@v6`, `actions/upload-pages-artifact@v3` and `actions/deploy-pages@v4`. No version bumps, no extra steps.
- Trigger: `push` to `master` only. No `pull_request`, no `schedule`, no `workflow_dispatch` (#92 "Trigger").
- Gate: `uv run ruff check . && uv run mypy src && uv run pytest -q` green. The baseline on `origin/feature/92-static-analysis-viewer` (a1db4c5) has 4 skipped tests, three of them in `test_site_workflow.py`. After this change the count drops to 1 skipped and passed grows by 3.
- Commit message from the issue: `ci(#92): build and deploy the viewer to GitHub Pages on push to master`.

## Review Focus

1. **Workflow deleted or renamed later.** Expected: the suite fails with `FileNotFoundError`, it does not skip. Task 1 Step 2 proves it by running the tests before the file exists.
2. **YAML `on:` parsed as boolean `True`.** PyYAML reads the bare key `on` as `True`. The existing test already reads `data.get("on", data.get(True))`, so no change is needed, but the passing run in Step 4 is what confirms it.
3. **Base URL.** Pages serves the repo at `http://myxomatosis.xyz/damodaran/`, so `/${{ github.event.repository.name }}/` resolves to `/damodaran/`, which matches. The test asserts the literal expression.
4. **Workflow syntax GitHub would reject.** No local runner exists. Step 4's YAML parse plus the shape assertions are the check. The first push to `master` is the real proof, and it happens after the story merges, outside this issue.
5. **Unused `pytest` import after the guard goes.** `pytest` is used only by the skip. Ruff (`F401`) catches a leftover import in Step 5.

---

### Task 1: Commit the workflow and make its tests mandatory

**Files:**
- Create: `.github/workflows/site.yml`
- Modify: `tests/unit/test_site_workflow.py` (`_load()` and the import block)

**Interfaces:** none. `bot site --out site --base-url ...` already exists on the base branch (`src/bot/web/site.py`).

- [ ] **Step 1: Remove the skip guard.** In `tests/unit/test_site_workflow.py`, make `_load()`:

```python
def _load() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(_WORKFLOW.read_text())
    return data
```

  Also delete the `import pytest` line, which nothing else uses.

- [ ] **Step 2: See it fail.** Run `uv run pytest -q tests/unit/test_site_workflow.py`. Expected: `3 failed`, each with `FileNotFoundError` on `.github/workflows/site.yml`.

- [ ] **Step 3: Add the workflow.** Create `.github/workflows/site.yml` with exactly:

```yaml
name: site
on:
  push:
    branches: [master]
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run mypy src
      - run: uv run pytest -q
      - run: uv run bot site --out site --base-url "/${{ github.event.repository.name }}/"
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 4: See it pass.** Run `uv run pytest -q tests/unit/test_site_workflow.py`. Expected: `3 passed`, no skips.

- [ ] **Step 5: Full gate.** Run `uv run ruff check . && uv run mypy src && uv run pytest -q`, then run `env -i PATH="$PATH" HOME="$HOME" uv run pytest -q` as well, because the CI runner has no `BOT_*` variables. Expected: green both times, `1051 passed, 1 skipped`. The remaining skip is `tests/unit/test_edgar_stooq_provider.py:192` ("fixture's newest bar has aged past freshness"), which is unrelated to this issue.

- [ ] **Step 6: Simulate the CI build step without env vars.** Run `env -i PATH="$PATH" HOME="$HOME" uv run bot site --out /tmp/site-94 --base-url "/damodaran/"` and check that `/tmp/site-94/index.html` exists. This is the command the `build` job runs after the gate.

- [ ] **Step 7: Commit.**

```bash
git add .github/workflows/site.yml tests/unit/test_site_workflow.py
git commit -m "ci(#92): build and deploy the viewer to GitHub Pages on push to master"
```

## Assumptions

- **The `import pytest` deletion.** The owner's comment on #94 asks only to remove the guard. Nothing else in the file uses `pytest`, so ruff `F401` would flag the leftover import. Rejected alternative: keep the import and add a `noqa`.
- **One task, not two.** Removing the guard without adding the file leaves the suite red, and the reverse leaves the guard as dead code. Rejected alternative: two commits, one for the test and one for the YAML.
- **No GitHub Actions run before `master`.** The trigger is `push` to `master` only (#92), so this branch never runs the workflow. The local checks in Steps 4 to 6 are the proxy. Rejected alternative: a temporary `workflow_dispatch` trigger, which #92 does not allow ("Trigger: `push` to `master` only").

## Out of this plan

- Pages source: already GitHub Actions. Stage 0 of #94 verified it through the API, so there is no step.
- First deploy and committing real `reports/*/analysis/*.json`: these happen after the story merges into `master` (#94 "After the merge").

## Grilling

- Rounds: 1, with 16 questions from the griller (model: fable). The revisions below added no step and changed no seam, so there was no second round.
- Sources: 6 ISSUE, 6 CODE, 3 DOC, 3 NO SOURCE. All three NO SOURCE answers are technical assumptions (see above). There were no spec ambiguities.
- Issues opened: none. Every question was in scope or answered from a source.
- Revisions: Step 5 now also runs the suite under `env -i` and names the remaining skip.
