# TLA+ models scaffold and the site model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every push runs TLC (through the pinned statechart skill) on every model under `docs/pipeline/models/`, and `docs/pipeline/models/site.*` is a checked model of one analysis sidecar going through publish, CI and `bot site`.

**Architecture:** `docs/pipeline/models/check.sh` loops over `*.tla` in its own folder and runs the skill's launcher per model, judging each `report.md`. A new `models` job in `.github/workflows/pipeline-diagram.yml` installs Java 21, Node 24, `tla2tools.jar` (pinned and checksummed) and the skill (sparse clone at a pinned commit), then runs `check.sh` and uploads `pipeline-models`. Python tests pin the script, the job and the model conventions; no test runs Java or Node.

**Tech Stack:** bash (shellcheck-clean), TLA+ / TLC 1.7.4, the cursor/plugins `statechart` skill (TypeScript on Node), GitHub Actions, pytest + PyYAML.

**Spec:** issue #163 (body is the spec), parent story #161 (plan comment, decisions 6, 7, 9).

## Global Constraints

- Pins, one value per file, newline-terminated: `TLA_VERSION` = `1.7.4`; `TLA_SHA256` = `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`; `STATECHART_COMMIT` = `4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`.
- The skill is cloned in CI, never vendored: `docs/pipeline/models/` holds only `site.tla`, `site.cfg`, `site.view.js`, `check.sh`, `README.md`, `TLA_VERSION`, `TLA_SHA256`, `STATECHART_COMMIT`.
- No file under `src/` changes. No pipeline code changes.
- No test runs Java or Node. shellcheck runs via `uv run` (the `shellcheck-py` dev dependency).
- Model labels: reader's words, never a variable, function or TLA+ action name; acronyms expanded at first use; conditions in `[brackets]` at the end of a step label.
- `site.view.js` groups are exactly `site-publish`, `site-ci`, `site-scan`, `site-views`; colors from `blue orange purple yellow teal tan pink`.
- Model under a few hundred distinct states (chart budget 500).

### Declared technical decision (deviation from the issue's literal text)

The issue writes the three maps as `export const states = {...}`. The skill's view loader (`scripts/frontends/view.ts`, `checkView`) throws when a view exports anything but `state`, `step`, `group`, `colors`, `title` ("The view exports …, which the command does not read"). So the maps are declared **without** `export`: `const states = {`, `const steps = {`, `const groups = {`; the five functions/values are the only exports. The convention test checks exactly that.

### Rule-definition convention (makes "INVARIANT-shaped" testable)

In a `.tla`, a `\*` line comment directly above a definition is reserved for rules: the reader's sentence (and, for a broken rule, a `\* broken: #<n>` line). Every other definition (helpers, actions) is commented with `(* ... *)` or not at all. Definitions are separated by blank lines. A definition is **INVARIANT-shaped** when it has no parameters, its body (up to the next blank line) contains neither `'` nor `UNCHANGED`, and the line directly above it is a `\*` comment.

## Review Focus

1. A report that contains `## Rules that hold` **and** a `## X breaks` section (TLC reports both): must fail. Test: `test_check_fails[breaks]` writes both headings.
2. A launcher that exits non-zero without writing `report.md` (exit 2 writes nothing): must fail with one `error` line, not crash the loop under `set -e`. Test: `test_check_fails[launcher-exit]` with no report.
3. Two models where the first fails: the second still runs, and the summary counts both. Test: `test_check_runs_every_model_and_counts`.
4. `STATECHART` or `TLA2TOOLS` unset: exit non-zero with a message naming the variable, before any model runs. Test: `test_check_requires_env`.
5. A rule in `.cfg` with no reader sentence above its definition, or a commented rule missing from `.cfg` without `\* broken: #n`: must fail the convention test. Covered by `test_rules_are_checked_or_marked_broken` and `test_every_cfg_invariant_has_a_sentence`.

---

### Task 1: pins and `check.sh`

**Files:**
- Create: `docs/pipeline/models/TLA_VERSION`, `TLA_SHA256`, `STATECHART_COMMIT`, `check.sh` (mode 755)
- Test: `tests/unit/test_pipeline_models.py` (written in the evals stage)

**Interfaces:**
- Produces: `check.sh OUT_DIR`; env `STATECHART` (launcher path, required), `TLA2TOOLS` (jar path, required), `JAVA` (optional, passed through by the environment). For each `*.tla` in `$(dirname "$0")`, sorted, it runs
  `"$STATECHART" "$DIR/<stem>.tla" --config "$DIR/<stem>.cfg" --view "$DIR/<stem>.view.js" --out "$OUT_DIR/<stem>"`.
  Output: one `error  <stem>: <why>` line per failing model (two spaces after `error`), final line `models | N models, R rules, E errors`; exit 1 when E > 0, else 0. R = sum over models of the comma-separated names on the line after `## Rules that hold`.
- A model fails when: `<stem>.cfg` or `<stem>.view.js` is missing (launcher not run); the launcher exits non-zero; `report.md` is missing; it has a heading matching `^## .+ breaks$`, `^## Rules not checked$` or `^## TLC stopped$`; or it lacks `^## Rules that hold$`.

- [ ] **Step 1: Tests (from the evals commit) fail:** `uv run pytest -q tests/unit/test_pipeline_models.py -k "pin or check"`. Expected: FAIL (files missing).

  The tests, with a fake launcher (bash script that `mkdir -p` the `--out` dir, copies `$FAKE_REPORT` to `report.md` when that file exists, appends `$*` to `$FAKE_LOG`, exits `${FAKE_EXIT:-0}`) and a temp folder holding a copy of `check.sh` plus fake model files:
  - `test_pins`: the three files equal the values above plus `\n`.
  - `test_check_script_is_executable_and_strict`: executable, starts `#!/usr/bin/env bash\n`, contains `set -euo pipefail`.
  - `test_check_script_is_shellcheck_clean`.
  - `test_check_passes_on_rules_that_hold`: report `## Rules that hold\nA, B, NoDeadlock\n` → exit 0, stdout last line `models | 1 models, 3 rules, 0 errors`; the log line is `<dir>/site.tla --config <dir>/site.cfg --view <dir>/site.view.js --out <out>/site`.
  - `test_check_fails` parametrized: `breaks` (`## A breaks` + `## Rules that hold`), `not-checked`, `tlc-stopped`, `no-holds` (report without the heading), `launcher-exit` (`FAKE_EXIT=2`, no report) → exit 1, stdout has `error  site: ` and ends `1 errors`.
  - `test_check_fails_without_cfg` and `..._without_view`: launcher never called, `error  site: ` names the missing file.
  - `test_check_runs_every_model_and_counts`: models `a` (fails) and `b` (holds) → both in the log, `models | 2 models, … 1 errors`, exit 1.
  - `test_check_requires_env`: with `STATECHART` unset (and separately `TLA2TOOLS`) → exit non-zero, stderr names the variable, launcher not called.
- [ ] **Step 2: Write the pins and `check.sh`.** Collect errors in an array; never let one model's failure stop the loop (`if ! "$STATECHART" ...; then`). Use `${VAR:?message}` for the required env.
- [ ] **Step 3: Run** `uv run pytest -q tests/unit/test_pipeline_models.py -k "pin or check"` → PASS.
- [ ] **Step 4: Commit** `feat(#163): models check script and pins`.

### Task 2: the `models` CI job

**Files:**
- Modify: `.github/workflows/pipeline-diagram.yml` (append job `models`; `render` unchanged)
- Modify: `tests/unit/test_pipeline_build.py` (`list(wf["jobs"]) == ["render", "models"]`; new `test_workflow_checks_models`)

**Interfaces:**
- Consumes: Task 1's `check.sh` and the three pin files.
- Produces: artifact `pipeline-models` = `/tmp/models/<stem>/{report.md,chart.mmd,tlc.out}`.

- [ ] **Step 1: Tests fail:** `uv run pytest -q tests/unit/test_pipeline_build.py`. `test_workflow_checks_models` asserts, in step order: `actions/checkout@v4`; `actions/setup-java@v4` with `distribution: temurin`, `java-version: "21"`; `actions/setup-node@v4` with `node-version: "24"`; a step whose run contains `https://github.com/tlaplus/tlaplus/releases/download/v$(cat docs/pipeline/models/TLA_VERSION)/tla2tools.jar` and `-o /tmp/tla2tools.jar`; a step (same or later) with `$(cat docs/pipeline/models/TLA_SHA256)` and `sha256sum -c`; a step with `git clone --filter=blob:none --no-checkout https://github.com/cursor/plugins /tmp/plugins`, `sparse-checkout set pstack/skills/statechart` and `checkout "$(cat docs/pipeline/models/STATECHART_COMMIT)"`; the check step running `docs/pipeline/models/check.sh /tmp/models` with `TLA2TOOLS=/tmp/tla2tools.jar` and `STATECHART=/tmp/plugins/pstack/skills/statechart/scripts/statechart`; last, `actions/upload-artifact@v4` with `if: always()`, `name: pipeline-models`, `path: /tmp/models`. checksum index < check index; `runs-on: ubuntu-latest`.
- [ ] **Step 2: Add the job** with exactly the commands of the issue (Task step 3).
- [ ] **Step 3: Run** the file's tests → PASS.
- [ ] **Step 4: Commit** `ci(#163): models job runs TLC on the pipeline models`.

### Task 3: the site model

**Files:**
- Create: `docs/pipeline/models/site.tla`, `site.cfg`, `site.view.js`
- Test: `tests/unit/test_pipeline_models.py` (convention tests, parametrized over every `.tla`)

**Interfaces:**
- Produces: phases and step labels later drawn as the site sub-boards (#164).

Variables (all finite): `phase`; `worktree` and `committedFiles` (subsets of `CheckoutFiles == {"sidecar", "other"}`: the checkout has the sidecar and other local changes); `committed`, `onMaster`, `workflowRan`, `wrote`, `row`, `page` (BOOLEAN); `failed` ∈ {"none","sync","ruff","mypy","pytest","site"}; `baseUrl` ∈ {"raw","normalised"}; `skip` ∈ {"none","folder not a date","stem not a ticker","schema version","ticker mismatch","not renderable"}; `margin` ∈ {"unread","no price","below 1.0","1.0 to 1.3","1.3 or more"}; `verdict` ∈ {"none","undervalued","fair","overvalued","na"}. Init: `phase = "written"`, sets empty, booleans FALSE, `failed = "none"`, `baseUrl = "raw"`, `skip = "none"`, `margin = "unread"`, `verdict = "none"`.

Phases, groups and actions (`from → to`, effect; code to cite in a `(* *)` comment above each action):

| group | phase | actions out |
| --- | --- | --- |
| site-publish | written | PublishFindsTheSidecar → found (`publish_site.sh` find) |
| site-publish | found | PublishCopiesItIntoTheResetWorktree → in_worktree; `worktree' = {f \in CheckoutFiles : f = "sidecar"}` (checkout/reset/clean, copy loop) |
| site-publish | in_worktree | TheSidecarIsAlreadyOnMaster → nothing_new (`diff --cached --quiet`); PublishCommitsTheSidecar → committed; `committed' = TRUE`, `committedFiles' = worktree` |
| site-publish | committed | ThePushFails → push_failed; ThePushSucceeds → on_master, `onMaster' = TRUE` |
| site-publish | nothing_new, push_failed, on_master | (end, end, see ci) |
| site-ci | — | from on_master: DependenciesInstall → installed / DependencyInstallFails → ci_failed (`failed' = "sync"`); both set `workflowRan' = TRUE` (`site.yml` on push to master) |
| site-ci | installed / linted / typed | RuffPasses → linted / RuffFails; MypyPasses → typed / MypyFails; PytestPasses → tested / PytestFails (each Fails → ci_failed with `failed'` = "ruff" / "mypy" / "pytest") |
| site-ci | tested | BotSiteNormalisesTheBaseUrl → base_url_set, `baseUrl' = "normalised"` (`build` first line). `ci_failed` is an end phase: no action leaves it. |
| site-scan | base_url_set | TheOutputDirIsUnsafe → out_refused, `failed' = "site"` (`_prepare_out_dir` raises); TheOutputDirIsReady → out_ready, `wrote' = TRUE` (marker written) |
| site-scan | out_ready | TheFolderIsNotADate / TheStemIsNotATicker / TheSchemaVersionIsWrong / TheTickerDoesNotMatch → skipped with that `skip'` (`index.scan`, `read_sidecar`); TheSidecarIsUsable → usable |
| site-scan | usable | TheAnalysisLacksAField → skipped, `skip' = "not renderable"` (`_renderable`); TheAnalysisHasEveryField → renderable |
| site-scan | out_refused, skipped, renderable | end, end, see views |
| site-views | — | from renderable: TheMarginIsAtLeastOnePointThree / TheMarginIsFromOneToOnePointThree / TheMarginIsBelowOne / TheAnalysisHasNoPrice → row; `margin'` = band, `verdict' = FromText(TextOf(band))`, `row' = TRUE` (`row_view` reads `data["verdict"]` via `verdict_from_text`; the text was written by `margin_verdict`) |
| site-views | row → listed → pages → live | TheListPagesShowTheRow; TheCompanyPagesAreWritten (`page' = TRUE`, `_write_company`); GitHubPagesDeploysTheSite (`deploy` needs `build`) |

`EndPhases == {"nothing_new", "push_failed", "ci_failed", "out_refused", "skipped", "live"}`. `TextOf(m)` mirrors `margin_verdict` (`"no price"` → `"n/a"`, `"below 1.0"` → `"potentially overvalued"`, `"1.0 to 1.3"` → `"around fair value"`, `"1.3 or more"` → `"potentially undervalued"`); `FromText(t)` mirrors `VERDICT_TEXT` inverted; `ThresholdVerdict(m)` is the rule from CONTEXT.md "Verdict" (`>=1.3` undervalued, `>=1.0` fair, `<1.0` overvalued, no price na). Use CASE; no EXTENDS needed.

Rules (INVARIANT, reader's sentence as `\*` comment directly above):

| rule | definition | sentence |
| --- | --- | --- |
| (a) ViewerOnlyFromMaster | `page => onMaster` | A sidecar reaches the viewer only through a commit pushed to master. |
| (b) NothingNewNoWorkflow | `(phase = "nothing_new" => ~committed) /\ (workflowRan => committed /\ onMaster)` | A publish with nothing new makes no commit, so no site workflow runs. |
| (c) OnlySidecarsCommitted | `committedFiles \subseteq {"sidecar"}` | The publish commit holds sidecars only, never the checkout's other changes. |
| (d) FailedStepDeploysNothing | `failed # "none" => phase # "live" /\ ~page` | Any failing workflow step deploys nothing. |
| (e) UnsafeOutputUntouched | `phase = "out_refused" => ~wrote` | An unsafe output directory is refused and nothing is written to it. |
| (f) SkippedNeverARow | `skip # "none" => ~row /\ ~page` | A sidecar that cannot be used or rendered never becomes a row or a page. |
| (g) OneVerdictFromTheMargin | `row => verdict = ThresholdVerdict(margin) /\ verdict # "none"` | Every listed company has one verdict, read from its sidecar, that matches its margin of safety. |
| (h) BaseUrlFirst | `wrote \/ page => baseUrl = "normalised"` | Nothing is written before the base address of the site is normalised. |

`site.cfg`: `SPECIFICATION Spec` and the eight `INVARIANT` lines. Deadlock checking stays on.

`site.view.js`: `const states`, `const steps`, `const groups` (one entry per line, unquoted keys, double-quoted values; `Done: null` hidden), the five exports with `title = "site: one sidecar through bot site"` and colors `site-publish: blue`, `site-ci: orange`, `site-scan: purple`, `site-views: teal`.

- [ ] **Step 1: Tests fail:** `uv run pytest -q tests/unit/test_pipeline_models.py -k "model or site"` (no `.tla` yet: `test_site_model_exists` fails). Convention tests, parametrized over each `*.tla` stem:
  - `test_model_files_sit_together`: `.cfg` and `.view.js` exist; first line of `.tla` matches `---- MODULE <stem> ----` (any run of 4+ dashes).
  - `test_cfg_has_spec_and_invariants`: `SPECIFICATION Spec` line; ≥1 `INVARIANT` line.
  - `test_tla_has_next_and_done`: lines starting `Next ==`, `Done ==`, `Spec ==`; `Done` body has `phase \in EndPhases` and `UNCHANGED vars`.
  - `test_next_names_every_step`: the `\/`-separated names in the `Next ==` body (which may span lines, up to the next blank line) equal the keys of `steps`. `Done` is a key of `steps` with a label ("the run ends"), as the skill asks; it stays in one chart state, so the chart does not draw it.
  - `test_labels_name_no_code`: no `states`/`steps` label contains a `steps` key, a variable name declared in `VARIABLES`, or an underscore.
  - `test_view_maps_and_exports`: `const states|steps|groups = {` each present; `export const` names exactly `{state, step, group, colors, title}`; the three function lines verbatim as in the issue.
  - `test_groups_are_stage_subboards`: every `groups` value matches `^<stem>-[a-z][a-z-]*$`; every `colors` key is a `groups` value and vice versa; colors in the seven allowed.
  - `test_states_and_groups_keys_match`.
  - `test_every_cfg_invariant_has_a_sentence`: each INVARIANT name is defined in the `.tla` with a `\*` comment directly above.
  - `test_rules_are_checked_or_marked_broken`: every INVARIANT-shaped definition is in the `.cfg` or has `\* broken: #<n>` among the `\*` lines above it.
  - `test_site_groups` (site only): set of `groups` values == the four site groups; ≥6 INVARIANTs.
- [ ] **Step 2: Write `site.tla`, `site.cfg`, `site.view.js`** from the tables above.
- [ ] **Step 3: Run** the tests → PASS. TLC is not available locally; the CI loop (Task 5) checks the model.
- [ ] **Step 4: Commit** `docs(#163): site model`.

### Task 4: docs

**Files:**
- Create: `docs/pipeline/models/README.md`
- Modify: `docs/pipeline/README.md` (new `## Models` paragraph pointing at `models/README.md`), `CONTEXT.md` ("Source of truth": bullet after the pipeline boards bullet)

- [ ] **Step 1: Tests fail:** `test_models_readme` (names `docs/pipeline/models/check.sh`, `pipeline-models`, `## Known broken rules` with a table header `| Stage | Rule | Reader's sentence | Issue |`), `test_models_folder_holds_only_ours` (every git-tracked file in the folder is one of `check.sh`, `README.md`, `TLA_VERSION`, `TLA_SHA256`, `STATECHART_COMMIT`, or `<stem>.tla|.cfg|.view.js`; the eight site/scaffold files are present; no `.ts`, no `SKILL.md`), `test_pipeline_readme_points_at_models` (`models/README.md` in `docs/pipeline/README.md`), `test_context_lists_the_models` (`docs/pipeline/models/` appears in CONTEXT.md after the `docs/pipeline/` boards bullet).
- [ ] **Step 2: Write** the README: what the models are (one per stage, one unit through one run), layout, the conventions (including the two declared decisions above), labelling rules in a few lines, the command (CI job and the local `TLA2TOOLS=… STATECHART=… docs/pipeline/models/check.sh /tmp/out`), how to read the artifact, the broken-rule protocol, empty "Known broken rules" table.
- [ ] **Step 3: Run** `uv run pytest -q tests/unit/test_pipeline_models.py` → PASS.
- [ ] **Step 4: Commit** `docs(#163): models README and pointers`.

### Task 5: TLC in CI (controller, not a subagent)

- [ ] Stopping rule: at most five push/watch rounds. If the `models` job is still red after the fifth, comment the stage and the report on #163 and stop with an error (the job only lands on the story branch through a green PR, so no red job reaches it).
- [ ] Push the branch; `gh run watch` the `pipeline-diagram` run; download `pipeline-models`; read `site/report.md`. Fix the model or the view until `check.sh` exits 0 with ≥6 rules holding and no breaks/unchecked/stopped. If the checksum step fails, take the hash of the real release asset and record it in the PR. A broken rule follows the broken-rule protocol of the issue (replay pytest, `bug` issue, `\* broken: #n`, README table); pipeline code never changes.
- [ ] Full suite, lint, `python3 docs/pipeline/check.py` → `0 errors`.

## Assumptions

- View maps are plain `const` (not exported), because the skill's `checkView` rejects other exports (`scripts/frontends/view.ts:58,72` at the pinned commit). Rejected alternative: `export const states` as the issue's text writes it, which makes the launcher exit 2.
- "INVARIANT-shaped" is defined by the plan, because the issue does not define it: a `\*` line comment directly above a definition is reserved for rules. Rejected alternative: matching definition names, which is fragile across models.
- An orphan `.cfg`/`.view.js` without a `.tla` is not an error, because the issue's `check.sh` loops over `*.tla`. Rejected alternative: failing on orphans.
- `Done` gets a step label rather than `null`, as the skill's SKILL.md asks ("give it a label in `step()`"). Rejected alternative: `null`.
- Rule (c) cannot break in the model by construction: it records the reset/clean/copy of `publish_site.sh:40-45` as a checked statement for the sub-board. Rejected alternative: a nondeterministic dirty worktree, which the code rules out.
- The CI loop is capped at five rounds. Rejected alternative: unbounded iteration.

## Grilling

- Rounds: 1 (the revisions tightened tests and fixed one table row; no step was added or removed and no seam changed, so no second round).
- Questions: 18. Sources: ISSUE 7, CODE 9, DOC 1, NO SOURCE 4. The four unsourced questions all landed in the technical-assumption bucket; there are no spec ambiguities and none was out of scope.
- Assumptions: see `## Assumptions`.
- Issues opened: none.
