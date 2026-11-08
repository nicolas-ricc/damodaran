# Assumptions README: what the hypergrowth story drives (#206) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale closing sentence of the "Hypergrowth story file" section of `config/assumptions/README.md` with a paragraph saying what a valid hypergrowth story does to the valuation. Make no code change.

**Architecture:** Documentation only. A new test in `tests/unit/test_hypergrowth_docs.py` reads the README section and pins two things: the stale sentence is gone, and the new text names the three effects (assumptions, scenarios, governance discount) in ADR 0009's own terms.

**Tech Stack:** Markdown, Python 3.12 / pytest.

**Spec:** GitHub issue #206 (follow-up of #198). Its "Agent Brief" and acceptance criteria are binding.

## Global Constraints

- No change under `src/`. No other doc changes: `docs/plano/`, `docs/leccion/` and the rest are out of scope.
- The README is in English, like ADR 0009 and `CONTEXT.md`. Terms come from the glossary: *story file*, *story type*, *governance discount*, *margin of safety*.
- Every claim matches the code:
  - `apply_story` (`src/bot/valuator/hypergrowth.py:289-338`) replaces `revenue_growth`, `operating_margin`, `sales_to_capital`, `wacc_path`, `tax_rate_path`, `terminal_roic`, `probability_of_bankruptcy`, `distress_proceeds_pct`, `fixed_commitments`, `extra_cash` and `governance_discount`, each sourced `STORY`. `resolve_assumptions` calls it (`src/bot/valuator/assumptions.py:1047-1056`).
  - `analyze` runs `scenario_range(scenario_cases(...))` when `scenarios` is set, and computes the margin of safety on `intrinsic_value * (1 - governance_discount)` (`src/bot/valuator/analysis.py:1012-1036`).
- Gates: `uv run pytest -q` and `uv run ruff check . && uv run mypy src`.
- Commits follow Conventional Commits and carry `#206`.

## Decisions taken here (not spelled out by the issue)

1. **"Valued and weighted."** The brief says "the scenarios are valued and weighted". The code does not weight the scenarios against each other: `scenario_range` runs "one plain `dcf` per case, in mapping order" (`src/bot/valuator/sensitivity.py:447-450`), and ADR 0009 says the report "shows the range next to the tornado". The only weighting in the code is the failure blend, `(1 - p) * EV + p * proceeds_pct * EV` (ADR 0009, "Failure blend on enterprise value"). The acceptance criterion requires consistency with ADR 0009, so the README says the scenarios are valued and shown as a range, and it describes the failure blend as part of what the story changes. It never says the scenarios are weighted.
2. **"Reinvestment."** The brief's "growth, margin and reinvestment assumptions" maps to `revenue_growth`, `operating_margin`, `sales_to_capital` and `terminal_roic`. The README also names the WACC and tax paths, because `apply_story` replaces those too.
3. **Location.** The new paragraph replaces the stale sentence in place, at the end of the "Hypergrowth story file" section, before "## Probability of bankruptcy". There is no new heading.

## Review Focus

1. **The stale sentence comes back.** It could return through a revert or a copy from an old branch. The test asserts that `does not read it yet` is absent from the whole README.
2. **The scenarios are described as weighted or averaged**, which contradicts the code (decision 1). The test asserts that the section does not contain `weighted`. The failure blend is worded without that word.
3. **The governance discount is described as inside the DCF**, which contradicts ADR 0009 ("never enters the DCF"). The test asserts that the section contains `never enters the DCF` and `margin of safety`.
4. **The paragraph omits the gate** (no story file, no hypergrowth valuation). The test asserts that the paragraph contains `story_type: hypergrowth`.
5. **A later edit to the section breaks the parse.** The test locates the section between `## Hypergrowth story file` and `## Probability of bankruptcy`, and fails loudly if either heading is missing.

---

### Task 1: README paragraph and its docs test

**Files:**
- Modify: `config/assumptions/README.md` (the last line of the "Hypergrowth story file" section)
- Test: `tests/unit/test_hypergrowth_docs.py` (append)

**Interfaces:**
- Consumes: none.
- Produces: none (a leaf task).

- [ ] **Step 1: Write the failing tests.** Append them to `tests/unit/test_hypergrowth_docs.py`, with a module constant `_ASSUMPTIONS_README = _ROOT / "config" / "assumptions" / "README.md"` and the existing `_section(text, start, end)` helper:

```python
def _story_file_section() -> str:
    text = _ASSUMPTIONS_README.read_text(encoding="utf-8")
    return _section(text, "## Hypergrowth story file", "## Probability of bankruptcy")


def test_assumptions_readme_drops_the_stale_sentence() -> None:
    assert "does not read it yet" not in _ASSUMPTIONS_README.read_text(encoding="utf-8")


def test_assumptions_readme_says_what_the_story_drives() -> None:
    section = _story_file_section()
    for phrase in (
        "story_type: hypergrowth",
        "apply_story",
        "ten-year paths",
        "sales_to_capital",
        "source `story`",
        "scenarios",
        "range",
        "governance_discount",
        "never enters the DCF",
        "margin of safety",
        "ADR 0009",
    ):
        assert phrase in section, phrase
    assert "weighted" not in section
```

- [ ] **Step 2: Run them to verify they fail.**
Run: `uv run pytest tests/unit/test_hypergrowth_docs.py -q -k assumptions_readme`
Expected: 2 failed. The first fails on `does not read it yet`; the second fails on its first missing phrase.

- [ ] **Step 3: Replace the sentence** `The story is parsed and validated; the valuation does not read it yet.` with this exact copy:

```markdown
A valid story file drives the valuation of that ticker (ADR 0009). Without one,
no hypergrowth valuation runs. With `story_type: hypergrowth` and a `story`:

- **Assumptions.** `resolve_assumptions` overlays the story on the resolved
  bundle through `apply_story`. Its ten-year paths replace the growth, margin
  and reinvestment assumptions: revenue growth (year 1 `year1_growth`, then
  solved so year-10 revenue meets `target_revenue_y10`), the operating margin
  (`year1_margin` to `target_margin` minus `regulatory_drag`), `sales_to_capital`
  and `terminal_roic`, plus the WACC and tax paths. The failure blend
  (`failure_probability`, `failure_proceeds_pct_of_value`), `fixed_commitments_pv`
  and `extra_cash` enter the DCF too. Each such input shows source `story` in the report.
- **Scenarios.** `bot analyze` values `base` and then every entry of
  `scenarios`, in file order, with one plain DCF each. The report shows the
  range next to the tornado.
- **Governance discount.** `governance_discount` never enters the DCF. The
  margin of safety is measured on the intrinsic value after the discount,
  `intrinsic_value * (1 - governance_discount)`.
```

- [ ] **Step 4: Run the tests to verify they pass.**
Run: `uv run pytest tests/unit/test_hypergrowth_docs.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full gates.**
Run: `uv run pytest -q` and `uv run ruff check . && uv run mypy src`.
Expected: green.

- [ ] **Step 6: Commit.**

```bash
git add config/assumptions/README.md tests/unit/test_hypergrowth_docs.py
git commit -m "docs(#206): assumptions README says what the story drives"
```

## Assumptions

- **A1. "Weighted" is dropped** (decision 1). The issue's criterion says "consistent with ADR 0009", and its brief says "The wording matches the CONTEXT.md glossary and ADR 0009". The code runs one plain DCF per scenario (`src/bot/valuator/sensitivity.py:447-461`), and the report lists the scenarios as rows with no weighted total (`src/bot/reporting/templates/analysis.md.j2:113-124`). A README that said "weighted" would contradict both. Rejected alternative: keep the word "weighted" for the scenarios.
- **A2. Commit type `docs`.** No repository document defines the Conventional Commit types. The convention is taken from history (`docs(#105)`, `docs(#78)` in `git log`). Rejected alternative: `fix(#206)`, chosen because the issue carries the `bug` label.

## Grilling

- **Rounds:** 1, with the `fable` griller. The plan was not changed substantially (no step added or removed, same seam), so there was no second round.
- **Questions:** 16. They are answered by source type as follows:
  - ISSUE: 4 (Q1, Q12, Q15, plus Q1's criterion quote).
  - CODE: 11.
    - Q2: `hypergrowth.py:53-71` (`StoryInputs` keys). The DCF names in the constraints are the bundle's.
    - Q3: `hypergrowth.py:222,248-264`. The growth rate is solved by bisection. The drag reaches every year of the margin path, because each year converges linearly on `target_margin - regulatory_drag`.
    - Q4: `assumptions.py:850-858` (mismatches raise `ValueError`) and `assumptions.py:1035-1041` (non-hypergrowth or no story returns the generic bundle).
    - Q5: `assumptions.py:123` (`STORY = "story"`) and `analysis.md.j2:44-70` (the source column).
    - Q6: `analysis.md.j2:54-70`. Rows are printed for the WACC path, tax path, terminal ROIC, failure proceeds, commitments and extra cash.
    - Q7: `hypergrowth.py:356` (`base` comes first). Scenarios are parsed into an insertion-ordered dict (`hypergrowth.py:162-163`).
    - Q8: `analysis.md.j2:113-124`. The "Scenario range" table follows the tornado table.
    - Q9: `config/assumptions/README.md:44`. This is the only hit in the repo.
    - Q10: `test_hypergrowth_docs.py:24-28`. `_section` uses `str.index`, so a missing heading raises `ValueError`.
    - Q11: `README.md:8,46`. These are the only two H2 headings around the section.
    - Q13: `hypergrowth.py:78` (`HORIZON: int = 10`), a module constant that is not configurable.
  - DOC: 1. Q14: ADR 0009, "`terminal_roic` sets the terminal reinvestment to `g / ROIC`".
  - NO SOURCE: 2. Q1 is partly sourced and recorded as A1. Q16 is recorded as A2. Both are technical assumptions.
- **Assumptions:** A1, A2.
- **Issues opened:** none.
