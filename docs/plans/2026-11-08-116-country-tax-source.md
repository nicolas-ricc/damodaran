# Country-sourced tax rate gets its own source — Implementation Plan

> **Superseded (#320):** analyst consensus is not a source, by decision (#63); mentions of it below are historical.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the tax rate falls back to the company's `damodaran_country` row, tag it `country_default_damodaran` instead of `sector_default_damodaran`, and explain the new source everywhere sources are explained to a reader.

**Architecture:** One new `AssumptionSource` member, emitted on the country step of `_resolve_tax_rate` only. The enum-set tests in the lesson and the pipeline boards derive their expectations from the enum, so the lesson's chapter 7 table and the two boards' source notes gain the value in the same task as the resolver (Task 1), keeping the suite green after every task. Task 2 gives the viewer glossary a worded term and pins the report and viewer rendering.

**Tech Stack:** Python 3.12, pytest, DuckDB, Jinja2, d2 v0.9.0 (boards, rendered by the `pipeline-diagram` CI workflow), ruff, mypy --strict.

**Spec:** GitHub issue #116 (`gh issue view 116 --repo nicolas-ricc/damodaran --comments`); the triage comment's Agent Brief and its five acceptance criteria are binding.

## Global Constraints

- New member: `AssumptionSource.COUNTRY_DEFAULT_DAMODARAN = "country_default_damodaran"`, placed after `SECTOR_DEFAULT_DAMODARAN_CROSS_REGION`, with a `#:` comment like its neighbours.
- `_resolve_tax_rate` order stays manual → sector → country → 25% (`_DEFAULT_TAX_RATE`). Only the country step's source changes. Manual stays `MANUAL`, the sector step stays `sector.source` (`SECTOR_DEFAULT_DAMODARAN` or `SECTOR_DEFAULT_DAMODARAN_CROSS_REGION`), the default stays `RULE_BASED`.
- No other resolver emits the new member (ERP country sources are out of scope).
- Out of scope (issue): the ISO/name country mismatch (#271, already merged), the fallback order, country sources for ERP.
- Never hand-edit an SVG or `docs/pipeline/rendered.sha256`: they come from `docs/pipeline/build.sh` with pinned d2, here through the `pipeline-render` artifact of the `pipeline-diagram` workflow (the repo's practice, see commit 2b6e611).
- Lesson copy is Spanish (rioplatense, `vos`), like the rest of `docs/leccion/index.html`. Viewer glossary copy is English, no snake_case identifiers (`test_glossary_has_no_leftover_identifier`).
- Green at the end: `uv run ruff check . && uv run mypy src && uv run pytest -q`, `python3 docs/leccion/check.py`, `python3 docs/pipeline/check.py` (the last one only after the render is committed).

## Assumptions (declared)

- **"Report rendering"** is the Markdown/JSON report: the `Source` column of `analysis.md.j2` prints the raw source value for every row and the JSON sidecar stores it. Neither has a per-source legend, so nothing in `src/bot/reporting` changes; Task 2 pins that a country-sourced tax row renders `country_default_damodaran`.
- **The viewer's "N of M are sector defaults" count** (`bot.web.views._defaulted`, compares to `"sector_default_damodaran"`) stops counting a country-sourced tax rate. That is the correct reading (it is not a sector default) and matches how cross-region rows are already treated. No change to `_defaulted`.
- **`docs/plano/part-data.js`** (its origins list already lacks `story_pattern` and `story`, a gap recorded on `analyze.d2` as `plano_sources`) and the design spec §7.3 list (already stale: it still names `analyst_consensus`) are not edited: the issue names the viewer glossary, the report, the lesson and the pipeline boards. The `plano_sources` gap stays as it is.
- **Board text.** Both boards' "source label" notes gain `country_default_damodaran: the country row of the company's country (tax rate only)`, and the `sector_default_damodaran` line drops "or country". The tax steps (`analyze.d2` `assumptions.tax`, `analyze-assumptions.d2` edge `tg_set -> ready`) say `3. country tax_rate → country_default_damodaran`.
- **The lesson** says "Las procedencias que existen en el código son nueve" (and "las nueve procedencias" in the `AssumptionSource` citation at `index.html:702`, and "el código tiene nueve" in the caveat at `index.html:710`: the three places "ocho" appears), drops "Si la industria no trae impuesto, se usa el del país, con la misma etiqueta." from the `sector_default_damodaran` row and adds a `country_default_damodaran` row after `sector_default_damodaran_cross_region`.

- **Module docstring.** `assumptions.py:16-17` files "the country's ERP / tax rate from damodaran_country" under "3. Sector default". No valuator resolver reads the country ERP (`grep -n '\.erp' src/bot/valuator/*.py` is empty). Those two lines become: medians from damodaran_industry; the country's tax rate from damodaran_country is sourced COUNTRY_DEFAULT_DAMODARAN.
- **The lesson's source count is free prose.** No test or `check.py` rule pins "nueve" to `len(AssumptionSource)` (`tests/unit/test_leccion.py` only checks the set, line 553). Rejected alternative: a new count test, which the issue does not ask for.
- **Lesson citations.** `docs/leccion/check.py` compares each `archivo:línea` with the symbol's real line and only warns (`check.py:51`, exit 0). Today it already reports 22 moved lines (pre-existing). This plan re-points only the four citations into `assumptions.py` (`AssumptionSource`, `Sourced`, `conventional_override_path`, `resolve_assumptions`, cited at `:102`, `:126`, `:704`, `:821`) to their lines after the edit. The other 18 are left alone, since they are outside this diff.
- **Isolation goldens and the viewer sidecar move.** The shared `_seed` of `tests/unit/test_valuator_analysis.py` inserts a `damodaran_industry` row without `tax_rate` and a `damodaran_country` row with `0.21`. Every golden company therefore takes the country step: the `tax_rate` source in `tests/fixtures/valuator/isolation/{cyclical,distressed,high_growth,mature_decline,mature_stable}.{json,md}` becomes `country_default_damodaran`, and so does the source in `tests/web_sidecars.real_sidecar()`. That is the deliberate behaviour change, so they are regenerated with the module's `regenerate()`, a "Regenerated for #116" line goes into its docstring, and `git diff tests/fixtures` must show only the tax source lines (`override.*` stays `manual`). `reports/` holds dated past outputs and is not regenerated.
- **Commit type `fix`.** The issue is labelled `bug` and its brief says "Category: bug". The repo history uses `fix(#N)` for bug issues (e.g. `fix(#271)`).

## Criteria → tasks

| Issue criterion | Where |
|---|---|
| 1. country step → country's rate, new source | Task 1 Step 1 (unit) |
| 2. sector and cross-region tax keep their sources | existing `test_tax_rate_uses_sector_default` and `test_cross_region_substitution_is_disclosed` (asserts `tax_rate.source is ..._CROSS_REGION`) run unchanged in Task 1 Step 6 |
| 3. pinned integration test flipped | Task 1 Step 1 |
| 4. enum-set tests (valuator, JSON, lesson, boards) include it; docs updated | Task 1 Steps 1, 3, 4 (the JSON `:39`, lesson `:553` and board `test_analyze_assumption_sources` `:1962` sets iterate the enum; the valuator set `:1171` is literal) |
| 5. viewer shows words + tooltip, no raw identifier | Task 2 |

## Review Focus

- A country row with `tax_rate = 0.0` (Bahamas in the fixtures): `0.0` is not `None`, so the country step is taken and sourced `country_default_damodaran`. Pinned in Task 1 (`test_tax_rate_zero_country_rate_is_still_the_country_source`).
- A sector row present but with `tax_rate = NULL`, from another region (cross-region): the sector step is skipped, so the country step wins with the country source, not `..._cross_region`. Pinned in Task 1 (`test_cross_region_sector_without_tax_falls_to_the_country_source`).
- No country row and no sector tax: still `0.25` `rule_based`. Pinned by the existing `test_tax_rate_rule_based_default_when_no_data`.
- A country row whose `tax_rate` is NULL, with no sector tax: `_resolve_tax_rate` checks `country.tax_rate is not None` (`assumptions.py:1305`), so the result is `0.25` `rule_based`, never the country source with `None`. Pinned in Task 1 (`test_tax_rate_null_country_rate_is_rule_based`).
- A hypergrowth story keeps the marginal tax rate's own source (the story only shapes `tax_rate_path`): unchanged code; the existing hypergrowth tests run unchanged.
- An older analysis JSON without the new value still renders in the viewer (the glossary falls back on unknown keys; known keys are unaffected). Covered by `test_unknown_names_fall_back_to_words_without_a_description`.

---

### Task 1: Emit `country_default_damodaran` on the country tax step, and document it

**Files:**
- Modify: `src/bot/valuator/assumptions.py:16-17` (module docstring), `:107-127` (enum), `:1287-1307` (`_resolve_tax_rate`, docstring says the country step is sourced `COUNTRY_DEFAULT_DAMODARAN`)
- Modify: `docs/leccion/index.html` (chapter 7 source table, the "son ocho" sentence; fix any line-moved warning of `check.py`)
- Modify: `docs/pipeline/analyze.d2` (`assumptions.tax`, `assumptions.sources`), `docs/pipeline/analyze-assumptions.d2` (edge `tg_set -> ready` tax lines, `sources` note)
- Modify (regenerated): `tests/fixtures/valuator/isolation/{cyclical,distressed,high_growth,mature_decline,mature_stable}.{json,md}`; docstring of `tests/unit/test_valuator_isolation_golden.py`
- Test: `tests/unit/test_valuator_assumptions.py` (tax section near line 907, enum set at 1171), `tests/integration/test_damodaran_import.py:221`, `tests/unit/test_country_iso_lookups.py:105`, `tests/unit/test_pipeline_diagram.py` (`"assumptions.tax"` needles), `tests/unit/test_pipeline_subboards.py` (`"analyze-assumptions"` needles)

**Interfaces:**
- Produces: `AssumptionSource.COUNTRY_DEFAULT_DAMODARAN` (value `"country_default_damodaran"`), used by Task 2.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_valuator_assumptions.py`, using the existing `_seed_company`, `_seed_industry`, `_seed_country` helpers:

```python
def test_tax_rate_falls_back_to_the_country_source(conn) -> None:
    _seed_company(conn)
    _seed_industry(conn, tax_rate=None)
    _seed_country(conn, tax_rate=0.30)
    tax = resolve_assumptions("ACME", conn).tax_rate
    assert tax.value == pytest.approx(0.30)
    assert tax.source is AssumptionSource.COUNTRY_DEFAULT_DAMODARAN

def test_tax_rate_zero_country_rate_is_still_the_country_source(conn) -> None:
    # same seeding, country tax_rate=0.0 → value 0.0, COUNTRY_DEFAULT_DAMODARAN

def test_tax_rate_null_country_rate_is_rule_based(conn) -> None:
    # industry tax_rate=None, country tax_rate=None → value 0.25, RULE_BASED

def test_cross_region_sector_without_tax_falls_to_the_country_source(conn) -> None:
    # seeding of test_cross_region_substitution_is_disclosed (DEU, Germany,
    # sector row only in "US"), but _seed_industry(..., tax_rate=None) and
    # _seed_country(..., tax_rate=0.30)
    # → value 0.30, COUNTRY_DEFAULT_DAMODARAN
```

Add `"country_default_damodaran"` to the expected set in the enum-set test (line 1171). Flip `test_valuator_falls_back_to_the_imported_country_tax_rate` and `test_valuator_tax_falls_back_to_iso_country` to `AssumptionSource.COUNTRY_DEFAULT_DAMODARAN`. Add `"country_default_damodaran"` to the `"assumptions.tax"` needles in `test_pipeline_diagram.py` and to the `"analyze-assumptions"` needles in `test_pipeline_subboards.py`.

- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/unit/test_valuator_assumptions.py tests/unit/test_country_iso_lookups.py tests/integration/test_damodaran_import.py tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py -q`. Expected: `AttributeError: COUNTRY_DEFAULT_DAMODARAN` in the valuator tests, a set mismatch in the enum test, missing needles in the two board tests.

- [ ] **Step 3: Implement** the enum member and the one-line source change in `_resolve_tax_rate`.

- [ ] **Step 4: Update the docs** as declared in Assumptions (lesson table and count; both boards' tax steps and source notes). Do not render: the SVGs and `rendered.sha256` come from CI (Global Constraints).

- [ ] **Step 5: Regenerate the isolation goldens**: `uv run python -c "from tests.unit.test_valuator_isolation_golden import regenerate; regenerate()"`, add the docstring line, and check `git diff --stat tests/fixtures` (ten files, `override.*` untouched) and `git diff tests/fixtures | grep '^[-+] '`. The only changed lines should be `sector_default_damodaran` → `country_default_damodaran` on the tax rate. `regenerate()` stamps the fixed `_GENERATED_ON` date, so any other changed line is unexpected. If one appears, stop and report it instead of accepting it or trimming it by hand.

- [ ] **Step 6: Run, expect PASS**: `uv run pytest -q` (whole suite: goldens, viewer and lesson tests included) and `python3 docs/leccion/check.py` (exit 0, with no `línea movida` warning left for `src/bot/valuator/assumptions.py`).

- [ ] **Step 7: Commit** `fix(#116): a country-sourced tax rate says country_default_damodaran`.

### Task 2: The viewer words the new source; the report shows it

**Files:**
- Modify: `src/bot/web/glossary.py:121-139` (`SOURCES`)
- Test: `tests/unit/test_web_glossary.py:56`, `tests/unit/test_web_views.py`, `tests/unit/test_reporting_analysis.py`

**Interfaces:**
- Consumes: `AssumptionSource.COUNTRY_DEFAULT_DAMODARAN` (Task 1).

- [ ] **Step 1: Write the failing tests**
  - `test_every_source_has_a_worded_term`: add `"country_default_damodaran"` to the tuple.
  - `test_web_views.py`: `test_country_tax_source_is_worded_with_a_tooltip` — `payload = real_sidecar()`, set `payload["analysis"]["assumptions"]["tax_rate"]["source"] = "country_default_damodaran"`, `detail = detail_view(_entry(_ref(payload)), _ref(payload))`; the `"Tax rate"` row's `source` is `"country default (Damodaran)"`, its `source_description` is non-empty, and neither contains `"_"`.
  - `test_reporting_analysis.py`: `test_render_shows_a_country_sourced_tax_rate`. The existing `analysis` fixture is already country-sourced (see Assumptions, isolation goldens). Assert `analysis.assumptions.tax_rate.source is AssumptionSource.COUNTRY_DEFAULT_DAMODARAN` and that the rendered Markdown's `| Tax rate |` line ends with `| country_default_damodaran |`.
  - The viewer renders a source only through `detail_view` → `LabelledValue.source`/`source_description` → `detail.html:71` (`term(a.source, a.source_description)`). `source_term` is called only at `views.py:359-361` and inside `source_label` (`views.py:94`). So asserting on `detail_view` covers what the page prints.

- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/unit/test_web_glossary.py tests/unit/test_web_views.py tests/unit/test_reporting_analysis.py -q`. Expected: the glossary and views tests fail (fallback term `"country default damodaran"` with an empty description); the report test passes already (it pins that the raw value reaches the report).

- [ ] **Step 3: Implement**: add to `SOURCES`, after `"sector_default_damodaran"`:

```python
"country_default_damodaran": Term(
    "country default (Damodaran)",
    "Damodaran's corporate tax rate for this company's country, used when its sector has no tax rate.",
),
```

- [ ] **Step 4: Run, expect PASS**: the Step 2 command, then `uv run ruff check . && uv run mypy src && uv run pytest -q`.

- [ ] **Step 5: Commit** `fix(#116): the viewer words the country tax source`.

### Final verification

- `uv run ruff check . && uv run mypy src && uv run pytest -q`
- `python3 docs/leccion/check.py`
- After the branch is pushed, the `pipeline-diagram` workflow (`on: [push, workflow_dispatch]`, so on every branch) renders the boards. Until the render commit lands, that workflow's `committed render is current` step is red on the branch, which is expected. Pick the run with `gh run list --workflow pipeline-diagram --branch <branch> --json databaseId,headSha,conclusion` whose `headSha` equals `git rev-parse HEAD`, and download its `pipeline-render` artifact (`gh run download <id> -n pipeline-render`), copy `analyze.svg`, `analyze-assumptions.svg` and `rendered.sha256` into `docs/pipeline/`, check `git status` shows only those, commit `chore(#116): render the analyze boards (pinned d2, CI artifact)`, then `python3 docs/pipeline/check.py` passes.

## Grilling

Two rounds; griller model: fable. 30 questions: 16 in round 1, 14 in round 2.

- **Answers by source:** CODE 24, ISSUE 3 (bug category, "Reports and the viewer then tell the reader it is a sector default", out-of-scope list), NO SOURCE 3.
- **Technical assumptions (the NO SOURCE answers):** the lesson count stays free prose; only the four `assumptions.py` lesson citations are re-pointed; the glossary wording follows the existing `sector default (Damodaran)` term.
- **Plan changes, round 1:** regenerate the five isolation goldens and note that `real_sidecar()` moves (the shared `_seed` has no industry tax, so its tax comes from the country step); a test for a NULL country tax; the lesson citations to re-point; the CI-artifact `headSha` check; a criteria-table fix.
- **Plan changes, round 2:** the third "ocho" in the lesson (`index.html:710`); the stale module docstring at `assumptions.py:16-17`; what to do if a golden diff shows more than the tax source.
- **Spec ambiguities:** none.
- **Out of scope:** the viewer glossary has no worded term for `manual`, `sector_default_damodaran_cross_region`, `story_pattern`, `story` or `unresolved`, and its `override` key is never emitted. Filed as https://github.com/nicolas-ricc/damodaran/issues/315.

