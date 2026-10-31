# Site sub-boards and the sub-board conventions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four d2 sub-boards (`site-publish`, `site-ci`, `site-scan`, `site-views`) draw the checked site statechart one level below `site.d2`, so a reader who clicks a step on `site.svg` sees one sidecar flow through it. Generic tests enforce the sub-board conventions for every later stage.

**Architecture:** Each sub-board is a flat d2 board (no containers). Its nodes are the model states of one `groups` value of `docs/pipeline/models/site.view.js`, plus the neighbouring states the flow enters from or leaves to, three fixed nodes (`objective`, `back`, `out`), and source nodes (files, cron, external services). Its edges are the model steps, labelled with the view's `steps` text, with the "how" on further lines. `tests/unit/test_pipeline_subboards.py` checks the shape of every `<stage>-<sub>.d2`. `tests/unit/test_pipeline_models.py` checks that the drawing matches the model: labels, edge endpoints and node classes. d2 renders in CI only.

**Tech Stack:** d2 v0.9.0 + TALA (CI only), pytest, the existing helpers in `docs/pipeline/check.py` and `tests/unit/test_pipeline_diagram.py`.

**Spec:** issue #164 (its body is the spec, including "Sub-board conventions"). Parent story #161, plan comment decisions 2 to 8.

## Global Constraints

- Files: `docs/pipeline/site-publish.d2`, `site-ci.d2`, `site-scan.d2`, `site-views.d2`, plus their `.svg` from the CI artifact `pipeline-render`, and `rendered.sha256` from the same run. Never edit an SVG or the hash by hand.
- Every sub-board starts with `...@classes`, then a blank line, then `direction: down`. `class:` is a node's first attribute. Expand every acronym at first use on each board (CI, MoS, ADR). Use no all-caps token outside `_ACRONYMS` / `_ACRONYMS_EXEMPT` of `test_pipeline_diagram.py`: no HEAD, SSH or ISO.
- Every number other than 0, 1 and 100 on a node or edge label is cited by `@const`/`@param` on that line. Otherwise write the number as a word ("twelve characters", "exit code two").
- At most 24 edges per sub-board.
- `site.d2` gains five `link:` lines and nothing else. `pipeline.d2` does not change. No file under `src/` changes. The TLA+ logic does not change.
- A node that is a model state uses that state's `states` label as the exact first line of its label. An edge that is a model step uses that step's `steps` label as the exact first line of its label.
- Links are written `link: "./<name>.svg"`.

## Declared decisions (issue text read literally, or a gap filled)

1. **Decision class.** The issue says: "class `decision` when more than one step leaves it under a [condition], else `step`". Read literally: a state is a `decision` when at least two of the model steps leaving it carry a `[condition]`. For site this gives `base_url_set` (2), `out_ready` (5) and `renderable` (4). `in_worktree`, `committed`, `on_master`, `installed`, `linted`, `typed` and `usable` each have one conditioned exit, so they are `step`. The rule applies to neighbour nodes too. It is tested.
2. **Unconditioned edge out of a decision.** "Every edge leaving a decision has a [condition]". An edge whose model label has no bracket (`the scan reads the sidecar`), or an extra edge to `out`, therefore carries the condition on its second line (`[it passes every check above]`).
3. **Cross-group steps are drawn on both boards** where both of their states appear. For example, `on_master → installed` appears on site-publish and on site-ci. The label match only needs one of them.
4. **Neighbour and terminal nodes.** The generic audit (`test_every_step_has_purpose_and_edges`) asks every `step` for an incoming and an outgoing edge, or for the words `No incoming edge` / `No outgoing edge` in its block. These nodes carry that text as a trailing comment:
   - a neighbour the flow enters from: `# No incoming edge: the flow enters from site-<sub>`;
   - a neighbour it leaves to: `# No outgoing edge: the flow goes on in site-<sub>`;
   - a terminal state (`nothing_new`, `push_failed`, `ci_failed`, `out_refused`, `skipped`): `# No outgoing edge: the run ends here`.

   A comment line holding only that text is not a directive and does not break `check.py`.
5. **`Done` ("the run ends")** is drawn once: `live -> out` on site-views.
6. **`out`'s incoming edge** comes from the last state of the group that hands data on: publish `on_master`, ci `tested`, scan `renderable` (a decision, so its edge to `out` carries `[the analysis is kept]`), views `live`.
7. **Sub-board order** = the order in which each group first appears in the view's `groups` map. For site: publish, ci, scan, views. The test reads the order from there.
8. **README line cap.** `test_readme_has_build_and_check_commands` caps `docs/pipeline/README.md` at 60 lines, and the file is already at 60. The new section needs room, so the cap goes to 90.
9. **"`site` green on the PR's head commit".** `site.yml` runs only on a push to master, so it does not run on a PR to the feature branch. Its four commands (`ruff check .`, `mypy src`, `pytest -q`, `bot site --out <tmp> --base-url /damodaran/`) are run locally on the head instead. The PR states this as manual verification.

## Assumptions (from the plan grilling; decided, with the rejected alternative)

- A1. **README cap 90** rather than the exact new length. This leaves headroom for the four later sub-board children, which will append to the same section. Rejected: setting the cap to the exact length, which each later child would have to bump.
- A2. **The `site` workflow is not runnable on the PR.** `.github/workflows/site.yml:2-4` triggers only on `push` to `master`. Its commands are run locally on the head as evidence, and the PR flags this. Rejected: adding `workflow_dispatch` or a PR trigger to `site.yml`, which would change CI behaviour outside this issue's scope.
- A3. **`link:` on a d2 container** (`publish`, `ci`, `build`, `serve`) and on a child (`build.rows`) inside a linked container. Nothing in the repository shows that d2 v0.9.0 renders both. The CI render is the proof: `test_stage_svg_links_its_subboards` reads the committed `site.svg`. If a container link is dropped, the fallback is to put the link on the container's first child step, and the PR says so. Rejected: guessing without a render.
- A4. **Edges to `out` and their conditions.** The issue requires `out` to have an incoming edge and every edge out of a decision to carry a [condition]. So `renderable→out` on site-scan carries `[the analysis is kept]`. It matches no model step. That is allowed, because the label match only requires every model step to be drawn, not every edge to be a model step. Rejected: making `out`'s source the neighbour `row`, which would leave `out` hanging off a node of the next board.

## Review Focus

1. **The SVG drops a link.** d2 can drop `link:` (README: "d2 v0.9.0 drops `link: <stage>.svg` on a board that has a node keyed `<stage>`"). Expected: every link a reader needs is in the rendered SVG. Test: `test_subboard_svg_hrefs` and `test_stage_svg_links_its_subboards` read the committed SVGs.
2. **A model step drawn between the wrong states**: the right label on the wrong arrow. Expected: the arrow joins the states the `.tla` action joins. Test: `test_subboard_edges_join_the_model_states` parses `phase = "a"` / `phase' = "b"` from each action.
3. **A digit on an edge label.** The existing audit only reads step-node labels, so an uncited threshold on an arrow would pass. Expected: every number on any label is cited on its line. Test: `test_subboard_digits_are_cited` covers node and edge labels.
4. **A new state or step added to the view later**, with no node or edge drawn. Expected: the suite fails, naming the label. Test: the label match in `test_pipeline_models.py`, parametrized over `_SUBBOARDED`.
5. **A sub-board file whose stem is not a group of its stage's model** (a typo such as `site-view.d2`). Expected: fail. Test: `test_subboard_names`.

---

### Task 1: evals (generic sub-board tests, label match, required citations)

Done in the evals stage, before any board exists. All new tests fail.

**Files:**
- Create: `tests/unit/test_pipeline_subboards.py`
- Modify: `tests/unit/test_pipeline_models.py` (append the label-match tests)
- Modify: `tests/unit/test_pipeline_diagram.py` (add entries to `_REQUIRED_*`, raise the README cap to 90, add a README sub-board test)

**Interfaces (produced by `test_pipeline_subboards.py`, imported by `test_pipeline_models.py`):**
- `subboards() -> dict[str, tuple[str, str]]`: stem → `(stage, sub)` for every `docs/pipeline/<stage>-<sub>.d2` whose `<stage>` is in `_STAGES`.
- `node_labels(text: str) -> dict[str, tuple[int, str | None, str]]`: dotted path → (0-based declaration line, class, label text). The label is the quoted string (with `\n` escapes kept as the two characters) or the `|md ... |` body, stripped.
- `edges(text: str) -> list[tuple[int, str, str, str]]`: (0-based line, src, dst, quoted label) for every `a -> b: "..."` line.
- `first_line(label: str) -> str`: the text before the first `\n` escape, with `\"` unescaped.
- `group_order(stage: str) -> list[str]`: the groups of `models/<stage>.view.js`, in order of first appearance.

Reuse `_nodes`, `_block`, `_cited_values`, `_uncited_numbers` and `_STAGES` from `tests.unit.test_pipeline_diagram`, and `_map` / `_definitions` from `tests.unit.test_pipeline_models`. Import them; do not copy them.

- [ ] **Step 1: Write `test_pipeline_subboards.py`.** Each test is parametrized over `sorted(subboards())`, except where noted:
  - `test_site_has_four_subboards`: `{s for s, (st, _) in subboards().items() if st == "site"} == {"site-publish", "site-ci", "site-scan", "site-views"}`.
  - `test_subboard_names`: `<sub>` is in `group_order(stage)` as `f"{stage}-{sub}"`. The board starts with `...@classes`, and its first non-blank line after that is `direction: down`.
  - `test_objective_note`: node `objective` has class `note`. Its label is one line and starts with `Objective:`.
  - `test_back_note`: node `back` has class `note`, label `back to the <stage> board`, and `link: "./<stage>.svg"` in its block.
  - `test_out_node`: node `out` has class `output`, its label starts with `Comes out:`, and at least one edge ends at `out`. Its link is `./<stage>-<next>.svg` for the next sub in `group_order`, or `./<stage>.svg` for the last one.
  - `test_every_edge_line_is_parsed`: every visible line containing `->` is matched by `edges()`. No unlabelled, chained or block edge can hide from the cap or from the label match.
  - `test_edge_cap`: `len(edges(text)) <= 24`.
  - `test_decision_edges_carry_a_condition`: every edge whose src has class `decision` has a label matching `\[[^\]]+\]`.
  - `test_step_and_decision_nodes_carry_a_directive`: for each node of class `step` or `decision`, some `check.directives(text)` entry has `d.line == decl_line + 1`.
  - `test_subboard_digits_are_cited`: `_uncited_numbers(label, cited.get(line + 1, [])) == []` for every node label and every edge label.
  - `test_no_store_only_container`: no node that has children has only `store`/`file`/`external` children.
  - `test_stage_board_links_its_subboards` (per stage that has sub-boards): `<stage>.d2` has `link: "./<stem>.svg"` for each sub-board stem.
  - `test_stage_svg_links_its_subboards` (per stage): `<stage>.svg` has `href="./<stem>.svg"` for each.
  - `test_subboard_svg_hrefs`: `<stem>.svg` has `href="./<stage>.svg"`, plus `href="./<stage>-<next>.svg"` when the board is not the last.
- [ ] **Step 2: Append to `test_pipeline_models.py`** `_SUBBOARDED = ("site",)` and these tests, parametrized over `_SUBBOARDED`:
  - `test_subboards_are_the_groups`: the set of `subboards()` stems of the stage equals the set of `groups` values.
  - `test_state_labels_are_drawn`: for each state with group `g`, `states[k]` equals `first_line` of some node label in `docs/pipeline/<g>.d2`.
  - `test_step_labels_are_drawn`: every non-null `steps` label equals `first_line` of some edge label across the stage's sub-boards.
  - `test_subboard_edges_join_the_model_states`: for each action whose body has `phase = "a"` and `phase' = "b"` (an action other than `Done` without that form fails the test; it is not skipped), some edge on some sub-board of the stage has that step label as its first line, a src node whose first line is `states[a]`, and a dst node whose first line is `states[b]`.
  - `test_subboard_state_classes`: every node whose first line is a `states` label has class `decision` if and only if at least two actions leaving that state have a step label containing `[`.
- [ ] **Step 3: Edit `test_pipeline_diagram.py`.**
  - `_REQUIRED_SYMBOLS`: `"site-publish": {"bot.reporting.analysis_json.render_analysis_json"}`, `"site-ci": {"bot.cli.site"}`, `"site-scan": {"bot.web.site.build", "bot.web.index.scan", "bot.web.index.read_sidecar", "bot.web.site._prepare_out_dir", "bot.web.site._renderable"}`, `"site-views": {"bot.web.views.verdict_of", "bot.web.views.row_view", "bot.web.views.filter_sort"}`.
  - `_REQUIRED_FILES`: `"site-publish": {"scripts/publish_site.sh", "scripts/weekly.sh"}`, `"site-ci": {".github/workflows/site.yml"}`, `"site-views": {".github/workflows/site.yml"}`.
  - `_REQUIRED_CONSTS`: `"site-scan": {"bot.reporting.analysis_json.SCHEMA_VERSION", "bot.web.site.MARKER", "bot.web.views.MOS_UNDERVALUED", "bot.web.views.MOS_FAIR"}`, `"site-views": {"bot.web.views.MOS_UNDERVALUED", "bot.web.views.MOS_FAIR", "bot.web.views.FILTERS", "bot.web.views.SORTS", "bot.web.views.DIRECTIONS"}`.
  - `_REQUIRED_ENUMS`: `"site-views": {"bot.web.views.Verdict"}`.
  - The README cap goes from `<= 60` to `<= 90`. Add `test_readme_documents_subboards`: README has `## Sub-boards`, and its text includes `<stage>-<sub>.d2`, `objective`, `back`, `out`, `Comes out:`, `24`, `statechart` and `models/`.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py`. Expected: the new tests fail because the boards are missing (`test_site_has_four_subboards`, label match, required citations, README). The tests that existed before still pass. `uv run ruff check tests` is clean.
- [ ] **Step 5: Commit** `test(#164): evals`.

### Task 2: `site-publish.d2` and `site-ci.d2`

**Files:** Create `docs/pipeline/site-publish.d2`, `docs/pipeline/site-ci.d2`.

**Interfaces:** Consumes Task 1's tests. Node keys are the model state keys (`written`, `found`, ...) plus `objective`, `back`, `out`, and the source nodes below.

The node and edge layout below is fixed. The wording of the "how" lines is the implementer's, within the Global Constraints. Each how line must be true of `scripts/publish_site.sh`, `scripts/weekly.sh` or `.github/workflows/site.yml`.

**site-publish.** Objective: get each new analysis sidecar onto master, where the site workflow picks it up; nothing else from this checkout is committed.
- Sources:
  - `sidecars` (file, `@symbol bot.reporting.analysis_json.render_analysis_json`): `reports/YYYY-MM-DD/analysis/TICKER.json`.
  - `weekly` (cron, `@file scripts/weekly.sh`).
  - `master` (external): GitHub repository, branch master.
- States (all `step`):
  - `written`, `found`, `in_worktree`, `committed`, `nothing_new` (terminal), `push_failed` (terminal), `on_master`. Each carries `@file scripts/publish_site.sh`; `written` carries the render symbol instead.
  - Neighbours `installed` and `ci_failed`, with `link: "./site-ci.svg"`, `@file .github/workflows/site.yml`, and the `No outgoing edge` comment.
- Edges (12):
  - Sources: `sidecars→written`, `weekly→found`, `master→in_worktree`.
  - Model: `written→found`, `found→in_worktree`, `in_worktree→nothing_new`, `in_worktree→committed`, `committed→push_failed`, `committed→on_master`.
  - Cross-group: `on_master→installed`, `on_master→ci_failed`.
  - `on_master→out`.
- How lines must show:
  - `find reports/*/analysis/*.json`, and none found: exit 0;
  - the detached worktree `.cache/site-publish`, reset to `origin/master` and cleaned, into which only the sidecars are copied;
  - `git add -- reports`;
  - the commit message `chore(site): publish analyses YYYY-MM-DD`;
  - when the push fails: exit 1, and the next run rebuilds the commit from origin/master.
- `out`: `Comes out:` one commit on master that holds only `reports/*/analysis/*.json`, with `link: "./site-ci.svg"`.

**site-ci.** Objective: the site continuous integration (CI) workflow proves, on every push to master, that the commit installs, lints, type-checks and passes its tests before any page is built.
- Sources: `site_yml` (file, `@file .github/workflows/site.yml`).
- States:
  - `installed`, `linted`, `typed`, `tested` (all `step`), and `ci_failed` (`step`, terminal).
  - Neighbour `on_master` (`step`, `link: "./site-publish.svg"`, `No incoming edge` comment).
  - Neighbour `base_url_set` (`decision`, `link: "./site-scan.svg"`, `@symbol bot.web.site.normalize_base_url`).
- Edges (11):
  - From `on_master`: `→installed`, `→ci_failed`.
  - Each check passes or fails: `installed→linted`, `installed→ci_failed`, `linted→typed`, `linted→ci_failed`, `typed→tested`, `typed→ci_failed`.
  - `tested→base_url_set` (`@symbol bot.cli.site`).
  - `tested→out`, `site_yml→installed`.
- How lines must show:
  - `uv sync --frozen`, `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q`;
  - a newer push cancels the running one;
  - a failing step stops the job and nothing is deployed;
  - `bot site --out site --base-url /<repo>/`.
- `out`: `Comes out:` the commit of master, installed, linted, type-checked and tested, handed to `bot site`, with `link: "./site-scan.svg"`.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py -k "publish or ci"`. Expected: FAIL.
- [ ] **Step 2:** Write both boards.
- [ ] **Step 3:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_diagram.py -k "publish or ci or acronym or directive or required or purpose"`. Expected: every test that does not need an SVG passes. `python3 docs/pipeline/check.py` reports only missing-SVG, missing-link-target and stale-hash errors.
- [ ] **Step 4:** Commit `docs(#164): site-publish and site-ci sub-boards`.

### Task 3: `site-scan.d2` and `site-views.d2`

**Files:** Create `docs/pipeline/site-scan.d2`, `docs/pipeline/site-views.d2`.

**site-scan.** Objective: start the build on a safe output folder and keep only the sidecars the viewer can read and render.
- Sources: `reports` (file): `reports/*/analysis/*.json` of the checked-out commit.
- States:
  - `base_url_set` (`decision`, `@symbol bot.web.site.normalize_base_url`);
  - `out_refused` (`step`, terminal, `@symbol bot.web.site._prepare_out_dir`);
  - `out_ready` (`decision`, `@const bot.web.site.MARKER`, label shows `.bot-site`);
  - `skipped` (`step`, terminal, `@symbol bot.web.index.read_sidecar`);
  - `usable` (`step`, `@symbol bot.web.index.scan`);
  - `renderable` (`decision`, `@symbol bot.web.site._renderable`).
- Neighbours:
  - `tested` (`step`, `link: "./site-ci.svg"`, `@file .github/workflows/site.yml`, `No incoming edge`);
  - `row` (`step`, `link: "./site-views.svg"`, `@symbol bot.web.views.row_view`, `No outgoing edge`).
- Edges (17):
  - `tested→base_url_set` (`@symbol bot.web.site.build`).
  - `base_url_set→out_refused`, `base_url_set→out_ready`.
  - Five `out_ready→skipped`, one per skip step.
  - `out_ready→usable`, whose second line is `[it passes every check above]`.
  - `usable→skipped`, `usable→renderable`.
  - Four `renderable→row`, one per margin band: `@const MOS_UNDERVALUED` on 1.3 or more; both consts on the 1.0 to 1.3 band; `MOS_FAIR` on below 1.0.
  - `renderable→out`, second line `[the analysis is kept]`.
  - `reports→out_ready`.
- How lines must show:
  - one leading and one trailing slash;
  - why the output folder is refused: it holds or is the reports folder, it exists and is not a folder, or it is not empty and has no `.bot-site` marker;
  - the folder is emptied (or created), and the marker is written before any page;
  - the folder name must be a `YYYY-MM-DD` date, read back unchanged;
  - the ticker is up to twelve characters among capital letters, digits, `.` and `-`;
  - `schema_version` 1 (`@const bot.reporting.analysis_json.SCHEMA_VERSION`);
  - `analysis.ticker` equals the file name;
  - the sidecar is grouped by ticker, newest analysis first;
  - a company with no analysis left is dropped;
  - a skip leaves a warning in the log.
- `out`: `Comes out:` each company the viewer can render, its analyses newest first, each one complete, with `link: "./site-views.svg"`.

**site-views.** Objective: turn each accepted analysis into its verdict, its place on the list pages and its own pages, then put the site online.
- Sources:
  - `design` (file, `@file docs/DESIGN.md`);
  - `github_pages` (external): GitHub Pages, `https://<owner>.github.io/<repo>/`.
- States:
  - `row` (`step`, `@symbol bot.web.views.row_view @symbol bot.web.views.verdict_of`);
  - `listed` (`step`, `@symbol bot.web.views.filter_sort`);
  - `pages` (`step`, `@symbol bot.web.site._write_company`);
  - `live` (`step`, `@file .github/workflows/site.yml`).
- Neighbour: `renderable` (`decision`, `link: "./site-scan.svg"`, `@symbol bot.web.site._renderable`).
- Edges (10):
  - Four `renderable→row`, each showing the verdict text and the filter value: 1.3 or more → potentially undervalued → undervalued; 1.0 to under 1.3 → around fair value → fair; below 1.0 → potentially overvalued → overvalued; no price → n/a → na. Carry `@enum bot.web.views.Verdict` on one of them.
  - `row→listed`, `listed→pages`, `pages→live`.
  - `live→out`, first line `the run ends`.
  - `design→pages`, `github_pages→live`.
- How lines must show:
  - the list row fields;
  - list rows read the verdict text the sidecar carries, while the value line and the grid cells recompute it from their own MoS;
  - verdict counts: all = every company, then one per verdict;
  - filters `all, undervalued, fair, overvalued, na`, sorts `ticker, mos, date`, directions `asc, desc`, each list shown on its line with `@const`;
  - ties by ticker ascending, and rows without a MoS last when sorted by MoS;
  - the page paths `c/TICKER.html`, `c/TICKER/YYYY-MM-DD.html`, `f/...`;
  - upload of the site folder as the Pages artifact, then the deploy job after the build job.
- `out`: `Comes out:` the live static viewer (`index.html`, `l/`, `rows/`, `c/`, `f/`, `404.html`, `robots.txt`, `static/`), with `link: "./site.svg"`.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py -k "scan or views"`. Expected: FAIL.
- [ ] **Step 2:** Write both boards.
- [ ] **Step 3:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py`. Expected: only the SVG-dependent tests and `test_check_py_exits_zero` fail.
- [ ] **Step 4:** Commit `docs(#164): site-scan and site-views sub-boards`.

### Task 4: stage board links and the README section

**Files:** Modify `docs/pipeline/site.d2` and `docs/pipeline/README.md`.

- [ ] **Step 1:** In `site.d2`, add one `link:` line as the first line inside each of the containers `publish` (`./site-publish.svg`), `ci` (`./site-ci.svg`), `build` (`./site-scan.svg`) and `serve` (`./site-views.svg`). For node `build.rows`, put `link: "./site-views.svg"` after `class: step`. Make no other change. Run `git diff --stat docs/pipeline/site.d2`; expected: `5 insertions(+)`.
- [ ] **Step 2:** In `README.md`, add a `## Sub-boards` section before `## Models`. It covers:
  - naming: `<stage>-<sub>.d2`, where `<sub>` is a group of the stage's model;
  - the three fixed nodes: `objective`, `back`, `out` with `Comes out:`;
  - navigation: stage → sub-board → back to the stage, or on to the next sub-board;
  - where states and edges come from: the checked statechart in `models/`, with the label match;
  - the decision rule;
  - neighbour nodes;
  - the cap of 24 edges.

  Update the opening paragraph so it counts the sub-boards. Keep every existing section. Total length is at most 90 lines.
- [ ] **Step 3:** Run `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "readme or site"`. Expected: PASS, except the SVG-dependent tests.
- [ ] **Step 4:** Commit `docs(#164): link the site sub-boards, document sub-boards`.

### Task 5: render in CI and commit the SVGs (the controller does this)

- [ ] Push. Get the latest run id with `gh run list --branch agent/164-site-subboards --workflow pipeline-diagram --limit 1`, then `gh run watch <id> --exit-status`. On a d2 error, read `gh run view <id> --log-failed`, fix and push again.
- [ ] Run `gh run download <id> -n pipeline-render -D /tmp/render` and copy `*.svg` and `rendered.sha256` into `docs/pipeline/`. Look at the PNGs of the four sub-boards. If a board has more than 24 edges or an unreadable label, apply step 7 of the issue (change the view labels or groups, never the TLA+ logic). Commit `docs(#164): render site sub-boards`, push.
- [ ] The run on the final head is green in both jobs. `uv run pytest -q`, `uv run ruff check . && uv run mypy src` and `python3 docs/pipeline/check.py` (`0 errors`) all pass locally.

## Grilling

- Rounds: one. The revisions were additive (one test, one stricter parse rule, an Assumptions section) and changed no seam or step, so no second round was run.
- Griller model: fable. It asked 18 questions.
- Sources used for the answers:
  - ISSUE: 8 (Q1 via the view labels quoted in the issue context, Q5, Q12, Q13, Q15, Q17, Q18, and Q8 for the CI loop's expected red run);
  - CODE: 15 (several questions cite both);
  - NO SOURCE: 4 (Q10, Q14, Q15 workaround, Q16). All four are technical assumptions: A1 to A3 above, plus `test_every_edge_line_is_parsed`.
- Spec ambiguities: none. Out of scope: none. No issues opened.
