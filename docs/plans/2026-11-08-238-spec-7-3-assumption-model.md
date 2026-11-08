# Spec §7.3 states the implemented assumption model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spec §7.3 stops saying revenue growth converges to nominal GDP by year 10 and stops listing an unimplemented `analyst_consensus` source: the growth row names terminal growth as the year-10 target over a 10-year horizon, and the source list is exactly the `AssumptionSource` enum, with `analyst_consensus` marked planned (#63).

**Architecture:** Docs only. Two edits to §7.3 of `docs/superpowers/specs/2026-05-25-investment-bot-design.md` (the source sentence at line 273 and the growth row at line 277), plus one stale docstring sentence in `_resolve_revenue_growth` that paraphrases the old spec. A new test module pins §7.3 against `AssumptionSource`, following the pattern of `tests/unit/test_hypergrowth_docs.py` (read the spec, slice the section, assert).

**Tech Stack:** Python 3.12, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #238 (`gh issue view 238 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec; it folds in #207 (the source list).

## Global Constraints

- The spec prose stays in Spanish (brief: "The prose stays in the spec's language").
- Only §7.3 of the spec changes. §7.1 ("mature-stable | Growth ≈ GDP nominal") is a story-type description, not the growth fade target, and stays.
- The lesson (`docs/leccion/`), the boards (`docs/pipeline/`), `docs/plano/` and the plans stay unchanged (brief: out of scope).
- No behaviour change under `src/`: the only `src/` edit is the `_resolve_revenue_growth` docstring.
- #116 (country tax source) is still open, so no new source is added to the list.
- `python3 docs/leccion/check.py` and `python3 docs/pipeline/check.py` still pass (acceptance criterion 4; these are what `.github/workflows/pipeline-diagram.yml` runs).
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Facts from the code (sources for the spec text)

- `AssumptionSource` (`src/bot/valuator/assumptions.py:107-127`): `manual`, `sector_default_damodaran`, `sector_default_damodaran_cross_region`, `rule_based`, `historical_average`, `story_pattern`, `story`, `unresolved`. No `analyst_consensus`.
- `_resolve_revenue_growth` (`assumptions.py:1108-1149`): a manual override (scalar or list) wins. Otherwise, with no terminal growth the path is `unresolved`. With history it starts at the historical revenue CAGR and fades linearly over `_HORIZON` (10) years to terminal growth, sourced `story_pattern` for `high-growth` and `historical_average` otherwise. With no history it starts at the currency's nominal GDP (`rule_based`). With neither, `unresolved`.
- `_resolve_terminal_growth` (`assumptions.py:1272-1284`): manual `terminal_growth`, else `min(rfr, nominal GDP)` of the valuation currency (`rule_based`), else `unresolved`.
- Hypergrowth (`src/bot/valuator/hypergrowth.py:198-253`): year 1 `year1_growth`, a solved stage rate for years 2-5, then a fade to terminal growth by year 10, sourced `story` (`hypergrowth.py:319`).
- `_SectorDefaults.source` (`assumptions.py:319-324`): `sector_default_damodaran_cross_region` when the sector row came from another region.

## Assumptions (declared)

- **Exact source text.** Line 273 becomes:

  ```markdown
  Cada supuesto lleva un `source` (`AssumptionSource` en `bot.valuator.assumptions`). El reporte muestra siempre cuál es cuál. Valores implementados:

  - `manual`: override en `config/assumptions/<TICKER>.yaml`.
  - `sector_default_damodaran`: mediana sectorial de Damodaran de la región de la empresa, o el dato de país de `damodaran_country`.
  - `sector_default_damodaran_cross_region`: mediana sectorial de Damodaran de otra región, porque la de la empresa no tiene filas ingeridas; el reporte muestra la sustitución.
  - `rule_based`: una regla fija, p. ej. `g = min(rfr, GDP nominal)` de la moneda de valuación, o el GDP nominal como arranque del growth sin historia.
  - `historical_average`: la historia propia de la empresa (CAGR de ingresos, margen promedio del ciclo).
  - `story_pattern`: trayectoria del patrón de proyección del story type (§7.1), derivada de datos de la empresa y del sector (growth de `high-growth`, rampa de margen).
  - `story`: la sección `story` del archivo de override; aplica solo para `hypergrowth`, ver §7.6.
  - `unresolved`: ninguna capa produjo un valor; el reporte muestra el hueco en lugar de un número.

  Planificado, no implementado: `analyst_consensus`, el consenso de analistas como arranque del growth de los años 1-5 (#63).
  ```

- **Exact growth row.** Line 277 becomes:

  ```markdown
  | Revenue growth path (10 años) | Arranca en el growth propio de la empresa: el CAGR histórico de ingresos (`story_pattern` en `high-growth`, `historical_average` en los demás), o el GDP nominal de la moneda sin historia (`rule_based`). Converge linealmente al terminal growth (g, ver abajo, o el `terminal_growth` manual) en y10. `hypergrowth` sigue su story (§7.6) y también termina en g en y10. Sin g, `unresolved` | Manual (escalar o lista de 10 años) |
  ```

  The old "Manual cuando consensus está sesgado" goes: there is no consensus to be biased.
- **Docstring.** `_resolve_revenue_growth`'s first paragraph ("Spec §7.3 wants analyst consensus for years 1-5 with convergence to nominal GDP by year 10. ...") would contradict the new spec. It becomes: "Spec §7.3 describes this path. Analyst consensus as the years 1-5 start is planned (#63) but not implemented (FMP's analyst-estimates endpoint is not wired, so there is no ANALYST_CONSENSUS source). Every path starts at the company's own growth and fades linearly to the terminal growth rate, so the last explicit year already grows at the rate the terminal value assumes." The remaining paragraphs stay.
- **How "listed as implemented" is tested.** The implemented list is the bullet list between the `source` sentence and the `Planificado` line. Its bullet keys must equal the enum values as a set. Every line of §7.3 that mentions `analyst_consensus` must contain `no implementado` and `#63`.

## Review Focus

- A source added to `AssumptionSource` later (for example by #116) without a §7.3 bullet: the set-equality test fails and names the missing value.
- A §7.3 line mentioning `analyst_consensus` without the "not implemented" marker, for example back in the table: the marker test fails on that line.
- The phrase "GDP nominal" survives legitimately in §7.3 (the terminal growth row, the `rule_based` bullet, the no-history start). So the test forbids the convergence claim, `converge a GDP nominal`, not the words "GDP nominal".
- Edits that break the table: the growth row must still have three `|`-separated cells, or the markdown table renders wrong.
- The lesson and board checks cite symbols, not spec text. They should stay green, and the full-suite step runs them.

---

### Task 1: §7.3 source list matches `AssumptionSource`

**Files:**
- Create: `tests/unit/test_spec_assumption_sources.py`
- Modify: `docs/superpowers/specs/2026-05-25-investment-bot-design.md:273`

**Interfaces:**
- Produces: the test module's helper `_section_7_3() -> str` (spec text from `### 7.3` up to `### 7.4`), reused by Task 2.

- [ ] **Step 1: Write the failing tests**

```python
_SPEC = Path(...).parents[2] / "docs/superpowers/specs/2026-05-25-investment-bot-design.md"

def _section_7_3() -> str: ...  # text between "### 7.3" and "### 7.4"

def _implemented_sources() -> set[str]:
    # bullets "- `name`: ..." in §7.3 before the "Planificado" line
    ...

def test_source_list_is_the_enum() -> None:
    assert _implemented_sources() == {s.value for s in AssumptionSource}

def test_analyst_consensus_only_as_not_implemented() -> None:
    lines = [l for l in _section_7_3().splitlines() if "analyst_consensus" in l]
    assert lines
    for line in lines:
        assert "no implementado" in line and "#63" in line
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_spec_assumption_sources.py -q`. Expected: FAIL (no bullets; `analyst_consensus` unmarked).
- [ ] **Step 3: Replace line 273 with the declared source text.**
- [ ] **Step 4: Run the tests.** `test_source_list_is_the_enum` passes. `test_analyst_consensus_only_as_not_implemented` still fails because of the table row; Task 2 fixes that.
- [ ] **Step 5: Commit** `docs(#238): §7.3 source list matches AssumptionSource`.

### Task 2: §7.3 growth row fades to terminal growth

**Files:**
- Modify: `tests/unit/test_spec_assumption_sources.py`
- Modify: `docs/superpowers/specs/2026-05-25-investment-bot-design.md:277`
- Modify: `src/bot/valuator/assumptions.py:1118-1122` (docstring only)

**Interfaces:**
- Consumes: `_section_7_3()` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
def _growth_row() -> str:
    rows = [l for l in _section_7_3().splitlines() if l.startswith("| Revenue growth path")]
    assert len(rows) == 1
    return rows[0]

def test_growth_does_not_converge_to_gdp() -> None:
    assert "converge a GDP nominal" not in _section_7_3()

def test_growth_row_targets_terminal_growth_over_ten_years() -> None:
    row = _growth_row()
    assert "terminal growth" in row and "y10" in row and "10 años" in row
    assert row.count("|") == 4  # three cells
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Replace line 277 with the declared growth row. Rewrite the docstring paragraph as declared.**
- [ ] **Step 4: Run** the module (all pass), then `python3 docs/leccion/check.py && python3 docs/pipeline/check.py`, then `uv run ruff check . && uv run mypy src && uv run pytest -q`.
- [ ] **Step 5: Commit** `docs(#238): §7.3 growth fades to terminal growth by y10`.
