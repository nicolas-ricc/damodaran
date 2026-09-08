# PR 68 Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every Spec-axis finding (a)–(c) from the PR 68 code review: fix the fragile high-growth fade coupling, legitimize the reviewed scope deviations in the original plan doc, and execute (and attest) the real-network run of Task 13.

**Architecture:** Three independent tasks on top of branch `worktree-conectar-fases-us-only`. One small code fix with a pinning test (`assumptions.py`), one docs amendment to the original plan (`2026-08-17-conectar-fases-us-only.md`), and one operational runbook task (the real run) that may spawn `fix(...)` commits for whatever breaks against the live network.

**Tech Stack:** Python 3.12+, DuckDB, pytest, uv, ruff, mypy --strict.

**Spec:** The PR 68 code-review report (Spec axis, items a–c). The findings are quoted verbatim inside each task below so this plan is self-contained; the underlying feature spec is `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md`.

## Global Constraints

- `uv run ruff check .` clean; `uv run mypy src` (strict) clean; full `uv run pytest` green (721 tests baseline — never fewer).
- Conventional Commits (`fix:`, `test:`, `docs:` …), Claude co-author trailer as per repo history.
- US-only scope: nothing here may add multi-currency, portfolio/IBKR, or analyst-consensus work.
- Work happens in the worktree `/home/nicolasr/Projects/investment-bot/.claude/worktrees/conectar-fases-us-only`; do not `cd` to the main checkout.

---

## Findings under remediation (verbatim from the review)

- **(a)1** — Task 13 (la corrida real) unverifiable, likely not executed: the branch has the deliverable docs but zero `fix(damodaran)` commits and no change to `src/bot/ingest/damodaran.py`, which the spec predicted would break on first real contact. → **Task 3.**
- **(b)1** — `sensitivity.py` rework (public `_PATH_AXES` → `PATH_AXES`, "(yr 1)" tornado labels) where spec Task 8 said "sin cambio". → **Task 2** (keep + document).
- **(b)2** — unrequested `assumptions.story_type.invalid` warning + `_STORY_TYPE_VALUES` validation. → **Task 2** (keep + document).
- **(b)3** — `.env.example` extra `BOT_ASSUMPTIONS_DIR` line; e2e seeds a third company. → **Task 2** (keep + document).
- **(c)1** — high-growth fade starts at `historical[0]`, which equals the average only while `_historical_growth_path` returns a flat path; no test pins the coupling. → **Task 1** (fix + pinning test).
- **(c)2** — `analyze --from-screen` splits the spec's single error into two messages, same exit 2. → **Task 2** (keep + document).

Decision on (b)/(c)2: **keep, don't revert.** Each deviation is behaviour-improving and already covered by tests on the branch (tornado labels in `tests/unit/test_valuator_sensitivity.py`, the invalid-story warning in `tests/unit/test_valuator_assumptions.py:370`, the third e2e company exercises the ADR 0006 coverage gate). The honest remediation for benign scope creep is to make the spec agree with the code, not to delete tested value. Reverting remains the fallback if the user objects.

---

### Task 1: De-couple the high-growth fade from the flat-history representation

**Files:**
- Modify: `src/bot/valuator/assumptions.py:607-637` (`_resolve_revenue_growth`) and the import block at `src/bot/valuator/assumptions.py:31-45`
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `_resolve_revenue_growth(historical, override, gdp_nominal, *, story_type)` and `_linear_path(start, end)` as they exist today; `StoryType.HIGH_GROWTH` from `bot.valuator.story_types`.
- Produces: same signature, but the fade start becomes `statistics.fmean(historical)` — correct for any year-varying history path, not just today's flat one. No caller changes.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_valuator_assumptions.py`, next to `test_high_growth_revenue_path_fades_from_history_to_gdp` (line ~401). Add `_resolve_revenue_growth` to the existing `from bot.valuator.assumptions import ...` statement at the top of the file.

```python
def test_high_growth_fade_starts_at_the_historical_average_not_year_one() -> None:
    # A year-varying history path: year-1 growth 50%, but the average is 18%.
    # The spec says the fade runs "promedio histórico → PBI nominal"; pin that
    # the start is the mean, not whatever happens to sit in historical[0].
    historical = (0.50, 0.10, 0.10, 0.10, 0.10)
    resolved = _resolve_revenue_growth(
        historical, {}, 0.04, story_type=StoryType.HIGH_GROWTH
    )
    path = resolved.value
    assert path is not None
    assert path[0] == pytest.approx(0.18)  # fmean(historical), NOT 0.50
    assert path[-1] == pytest.approx(0.04)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py::test_high_growth_fade_starts_at_the_historical_average_not_year_one -v`
Expected: FAIL — `path[0]` is `0.50` (today's code uses `historical[0]`).

- [ ] **Step 3: Write minimal implementation**

In `src/bot/valuator/assumptions.py`, add to the stdlib import block (after `import itertools`):

```python
from statistics import fmean
```

Then in `_resolve_revenue_growth`, change the high-growth branch (line ~628):

```python
    if story_type is StoryType.HIGH_GROWTH and historical is not None:
        return Sourced(
            value=_linear_path(fmean(historical), gdp_nominal),
            source=AssumptionSource.STORY_PATTERN,
        )
```

Also fix the docstring sentence (line ~621-623) so it reads: "…the path linearly fades from the mean of the historical path down to nominal GDP over the explicit horizon instead of staying flat."

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -v`
Expected: all PASS, including the pre-existing `test_high_growth_revenue_path_fades_from_history_to_gdp` (unchanged behaviour: on a flat path, `fmean == historical[0]`).

- [ ] **Step 5: Full gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy src`
Expected: all green/clean, ≥ 722 tests.

- [ ] **Step 6: Commit**

```bash
git add src/bot/valuator/assumptions.py tests/unit/test_valuator_assumptions.py
git commit -m "fix(valuator): start the high-growth fade at the historical mean, not element zero"
```

---

### Task 2: Record the accepted deviations in the originating plan

**Files:**
- Modify: `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md` (append a new section right before `## Self-Review`)

**Interfaces:**
- Consumes: nothing from other tasks (independent).
- Produces: a `## Desviaciones aceptadas (post-review, 2026-08-22)` section — the doc-of-record future reviewers diff the code against.

- [ ] **Step 1: Append the section**

Insert before the `## Self-Review` heading (line ~1398), matching the doc's Spanish register:

```markdown
## Desviaciones aceptadas (post-review, 2026-08-22)

La revisión de la PR 68 encontró cuatro desvíos del plan. Los cuatro quedan
**aceptados** — mejoran el comportamiento y ya tienen tests — y este es el
registro para que el plan y el código vuelvan a coincidir:

1. **`sensitivity.py` sí cambió** (la Tarea 8 decía "sin cambio"):
   `_PATH_AXES` se hizo público y el tornado etiqueta ejes de path como
   "(yr 1)". Motivo: con `operating_margin` convertido en path, la etiqueta
   vieja mentía sobre qué perturba el tornado. Tests en
   `tests/unit/test_valuator_sensitivity.py`.
2. **Validación de `story_type` con warning** (`assumptions.story_type.invalid`
   + `_STORY_TYPE_VALUES`): el plan solo pedía el guard silencioso. Un typo en
   un override YAML ahora se ve en el log en vez de ignorarse. Test en
   `tests/unit/test_valuator_assumptions.py`.
3. **`.env.example` lleva `BOT_ASSUMPTIONS_DIR`** además de las cuatro líneas
   del plan: documenta el default de la Tarea 9 en el único archivo que un
   usuario nuevo copia.
4. **`analyze --from-screen` distingue dos errores** ("no hay run" vs
   "shortlist vacía"), ambos exit 2. El plan pedía un solo mensaje; dos
   diagnósticos distintos merecen dos textos. El contrato (exit 2) no cambia.
   El test E2E además siembra una tercera empresa para ejercitar la compuerta
   de cobertura de la ADR 0006 — más cobertura, mismo spec.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md
git commit -m "docs(plan): record the four review-accepted deviations from the connect-phases plan"
```

---

### Task 3: Execute and attest the real-network run (Task 13 of the original plan)

**Files:**
- Read: `README.md` (quickstart, lines 14-27), `.env.example`
- Modify: `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md` (attestation appended to the section added in Task 2)
- Possibly modify: `src/bot/ingest/damodaran.py`, `src/bot/ingest/fmp.py`, `src/bot/ingest/universe.py` — whatever the live run breaks (unknowable in advance; that's the point of the task)

**Interfaces:**
- Consumes: the Task 1 fix (run with the corrected fade); a filled `.env`.
- Produces: an attested, reproducible real run; zero-or-more `fix(...)` commits.

**⚠ BLOCKED ON USER INPUT:** this task needs a real `.env` (FMP API key + `BOT_SEC_USER_AGENT`) and network access. If `.env` is missing or `uv run bot doctor` exits 1, STOP and ask the user for credentials — do not fake, stub, or skip the run, and do not mark this task done without it.

- [ ] **Step 1: Preflight**

Run: `test -f .env && uv run bot doctor`
Expected: exit 0. On exit 1 → blocked; ask the user.

- [ ] **Step 2: Sector benchmarks (the never-exercised path)**

Run: `uv run bot refresh --damodaran`
Expected: US sector rows ingested with non-NULL WACC. The original spec predicted this exact step would break ("`download` de Damodaran jamás se ejerció sin parchear"). On any failure: use superpowers:systematic-debugging, fix the adapter, add a regression test for the failure shape, commit as `fix(damodaran): <what broke>`.

- [ ] **Step 3: Universe + prices, quota-bounded**

Run: `uv run bot refresh --fmp --limit 25 && uv run bot refresh --prices --limit 25`
Expected: ≥ 1 ticker `ok`; a 429 must produce `deferred` (not `failed`) outcomes and a clean stop. Same debugging/fix/commit protocol on failure. If quota allows, re-run without `--limit` to widen coverage.

- [ ] **Step 4: Screen and analyze**

Run: `uv run bot screen --preset damodaran_value --top 10 && uv run bot analyze --from-screen`
Expected: the screen report prints the `Excluded (no sector benchmark, ADR 0006): N` line; analyze produces a report per shortlisted ticker. Same fix protocol on failure.

- [ ] **Step 5: Attest**

Append to the `## Desviaciones aceptadas` section of `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md`:

```markdown
### Corrida real (Tarea 13) — ejecutada 2026-08-XX

`doctor` OK · `refresh --damodaran` OK (<n> sectores) · `refresh --fmp/--prices
--limit 25`: <ok/deferred/failed> · `screen`: <candidatos, excluidos ADR 0006>
· `analyze --from-screen`: <n> reportes. Roturas encontradas y arregladas:
<lista de commits fix(...), o "ninguna">.
```

Fill every `<...>` with the real numbers from Steps 1–4; never commit the template.

- [ ] **Step 6: Full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy src`
Expected: green/clean. Then:

```bash
git add docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md
git commit -m "docs(plan): attest the real-network run of Task 13"
```
