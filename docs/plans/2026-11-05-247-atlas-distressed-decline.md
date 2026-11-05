# Atlas, model labels, lesson and plano describe the distressed and mature-decline branches — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every document that still says "p stays 0" or "mature-decline has no treatment of its own" now describes what the code on `feature/213-story-types-drive-assumptions` actually does. That covers the analyze boards, the TLA+ model labels, the lesson and the two plano sources.

**Architecture:** This is a documentation-only change. No file under `src/` changes. Each document is checked by an existing test or script (`docs/pipeline/check.py`, `docs/leccion/check.py`, `docs/plano/build.py`, `tests/unit/test_pipeline_*.py`). A new test file, `tests/unit/test_story_branch_docs.py`, pins the issue's exact text. The SVGs are rendered by the `pipeline-diagram` CI workflow (d2 is not installable locally) and copied back from its artifact.

**Tech Stack:** d2 boards, TLA+ comments plus a JS view map, static HTML (Spanish), Python data modules (`estado.py`), a JS object literal (`part-data.js`), pytest.

**Spec:** issue #247 (child of story #213). Its "Files to change" section pins the exact text and is binding.

## Global Constraints

- Code facts to describe. They are already on BASE; read the functions, do not change them:
  - `_resolve_operating_margin` (`src/bot/valuator/assumptions.py:1093`): for mature-decline with an own margin, `(company_margin,) * _HORIZON` with source `historical_average`. With no own margin, it falls back to the sector median.
  - `_resolve_probability_of_bankruptcy` (`assumptions.py:1235`): manual wins. Distressed: coverage → `rating_for` → `probability_for` gives `rule_based` and a `BankruptcyDerivation`. Unknown coverage, an empty table, no bracket or no row gives p = 0 `rule_based` plus a `reason`. Every other story gets 0 `rule_based`.
  - Tables: `config/default_spreads.yaml`, loaded by `bot.reference.default_spreads.load_default_spreads` (`src/bot/reference/default_spreads.py:239`).
  - Distress value per share is manual or 0. Altman Z is computed nowhere. Sales-to-capital does not vary by story type.
- Pinned text is copied verbatim from the issue (line breaks may be adapted with `\n` in d2). Write "ten-year" in words on d2 step labels: a digit on a step label needs an `@const` citation.
- `analyze-assumptions.d2` keeps exactly 24 edges. No node and no edge is added.
- `analyze.tla`: only the `(* ... *)` comment lines above `MarginIsResolved` and `TaxAndBankruptcyAreSet` change. No logic changes.
- `story_type.distressed.altman` (analyze.d2) stays. `part-data.js` card `s-ds` must keep the phrase `El Altman Z decide la clasificación`, because `test_document_gaps_are_current` ties that gap to it.
- `estado.py`: `AUDITADO_EN`/`AUDITADO_EL` are unchanged (`test_estado_audit_stamp` pins them). There are still 79 rows. Rows `story-uso`, `a-quiebra` and `dcf-quiebra` still mention `hypergrowth`, and `story-uso` evidence still cites `valuator/hypergrowth.py:` (`test_estado_rows_carry_hypergrowth_evidence`). Card `a-default` still names `failure_probability` and `failure_proceeds_pct_of_value`.
- The lesson and plano are in Spanish (rioplatense, voseo), matching the surrounding prose.
- Technical decision: the `manual_only` gap node is **renamed** `altman`, as `assumptions.bankruptcy.altman`, because its text is now about Altman Z. The issue says "replace the gap note"; a key that says `manual_only` over a text that says the opposite would mislead. The three existing pins in `tests/unit/test_pipeline_diagram.py` (node list ≈l.1582, phrase list ≈l.1696, `_ANALYZE_GAPS` ≈l.1969) move to the new key and text.
- Commits: `docs(#213): boards, model labels, lesson and plano describe the distressed and mature-decline branches` (issue-pinned subject; implementer tasks may split it with the same prefix), `docs(#213): re-render the boards`.
- `uv run ruff check . && uv run mypy src` clean; `uv run pytest -q` green.

## Review Focus

1. **A label that equals the view label but not the d2 edge**, or the other way round: `test_step_labels_are_drawn` matches the view labels against the d2 edge first lines character by character. Both come from one pinned string. Pinned by `test_assumptions_board_first_lines_equal_the_view_labels` (Task 2).
2. **An uncited digit on a d2 step label** (for example "10-year" in the bankruptcy node, or "0.6"): `test_every_step_has_purpose_and_edges` fails. Write "ten-year" in words. That existing test covers this.
3. **Removing the plano phrase the Altman gap depends on**: `test_document_gaps_are_current` (existing) covers it.
4. **Stale `class="at"` line for the new lesson symbol**: `docs/leccion/check.py` only warns on a moved line. Pinned by `test_leccion_cites_load_default_spreads_at_its_line` (Task 3), which asserts the cited line equals the `def` line.
5. **Committed SVGs that lag the d2**: `test_svgs_show_their_step_labels` checks the first lines of step nodes, and the CI step "committed render is current" checks `rendered.sha256`. Task 5 covers this by re-rendering from CI, and again after any later d2 edit.

---

### Task 1: `analyze.d2` margin and bankruptcy nodes, the Altman-only gap

**Files:**
- Modify: `docs/pipeline/analyze.d2` (`assumptions.margin` ≈l.116, `assumptions.bankruptcy` ≈l.136-139)
- Modify: `tests/unit/test_pipeline_diagram.py` (pins ≈l.1582, 1696, 1969)
- Test: `tests/unit/test_story_branch_docs.py` (written in stage 3)

**Interfaces:** none (text only).

- [ ] **Step 1: Run the stage-3 tests and confirm they fail:** `uv run pytest -q tests/unit/test_story_branch_docs.py -k "analyze_board"` gives FAIL.
- [ ] **Step 2: Rewrite the `margin` label** with the issue's seven pinned segments: `operating margin, a 10-year path` / `1. manual → manual` / `2. high-growth … → story_pattern` / `3. cyclical with ≥ 4 years … → historical_average` / `4. mature-decline with a latest EBIT ÷ revenue: that margin each year → historical_average` / `5. sector op_margin each year → sector label` / `no sector op_margin: unresolved`. Keep the existing directive (`@symbol …_resolve_operating_margin @const …_HORIZON @const …_MIN_CYCLE_YEARS`).
- [ ] **Step 3: Rewrite the `bankruptcy` label** with the issue's pinned segments, and set its directive to `# @symbol bot.valuator.assumptions._resolve_probability_of_bankruptcy @file config/default_spreads.yaml @symbol bot.reference.default_spreads.load_default_spreads`.
- [ ] **Step 4: Replace the child gap** `manual_only` with `altman: |md Gap: spec §7.3 derives a distressed company's p from its rating or Altman Z; Altman Z is computed nowhere, so the rating is synthetic, from interest coverage alone; the distress value per share is still manual or 0. | {class: gap}`.
- [ ] **Step 5: Update the three pins** in `test_pipeline_diagram.py`. Use `("assumptions.bankruptcy.altman", "gap")`. The phrase list for `assumptions.bankruptcy` becomes `["manual", "interest coverage", "synthetic rating", "rule_based", "config/default_spreads.yaml"]`. `_ANALYZE_GAPS["assumptions.bankruptcy.altman"] = ["Altman Z", "computed nowhere", "interest coverage alone"]`. Add `"mature-decline"` to the `assumptions.margin` phrase list.
- [ ] **Step 6:** `python3 docs/pipeline/check.py` reports 0 errors. `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_story_branch_docs.py -k "analyze_board or pipeline_diagram"` passes, except `test_svgs_show_their_step_labels`, which waits for Task 5.
- [ ] **Step 7: Commit** with the `docs(#213): …` subject.

### Task 2: `analyze-assumptions.d2` edges, view labels, TLA citation comments

**Files:**
- Modify: `docs/pipeline/analyze-assumptions.d2` (edges `growth_set -> margin_set` with the first, non-"unresolved" label, and `tg_set -> ready` with the first, non-hypergrowth label)
- Modify: `docs/pipeline/models/analyze.view.js` (l.88, l.98)
- Modify: `docs/pipeline/models/analyze.tla` (comments l.308 and l.378 only)
- Test: `tests/unit/test_story_branch_docs.py`

- [ ] **Step 1:** Confirm the stage-3 `assumptions_board` / `view` / `tla` tests fail.
- [ ] **Step 2: `growth_set -> margin_set`.** The first line is exactly `operating margin gets a source [manual, story pattern, cycle average, own margin, or sector]`. Then the numbered steps mirror Task 1: insert step `4. mature-decline with a latest earnings before interest and taxes (EBIT) ÷ revenue: that margin each year → historical_average` (or the "EBIT ÷ revenue" short form, since EBIT is expanded in step 2) and renumber the sector step to `5.`. The directive is unchanged.
- [ ] **Step 3: `tg_set -> ready`.** The first line is exactly `tax rate and bankruptcy odds are set [no story; tax manual, sector, country, or 25%; bankruptcy manual, from the coverage rating of a distressed company, or 0]`. Replace the last line (`bankruptcy odds and distress value per share: manual, else 0 → rule_based`) with the bankruptcy steps: `1. manual → manual`, `2. distressed: interest coverage → synthetic rating → ten-year cumulative default probability, both tables in config/default_spreads.yaml → rule_based; coverage unknown, or the file absent or malformed: 0 → rule_based, and the report says why`, `3. else 0 → rule_based`, `distress value per share: manual, else 0 → rule_based`. Append `@file config/default_spreads.yaml @symbol bot.reference.default_spreads.load_default_spreads` to the existing directive.
- [ ] **Step 4: Update `analyze.view.js`.** Set `MarginIsResolved` and `TaxAndBankruptcyAreSet` to the two first lines above, byte for byte.
- [ ] **Step 5: Update `analyze.tla`.** The comment above `MarginIsResolved` becomes `(* src/bot/valuator/assumptions.py: _resolve_operating_margin (manual; high-growth ramp; cyclical cycle average; mature-decline own latest margin, flat; sector) *)`. The comment above `TaxAndBankruptcyAreSet` becomes `(* src/bot/valuator/assumptions.py: _resolve_tax_rate, _resolve_probability_of_bankruptcy (manual; distressed: interest coverage -> rating -> default probability, src/bot/reference/default_spreads.py), _resolve_distress_value_per_share *)`. No other line changes.
- [ ] **Step 6:** `uv run pytest -q tests/unit/test_pipeline_models.py tests/unit/test_pipeline_subboards.py tests/unit/test_story_branch_docs.py` passes, and `python3 docs/pipeline/check.py` reports 0 errors.
- [ ] **Step 7: Commit** with the same subject prefix.

### Task 3: Lesson chapters 6 and 7

**Files:**
- Modify: `docs/leccion/index.html` (cap-6 table row ≈l.626, cap-6 caveat ≈l.645-646, cap-7 `rule_based` row ≈l.666, the cap-7 "En el código" list)
- Test: `tests/unit/test_story_branch_docs.py`

- [ ] **Step 1:** Confirm the stage-3 `leccion` tests fail.
- [ ] **Step 2: Split the cap-6 row** `mature-stable, mature-decline, distressed` into three `<tr>` rows, each `<th scope="row"><code>…</code></th>`:
  - `mature-stable`: growth as today ("Sin tratamiento propio: baja en línea recta …"), margin "Sin tratamiento propio: la mediana del sector, plana."
  - `mature-decline`: growth like the others. Margin: its own operating margin from the last year, flat for the ten years, without converging to the sector (`historical_average`); without its own margin, the sector median.
  - `distressed`: growth and margin like the others (the sector median, flat). What changes is the probability of bankruptcy (chapter 7).
  Update the sentence above the table ("es menos que lo que describe el diseño") only if it now contradicts the table.
- [ ] **Step 3: Rewrite the caveat.** It must say that p now comes from the interest coverage through the two curated tables in `config/default_spreads.yaml` (coverage → rating sintético → probabilidad acumulada a diez años), that a manual value wins, that Altman Z is still not computed, and that the distress value per share is still manual. Keep the Altman / `analyze` paragraph. Drop "Nada de eso se calcula solo" and "esa probabilidad queda en 0 salvo".
- [ ] **Step 4: Update the cap-7 `rule_based` row.** p is 0 except for a `distressed`, where it comes from the chain coverage → rating sintético → probabilidad de default a diez años. Also extend the `historical_average` row: "o el último margen propio, plano, en una `mature-decline`".
- [ ] **Step 5:** Add `<li><code data-symbol="bot.reference.default_spreads.load_default_spreads">bot.reference.default_spreads.load_default_spreads</code> · <code class="at">src/bot/reference/default_spreads.py:239</code>: …</li>` to the cap-7 "En el código" list. The text says what it loads and that a missing or malformed file gives an empty table and p = 0.
- [ ] **Step 6:** `python3 docs/leccion/check.py` reports 0 errors and no warning for the new symbol. `uv run pytest -q tests/unit/test_leccion.py tests/unit/test_leccion_check.py tests/unit/test_story_branch_docs.py` passes.
- [ ] **Step 7: Commit.**

### Task 4: Plano: four `estado.py` entries and three `part-data.js` cards

**Files:**
- Modify: `docs/plano/estado.py` (`story-uso`, `story-altman`, `a-quiebra`, `dcf-quiebra`, ≈l.107-128)
- Modify: `docs/plano/part-data.js` (`s-md` ≈l.200-203, `s-ds` ≈l.210-214, `a-default` ≈l.266-272)
- Test: `tests/unit/test_story_branch_docs.py`

- [ ] **Step 1:** Confirm the stage-3 `plano` tests fail.
- [ ] **Step 2: Update the `estado.py` entries** (status token, title and evidence path stay unless noted):
  - `story-uso` (`a-medias`): add that `_resolve_operating_margin` keeps a mature-decline's own latest margin, flat, and that a distressed company gets p from its coverage (`_resolve_probability_of_bankruptcy`). Mature-stable has no branch of its own, and sales-to-capital still does not vary by story type. Drop "Siguen faltando los otros cinco arquetipos". Refresh the evidence lines to the current `def` lines.
  - `story-altman` (`falta`): Altman Z is still computed nowhere. The rating behind p is synthetic, from interest coverage alone.
  - `a-quiebra` (`a-medias`): manual wins. Hypergrowth comes from the story. A distressed company gets coverage → rating → ten-year probability via `config/default_spreads.yaml` (`reference/default_spreads.py`). Still missing: Altman Z and the distress value per share (manual or 0). Evidence: `valuator/assumptions.py:<def line>; reference/default_spreads.py:239; valuator/hypergrowth.py:329,333`.
  - `dcf-quiebra` (`hecho`): the per-share path is now fed for a distressed company (p from coverage), but `distress_value_per_share` is still manual or 0.
- [ ] **Step 3: Update the `part-data.js` cards:**
  - `s-md`: add a `notes` entry. The bot keeps the company's own latest operating margin, flat, without converging to the sector. Growth fades like every story's. Neither negative growth nor minimal reinvestment is derived.
  - `s-ds`: keep the phrase `El Altman Z decide la clasificación`. The rest of the note says p comes from the interest coverage → synthetic rating → ten-year default probability (`config/default_spreads.yaml`), that a manual value wins, and that the distress value stays manual or 0.
  - `a-default`: the lead and the idea paragraph "Esa derivación no está hecha…" now say that in a distressed company p comes from the coverage chain, that Altman Z is not computed, and that the distress value is still manual. The `code.where` "se mueve con" row adds the coverage. Keep the hypergrowth keys.
- [ ] **Step 4:** `python3 docs/plano/build.py` passes. `uv run pytest -q tests/unit/test_hypergrowth_docs.py tests/unit/test_pipeline_diagram.py tests/unit/test_story_branch_docs.py` passes.
- [ ] **Step 5: Commit.**

### Task 5: Re-render from CI (run by the session, not a subagent)

- [ ] Push the branch. In the foreground, run `gh run list --branch <branch> --workflow pipeline-diagram --limit 1 --json databaseId,status`, then `gh run watch <id> --exit-status` (timeout ≥ 10 min). The `render` job's "committed render is current" step fails as expected until the SVGs land; the artifact is uploaded regardless.
- [ ] `gh run download <id> -n pipeline-render -D <new empty dir outside the repo>`. Copy only `*.svg` and `rendered.sha256` into `docs/pipeline/`.
- [ ] `python3 docs/pipeline/check.py` passes, and so does `uv run pytest -q`. Commit `docs(#213): re-render the boards` and push. The next run's `render` job (including "committed render is current") and `models` job must be green.
- [ ] Repeat after any later d2 edit (review fixes, deslop).
