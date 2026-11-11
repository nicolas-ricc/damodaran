# Harden the GitHub workflows: job-scoped permissions, SHA pins, Dependabot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `site.yml` grants Pages/OIDC permissions only to its `deploy` job, every action in both workflows is pinned to a commit SHA with a version comment, Dependabot proposes weekly action bumps, and the workflow tests pin all of it with readable failures.

**Architecture:** Config and tests only, no `src/` change. Two workflow files are edited, `.github/dependabot.yml` is added, `tests/unit/test_site_workflow.py` is tightened, `tests/unit/test_pipeline_build.py` is loosened from `@v4` literals to prefixes, and a new cross-workflow test module `tests/unit/test_workflow_pins.py` checks the pins and the Dependabot file. One spec section records the new shape.

**Tech Stack:** GitHub Actions YAML, Python 3.12, pytest, PyYAML, ruff, mypy --strict.

**Spec:** GitHub issue #96 (`gh issue view 96 --repo nicolas-ricc/damodaran --comments`). The binding spec is the planner comment ("Plan written by the planner agent (mode: plan), 2026-11-08"), decisions 1–9 and its acceptance criteria, which implements the maintainer's grill-session "Decisions" comment.

## Global Constraints

- `site.yml` concurrency stays `group: pages`, `cancel-in-progress: true`. The trigger stays only `push` to `master`: no `workflow_dispatch`, no `pull_request`.
- `site.yml` workflow-level `permissions` is exactly `{contents: read}`. `jobs.deploy.permissions` is exactly `{pages: write, id-token: write}`. `jobs.build` has no `permissions` key.
- Every `uses:` line in `.github/workflows/*.yml` has the form `owner/repo@<40-hex sha> # vX.Y.Z`, with one space before `#`. The SHA is the commit the named tag points to, and the tag stays in today's major. No upgrades.
- Pins (re-resolved 2026-11-08 with `gh api repos/<r>/git/ref/tags/<tag>`; each one equals the commit the current major tag points to):

  | action | sha | tag |
  |---|---|---|
  | `actions/checkout` | `11d5960a326750d5838078e36cf38b85af677262` | `v4.4.0` |
  | `astral-sh/setup-uv` | `d0cc045d04ccac9d8b7881df0226f9e82c39688e` | `v6.8.0` |
  | `actions/upload-pages-artifact` | `56afc609e74202658d3ffba0e8f6dda462b719fa` | `v3.0.1` |
  | `actions/deploy-pages` | `d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e` | `v4.0.5` |
  | `actions/upload-artifact` | `ea165f8d65b6e75b540449e92b4886f43607fa02` | `v4.6.2` |
  | `actions/setup-java` | `cf277c60eb25467037889841efdb72551f06f6c3` | `v4.9.1` |
  | `actions/setup-node` | `49933ea5288caeca8642d1e84afbd3f7d6820020` | `v4.4.0` |

- The `.github/dependabot.yml` content is exactly planner decision 4: `version: 2`; one update for `github-actions`, `directory: /`, weekly, grouped under `github-actions` with `patterns: ["*"]`. No labels, reviewers or commit-message options.
- Out of scope by maintainer decision: a PR gate workflow, `workflow_dispatch`, any change to `cancel-in-progress`. No follow-up issue for any of them.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Review Focus

- **The deploy step's `uses:` has no leading `- `.** It sits under `- id: deployment`. The pin regex must accept both `- uses:` and `uses:`. Task 2's pin test covers this line because it counts at least 10 lines, and one of the 10 is this one.
- **A version comment that names a different major or a non-semver tag** (`# v4`, `# main`). The regex requires `v\d+\.\d+\.\d+`, so `# v4` fails.
- **A SHA in the wrong case or of the wrong length** (short SHA, uppercase). The regex requires exactly `[0-9a-f]{40}`.
- **A gate command removed from `site.yml`.** The failure must name the command, not raise `ValueError` (Task 1).
- **A future job in `site.yml` that silently picks up write permissions.** The top-level dict is asserted exactly and `build` must have no `permissions` key (Task 1).

## Note on stage ordering

The pipeline's stage 3 (evals) writes and commits every failing test of Tasks 1 and 2 before implementation. Each task's implementer starts from those committed tests. They confirm that the tests are red, make them green, and do not weaken them.

---

### Task 1: `site.yml` job-scoped permissions, frozen concurrency, readable gate assertion

**Files:**
- Modify: `.github/workflows/site.yml` (the `permissions` block and `jobs.deploy`)
- Modify: `tests/unit/test_site_workflow.py`
- Modify: `docs/superpowers/specs/2026-10-04-web-viewer-design.md:213-214` (§"CI / deploy" item 4)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks use. (Task 2 edits the `uses:` lines of the same file. That does not conflict with this task.)

- [ ] **Step 1: Tests (committed in stage 3)**

In `test_deploy_needs_build_and_uses_pages`, replace the last assertion with:

```python
    assert data["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert "permissions" not in data["jobs"]["build"]
```

New test:

```python
def test_concurrency_cancels_superseded_deploys() -> None:
    assert _load()["concurrency"] == {"group": "pages", "cancel-in-progress": True}
```

In `test_build_gates_then_builds_the_site`, replace `positions = [runs.index(cmd) for cmd in gate]` with a loop. For each `cmd`, it first asserts `cmd in runs, f"gate command missing from the build job of site.yml: {cmd}"`, then appends `runs.index(cmd)` to `positions`. Everything else in that test stays unchanged.

- [ ] **Step 2: Run, expect red**

Run: `uv run pytest -q tests/unit/test_site_workflow.py`
Expected: `test_deploy_needs_build_and_uses_pages` FAILS on the permissions dict. The other tests pass, including the concurrency test, which only freezes the current value.

- [ ] **Step 3: Edit `site.yml`**

The workflow-level `permissions:` keeps only `contents: read`. Add `permissions:` with `pages: write` and `id-token: write` under `jobs.deploy`, after `needs: build`. Do not touch `build`, `concurrency` or `on`.

- [ ] **Step 4: Spec item 4**

Replace item 4 of §"CI / deploy" with: "`actions/upload-pages-artifact` → `actions/deploy-pages` (environment `github-pages`; permisos `pages: write`, `id-token: write` solo en el job `deploy`; el workflow entero tiene `contents: read`, #96)."

- [ ] **Step 5: Run, expect green**

Run: `uv run pytest -q tests/unit/test_site_workflow.py tests/unit/test_pipeline_diagram.py tests/unit/test_readme_dev_docs.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/site.yml docs/superpowers/specs/2026-10-04-web-viewer-design.md
git commit -m "feat(#96): site.yml grants pages and id-token write only to the deploy job"
```

---

### Task 2: SHA pins in both workflows, Dependabot, pin tests

**Files:**
- Modify: `.github/workflows/site.yml` (4 `uses:` lines)
- Modify: `.github/workflows/pipeline-diagram.yml` (6 `uses:` lines)
- Create: `.github/dependabot.yml`
- Create: `tests/unit/test_workflow_pins.py`
- Modify: `tests/unit/test_pipeline_build.py:173,181,210,211,213,232`
- Modify: `docs/superpowers/specs/2026-10-04-web-viewer-design.md` (§"CI / deploy", new item 6)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Tests (committed in stage 3)**

`tests/unit/test_workflow_pins.py`, with a module docstring that cites issue #96. The module defines `_ROOT = Path(__file__).resolve().parents[2]` and the following two tests.

`test_every_action_is_pinned_to_a_sha_with_a_version_comment`:
- Read the raw text of each file in `sorted((_ROOT / ".github" / "workflows").glob("*.yml"))`. Raw text is needed because PyYAML drops comments.
- Every line that contains `uses:` must match `^\s*(?:- )?uses:\s*[\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+\s*$`.
- The assertion message names the file and the line.
- Assert that there are at least 10 such lines in total.

`test_dependabot_updates_github_actions_weekly`:
- `yaml.safe_load` the file `_ROOT / ".github" / "dependabot.yml"`.
- `data["version"] == 2` and `len(data["updates"]) == 1`.
- The update has `package-ecosystem == "github-actions"`, `directory == "/"`, `schedule == {"interval": "weekly"}` and `groups == {"github-actions": {"patterns": ["*"]}}`.

In `test_pipeline_build.py`, change the six `s.get("uses") == "actions/<name>@v4"` lambdas to `s.get("uses", "").startswith("actions/<name>@")`. Nothing else changes.

- [ ] **Step 2: Run, expect red**

Run: `uv run pytest -q tests/unit/test_workflow_pins.py tests/unit/test_pipeline_build.py`
Expected: both `test_workflow_pins` tests FAIL. The pin test fails on the first `@v4` line, and the Dependabot test fails with `FileNotFoundError`. `test_pipeline_build` PASSES, because it only loosens.

- [ ] **Step 3: Pin every `uses:`**

Rewrite each `uses:` as `<owner>/<repo>@<sha> # <tag>`, with values from the Global Constraints table. `site.yml` has 4 lines. `pipeline-diagram.yml` has 6: checkout ×2, upload-artifact ×2, setup-java, setup-node.

- [ ] **Step 4: Add `.github/dependabot.yml`**

Use exactly the planner's decision 4 YAML.

- [ ] **Step 5: Spec item 6**

Append item 6 to §"CI / deploy": "Cada `uses:` fijado a un SHA de commit con la versión como comentario; `.github/dependabot.yml` propone las actualizaciones semanalmente (#96)."

- [ ] **Step 6: Run, expect green**

Run: `uv run pytest -q tests/unit/test_workflow_pins.py tests/unit/test_pipeline_build.py tests/unit/test_site_workflow.py tests/unit/test_pipeline_diagram.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/site.yml .github/workflows/pipeline-diagram.yml .github/dependabot.yml docs/superpowers/specs/2026-10-04-web-viewer-design.md
git commit -m "feat(#96): pin every action to a commit SHA and add Dependabot for github-actions"
```

---

## Final verification

- `uv run ruff check . && uv run mypy src && uv run pytest -q`: green.
- After the push: `gh run list --workflow pipeline-diagram --branch agent/96-harden-workflows --limit 1` is green. This is the pre-merge proof that the pinned SHAs resolve. `site.yml` only runs on `master` after the merge.

## Assumptions

- **The Dependabot test also asserts `groups`.** The planner's test list (decision 6) checks only version, ecosystem, directory and schedule. The acceptance criterion, however, requires "the content of decision 4", which includes the group. Rejected alternative: leave `groups` unpinned by any test.
- **The pin regex accepts only `owner/repo@sha`.** Subpath actions, local `./` actions and `docker://` refs fail it. Neither workflow uses any of those forms today (`grep -n uses: -r .github`). Whoever adds one later amends the regex in the same change. Rejected alternative: a broader regex that nothing exercises today.
- **Staging uses explicit file paths** rather than `git add .github/`. Today `.github/` holds only the two workflows. Rejected alternative: stage the whole directory.
- **The spec's item 6 is appended after item 5**, so Task 1's edit to item 4 does not move it. Rejected alternative: none.

## Grilling

- Rounds: 1, with 18 questions. The plan changed only locally (one more assertion and explicit `git add` paths), so no second round ran.
- Sources: 14 answered from CODE, 2 from ISSUE, and 2 had no source. The two unsourced ones are technical assumptions (the regex scope and the groups assertion). There were 0 spec ambiguities and 0 out-of-scope items.
- Follow-up issues opened: none.
