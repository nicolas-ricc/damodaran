# Governance trap detector in the status plan and the lesson — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the hand-curated status plan (`docs/plano/estado.py`), its summary sentence (`docs/plano/build_estado.py`) and the lesson's trap-chapter prose (`docs/leccion/index.html`, `cap-4`) say what the code ships since #276: a sixth trap detector, `auditor_changes_and_late_filings`, and an engine test that rejects a company by it.

**Architecture:** Docs only. Card texts, one subtitle, one `BLOQUES` value, one sentence of `build_estado.py` and one lesson paragraph change. The card count stays 79. A new test module pins the decided strings and checks that every line range cited in the touched cards points at the code it names.

**Tech Stack:** Python 3.12, pytest, ruff, mypy --strict; `docs/plano/build_estado.py` (generates the git-ignored `estado.html`) and `docs/leccion/check.py` (symbol-citation check).

**Spec:** GitHub issue #277 (`gh issue view 277 --repo nicolas-ricc/damodaran`). Its four "Decisions (taken by the planner; do not reopen)" and its acceptance criteria are binding; exact strings are copied from there. Story context: #61.

## Global Constraints

- Docs only: no change under `src/`, no change to existing test logic. Only additions are a new test module and these three files: `docs/plano/estado.py`, `docs/plano/build_estado.py`, `docs/leccion/index.html`.
- `INVENTARIO` keeps **79 cards** (`tests/unit/test_hypergrowth_docs.py::test_estado_still_79_rows`); `docs/plano/README.md` keeps `79 componentes`.
- Block `"capa-b"` subtitle: `"diecisiete reglas, cero subjetividad"`.
- Card `traps-4` is replaced in place (same position) by `("traps-5", "Cinco de los seis trap detectors", "hecho", "screener/rules.py:529-804", "Ingresos, margen, accruals, dilución y gobernanza. El detector de gobernanza lee de filings_log los 8-K ítem 4.01 (cambio de auditor) y los avisos NT 10-K/10-Q de los últimos dos años, que el proveedor EDGAR guarda desde el índice de submissions; fuera de la región US no hay índice y el detector se saltea, y saltearse elimina (ADR 0006). El tope de dilución no implementa la excepción por adquisición justificada que pide el spec, y lo dice en su propio docstring.")`. `529` is the `@register` of `RevenueNotDeclining`; `804` is the last line of `AuditorChangesAndLateFilings`, the file's last line (`src/bot/screener/rules.py`).
- Card `registro`: text `"Los tres presets cargan y construyen sin error. qarp usa dieciséis reglas: omite EV/EBITDA sin comentarlo."`; evidence `screener/config.py:140` unchanged (`def load_screener_config`).
- Card `motor-trap`: state `"hecho"`, evidence `"screener/engine.py:779-787"` (the `for detector in trap_detection:` loop of `evaluate_company`), text `"El test de motor que faltaba existe: run_screen rechaza una empresa sembrada con un aviso NT 10-K reciente y la deja en rejected con auditor_changes_and_late_filings entre sus reglas falladas (tests/unit/test_screener_engine.py)."`.
- `BLOQUES["traps"]`: `"hecho"` (see Assumptions).
- `build_estado.py`: `dieciséis reglas reales` → `diecisiete reglas reales`; nothing else in the sentence.
- Lesson: the paragraph starting `Dos aclaraciones sobre cómo leer esto.` starts `Tres aclaraciones sobre cómo leer esto.` and gains one governance sentence (exact copy in Task 2). `aunque parezca barata por cuatro motivos` stays.
- `python3 docs/plano/build_estado.py` exits 0; `python3 docs/leccion/check.py` exits 0 with the same 18 pre-existing `aviso` lines and no new one; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- **Which cards make the `"traps"` block.** `BLOQUES` has no card→block mapping in code (`docs/plano/estado.py:27-34`, `docs/plano/iso.py:80`); it is curated by topic (the `"gates"` block is `hecho` while the gates-related `huecos` card is `a-medias`). The cards about trap detection are `traps-5`, `trap-roic` and `motor-trap`; after this change all three are `hecho`, so `"traps"` becomes `"hecho"`. Rejected: reading "that block" as the whole `capa-b` inventory block, which mixes the `gates`, `value`, `traps` and `ranking` axonometry blocks and would make `"gates": "hecho"` already wrong today.
- **Range of the five non-ROIC trap rules.** `ROICAboveSectorWACC` sits between them (`rules.py:609`); the original evidence `521-719` also spanned it. The new range keeps that convention: one contiguous range from the first non-ROIC detector's decorator (529) to the end of the last (804).
- **`AUDITADO_EN` / `AUDITADO_EL` unchanged.** This issue updates three cards, not a full re-audit (`docs/plano/README.md`, step 2); moving the audit stamp would claim an audit that did not happen.
- **`trap-roic` evidence unchanged.** Decision 1 names it "(unchanged)"; its `rules.py:601-624` and `engine.py:698-707` lines predate #276 and are not one of the touched cards.
- **Pre-existing `check.py` warnings.** The 18 `línea movida` warnings exist on the base branch before this change (none cite `screener/`); this change adds no citation, so it causes none and fixes none.

## Review Focus

1. A cited range out of bounds or off by one (the range ends past the file, or starts inside the previous class): the test opens the file and checks the first and last lines. Pinned in Task 1 (`test_touched_cards_cite_real_lines`).
2. The card count drifting (a card added beside `traps-4` instead of replacing it): pinned by the existing `test_estado_still_79_rows` plus `test_traps_4_is_gone`.
3. The lesson paragraph still saying `Dos aclaraciones` somewhere, or `cuatro motivos` being "fixed" to `seis`: pinned in Task 2 (`test_trap_paragraph_has_three_clarifications`, `test_cuatro_motivos_stays`).
4. The new lesson sentence breaking `test_leccion.py` (a stray `data-param` or a citation `check.py` cannot resolve): Task 2 adds no markup, only text; `uv run pytest tests/unit/test_leccion.py` runs in Task 2.
5. HTML escaping: the paragraph is plain UTF-8 text (`ó`, `í`) like its neighbours, no entities.

## Acceptance criteria → tasks

| Issue item | Task |
|---|---|
| AC 1 (decision 1, build runs, 79 cards), AC 2 (decision 2), AC 4 (cited ranges) | Task 1 |
| AC 3 (decision 3, `check.py`, `test_leccion.py`) | Task 2 |
| AC 5 (lint, types, full suite) | both, final run |

---

### Task 1: Status plan cards, `BLOQUES` and the `build_estado` sentence

**Files:**
- Modify: `docs/plano/estado.py:30,73,78-79,84-85,88-89`
- Modify: `docs/plano/build_estado.py:278`
- Test: `tests/unit/test_governance_docs.py` (new; stage-3 evals)

**Interfaces:**
- Consumes: `estado.INVENTARIO`, `estado.BLOQUES` (loaded with `importlib` as `tests/unit/test_hypergrowth_docs.py::_load` does).
- Produces: nothing code-level.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_governance_docs.py`:
  - `test_capa_b_subtitle_counts_seventeen_rules`: `INVENTARIO["capa-b"][1] == "diecisiete reglas, cero subjetividad"`.
  - `test_traps_card_counts_five_of_six`: the card with id `traps-5` equals the tuple in Global Constraints, and sits at the index `traps-4` had (index 2 of `capa-b`).
  - `test_traps_4_is_gone`: no card id `traps-4` in any block.
  - `test_registro_counts_sixteen_qarp_rules`: `registro` text equals the decided string.
  - `test_motor_trap_is_done`: `motor-trap` is `("motor-trap", "La rama que elimina por trampa", "hecho", "screener/engine.py:779-787", <decided text>)`.
  - `test_traps_block_is_done`: `BLOQUES["traps"] == "hecho"`.
  - `test_touched_cards_cite_real_lines`: for `traps-5`, `src/bot/screener/rules.py` line 529 is `@register` and line 530 starts `class RevenueNotDeclining`; lines 529-804 contain `class OperatingMarginNotContracting`, `class SloanAccrualsBelow`, `class ShareCountNotDiluting`, `class AuditorChangesAndLateFilings`; 804 is the file's last line. For `motor-trap`, `src/bot/screener/engine.py` line 779 is `    for detector in trap_detection:`, line 787 is `            passed = False`, and both lie inside `def evaluate_company`. For `registro`, `src/bot/screener/config.py` line 140 starts `def load_screener_config`. The test parses the numbers from the card evidence, it does not hard-code them twice.
  - `test_build_estado_says_seventeen_rules`: `build_estado.py` text contains `diecisiete reglas reales` and not `dieciséis reglas reales`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_governance_docs.py -q`. Expected: the eight Task 1 tests FAIL (strings not there yet; `traps-5` missing).
- [ ] **Step 3: Edit `docs/plano/estado.py`** with the Global Constraints strings, and `build_estado.py:278`.
- [ ] **Step 4: Run** `python3 docs/plano/build_estado.py` (exit 0, prints `79 componentes`) and `uv run pytest tests/unit/test_governance_docs.py tests/unit/test_hypergrowth_docs.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `docs(#61): the status plan counts the governance trap detector (#277)`.

### Task 2: The lesson's trap paragraph

**Files:**
- Modify: `docs/leccion/index.html:520`
- Test: `tests/unit/test_governance_docs.py` (same module)

**Interfaces:** none.

- [ ] **Step 1: Write the failing tests**:
  - `test_trap_paragraph_has_three_clarifications`: `index.html` has no `Dos aclaraciones sobre cómo leer esto.` and exactly one `<p>` starting `Tres aclaraciones sobre cómo leer esto.`; that paragraph still contains the Sloan and dilution sentences and contains the governance sentence below verbatim.
  - `test_cuatro_motivos_stays`: `aunque parezca barata por cuatro motivos` is still in `index.html`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_governance_docs.py -q -k "clarifications or motivos"`. Expected: `test_trap_paragraph_has_three_clarifications` FAILS; `test_cuatro_motivos_stays` passes (a guard).
- [ ] **Step 3: Edit line 520** to exactly:

  ```html
      <p>Tres aclaraciones sobre cómo leer esto. El ratio de Sloan mira cuánto de la ganancia declarada no se cobró en efectivo; si es mucho, las ganancias son de papel. La dilución cuenta el crecimiento promedio de acciones: una empresa que emite acciones todos los años le va regalando tu parte. Y el detector de gobernanza busca dos señales rojas ante la SEC: cambiar de auditor y pedir más tiempo para presentar un balance. Las dos quedan en el índice de presentaciones de la empresa, que solo existe para las que reportan en Estados Unidos; a una empresa de afuera el detector la saltea, y como saltearse elimina, queda descartada.</p>
  ```

  (The second clarification loses its leading `Y` so that only the last one carries it.)
- [ ] **Step 4: Run** `python3 docs/leccion/check.py` (exit 0, `18 avisos`, same list as before) and `uv run pytest tests/unit/test_governance_docs.py tests/unit/test_leccion.py -q`. Expected: PASS.
- [ ] **Step 5: Run the full gate** `uv run ruff check . && uv run mypy src && uv run pytest -q`. Expected: green.
- [ ] **Step 6: Commit** `docs(#61): the lesson explains the governance trap detector (#277)`.
