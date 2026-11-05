# A mature-decline company keeps its own operating margin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_resolve_operating_margin` gives a `mature-decline` story its own latest margin, flat over the 10-year horizon, and the `story_types.py` docstring stops claiming that `mature-stable` anchors growth on nominal GDP.

**Architecture:** One new branch in `_resolve_operating_margin` (`src/bot/valuator/assumptions.py`), placed after the cyclical branch and before the sector-median fallback. It reuses the input the high-growth ramp already reads (`AssumptionInputs.company_operating_margin`). No new input, no new source enum. The docstrings that list the margin branches are updated. The isolation golden's `mature_decline` fixture is regenerated. The second-pass golden is re-run, stays unchanged, and gets a docstring note.

**Tech Stack:** Python 3.12, DuckDB, pytest, mypy --strict, ruff.

**Spec:** issue #244 (child of story #213; maintainer decision of 2026-11-05).

## Global Constraints

- Branch order in `_resolve_operating_margin`: manual → high-growth ramp → cyclical average → **mature-decline with a `company_margin`** → sector median (unchanged).
- The mature-decline path is `Sourced(value=(company_margin,) * _HORIZON, source=AssumptionSource.HISTORICAL_AVERAGE)`, with `_HORIZON = 10`.
- A mature-decline company with `company_margin is None` falls back to the sector median, as today.
- `mature-stable` gets no branch.
- Do not touch the probability of bankruptcy, the report template or `docs/` (sibling issues #246 and #247 own them). The only `docs/` file this branch adds is this plan.
- The `story_types.py` replacement sentence is copied verbatim from the issue (Task 1, Step 5).
- `uv run ruff check . && uv run mypy src` are clean and `uv run pytest -q` is green.
- Commits: `feat(#213): a mature-decline company keeps its own operating margin`, `test(#213): regenerate the mature-decline golden`.

## Review Focus

1. **A loss-making mature-decline company** (latest EBIT < 0): the maintainer's rule is "keeps its own latest margin, flat", so a negative margin stays negative over the whole horizon. It is not clamped and not swapped for the sector median. Pinned by `test_mature_decline_keeps_a_negative_own_margin` (Task 1).
2. **Mature-decline set by a manual `story_type` without a manual margin**: the branch keys on the *resolved* story type, so `story_type: mature-decline` in the override triggers it the same way auto-classification does. Pinned by `test_manual_story_type_mature_decline_uses_own_margin` (Task 1).
3. **Mature-decline with no sector row**: the own margin still resolves, because the branch does not need `sector_margin`. Covered by the code order (the branch sits before the `sector_margin is None` check). No extra test; the own-margin test already proves the branch never reads the sector.
4. **Other story types unaffected**: high-growth, cyclical and mature-stable keep their paths. The existing tests (l.538, l.557, l.578) and the isolation goldens for the other four cases stay byte-identical.
5. **Revenue growth unchanged for mature-decline**: no growth branch is added. Asserted inside `test_mature_decline_keeps_its_own_margin_flat`.

---

### Task 1: mature-decline margin branch and docstrings

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`_resolve_operating_margin` ~l.1046-1085; `Assumptions.operating_margin` attribute doc ~l.150-153; `AssumptionInputs.company_operating_margin` attribute doc ~l.323-325)
- Modify: `src/bot/valuator/story_types.py:14-16`
- Test: `tests/unit/test_valuator_assumptions.py` (next to `test_mature_stable_keeps_sector_margin_and_historical_growth`, l.578)

**Interfaces:**
- Consumes: the existing helpers `_seed_company`, `_seed_industry(op_margin=…)`, `_seed_country`, `_seed_financials(rows=((year, revenue, ebit), …))`, `_usd()`, `_write_override(tmp_path, body)`; `resolve_assumptions(ticker, conn, *, override_path=…, auto_story_type=…, currencies=…)`.
- Produces: no new names. `_resolve_operating_margin`'s signature does not change.

- [ ] **Step 1: Write the failing tests**

```python
def test_mature_decline_keeps_its_own_margin_flat(conn):
    _seed_company(conn); _seed_industry(conn, op_margin=0.12); _seed_country(conn)
    _seed_financials(conn, rows=((2022, 100.0, 5.0), (2023, 95.0, 4.5), (2024, 90.0, 3.6)))
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.MATURE_DECLINE, currencies=_usd())
    assert a.operating_margin.value == (pytest.approx(0.04),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE
    assert a.revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE

def test_mature_decline_without_own_margin_falls_back_to_sector(conn):
    # same seeds, no _seed_financials
    assert a.operating_margin.value == (0.12,) * 10
    assert a.operating_margin.source == AssumptionSource.SECTOR_DEFAULT_DAMODARAN

def test_manual_margin_beats_mature_decline(conn, tmp_path):
    # same seeds + financials as the first test;
    # override "operating_margin: 0.25\nstory_type: mature-decline\n"
    assert a.operating_margin.value == (0.25,) * 10
    assert a.operating_margin.source == AssumptionSource.MANUAL

def test_mature_decline_keeps_a_negative_own_margin(conn):
    # rows ((2023, 100.0, 2.0), (2024, 90.0, -4.5)) -> latest -0.05
    assert a.operating_margin.value == (pytest.approx(-0.05),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE

def test_manual_story_type_mature_decline_uses_own_margin(conn, tmp_path):
    # first test's seeds; override "story_type: mature-decline\n"; no auto_story_type
    assert a.operating_margin.value == (pytest.approx(0.04),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE
```

Every call passes `currencies=_usd()`. `test_mature_stable_keeps_sector_margin_and_historical_growth` stays unchanged.

- [ ] **Step 2: Run the tests and check that they fail**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -q -k "mature_decline"`
Expected: the own-margin tests FAIL (the source is `sector_default_damodaran` and the value is 0.12). The fallback and manual tests already PASS, because they pin behaviour that exists today.

- [ ] **Step 3: Add the branch to `_resolve_operating_margin`**

Insert after the cyclical `if`, before `if sector_margin is None:`:
`if story_type is StoryType.MATURE_DECLINE and company_margin is not None: return Sourced(value=(company_margin,) * _HORIZON, source=AssumptionSource.HISTORICAL_AVERAGE)`.
In the function's docstring, add a "mature-decline:" paragraph (the company's own latest margin, flat, no convergence to the sector, and the sector median when there is no own margin). Change "Every other archetype" so that it still reads true.

- [ ] **Step 4: Update the attribute docs**

- `Assumptions.operating_margin`: "Flat across the horizon for most archetypes, but a high-growth story ramps it, a cyclical story flattens it to the cycle average, a mature-decline story keeps the company's own latest margin (spec §7.1)."
- `AssumptionInputs.company_operating_margin`: "…used as the starting point of the high-growth margin ramp and as a mature-decline story's flat margin (spec §7.1)."

- [ ] **Step 5: Replace the `story_types.py` docstring sentence**

Replace l.14-16 with this text, verbatim (re-wrapped at the module's width):
"The story type drives default assumption resolution (see :mod:`bot.valuator.assumptions`): every story fades revenue growth from its own history to terminal growth; a ``high-growth`` story ramps its margin to the sector median, a ``cyclical`` one averages its own cycle, a ``mature-decline`` one keeps its own latest margin, and ``mature-stable`` has no branch of its own."
Keep the archetype table above it.

- [ ] **Step 6: Run the tests and check that they pass**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -q` → all pass.
Run: `grep -n "anchors growth on nominal GDP" src/bot/valuator/story_types.py` → prints nothing.
Run: `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 7: Commit**

`git commit -m "feat(#213): a mature-decline company keeps its own operating margin"` (the src and test files only).

### Task 2: goldens

**Files:**
- Regenerate: `tests/fixtures/valuator/isolation/mature_decline.md`, `tests/fixtures/valuator/isolation/mature_decline.json`
- Modify: `tests/unit/test_valuator_isolation_golden.py` (module docstring)
- Modify: `tests/unit/test_screener_second_pass_golden.py` (module docstring only)

**Interfaces:**
- Consumes: Task 1's branch; `regenerate()` in `tests/unit/test_valuator_isolation_golden.py`.

- [ ] **Step 1: Run the isolation golden and check that only mature_decline fails**

Run: `uv run pytest tests/unit/test_valuator_isolation_golden.py -q`
Expected: only the `mature_decline` parametrisations fail. Fixture `DECL` has its own margin 122/1020 = 11.96% against the sector's 12.0%.

- [ ] **Step 2: Regenerate from the repo root**

Run: `uv run python -c "from tests.unit.test_valuator_isolation_golden import regenerate; regenerate()"`
Then run `git status --short tests/fixtures`. It must list only `mature_decline.md` and `mature_decline.json`, and the margin row's source must read `historical_average`. If any other fixture changed, revert it with `git checkout -- tests/fixtures` and investigate before going on.

- [ ] **Step 3: Docstring notes**

- Isolation golden: append the paragraph "Regenerated for #213 (a mature-decline company keeps its own latest margin): only the mature_decline fixture moved."
- Second-pass golden: append "Re-run for #213 (mature-decline keeps its own margin): unchanged, no seeded company declines." Do not regenerate this golden.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/unit/test_valuator_isolation_golden.py tests/unit/test_screener_second_pass_golden.py -q` → pass.
Run: `uv run pytest -q` → green. Run `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 5: Commit**

`git commit -m "test(#213): regenerate the mature-decline golden"`

## Assumptions

- **A negative latest margin is kept as-is** (Review Focus 1). The issue's rule is "keeps its own latest margin, flat, with no convergence to the sector", and `_margins_from_rows` (`assumptions.py:518-522`) keeps negative ratios (it drops only NULL and zero revenue). Rejected: clamping at 0 or falling back to the sector, neither of which the issue asks for.
- **Two commits, the first one leaves the isolation golden red** until the second one lands. The issue prescribes the two commit titles, and the PR is squash-merged, so the feature branch never sees the red state. Rejected: a single commit, which would contradict the issue's commit list.
- **"(spec §7.1)" stays on the attribute docs** because it is already there (`assumptions.py:150-153`). It cites the archetype table (§7.1, "márgenes erosionándose"), not the own-margin rule. The own-margin rule is the maintainer decision recorded in the issue.

## Grilling

- Rounds: 1. The plan's revision was not substantial (one Assumptions section, no step added or removed), so there was no second round.
- Questions: 16. Sources: ISSUE 7 (Q3, Q5, Q7, Q8, Q13, Q16 and the decision half of Q1), CODE 12 (Q1, Q2, Q4, Q7, Q8, Q9, Q10, Q11, Q12, Q14; one answer can cite both), DOC 1 (Q6, spec §7.1). NO SOURCE: 1 (Q15), handled as a technical assumption.
- Assumptions: the three above.
- Issues opened: none. Spec ambiguities: none.
