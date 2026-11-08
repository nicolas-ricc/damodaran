# Drop analyst consensus from the docs (#320) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyst consensus is no longer described anywhere under `docs/` as specified, planned or missing: #63 closed it as wontfix, so the revenue growth path (historical revenue CAGR fading to terminal growth by year 10, manual override unchanged) is the decided design, not a stopgap.

**Architecture:** Documentation-only change plus the tests that pin it. The spec, the analyze board, the two plano pages, the lesson and three docstrings in `bot.valuator.assumptions` are reworded; no behaviour changes. One sweep test enforces the acceptance criterion over `docs/`.

**Tech Stack:** Markdown, d2 (rendered by CI), the plano/lesson HTML generators (`docs/plano/build.py`, `docs/plano/build_estado.py`, `docs/leccion/check.py`), pytest.

**Spec:** issue #320; the spec it amends is `docs/superpowers/specs/2026-05-25-investment-bot-design.md`.

## Global Constraints

- Nothing under `docs/` (outside the dated plan folders, see Decisions) presents analyst consensus as specified or missing.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- Manual override of the growth path is unchanged (no code path changes).
- Docs are Spanish where they already are (spec, plano, lesson), English where they already are (boards, plans, docstrings).

## Decisions

- **State of the spec today.** #238 (`0194683`) already rewrote the §7.3 growth row to "CAGR histórico … converge linealmente al terminal growth … en y10" and the source bullets to the `AssumptionSource` enum. What remains in the spec is the line `Planificado, no implementado: analyst_consensus … (#63).` (§7.3, l.284) and §16 risk 4 (l.584, "consensus de analistas sesgado"). The growth row (l.288) already says what the issue asks and is not edited.
- **Mentions that remain.** A doc may still name analyst consensus when it states the decision: the line cites `#63` and does not call it planned, pending or a gap. The sweep test (Task 1) encodes exactly that.
- **Dated plans are records.** `docs/superpowers/plans/` is excluded by the issue's acceptance criterion. `docs/plans/*.md` is not, but its files record what a past run decided, and rewriting their bodies falsifies history. So each `docs/plans/` file that names analyst consensus gets one banner line under its title (Task 5) and its body stays; the sweep accepts a `docs/plans/` file with a match only if it carries that banner. The 148 plan, named by the issue, also loses its `growth.consensus` gap entries (Task 2), since they describe the board as it should be drawn.
- **Docstrings.** `src/bot/valuator/assumptions.py` module docstring (item 2 "Analyst consensus — FMP (M2)"), the `_HORIZON` comment ("analyst-consensus / story-type layer") and `_resolve_revenue_growth`'s docstring ("planned (#63) but not implemented") still present it as pending. They are under `src/`, not `docs/`, but the issue's intent ("describes what the code does and will keep doing") covers them and `test_spec_assumption_sources.py` already pins that docstring. Same for the module docstring of `tests/unit/test_valuator_assumptions.py` (item 2).
- **Rendering.** `d2` is not installable in the agent sandbox. Per `docs/pipeline/README.md` step 4, the branch is pushed and `analyze.svg`, `analyze.png` and `rendered.sha256` are taken from the `pipeline-render` artifact of the `pipeline-diagram` workflow run on that push (`gh run download <id> -n pipeline-render`), then committed.

## Review Focus

- A reader of plano `a-growth` still sees why the historical CAGR is biased (the inertial bias) once the consensus comparison goes: keep that sentence, reworded without "todavía".
- The `plano_sources` gap stays open and pins the phrase `el default es el promedio histórico` in `docs/plano/part-data.js` (`test_document_gaps_are_current`): the `a-growth` rewrite must keep that exact phrase.
- `estado.py` `a-crecimiento` flips from `a-medias` to `hecho`: `BLOQUES["assumptions"]` stays `a-medias` (WACC and bankruptcy are still `a-medias`).
- The `svg` render must stop showing the gap: `analyze.svg` is part of the sweep.
- A Spanish or mixed wording ("consenso de analistas", "consensus de analistas", "analyst-consensus") slips past an English-only regex: the sweep pattern covers all of them.

---

### Task 1: Spec, sweep test and docstrings

**Files:**
- Modify: `docs/superpowers/specs/2026-05-25-investment-bot-design.md:284` (delete the `Planificado, no implementado` paragraph and its blank line) and `:584` (risk 4)
- Modify: `src/bot/valuator/assumptions.py` (module docstring l.9-23, `_HORIZON` comment l.80-85, `_resolve_revenue_growth` docstring first paragraph l.1122-1126)
- Modify: `tests/unit/test_valuator_assumptions.py:1-12` (module docstring)
- Modify: `tests/unit/test_spec_assumption_sources.py`
- Create: `tests/unit/test_docs_analyst_consensus.py`

**Interfaces:**
- Produces: `tests/unit/test_docs_analyst_consensus.py::test_no_doc_presents_analyst_consensus_as_pending`, which Tasks 2-4 turn green file by file.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_spec_assumption_sources.py`, replace `test_analyst_consensus_only_as_not_implemented` with:

```python
def test_section_7_3_does_not_name_analyst_consensus() -> None:
    section = _section_7_3().lower()
    assert "consensus" not in section and "consenso" not in section


def test_garbage_in_risk_names_the_historical_cagr() -> None:
    text = _SPEC.read_text(encoding="utf-8")
    risks = text[text.index("## 16. ") :]
    risk = next(line for line in risks.splitlines() if line.startswith("4. **DCF garbage-in"))
    assert "consens" not in risk.lower()
    assert "CAGR histórico" in risk


def test_growth_docstring_states_the_decision() -> None:
    doc = _resolve_revenue_growth.__doc__ or ""
    assert "planned" not in doc and "not implemented" not in doc
    assert "#63" in doc
```

Create `tests/unit/test_docs_analyst_consensus.py`:

```python
_PATTERN = re.compile(r"analyst[ _-]consensus|consens\w* de (los )?analistas", re.I)
_PENDING = re.compile(
    r"\b(planned|planificado|pendiente|todavía|pide|gap)\b|no implementado|not implemented", re.I
)
_SKIPPED = ("docs/superpowers/plans/",)
_PLANS = "docs/plans/"
BANNER = "> **Superseded (#320):** analyst consensus is not a source, by decision (#63); mentions of it below are historical."

def test_no_doc_presents_analyst_consensus_as_pending() -> None:
    # files = `git ls-files docs` (tracked only: the generated, gitignored plano.html and
    # estado.html never feed it), every file except .png and .b64, read with
    # errors="replace", minus _SKIPPED.
    # A docs/plans/ file with any _PATTERN match must contain BANNER verbatim.
    # Any other file: each line matching _PATTERN must contain "#63" and not match _PENDING.
    # Failure message lists "path:line" (or "path: no banner").
```

Plus a module docstring naming #320/#63, and `test_assumptions_module_docstring_has_no_consensus_layer`: `bot.valuator.assumptions.__doc__` does not match `_PATTERN` without `#63` on the same line, and its resolution order has no "Analyst consensus" item.

- [ ] **Step 2: Run them, verify they fail**

Run: `uv run pytest -q tests/unit/test_spec_assumption_sources.py tests/unit/test_docs_analyst_consensus.py`
Expected: the new spec tests, the docstring test and the sweep FAIL (sweep lists spec l.284/l.584, analyze.d2:114, analyze.svg, estado.py:114, part-body.html:93, part-data.js:234-237, leccion index.html:711, and the six `docs/plans/` files of Task 5 plus this plan, without banner).

- [ ] **Step 3: Edit the spec and the docstrings**

- Spec l.284: delete the paragraph. §7.3 keeps only the enum bullets and the table.
- Spec risk 4, exact copy: `4. **DCF garbage-in/garbage-out**: el valor del bot depende críticamente de la calidad de los supuestos. La sensitivity analysis y los narrative flags mitigan, pero no eliminan, el riesgo de confiar en un intrinsic value derivado de un CAGR histórico de ingresos que no representa el futuro de la empresa: proyecta hacia adelante lo que ya pasó.`
- Wrap docstrings so every line naming analyst consensus also carries `(#63)` (the docstring tests check line by line); keep lines ≤ 100 columns (ruff line length).
- Module docstring: drop item 2; renumber (`1. Manual override`, `2. Sector default`, `3. Rule-based`), and put the growth fact under the list: revenue growth starts at the company's own history (historical revenue CAGR) and fades to terminal growth over ten years; analyst consensus is not a source, by decision (#63).
- `_HORIZON` comment: "a richer year-by-year path comes from the analyst-consensus / story-type layer (M4.3+)" → "a hypergrowth story file supplies its own year-by-year path (§7.6), which overrides this default."
- `_resolve_revenue_growth` first paragraph: "Spec §7.3 describes this path. Analyst consensus is not a source, by decision (#63): every path starts at the company's own growth and fades linearly to the terminal growth rate, so the last explicit year already grows at the rate the terminal value assumes."
- `tests/unit/test_valuator_assumptions.py` docstring: drop item 2, renumber, same order as the module.

- [ ] **Step 4: Run, verify the spec/docstring tests pass** (the sweep still fails on the other docs)

Run: `uv run pytest -q tests/unit/test_spec_assumption_sources.py tests/unit/test_valuator_assumptions.py`
Expected: PASS

- [ ] **Step 5: Commit** `docs(#320): spec drops analyst consensus; docstrings state the decision`

### Task 2: Analyze board loses the `growth.consensus` gap

**Files:**
- Modify: `docs/pipeline/analyze.d2:114` (delete the `consensus:` gap node inside `growth`)
- Modify: `tests/unit/test_pipeline_diagram.py:1581` (drop `("assumptions.growth.consensus", "gap")` from the expected node list) and `:1981` (drop the `_ANALYZE_GAPS` entry)
- Modify: `docs/plans/2026-10-29-148-analyze-board.md` (l.84: drop the `Gap growth.consensus: …` sentence after the growth node; l.200: drop the `growth.consensus` item and say "seven gap keys")
- Modify (after push): `docs/pipeline/analyze.svg`, `docs/pipeline/analyze.png`, `docs/pipeline/rendered.sha256`

- [ ] **Step 1: Write the failing test** in `tests/unit/test_pipeline_diagram.py`:

```python
def test_analyze_growth_has_no_consensus_gap() -> None:
    # #320: analyst consensus was dropped by decision (#63), it is not a gap.
    assert _node_class(_analyze(), "assumptions.growth.consensus") is None
    assert "consensus" not in (_analyze_block("assumptions.growth") or "").lower()
```

(Check `_node_class`'s return for a missing node and adapt the first assertion to it.)

- [ ] **Step 2: Run, verify it fails.** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "consensus or gap_notes or node"`

- [ ] **Step 3: Delete the node, the two test entries, edit the 148 plan.**

- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py` and `python3 docs/pipeline/check.py`. Expected: tests PASS except render-freshness ones; `check.py` reports only `rendered.sha256 is stale`.

- [ ] **Step 5: Commit** `docs(#320): analyze board drops the growth.consensus gap`. The render is fetched at stage 8: push, `gh run list --workflow pipeline-diagram --branch <branch>`, `gh run watch`, `gh run download <id> -n pipeline-render -D /tmp/render-320`, copy `analyze.svg`, `analyze.png`, `rendered.sha256` (and any other changed board files: none expected) into `docs/pipeline/`, then `python3 docs/pipeline/check.py` clean, commit `docs(#320): render analyze board`.

### Task 3: Plano pages (estado, plano)

**Files:**
- Modify: `docs/plano/estado.py:113-114` (`a-crecimiento`)
- Modify: `docs/plano/part-data.js:233-238` (`a-growth`)
- Modify: `docs/plano/part-body.html:93`
- Modify: `docs/plano/views.py:178` (`a-growth` subtitle)

- [ ] **Step 1:** the sweep test from Task 1 is the failing test for these files; run `uv run pytest -q tests/unit/test_docs_analyst_consensus.py` and see them listed.

- [ ] **Step 2: Edit.**

- `estado.py` `a-crecimiento`: state `"hecho"`, evidence `"valuator/assumptions.py:<def line of _resolve_revenue_growth after Task 1>"` (get it with `grep -n "def _resolve_revenue_growth" src/bot/valuator/assumptions.py`; no test resolves evidence lines, so it must be read, not trusted), note: `"Coincide con el spec (§7.3): arranca en la tasa anual compuesta histórica de las ventas de la propia empresa (o en el PBI nominal de la moneda, sin historia) y baja en línea recta hasta el crecimiento terminal en diez años; un override manual gana siempre. El consenso de analistas no es una fuente: se decidió no integrarlo (#63)."`
- `part-data.js` `a-growth`, `idea[0]`: Damodaran's growth convergence argument stays, without saying the method asks for consensus here: "El crecimiento de los primeros años arranca en el de la propia empresa y después converge al crecimiento terminal. La convergencia no es una concesión conservadora: …" (rest unchanged). `idea[1]`: "El default es el promedio histórico de la propia empresa (…), que baja en línea recta hasta el crecimiento terminal en diez años; y si no hay serie suficiente, una regla sobre el PBI nominal. El consenso de analistas quedó afuera por decisión (#63), no por falta." — must contain the exact phrase `el default es el promedio histórico` (lowercase `el`, as the `plano_sources` gap pins it): write "…en diez años. Así, el default es el promedio histórico de la propia empresa…" or equivalent that keeps the substring. `idea[2]`: keep the inertial-bias point without the comparison: "El promedio histórico tiene un sesgo inercial: proyecta hacia adelante lo que ya pasó, que es exactamente lo que falla en una empresa que está cambiando." `code.where`: drop `["lo que pide el spec","analyst_consensus"]`.
- `part-body.html:93`: "Un DCF vale lo que valen sus supuestos, y el que más pesa es el crecimiento de los primeros años. El programa lo arranca en el promedio histórico de la propia empresa, que tiene un sesgo inercial y es discutible. La sensitivity y las banderas narrativas mitigan eso; no lo eliminan."
- `views.py:178` subtitle `"hoy: promedio histórico, plano"` → `"CAGR histórico, converge al terminal"` (the path is not flat since #216; "hoy:" implied a pending replacement).

- [ ] **Step 3: Run** `python3 docs/plano/build.py && python3 docs/plano/build_estado.py` (both exit 0; `build_estado.py` may warn about the audit commit, that is expected) and `uv run pytest -q tests/unit/test_pipeline_diagram.py -k document_gaps tests/unit/test_estado_desfasaje.py`. Expected: PASS. `git status` shows no generated HTML to commit (they are untracked outputs; do not add them).

- [ ] **Step 4: Commit** `docs(#320): plano states the growth path as decided`

### Task 4: Lesson

**Files:**
- Modify: `docs/leccion/index.html:711`

- [ ] **Step 1:** sweep test lists `docs/leccion/index.html:711`.

- [ ] **Step 2: Edit** the caveat paragraph. New copy: `<p>El crecimiento sale de la tasa anual compuesta histórica de las ventas de la propia empresa, no de proyecciones de analistas: el consenso de analistas no se integra, por decisión (#63). Una diferencia con el diseño: el valor de liquidación por acción no se deriva nunca de forma automática: queda en 0 salvo que lo cargues a mano; la probabilidad de quiebra solo se deriva en una <code>distressed</code>, desde la cobertura de intereses (capítulo 6).</p>` (the "cinco procedencias / nueve" comparison goes: spec §7.3 now lists the enum).

- [ ] **Step 3: Run** `python3 docs/leccion/check.py` and `uv run pytest -q tests/unit/test_leccion.py tests/unit/test_leccion_check.py tests/unit/test_docs_analyst_consensus.py`. Expected: PASS except the sweep, which only lists `docs/pipeline/analyze.svg` until the render lands.

- [ ] **Step 5: Commit** `docs(#320): lesson states the growth decision`

### Task 5: Banner on the dated plans in `docs/plans/`

**Files:**
- Modify (one line under the `# ` title, then a blank line): `docs/plans/2026-10-14-120-leccion-pipeline.md`, `docs/plans/2026-10-29-148-analyze-board.md`, `docs/plans/2026-11-05-216-fade-to-terminal-growth.md`, `docs/plans/2026-11-08-116-country-tax-source.md`, `docs/plans/2026-11-08-238-spec-7-3-assumption-model.md`, `docs/plans/2026-11-08-291-fixture-paths-test-hygiene.md`, and this plan.

- [ ] **Step 1:** the sweep lists these files as "no banner".
- [ ] **Step 2:** insert `BANNER` (a blank line, the banner, a blank line between the `# ` title and the existing `> **For agentic workers:**` line; no test reads plan structure) (exact copy from Task 1) after the title line of each; bodies untouched. Get the list with `git ls-files docs/plans | xargs grep -liE "analyst[ _-]consensus|consens[a-z]* de (los )?analistas"`, not from this plan, in case the list moved.
- [ ] **Step 3:** `uv run pytest -q tests/unit/test_docs_analyst_consensus.py`: only `docs/pipeline/analyze.svg` left.
- [ ] **Step 4: Commit** `docs(#320): dated plans carry the #63 banner`

### Final check

`uv run ruff check . && uv run mypy src && uv run pytest -q`: green except the sweep on `analyze.svg` until the CI render is committed at stage 8; after that, fully green.

## Assumptions

- Sweep over `git ls-files docs`, not the filesystem (rejected: walking `docs/`, which reads stale gitignored `plano.html`/`estado.html` builds).
- Dated plans in `docs/plans/` get a banner, bodies untouched (rejected: rewriting history; rejected: excluding the folder, which the acceptance criterion does not grant).
- `_PENDING` uses word boundaries (rejected: bare substrings, which flag "impide").
- The branch carries red commits (render freshness, sweep on `analyze.svg`) between the first push and the commit of the CI render (rejected: none available; d2 cannot be installed in the sandbox, and README step 4 documents the artifact path). The `pipeline-diagram` workflow fires on every push (`on: [push, workflow_dispatch]`) and uploads `pipeline-render` with `if: always()` before `check.py` runs, so a stale `rendered.sha256` does not prevent the upload. If the run or artifact fails, the stage is blocked and documented on the issue.
- Every new long string that names analyst consensus (estado note, `idea[1]`, lesson `<p>`, docstrings) keeps `(#63)` in the same sentence and on the same physical line; JS/HTML/`estado.py` strings are single physical lines today and stay so. The sweep run in each task's verification step checks it.
- `AUDITADO_EN` in `estado.py` is not bumped: this is not the full re-audit `docs/plano/README.md` describes, only one item whose evidence was read (rejected: bumping it, which would claim an audit that did not happen).
- From the `pipeline-render` artifact only `analyze.svg`, `analyze.png` and `rendered.sha256` are committed; any other board file that differs is discarded (same pinned d2 v0.9.0, and `check.py` reports 0 errors on master, so none is expected).
- The 148 plan body is edited (Task 2) because the issue names it; it still matches the sweep pattern afterwards (l.249 CODE fact), so it also gets the banner.
- `views.py` `a-growth` subtitle changes ("hoy:" implied a pending replacement; "plano" is false since #216).

## Grilling

Round 1: 17 questions (griller model fable). Sources: CODE 14 (test_pipeline_diagram.py:799-804, 1529-1536, 1978-1994, 2697-2750; estado.py:27-34, 113-119; .gitignore; build.py; check.py run on master: 0 errors; hypergrowth.py:289; spec l.271/295/321/579/584; .github/workflows/pipeline-diagram.yml), DOC 1 (docs/pipeline/README.md step 4), ISSUE 1 (acceptance criterion on `docs/superpowers/plans/`), NO SOURCE 3 → technical assumptions above. Spec ambiguities: none. Follow-up issues: none.

Round 2: 15 questions (griller model fable). Sources: CODE 11 (analyze.d2:114 holds "analyst consensus" and "analyst_consensus"; analyze.svg grep: 1 hit each on one line; `git ls-files docs` non-text suffixes: b64, cfg, sh, sha256, tla, version files, none matching the pattern, so the sweep reads all tracked files except .png/.b64; test_pipeline_diagram.py:1533 defines `_analyze_block`, :799-804 `_node_class` returns None for a missing node; no test pins leccion l.711 (`grep procedencias tests/` empty); estado.py:27-34 BLOQUES is hand-set, no consistency test; estado.py:16 AUDITADO_EN=90f717c, test_estado_desfasaje.py only counts commits on src/; test_spec_assumption_sources.py `_section_7_3` ends at `### 7.4 `, spec §7.3 has only l.284 matching; no test reads docs/plans structure; tests already shell out to git, e.g. test_pipeline_build.py:192-195), ISSUE 1 (acceptance criterion names only `docs/superpowers/plans/`), NO SOURCE 3 → technical assumptions (banner over historical bodies; AUDITADO_EN not bumped; artifact files other than analyze discarded). Spec ambiguities: none. Follow-up issues: none. Result: ok.
