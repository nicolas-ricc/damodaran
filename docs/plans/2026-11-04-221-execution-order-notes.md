# Execution order, not dependency: notes on three analyze boards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Say on `analyze-flags.d2`, `analyze-verdict.d2` and `analyze.d2` that the flags → verdict → sanity check chain is the order `analyze` runs them in, not a data dependency. Add a test that fails when that stops being true.

**Architecture:** Three `note` nodes, each keyed `execution_order`. Two are top-level on the sub-boards. The third is top-level on `analyze.d2`, declared right after section 8 (`sanity_check`) and before section 9 (`reports`). Notes add no edges, and the statechart, its edges and `models/` stay as they are. One characterization test in `tests/unit/test_valuator_analysis.py` pins the claim against `analyze()`. The SVGs and `rendered.sha256` come from the `pipeline-render` artifact of the `pipeline-diagram` workflow, because d2 is not on `PATH` here and installing it was refused.

**Tech Stack:** d2 v0.9.0 (CI), pytest, `docs/pipeline/check.py`.

**Spec:** issue #221 and its Agent Brief comment. The board conventions are in `docs/pipeline/README.md`.

## Global Constraints

- No change under `models/` (`docs/pipeline/models/`) or `src/` (AC2).
- The statechart and edges stay as they are. Redrawing the boards as parallel outputs is out of scope, and so are the verdict threshold constants (#220).
- Notes use `class: note`, never `gap`. There is no `@` inside the `|md ... |` block, and no digits in the copy.
- At most 24 edges per board (`test_edge_cap`). Notes add none.
- Never edit an SVG or `rendered.sha256` by hand.

## Decisions taken here

1. **The brief's sentence is corrected to match the code.** The brief proposes: "Execution order, not dependency: the margin of safety, the verdict and the sanity check read the DCF result and the price only; the flags do not change them." Two parts of `analyze` (`src/bot/valuator/analysis.py:829-853`) make "the DCF result and the price only" false:
   - The margin of safety reads `intrinsic_after_governance`, which applies the story file's governance discount.
   - `_sanity_check` also reads the latest net income, revenue and shares, and the sector multiples. The issue body itself says "the price and the sector row".
   
   Precedent: #218 corrected a brief sentence for the same reason. The exact copy, identical on all three boards:

   `Execution order, not dependency: the margin of safety and the verdict read the value after the governance discount and the latest close; the sanity check reads the latest close, net income, diluted shares and revenue, the discounted cash flow's intrinsic value per share and enterprise value, and the sector multiples. The flags change none of them, and the sanity check does not read the verdict.`
2. **Note key `execution_order`** on all three boards, top-level. On `analyze.d2` it sits between sections 8 and 9. "Near sections 6–8" is met by declaration order; TALA chooses the final placement.
3. **A guard test backs the note.** The test monkeypatches `bot.valuator.analysis.narrative_flags` and `bot.valuator.analysis.hypergrowth_flags` so that every flag comes out red. It then asserts that `margin_of_safety`, `margin_verdict(margin_of_safety)` and `sanity_check` equal the unpatched run. The test lives under `tests/`, so AC2 holds.

## Review Focus

- Someone makes a red flag cap the verdict → the Task 1 guard fails.
- Someone feeds the verdict into the sanity check → there is no runtime test for it. `_sanity_check`'s signature (`analysis.py:614`) has no verdict parameter, and the Task 1 guard covers flags only. This is accepted: the note names it, and the check is a pure function of its six arguments.
- A sub-board loses the note in a re-render → `rendered.sha256` (`check.py`) plus the `_ANALYZE_TEXT` phrases in Task 2.
- A reader of `analyze-flags` thinks the note contradicts the edge `hypergrowth_checked -> discounted` → the note opens with "Execution order", the word the brief chose, and the edge stays because it mirrors `models/analyze.tla`.

---

### Task 1: Guard — flags change neither the margin of safety, the verdict nor the sanity check

**Files:**
- Test: `tests/unit/test_valuator_analysis.py` (after `test_analyze_sanity_check_vs_sector_multiples`)

**Interfaces:**
- Consumes: `analyze`, the `seeded_conn` fixture, `NarrativeFlag(name, color, reason)`, `FlagColor.RED`, and `bot.reporting.analysis_report.margin_verdict`.
- Produces: nothing.

- [ ] **Step 1: Write the test** `test_flags_change_neither_the_verdict_nor_the_sanity_check(seeded_conn, monkeypatch)`:

```python
baseline = analyze("AAPL", seeded_conn)
red = lambda *a, **k: (NarrativeFlag("forced", FlagColor.RED, "forced red"),)
monkeypatch.setattr("bot.valuator.analysis.narrative_flags", red)
monkeypatch.setattr("bot.valuator.analysis.hypergrowth_flags", red)
forced = analyze("AAPL", seeded_conn)
assert all(f.color is FlagColor.RED for f in forced.narrative_flags)
assert forced.margin_of_safety == baseline.margin_of_safety
assert margin_verdict(forced.margin_of_safety) == margin_verdict(baseline.margin_of_safety)
assert forced.sanity_check == baseline.sanity_check
```

(Write `red` as a `def` with typed `*args: object` for mypy and ruff.)

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_valuator_analysis.py -k flags_change_neither`. Expected: PASS. It is a characterization guard. To check its red state, temporarily make `analyze` multiply `margin_of_safety` by 0.5 when any flag is red, see the test fail, then revert. The revert is mandatory: `src/` must stay unchanged.
- [ ] **Step 3: Commit** `test(#221): ...`, after `git diff --exit-code -- src/ docs/pipeline/models/` exits 0 (the red-state edit is reverted). If the commit ever carries a `src/` change, `git revert` it before going on.

### Task 2: The three notes

**Files:**
- Modify: `docs/pipeline/analyze-flags.d2` (after `only_red`, before `# Neighbours`)
- Modify: `docs/pipeline/analyze-verdict.d2` (after `back`, before `# States`)
- Modify: `docs/pipeline/analyze.d2` (after the `sanity_check` block, before `# Section 9: reports`)
- Test: `tests/unit/test_pipeline_subboards.py` (`_ANALYZE_TEXT["analyze-flags"]`, `_ANALYZE_TEXT["analyze-verdict"]`), `tests/unit/test_pipeline_diagram.py` (`_ANALYZE_NODES`, `_ANALYZE_TEXT`)

- [ ] **Step 1: Failing tests.**
  - In `test_pipeline_subboards.py`, add `"Execution order, not dependency"`, `"The flags change none of them"` and `"does not read the verdict"` to both `_ANALYZE_TEXT["analyze-flags"]` and `_ANALYZE_TEXT["analyze-verdict"]`.
  - In `test_pipeline_diagram.py`, add `("execution_order", "note")` to `_ANALYZE_NODES`.
  - Also in `test_pipeline_diagram.py`, add `"execution_order": [the same three phrases, plus "the value after the governance discount"]` to `_ANALYZE_TEXT`.
  - In `test_pipeline_subboards.py`, add `test_execution_order_note_is_the_same_on_three_boards`. It asserts that the `execution_order` label (`node_labels(_text(stem))["execution_order"]`) has class `note` and the same text on `analyze`, `analyze-flags` and `analyze-verdict`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py`. Expected: the new entries FAIL.
- [ ] **Step 3: Add** `execution_order: |md <Decision 1 copy> | {class: note}` on each of the three boards.
- [ ] **Step 4: Run** the same tests, plus `uv run pytest -q tests/unit/test_pipeline_models.py`. Expected: PASS. Also run `python3 docs/pipeline/check.py`. Expected: it fails only on the stale `rendered.sha256` (Task 3).
- [ ] **Step 5: Commit** `docs(#221): ...`.

### Task 3: Render

- [ ] Push the branch. Wait for the `pipeline-diagram` run on its head commit: `gh run list --branch <b> --workflow pipeline-diagram`, then `gh run watch <id>`. Download the render with `gh run download <id> -n pipeline-render -D <tmpdir>`.
- [ ] Copy only `analyze.svg`, `analyze-flags.svg`, `analyze-verdict.svg` and `rendered.sha256` into `docs/pipeline/`. `rendered.sha256` hashes the `.d2` sources, not the SVGs (`build.sh`), so leaving the untouched SVGs as committed keeps the hash consistent, even if TALA would draw them differently.
- [ ] `python3 docs/pipeline/check.py` and the full suite must pass. Commit `docs(#221): render`.

## Assumptions

Technical choices made in the plan review, each with the alternative it rejected:

- **A1. The note copy corrects the brief's sentence (Decision 1).** The rejected alternative is the brief's sentence verbatim. Backing:
  - The issue body says "read only the DCF result, the price and the sector row".
  - `analysis.py:829-853` reads the governance discount and `_sanity_check(current_price, net_income, shares, enterprise_value, revenue, sector)`.
  
  The brief's intent and its opening words, "Execution order, not dependency", are kept, and so is its claim that the flags change none of them.
- **A2. The Task 1 guard is added by the plan; no AC asks for it.** Rejected alternative: notes only. The guard is what makes the note's claim checked against the code. It changes no `src/`.
- **A3. The guard is a characterization test.** It passes on its first run, and its red state is shown by a temporary, reverted edit. Rejected alternative: a committed failing test, which is impossible for a property the code already has.
- **A4. Placement on `analyze.d2` is by declaration order.** No test asserts position, and TALA lays out the board. Rejected alternative: nesting the note in section 7 or 8, which would make it read as belonging to one section only.
- **A5. Only the three changed SVGs come from the CI artifact (Task 3).** Rejected alternative: copying every SVG, which would widen the diff beyond #221.

## Rebase onto #219

#219 (0c3aa2a) added `intrinsic_value=dcf_result.intrinsic_value` to `_sanity_check` (implied P/E = intrinsic value per share ÷ EPS). The note copy now names "the discounted cash flow's intrinsic value per share and enterprise value". The SVGs were re-rendered after the rebase.

## Grilling

- **Rounds:** one. The revision added assertions and a verification line to existing steps; no step or seam changed.
- **Questions:** 17.
- **Answers by source:** CODE 10, ISSUE 2, DOC 3, NO SOURCE 2. Both NO SOURCE answers are technical assumptions (A3, A4).
- **Assumptions:** A1 to A5 above.
- **Issues opened:** none.
- **Changes the answers made to the plan:** a `src/`/`models/` diff check before the Task 1 commit (Q8), an identical-copy test (Q10), and the rule to copy only the three SVGs (Q12).
