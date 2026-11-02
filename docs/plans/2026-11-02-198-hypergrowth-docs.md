# Hypergrowth written record: ADR 0009, spec §7, glossary, plans and lesson (#198) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the hypergrowth story type into every document that describes the valuator, true to the code merged on `feature/192-hypergrowth-story` (head `90f717c`), with no code change.

**Architecture:** Documentation only. One new ADR, edits to `CONTEXT.md`, the spec, the two plans (`docs/plano/`), and the lesson (`docs/leccion/index.html`). Every claim is read from `src/bot/valuator/` and cited by symbol or `file:line`. A new test module `tests/unit/test_hypergrowth_docs.py` and extended tables in `tests/unit/test_leccion.py` pin each deliverable. The existing checkers (`docs/plano/build.py`, `docs/plano/build_estado.py`, `docs/leccion/check.py`) stay green.

**Tech Stack:** Markdown, HTML, plain JS object literals, Python 3.12 (build scripts, pytest).

**Spec:** GitHub issue #198 (child of story #192). Its "What the code does" and "Deliverables" sections are binding. Read it alongside this plan.

## Global Constraints

- No change under `src/`. `tests/unit/test_valuator_isolation_golden.py` stays green untouched.
- The spec and the two plans and the lesson are in Spanish (rioplatense, "vos"); ADR 0009 and `CONTEXT.md` are in English, like their neighbours.
- ADR 0009 format is that of `docs/adr/0008-read-only-web-viewer.md`: `# 0009 — <title>`, then `## Status`, `## Context`, `## Decision`, `## Consequences`. Status line: `Accepted (2026-11-02). Implemented (2026-11-02, issue #192).`
- Exact values cited: `_HYPERGROWTH_LAST_YEAR_GROWTH = 0.50`, `_HYPERGROWTH_CAGR = 0.40`, `_HYPERGROWTH_MAX_AGE_YEARS = 15`, `_LARGEST_COMPANY_REVENUE = 750e9`, `_ROIC_SECTOR_MULTIPLE = 2.0`, `hypergrowth.HORIZON = 10`.
- Names: the story-file keys are the fields of `StoryInputs` (`src/bot/valuator/hypergrowth.py:53-71`), e.g. `failure_probability`, `failure_proceeds_pct_of_value`, `fixed_commitments_pv`. The resolved bundle and the DCF use their own names (`Assumptions.probability_of_bankruptcy`, `distress_proceeds_pct`, `fixed_commitments`, `extra_cash` in `src/bot/valuator/assumptions.py:136-198` and `src/bot/valuator/dcf.py:77-141`). A doc names a story key with the first set and a DCF input with the second.
- Story file money amounts are in the raw reporting currency of `financials_annual` (not millions) — `src/bot/valuator/hypergrowth.py` module docstring, `config/assumptions/README.md`.
- `python3 docs/plano/build.py`, `python3 docs/plano/build_estado.py`, `python3 docs/leccion/check.py` exit 0; `check.py` prints `0 errores, 0 avisos`.
- **Do not remove the phrases `tests/unit/test_pipeline_diagram.py::_DOC_GAPS` pins** in `docs/plano/part-data.js` and `docs/leccion/index.html` (`"rule_based · unresolved"`, `"el default es el promedio histórico"`, `"El Altman Z decide la clasificación"`, `"más ajustes por minoritarios"`, `"no caen en promedio más de"`, and the rest of that table). Those gaps live on the pipeline boards, which #199 owns; removing a phrase here fails `test_document_gaps_are_current`.
- Gates: `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py`.
- Commits: Conventional Commits with `#198` (`docs(#198): ...`, `test(#198): ...`).

## Decisions taken here (not spelled out by the issue)

1. **The "a-default" inventory row** named by the issue is the `a-quiebra` row of `estado.py` ("Supuesto: probabilidad de quiebra"); `a-default` is its card id in `part-data.js`. Both are updated. The `dcf-quiebra` row ("La mezcla por probabilidad de quiebra", today `muerto` because its input is always 0) is also re-audited, since a story now feeds it (`apply_story` sets `probability_of_bankruptcy` and `distress_proceeds_pct`).
2. **New card ids**: `s-hy` (story type) and `f-hy-story`, `f-hy-scale`, `f-hy-roic` (flags). They are added to `views.py` (`STORIES`, `FLAGS`), `part-data.js`, `part-meta.js` and the `ORDEN` list of `part-js.js` (the dialog's navigation order).
3. **Layout**: `plan_c` in `views.py` hard-codes five story chips (`x = [58, 218, 378, 538, 698]`) and five flag chips (`x = 58 + i * 160`). Six story chips go on one row with a step of 132 and a chip width of 124 (last chip ends at x = 842 inside the 800-wide band starting at 46); the inner sheet keeps the 11-unit padding (`x + 11`, width chip − 22) and all six spark paths, drawn on a 0–122 x range, get `scale(0.8,1)` after their `translate`; subtitles wrap at 17 characters instead of 21; the eight flags go on two rows of four (step 196, same 148×76 chip size with wider text room), band and viewBox heights grown to match. The flags band is the last element of `plan_c` (`views.py:295-309`), so nothing below it moves.
4. **Spec §7.5** also gets the three hypergrowth flags (the issue names §7.1, §7.3, §7.6; leaving §7.5 at five flags would make the spec false about what the report shows). One bullet per flag, same style.
5. **`CONTEXT.md` "Margin of safety"** entry is corrected to the code: `intrinsic_value_after_governance / current_price`, equal to `intrinsic_value / current_price` when there is no governance discount (`src/bot/valuator/analysis.py`, `Analysis.margin_of_safety` docstring). The glossary's *Governance discount* links to it.
6. **ADR links in `CONTEXT.md`**: the *Story type*, *Hypergrowth* and *Story file* entries link `[ADR 0009](docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md)`, the way *Coverage gate* links ADR 0006.
7. **`AUDITADO_EN = "90f717c"`** (the head of `feature/192-hypergrowth-story` whose `src/` this audit reads; later commits of this branch touch no `src/`), `AUDITADO_EL = "2 de noviembre de 2026"`. The test pins only the two values; `git rev-list --count 90f717c..HEAD -- src` = 0 (run from the repo root) is a verification step, not a test, because CI runs pytest on a `fetch-depth: 1` checkout (`.github/workflows/site.yml`) and any later `src/` commit would turn it red. `build_estado.py`'s own stale check never fires (#205), so it proves nothing here.
8. **Lesson chapter numbering**: the flags table is in chapter 8 ("Dudar del resultado"); the projection table and the rules table are in chapter 6; the source table is in chapter 7. All twelve existing line warnings of `check.py` are fixed in the same pass (the issue requires "no line warnings").
9. **Boards and model untouched**: `docs/pipeline/**` is #199. The ADR's Consequences say what the boards show today (the hypergrowth rule on the classifier labels) and that #199 draws the story branch.

## Review Focus

1. **A phrase pinned by `_DOC_GAPS` disappears** while rewriting a plano card or a lesson paragraph: `test_document_gaps_are_current` fails. Every task that edits `part-data.js` or `index.html` runs `uv run pytest tests/unit/test_pipeline_diagram.py -q -k document_gaps`.
2. **A cited line number moves later** (the line of a `def` shifts after a rebase onto a moved base): `check.py` warns. Task 6 runs `check.py` after the rebase and requires `0 errores, 0 avisos`; the permanent test stays the existing exit-code one.
3. **A doc states a unit or default the code does not have** (e.g. story amounts "in millions", `wacc_terminal` default "risk-free"): Task 1 and Task 2 tests assert the exact phrases for raw units and the sector-WACC default.
4. **The estado inventory count text** ("79 componentes") in `docs/plano/README.md` drifts if rows are added: this plan adds no row (rows are rewritten in place), so the count stays 79. Task 4's `test_estado_still_79_rows` counts the rows and reads `docs/plano/README.md`.
5. **A new data-const with an exponent** (`750e9`): `test_named_constants_match_code` parses `value` with `float()`. Task 5 writes `value="750000000000"`.

---

### Task 1: ADR 0009 and the `CONTEXT.md` glossary

**Files:**
- Create: `docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md`
- Modify: `CONTEXT.md` (Domain language entries, Margin of safety)
- Test: `tests/unit/test_hypergrowth_docs.py`

**Interfaces:**
- Produces: the ADR path above, cited by later tasks and by #199 as "ADR 0009 (Implemented)".

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_hypergrowth_docs.py`:
  - `test_adr_0009_exists_and_is_implemented`: exactly one `docs/adr/0009-*.md`; its `## Status` section contains `Accepted (2026-11-02)` and `Implemented (2026-11-02, issue #192)`; it has the four headings `## Status`, `## Context`, `## Decision`, `## Consequences` in that order.
  - `test_adr_0009_decision_covers_the_design`: the Decision section contains each of `story`, `high-growth`, `red`, `year1_margin`, `target_revenue_y10`, `wacc_path`, `tax_rate_path`, `terminal_roic`, `distress_proceeds_pct`, `fixed_commitments`, `extra_cash`, `governance_discount`, `scenarios`, `hypergrowth_story`, `hypergrowth_revenue_scale`, `hypergrowth_terminal_roic`, `screener`, `raw reporting currency`.
  - `test_adr_0009_consequences`: the Consequences section contains `never applied automatically`, `schema_version` and `1`, `447.34`, `same-year`, `10-point` (or `0.10`).
  - `test_context_links_adr_0009_and_defines_the_terms`: `CONTEXT.md` contains `docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md`; the *Story type* line lists `hypergrowth`; there are bullet entries starting `- **Hypergrowth**`, `- **Story file**`, `- **Governance discount**`; the *Margin of safety* line contains `intrinsic_value_after_governance`.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_hypergrowth_docs.py -q` — expected FAIL (no ADR).

- [ ] **Step 3: Write the ADR.** Context: Damodaran's Anthropic method (link in the issue), why the classifier made it `distressed`, why `high-growth` is too broad, IPO-based age, the five-year scalar-WACC DCF, the screener excluding these companies. Decision bullets, one each, in the order the issue lists: two keys; fallback to `high-growth` + red `hypergrowth_story`; story file schema (every `StoryInputs` key with its default, units = raw reporting currency, `founded_year`); ten-year paths (growth: year 1 = `year1_growth`, years 2–5 one rate solved by bisection so year-10 revenue = `target_revenue_y10`, years 6–10 fade linearly to terminal growth; margin: `year1_margin` then linear to `target_margin − regulatory_drag` by `margin_converge_year`, flat after; WACC: `wacc_start` years 1–5, linear to `wacc_terminal` (default sector WACC) by year 10; tax: `effective_tax_rate` years 1–5, linear to the marginal rate by year 10); DCF extensions and their defaults (`wacc_path` cumulative factor, `tax_rate_path`, `terminal_roic` → terminal reinvestment `g ÷ ROIC`, `distress_proceeds_pct`; every default reproduces the old maths bit for bit); failure blend on enterprise value; commitments as debt and `extra_cash` in the bridge; governance outside the DCF (margin of safety on `intrinsic × (1 − governance_discount)`; tornado, grid and scenarios on the raw value); scenarios (`scenario_range`, base first then file order, `base` reserved); the three flags; the screener untouched; the cost-of-equity axis carries the WACC path, the cost-of-debt axis is skipped (`active_axes`). Consequences: never applied automatically; calibration (equity 1,473,576 vs 1,475,406, 446.79 vs 447.34; deviations: same-year reinvestment, 10-point worst-case drag; worst −371,991 vs −373,000, best 4,076,137 vs 4,040,000 — targets and tolerances asserted in `tests/unit/test_hypergrowth_calibration.py:110-161`, computed values re-run on `90f717c` during plan review); sidecars stay `schema_version` 1 with additive fields; the reports show the story inputs with source `story`, the scenario range, both values; the boards show the rule and #199 draws the branch.

- [ ] **Step 4: Edit `CONTEXT.md`.** *Story type* entry lists the six labels and links ADR 0009. New entries after it, same format: *Hypergrowth* (the label, four signals, valued as such only with a story file), *Story file* (the `story` / `scenarios` / `founded_year` keys of `config/assumptions/<TICKER>.yaml`, raw reporting currency; `_Avoid_: story override, narrative file`), *Governance discount* (story key, haircut applied to the intrinsic value before the margin of safety, never in the DCF; `_Avoid_: governance haircut in the WACC`). *Margin of safety* per decision 5.

- [ ] **Step 5: Run** `uv run pytest tests/unit/test_hypergrowth_docs.py tests/unit/test_web_docs.py tests/unit/test_pipeline_diagram.py -q` — PASS.

- [ ] **Step 6: Commit** `docs(#198): ADR 0009 and the hypergrowth glossary`.

### Task 2: Spec §7.1, §7.3, §7.5, §7.6

**Files:**
- Modify: `docs/superpowers/specs/2026-05-25-investment-bot-design.md:232-305`
- Test: `tests/unit/test_hypergrowth_docs.py`

- [ ] **Step 1: Write the failing tests:**
  - `test_spec_7_1_has_the_hypergrowth_row`: §7.1 (text between `### 7.1` and `### 7.2`) has a table row starting `| \`hypergrowth\` |` containing `story file`/`archivo de story` wording chosen in Step 3 — assert the row contains `año 10`, `rampa`, `WACC`, `quiebra`, `compromisos` and `deuda`; and §7.1 contains `sección \`story\``.
  - `test_spec_7_3_lists_story_source`: §7.3 `source ∈ {...}` set contains `story`.
  - `test_spec_7_5_lists_hypergrowth_flags`: §7.5 contains `hypergrowth_story`, `hypergrowth_revenue_scale`, `hypergrowth_terminal_roic`.
  - `test_spec_7_6_documents_every_story_key`: §7.6 contains every field name of `bot.valuator.hypergrowth.StoryInputs` (`dataclasses.fields`), plus `founded_year`, `scenarios`, `worst`, `best`.

- [ ] **Step 2: Run** them — FAIL.

- [ ] **Step 3: Edit the spec.** §7.1: "Cinco arquetipos" → six; the `hypergrowth` row ("Story-driven: ingresos del año 10 como objetivo, rampa de margen desde `year1_margin`, trayectoria de WACC, riesgo de quiebra sobre el valor operativo, compromisos fijos como deuda; solo con la sección `story`"); after the auto-assignment sentence, one sentence: auto-assignment of `hypergrowth` needs the story file, otherwise `high-growth` with a red flag (ADR 0009). §7.3: add `story` (and `story_pattern`, `sector_default_damodaran_cross_region`, `unresolved` only if you also say they exist — keep it to adding `story` plus one sentence "solo para `hypergrowth`, ver §7.6"). §7.5: three bullets. §7.6: a sub-block listing the keys (YAML block like the issue's, raw units, defaults and ranges from `_RULES` in `hypergrowth.py`), the validation rule (`ValueError` per ticker), and scenarios (merged over `story`, `base` reserved, worst/base/best range next to the tornado). Keep Spanish and the table style.

- [ ] **Step 4: Run** the tests — PASS.

- [ ] **Step 5: Commit** `docs(#198): spec §7 documents the hypergrowth story type`.

### Task 3: The architecture plan (`plano.html`)

**Files:**
- Modify: `docs/plano/views.py:163-330`, `docs/plano/part-data.js`, `docs/plano/part-meta.js:33-55`, `docs/plano/part-js.js:23-26`
- Test: `tests/unit/test_hypergrowth_docs.py`

- [ ] **Step 1: Write the failing tests** (load `views.py` with `importlib.util.spec_from_file_location`; read the JS files as text):
  - `test_plano_story_has_hypergrowth`: `views.STORIES` has an entry whose first three items are `("s-hy", "hypergrowth", "la historia manda, no el balance")`.
  - `test_plano_flags_have_the_hypergrowth_three`: `views.FLAGS` ids include `f-hy-story`, `f-hy-scale`, `f-hy-roic`, after the five existing ones.
  - `test_plano_cards_and_meta`: `part-data.js` contains `"s-hy":{role:"valua"` and each flag id key; `part-meta.js` maps `"s-hy"` to `src/bot/valuator/story_types.py:StoryType`, `f-hy-story` to `src/bot/valuator/narrative_flags.py:hypergrowth_story_flag`, `f-hy-scale` to `...:hypergrowth_revenue_scale_flag`, `f-hy-roic` to `...:hypergrowth_terminal_roic_flag`; `part-js.js` `ORDEN` contains the four ids.
  - `test_plano_a_default_mentions_the_story`: the `a-default` card text contains `failure_probability` and `failure_proceeds_pct_of_value`, both asserted to be fields of `StoryInputs`.
  - `test_plano_build_passes`: `subprocess.run([sys.executable, "docs/plano/build.py"])` returns 0.

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Edit.** `STORIES` gets `("s-hy", "hypergrowth", "la historia manda, no el balance", <spark path>)`, a steep rise that bends (e.g. `"M8,48 C24,46 34,40 46,24 S84,8 122,6"`). `FLAGS` gets `("f-hy-story", "hypergrowth_story", "rojo", "bad", ["hypergrowth_", "story"])`, `("f-hy-scale", "hypergrowth_revenue_scale", "amarillo", "warn", ["hypergrowth_revenue_", "scale"])`, `("f-hy-roic", "hypergrowth_terminal_roic", "amarillo", "warn", ["hypergrowth_terminal_", "roic"])`. `ASSUMPTIONS` `a-default` note: `"cero salvo distressed a mano o story"`. Layout per decision 3. `part-data.js`: `s-hy` card (role `valua`; idea paragraphs: Damodaran's four questions — revenue in year 10 = market × share, target margin, sales to capital, cost of capital — plus failure risk and regulation, "the S-1 is a kindergartner's report card"; code `where`: `["valor","\"hypergrowth\""]`, `["clasifica con","crecimiento ≥ 50% el último año, CAGR ≥ 40%, margen bajo el sector, fundada hace ≤ 15 años"]`, `["exige","sección story en config/assumptions/&lt;TICKER&gt;.yaml"]`, `["proyecta","valuator/hypergrowth.py: apply_story"]`; notes: the gate and the fallback). Three flag cards in the style of `f-tv`. `a-default` card: lead and text say the probability is zero by default, set by hand for a distressed company, and taken from `failure_probability` of the story file for a hypergrowth one, with failure proceeds as a share of enterprise value (`failure_proceeds_pct_of_value`); **keep** the `s-ds` card's "El Altman Z decide la clasificación" and every other `_DOC_GAPS` phrase. `flags` card: `["cantidad","5 + 3 de hypergrowth"]` and one note. `story` card notes: hypergrowth is assigned only with a story file. `part-meta.js` and `ORDEN` per the tests.

- [ ] **Step 4: Run** the tests and `uv run pytest tests/unit/test_pipeline_diagram.py -q -k document_gaps` — PASS. `build.py` checks symbols and tensions only (`docs/plano/README.md`, "Por qué falla el build a propósito"), not layout: open `docs/plano/plano.html` with `agent-browser`, go to the «Capa C» view, take a screenshot and check that no chip, subtitle or spark overlaps or leaves its band.

- [ ] **Step 5: Commit** `docs(#198): plano shows the hypergrowth story type and its flags`.

### Task 4: The status plan (`estado.py`)

**Files:**
- Modify: `docs/plano/estado.py:16-17,105-133,179,207-212`
- Test: `tests/unit/test_hypergrowth_docs.py`

- [ ] **Step 1: Write the failing tests** (import `estado.py` via `importlib`):
  - `test_estado_audit_is_current`: `estado.AUDITADO_EN == "90f717c"`, `estado.AUDITADO_EL == "2 de noviembre de 2026"`.
  - `test_estado_rows_carry_hypergrowth_evidence`: in `INVENTARIO["capa-c"]` the rows `classify`, `story-uso`, `a-quiebra`, `dcf-quiebra`, `flags-4` and in `INVENTARIO["proyecto"]` the row `m4` each mention `hypergrowth` in evidence or note; `classify`'s evidence cites `valuator/story_types.py:` and `story-uso`'s cites `valuator/hypergrowth.py:`.
  - `test_estado_still_79_rows`: total rows across `INVENTARIO` is 79 and `docs/plano/README.md` still says `79 componentes`.
  - `test_estado_build_passes`: `build_estado.py` exits 0.

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Re-audit and edit.** Read the code at `90f717c` (manda el código, no el spec). Rewrite in place, with `file:line` ranges from the current tree: `classify` (six types reachable, hypergrowth before distress; `story_types.py:` ranges of `_is_hypergrowth` and `classify`); `story-uso` (hypergrowth now projects ten years from the story: `hypergrowth.py` `apply_story`, `growth_path`, `margin_path`; `assumptions.py` `resolve_assumptions` story branch; the rest of the note's gaps for other types stay true); `a-quiebra` (no longer always zero: a story sets it; for distressed still manual only → state `a-medias`); `dcf-quiebra` (fed by the story with a failure blend on EV → `hecho` for that path, keep the per-share path's note; state by your audit); `flags-4` (the five + three hypergrowth flags; name stays, note says eight); `m4` note. `BLOQUES`: change only if the worst state of a block changed. `BRECHAS`: the "story type cambia toda la proyección" gap is revised to say hypergrowth does change the whole projection (growth, margin, WACC, tax, terminal reinvestment, failure) while the other five still do not branch sales-to-capital or terminal growth. `AUDITADO_EN`/`AUDITADO_EL` per decision 7.

- [ ] **Step 4: Run** the tests — PASS — and `git rev-list --count 90f717c..HEAD -- src` from the repo root — `0`. `BLOQUES` is hand-written (`estado.py` `css_bloques` only paints it): check by hand that each block's state is the worst of its rows' states you changed.

- [ ] **Step 5: Commit** `docs(#198): estado re-audited on 90f717c`.

### Task 5: The lesson

**Files:**
- Modify: `docs/leccion/index.html` (chapters 6, 7, 8 and every stale `class="at"` line)
- Modify: `tests/unit/test_leccion.py` (`_REQUIRED_SYMBOLS`, `_REQUIRED_CONSTS`; new test)

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_leccion.py`:
  - `_REQUIRED_SYMBOLS["cap-6"]` gains `bot.valuator.hypergrowth.apply_story`, `bot.valuator.hypergrowth.solve_stage_growth`; `["cap-8"]` gains `bot.valuator.narrative_flags.hypergrowth_story_flag`, `bot.valuator.narrative_flags.hypergrowth_revenue_scale_flag`, `bot.valuator.narrative_flags.hypergrowth_terminal_roic_flag`.
  - `_REQUIRED_CONSTS["cap-6"]` gains the three `_HYPERGROWTH_*` constants and `bot.valuator.hypergrowth.HORIZON`; `["cap-8"]` gains `bot.valuator.narrative_flags._LARGEST_COMPANY_REVENUE`, `bot.valuator.narrative_flags._ROIC_SECTOR_MULTIPLE`.
  - `test_hypergrowth_rows_in_chapters_6_to_8`: chapter 6's projection table has a row headed `hypergrowth`; chapter 8's flags table has rows headed `hypergrowth_story`, `hypergrowth_revenue_scale`, `hypergrowth_terminal_roic`; chapter 7's `story` row mentions `failure_probability` and `governance_discount`, and both names are asserted to be fields of `StoryInputs`.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_leccion.py -q` — FAIL.

- [ ] **Step 3: Edit `index.html`.** Chapter 6 rules row 0: the four signals (already there), the gate and the fallback to `high-growth` with the red `hypergrowth_story` flag, the age from `founded_year` (not the IPO date). Projection table: a `hypergrowth` row — growth: year 1 from the story, years 2–5 one rate the bot solves so year-10 revenue hits the target, years 6–10 fade to terminal growth, over <data data-const="bot.valuator.hypergrowth.HORIZON" value="10">10 años</data>; margin: from `year1_margin` in a straight line to target minus regulatory drag by `margin_converge_year`, flat after; then one sentence under the table on the WACC path (held five years, converging to the terminal WACC), the tax path, and terminal reinvestment from ROIC (`g ÷ ROIC`). Symbols list: `apply_story` and `solve_stage_growth` with `<code class="at">src/bot/valuator/hypergrowth.py:LINE</code>` (lines from `check.py`). Chapter 6 example or caveat: one sentence that the screener never lets these in; only `bot analyze <TICKER>` values them. Chapter 7: `story` row lists what it sets (growth and margin paths, sales-to-capital, WACC path, tax path, terminal ROIC, failure probability and proceeds, commitments, extra cash, governance discount); caveat's "probabilidad de quiebra ... quedan en 0 salvo que los cargues a mano" gets "o que venga de la sección `story`". Chapter 8: "Cinco controles" → five plus three for hypergrowth; three table rows with colours and thresholds (`hypergrowth_story`: red signals without file, yellow file without signals, green otherwise; `hypergrowth_revenue_scale`: yellow above <data data-const="bot.valuator.narrative_flags._LARGEST_COMPANY_REVENUE" value="750000000000">750 mil millones</data>; `hypergrowth_terminal_roic`: yellow above <data data-const="bot.valuator.narrative_flags._ROIC_SECTOR_MULTIPLE" value="2.0">2</data> veces el ROIC del sector, unknown when either is missing or the sector's is not positive); symbol list entries for the three functions; the MoS paragraph says a story's governance discount is applied before the MoS and the scenario range (worst / base / best) sits next to the tornado. Fix every `class="at"` line `check.py` reports. Keep "no caen en promedio más de" and no math notation (`^`, `∑`).

- [ ] **Step 4: Run** `python3 docs/leccion/check.py` (0 errores, 0 avisos) and `uv run pytest tests/unit/test_leccion.py tests/unit/test_pipeline_diagram.py -q` — PASS.

- [ ] **Step 5: Commit** `docs(#198): the lesson teaches the hypergrowth story type`.

### Task 6: Full gates

- [ ] Run `python3 docs/leccion/check.py` and require `0 errores, 0 avisos`; run `git rev-list --count 90f717c..HEAD -- src` and require `0`.
- [ ] Run `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/plano/build.py`, `python3 docs/plano/build_estado.py`, `python3 docs/leccion/check.py`. All exit 0. No commit unless something had to change.

## Assumptions

Technical decisions recorded during plan grilling (no written source; any option satisfies the issue):

- **A1. §7.5 gets the three flags and `CONTEXT.md`'s *Margin of safety* is corrected** under the issue's "all true to the code as merged on the feature branch". Leaving them would keep two statements the code contradicts (`narrative_flags.hypergrowth_flags`; `Analysis.margin_of_safety` docstring, `src/bot/valuator/analysis.py:113-115`). Rejected: touching only the sections the deliverables name.
- **A2. "a-default" = `a-quiebra` row + `a-default` card.** Both describe the probability of bankruptcy (`estado.py` "Supuesto: probabilidad de quiebra"; `part-data.js` `a-default` "Probabilidad de quiebra"); no id links them. Rejected: adding an `a-default` row to `estado.py`, which would change the 79-row count.
- **A3. The audit commit and zero line warnings are verification steps, not permanent tests**: CI runs pytest on a shallow checkout (`.github/workflows/site.yml`, `actions/checkout@v4` default depth 1), and a permanent zero-warning test would fail the next unrelated `src/` refactor; `docs/leccion/README.md` leaves fixing warnings to whoever changes `src/`. Rejected: tests that skip when the commit is unknown.
- **A4. Layout of the Capa C view** (decision 3) is checked by an `agent-browser` screenshot, since `build.py` does not check layout. Rejected: computing text widths in a test.
- **A5. `BLOQUES` is reviewed by hand**: it is hand-written and nothing derives or checks it (`estado.py` `css_bloques`).
- **A6. The `_DOC_GAPS` phrases stay** (`tests/unit/test_pipeline_diagram.py:2587-2631`); none pins the `a-default` zero text or the `dcf-quiebra` state, so those can be rewritten. The board gap `analyze.d2` `manual_only` (p only from a manual override) goes stale for hypergrowth and is #199's.

## Grilling

- Rounds: 1 (the revision changed steps' contents and tests, not the task seams; no second round).
- Questions: 18. Answered from CODE: 13; ISSUE: 2 (Q4 Decision 8, Q12 count text); DOC: 1 (Q8); NO SOURCE: 2 → technical assumptions A1, A2 (plus A3–A6 recorded from CODE-backed answers).
- Spec ambiguities: none.
- Issues opened (out of scope): #205 (`build_estado.py` stale-audit check never fires), #206 (`config/assumptions/README.md` says the valuation does not read the story), #207 (spec §7.3 source set behind the code).
