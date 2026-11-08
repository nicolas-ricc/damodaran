# Docs and presets describe the dilution M&A exception (#280) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `.agents/skills/subagent-driven-development` (implementers use `.agents/skills/test-driven-development`) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The presets, the d2 pipeline boards, the lesson, the plano card and the estado entry say what `ShareCountNotDiluting` does since #279: the 5% share-growth cap is lifted when cash paid for acquisitions over the last `ma_window` (3) fiscal years reaches `ma_materiality` (0.10) of total assets.

**Architecture:** This is a docs-only change plus two preset params. The rule already takes `ma_window` and `ma_materiality` with defaults (`src/bot/screener/rules.py:692-702`); the presets make them explicit. Adding them to `damodaran_value.yaml` changes what `tests/unit/test_pipeline_diagram.py` and `tests/unit/test_leccion.py` require (every preset param cited on the boards and shown in lesson chapter `cap-4`), so the presets, the boards and the lesson row land together in Task 1. The plano card and the estado entry are independent HTML generators and form Task 2.

**Tech Stack:** YAML presets, d2 v0.9.0 with TALA (`docs/pipeline/build.sh`), static HTML generators in Python (`docs/plano/build.py`, `build_estado.py`), pytest.

**Spec:** GitHub issue #280 (design decisions inherited from story #62, `Branch: feature/62-dilution-ma-exception`).

## Global Constraints

- Presets: add `ma_window: 3` and `ma_materiality: 0.10` under `share_count_not_diluting` in `damodaran_value.yaml`, `deep_value.yaml` and `qarp.yaml`, each with a comment in the existing style. The three trap layers stay equal (`test_trap_detection_shared_with_damodaran_value`).
- Boards in English; plano, estado and lesson in Spanish, as today.
- Every digit on a board label is cited with `@param`/`@const` on that source line; acronyms expanded; counts in words (`docs/pipeline/README.md:78-79`).
- Keep `@rule share_count_not_diluting` on both board nodes and `@symbol bot.screener.rules._avg_growth_rate` on the `screen-traps.d2` node. Add no edges to `screen-traps.d2` (22 now, cap 24).
- Do not touch the `auditor` gap note, auditor changes or late filings anywhere. Story #61 owns them.
- Never edit an SVG or `rendered.sha256` by hand: run `docs/pipeline/build.sh` (d2 v0.9.0 is in `~/.local/bin`; `export PATH="$HOME/.local/bin:$PATH"`).
- `tests/unit/test_pipeline_diagram.py`: remove only the `mergers` tuple from `_SCREEN_NODES` (line 1294) and the `mergers and acquisitions` assertion from `test_screen_gap_notes` (lines 1503-1505).
- `estado.py`: do not change `AUDITADO_EN`, the count of detectors ("Cuatro de los cinco"), or the row count (`test_estado_still_79_rows`).
- `uv run pytest -q` passes; `uv run ruff check . && uv run mypy src` is clean.

## Declared technical assumptions

- **Board labels keep the substrings existing tests pin.** `_DIRECTIONS` (test_pipeline_diagram.py:1474) needs `average diluted share count growth ≤ 5% a year` in the `screen.d2` block, `_SCREEN_EXTRA` (line 1363) needs `whole share history`, and `_SCREEN_TEXT["screen-traps"]` (test_pipeline_subboards.py:329) needs `≤ 5%`. The issue says to change nothing else in those tests, so the new labels keep these phrases word for word and add the exception after them.
- **Label wording, fixed here.** `screen.d2`: `"average diluted share count growth ≤ 5% a year\nover the whole share history\nunless cash paid for acquisitions over the last 3 reported fiscal years\n≥ 10% of the latest total assets\nfewer than 2 counts or undefined growth: fails"`. `screen-traps.d2`: `"share_count_not_diluting\naverage diluted share count growth ≤ 5% a year\nunless cash paid for acquisitions over the last 3 reported fiscal years\n≥ 10% of the latest total assets\nfewer than two counts, or a base ≤ 0\n(growth undefined): fails"`. The `2` in the `screen.d2` label is there today with no citation and stays: `_uncited_numbers` runs only on `step` nodes (`test_pipeline_diagram.py:2668-2681`) and this node is a `decision`. The three `@param`s are cited anyway, because the README convention and the issue require it and `test_every_directive_is_valid` checks that each cited value is shown.
- **Snapshot note:** the histories list becomes `revenue, operating cash flow, diluted shares, operating margin, acquisitions` (`screen.d2:76`).
- **Estado evidence range** becomes `screener/rules.py:528-760`, from `class RevenueNotDeclining` to the end of `ShareCountNotDiluting`, the last trap rule in the file.
- **Preset comments:** `damodaran_value.yaml` keeps its existing `max_annual_growth` comment. The new lines get `# M&A window: last 3 fiscal years` and `# acquisitions ≥ 10% of total assets lift the cap`. `deep_value.yaml` and `qarp.yaml` have no comment on `max_annual_growth` today; the new lines there get the same two comments.
- **New eval tests go in a new file**, `tests/unit/test_dilution_ma_docs.py`, so the existing test files change only as the issue allows.

## Acceptance criteria → tasks

| #280 acceptance criterion | Task |
|---|---|
| `build.sh` run after the `.d2` edits; SVGs and `rendered.sha256` committed; `check.py` exits 0 | 1 |
| `screen.d2` has no `mergers` gap note; both boards cite `ma_window` and `ma_materiality`; `test_pipeline_diagram.py` and `test_pipeline_subboards.py` pass | 1 |
| The three presets load through `load_screener_config` and build the rule with the two new params; `test_leccion.py` passes with the lesson row showing both | 1 |
| `build.py` and `build_estado.py` run clean; `plano.html` carries the new `t-dilution` text | 2 |
| Full suite, ruff and mypy clean | both, checked at the end of stage 4 |

## Stage-3 evals (`tests/unit/test_dilution_ma_docs.py`, written and committed failing before Task 1)

- `test_presets_build_share_count_rule_with_ma_params[preset]`: each of the three presets, loaded with `load_screener_config`, builds a `ShareCountNotDiluting` with `max_annual_growth == 0.05`, `ma_window == 3`, `ma_materiality == 0.10`, and its YAML lists both keys explicitly.
- `test_lesson_row_shows_ma_params`: `docs/leccion/index.html` has `data-param="share_count_not_diluting.ma_window" value="3"` and `data-param="share_count_not_diluting.ma_materiality" value="0.10"`, and still has the `max_annual_growth` one.
- `test_screen_board_has_no_mergers_gap`: `screen.d2` contains neither `mergers:` nor `exempts dilution`.
- `test_boards_cite_ma_params[screen|screen-traps]`: the `share_count_not_diluting` declaration line cites `@param share_count_not_diluting.ma_window` and `@param share_count_not_diluting.ma_materiality` and keeps `@rule share_count_not_diluting`. On screen-traps it also keeps `@symbol bot.screener.rules._avg_growth_rate`.
- `test_screen_traps_edge_count_unchanged`: `screen-traps.d2` has exactly 22 `->` edges.
- `test_snapshot_histories_list_acquisitions`: `screen.d2` contains `operating margin, acquisitions`.
- `test_plano_card_describes_ma_exception`: runs `docs/plano/build.py` itself in a subprocess, then reads the fresh `plano.html` and finds `adquisición material`, `ma_window: 3` and `ma_materiality: 0.10`.
- `test_estado_traps_entry_describes_ma_exception`: loads `estado.py` (as `test_hypergrowth_docs._load` does). The `traps-4` row's evidence is `screener/rules.py:528-760`, its text contains `excepción por adquisición justificada del spec §6.4` and no longer contains `no implementa la excepción`. The test also checks that line 528 of `rules.py` starts `class RevenueNotDeclining` and line 760 is the last line of `ShareCountNotDiluting`, so a shifted range fails loudly.

## Review Focus

1. Each `@param` value has to be shown on its own source line (`_directive_problem` → `check.shown`). `3`, `10%` and `5%` all sit on the single label line, which carries all three directives. Task 1 runs `test_every_directive_is_valid`.
2. `rendered.sha256` has to match the committed `.d2` files exactly: a `.d2` edit after the render breaks `check.py` and CI's "committed render is current" step. Task 1 renders last and checks that `git status` shows no `.d2` change after `build.sh`.
3. If the `screen-traps.d2` label grows, TALA may relayout the board, but the edge count must stay at 22. Task 1 test.
4. `plano.html` and `estado.html` are gitignored build outputs. The eval reads the freshly built `plano.html`, not a committed copy. Task 2 test.
5. A stray change to the auditor gap note would collide with story #61. Not a test (story #61 may legitimately change that block): the stage-5 review checks that `git diff origin/feature/62-dilution-ma-exception` touches no line mentioning `auditor`.

---

### Task 1: Presets, lesson row and boards cite the M&A exception

**Files:**
- Modify: `config/presets/damodaran_value.yaml:66-68`, `config/presets/deep_value.yaml:74-76`, `config/presets/qarp.yaml:73-75`
- Modify: `docs/leccion/index.html:516`
- Modify: `docs/pipeline/screen.d2:76,172-175`, `docs/pipeline/screen-traps.d2:44`
- Regenerate: `docs/pipeline/screen.svg`, `docs/pipeline/screen-traps.svg`, `docs/pipeline/rendered.sha256` with `build.sh`. If `build.sh` also rewrites an SVG whose `.d2` did not change, restore it with `git checkout -- <svg>`. CI checks only `rendered.sha256` and untracked renders (`.github/workflows/pipeline-diagram.yml`, "committed render is current"), not SVG bytes.
- Modify: `tests/unit/test_pipeline_diagram.py:1294,1503-1505`
- Test: `tests/unit/test_dilution_ma_docs.py` (written in stage 3)

**Interfaces:**
- Produces: preset keys `share_count_not_diluting.ma_window = 3`, `share_count_not_diluting.ma_materiality = 0.10`.

- [ ] **Step 1: Run the stage-3 evals and confirm they fail.** `uv run pytest -q tests/unit/test_dilution_ma_docs.py -k "preset or lesson or board"`. Expected: FAIL.
- [ ] **Step 2: Edit the three presets** as in Global Constraints.
- [ ] **Step 3: Extend the lesson row** (`index.html:516`) after the existing `max_annual_growth` `<data>`: `por año, salvo que la caja pagada por adquisiciones en los últimos <data data-param="share_count_not_diluting.ma_window" value="3">3</data> ejercicios llegue al <data data-param="share_count_not_diluting.ma_materiality" value="0.10">10 %</data> de los activos totales`.
- [ ] **Step 4: Edit `screen.d2` and `screen-traps.d2`** with the declared labels and the directive `# @rule share_count_not_diluting @param share_count_not_diluting.max_annual_growth @param share_count_not_diluting.ma_window @param share_count_not_diluting.ma_materiality` (plus the `@symbol` on screen-traps). Delete the `mergers` line; the node keeps `class: decision`. Add `acquisitions` to the snapshot histories.
- [ ] **Step 5: Edit `test_pipeline_diagram.py`**, removals only.
- [ ] **Step 6: Render.** `export PATH="$HOME/.local/bin:$PATH"; docs/pipeline/build.sh && python3 docs/pipeline/check.py`. Expected: `0 errors`, exit 0.
- [ ] **Step 7: Run** `uv run pytest -q tests/unit/test_dilution_ma_docs.py tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_check.py tests/unit/test_leccion.py tests/unit/test_leccion_check.py tests/unit/test_screener_extra_presets.py tests/unit/test_screener_config.py`. Expected: PASS.
- [ ] **Step 8: Commit** `docs(#280): presets, lesson and boards describe the dilution M&A exception`, including SVGs and `rendered.sha256` (PNGs are gitignored).

### Task 2: Plano card and estado entry

**Files:**
- Modify: `docs/plano/part-data.js:175-178` (card `t-dilution`)
- Modify: `docs/plano/estado.py:78-79` (entry `traps-4`)
- Test: `tests/unit/test_dilution_ma_docs.py` (written in stage 3)

- [ ] **Step 1: Run the plano/estado evals and confirm they fail.** `uv run pytest -q tests/unit/test_dilution_ma_docs.py -k "plano or estado"`. Expected: FAIL.
- [ ] **Step 2: Card `t-dilution`.** The lead becomes `Las acciones no crecen más de 5% anual, salvo que una adquisición material lo explique.` The second `idea` paragraph keeps its point about chronic issuance and adds that the exception is implemented by comparing the cash paid for acquisitions over the last three fiscal years with total assets. `code.where` gains `["parámetro","ma_window: 3"]` and `["parámetro","ma_materiality: 0.10"]` after `max_annual_growth`.
- [ ] **Step 3: Entry `traps-4`.** Evidence becomes `screener/rules.py:528-760`. Only the second sentence changes: `El tope de dilución ya implementa la excepción por adquisición justificada del spec §6.4: compara la caja pagada por adquisiciones con los activos totales.` The first sentence stays.
- [ ] **Step 4: Run** `python3 docs/plano/build.py && python3 docs/plano/build_estado.py && uv run pytest -q tests/unit/test_dilution_ma_docs.py tests/unit/test_hypergrowth_docs.py`. Expected: PASS.
- [ ] **Step 5: Commit** `docs(#280): plano card and estado entry describe the dilution M&A exception`.

## Assumptions

- **Eval tests live in a new file.** Rejected alternative: adding them to `test_pipeline_diagram.py`, whose edits the issue restricts to the two removals.
- **`screen.d2` keeps `fewer than 2 counts`.** The "counts in words" rule covers step labels (`docs/pipeline/README.md:78`), and this node is a decision. Rejected alternative: rewording text outside the M&A change.
- **SVGs whose `.d2` did not change are restored**, not committed. Rejected alternative: committing TALA re-render noise.
- **No auditor-block test.** Story #61 may change that block. The stage-5 diff review guards it instead.
- **The estado range is pinned by an eval** that checks lines 528 and 760 of `rules.py`. Rejected alternative: an unchecked number that goes stale silently.
- **Rollback mid-Task 1:** `git checkout -- config docs tests` brings back the last commit, including SVGs and `rendered.sha256` (they are tracked). Nothing outside the repo changes.

## Grilling

- Rounds: 1 (the revisions were clarifications and one dropped test, not a different seam). Griller model: fable.
- Questions: 18. Sources: ISSUE 7 (Q1, Q2, Q5, Q7, Q8, Q15, Q18 partly), CODE 14 (Q3 `config.py:63-70`, Q4 `check.py:148-171`, Q9 `pipeline-diagram.yml`, Q10 `screen.d2:174`, Q11 `test_screener_extra_presets.py:187-190`, Q12 `test_hypergrowth_docs.py:180-185`, Q13 `test_leccion.py:489` and `index.html:515`, Q14 `test_leccion.py:474`, Q16 `test_hypergrowth_docs.py:212-222`, Q17 `screen.d2:58-77`), DOC 2 (Q6 `docs/pipeline/README.md:78`, Q15 the spec at `docs/superpowers/specs/2026-05-25-investment-bot-design.md:202`), NO SOURCE 4 (Q1, Q7, Q9, Q18 → technical assumptions above). Some questions drew more than one source.
- Spec ambiguities: none. Out of scope / issues opened: none.
- Result: ok.
