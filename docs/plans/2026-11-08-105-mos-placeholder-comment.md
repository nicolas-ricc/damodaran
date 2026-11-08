# PLACEHOLDER_MARGIN_OF_SAFETY comment describes the DCF fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `#:` comment on `PLACEHOLDER_MARGIN_OF_SAFETY` (`src/bot/screener/ranking.py:49-51`) stops calling the constant a stand-in "until M4.7 wires the real DCF in" and describes it as the neutral margin used when the DCF cannot value a shortlisted candidate or a caller passes no margin.

**Architecture:** Docs only. The three comment lines change; the constant, its value `0.5`, and every caller stay as they are. A new test module pins the comment's content so it does not drift back.

**Tech Stack:** Python 3.12, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #105 (`gh issue view 105 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec.

## Global Constraints

- No change to code, to the constant's name, or to its value `0.5`. Ranking maths and fallback behaviour stay unchanged.
- No existing test is edited.
- The comment stays a Sphinx `#:` doc comment directly above `PLACEHOLDER_MARGIN_OF_SAFETY = 0.5`.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared)

- **New comment text** (composed here; the brief gives its content, not its words):

  ```python
  #: Neutral margin-of-safety sub-score for a shortlisted candidate the DCF cannot
  #: value (the valuator returns ``None`` in :func:`bot.screener.engine.run_screen`'s
  #: second pass), and the default when a caller passes no margin. Mid-scale, so it
  #: neither rewards nor penalises the candidate. A DCF failure is not an ADR 0006
  #: coverage-gate reason, so the candidate stays in the shortlist and rankable.
  ```

  It matches the module docstring (`ranking.py:27-33`: "only when no DCF value is available (the valuator could not value the company, or a caller passes no value)") and the engine docstrings (`engine.py:93-98`, `engine.py:133-135`).
- **How ADR 0006 is cited.** The brief says the fallback keeps such companies rankable "per ADR 0006". ADR 0006 does not mention the DCF: it removes companies without sector benchmarks via the coverage gate, whose reasons are `industry_unmapped`, `benchmark_missing`, `currency_uncovered`. A DCF failure is none of those, so the candidate stays. The comment says exactly that rather than claiming ADR 0006 prescribes a neutral margin, which it does not (it says "no metric ever defaults to a neutral zero" about percentile inputs).
- **"No test changes" allows a new test module.** The acceptance criterion "No code, value or test changes" is read as: no existing code, value or test changes. The pipeline running this issue requires executable evals, and repo precedent pins doc text in new test modules (`tests/unit/test_readme_dev_docs.py` for #78, `tests/unit/test_governance_docs.py` for #277). Rejected: no test at all, which leaves AC 1 and 2 unchecked.
- **M4.7 is not mentioned at all.** AC 1 forbids saying M4.7 is pending. The module docstring already records that M4.7 wired the DCF; the constant's comment describes what the constant is now, so it drops the milestone entirely. The test asserts `"M4.7"` is absent, plus `"until"` and `"cannot yet"` (the old wording's two pending markers).
- **Comment extraction.** The test reads `ranking.py` as text, finds the line starting with `PLACEHOLDER_MARGIN_OF_SAFETY = `, and collects the contiguous `#:` lines directly above it, strips the `#:` prefix and joins them with whitespace collapsed. Assertions run on that string, so line wrapping does not matter.
- **Plan location `docs/plans/`.** Recent issue plans live there (`docs/plans/2026-11-08-78-readme-ruff-format.md`, `2026-11-08-293-source-cosmetics.md`).

## Review Focus

1. The comment block detached from the constant (blank line inserted, or `#` instead of `#:`) so Sphinx and readers lose it: the helper requires contiguous `#:` lines directly above the assignment and asserts it found some. Pinned in Task 1 (`_placeholder_comment`).
2. The value silently changed while rewording: pinned by `test_placeholder_value_unchanged` (`== 0.5`, and the module docstring's `(= 0.5)` still present).
3. Pending wording surviving in a different phrasing ("cannot yet value"): pinned by `test_comment_does_not_say_m47_is_pending`.
4. The "caller passes no margin" case dropped while the DCF case is described: pinned by `test_comment_names_the_fallback_cases`.
5. None further: the change has no runtime path.

## Acceptance criteria → tasks

| Issue item | Task |
|---|---|
| AC 1 (no M4.7 pending / "until M4.7") | Task 1 |
| AC 2 (names the "cannot be valued" fallback) | Task 1 |
| AC 3 (no code, value or test changes; lint passes) | Task 1, steps 5-6 |

---

### Task 1: Reword the comment and pin it

**Files:**
- Modify: `src/bot/screener/ranking.py:49-51`
- Create: `tests/unit/test_ranking_placeholder_comment.py`

**Interfaces:**
- Consumes: `bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_ranking_placeholder_comment.py`, module docstring `"""The PLACEHOLDER_MARGIN_OF_SAFETY comment describes the DCF fallback (#105)."""`, `_RANKING = Path(__file__).resolve().parents[2] / "src" / "bot" / "screener" / "ranking.py"`, and a typed helper `_placeholder_comment() -> str` as described under Assumptions (asserts the assignment line exists and the comment is non-empty).

```python
def test_comment_does_not_say_m47_is_pending() -> None:
    comment = _placeholder_comment()
    assert "M4.7" not in comment
    assert "until" not in comment.lower()
    assert "cannot yet" not in comment.lower()

def test_comment_names_the_fallback_cases() -> None:
    comment = _placeholder_comment()
    assert "DCF cannot value" in comment
    assert "caller passes no margin" in comment
    assert "neither rewards nor penalises" in comment
    assert "ADR 0006" in comment

def test_placeholder_value_unchanged() -> None:
    assert PLACEHOLDER_MARGIN_OF_SAFETY == 0.5
    assert "(= 0.5)" in " ".join(_RANKING.read_text(encoding="utf-8").split())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ranking_placeholder_comment.py -v`
Expected: `test_comment_does_not_say_m47_is_pending` and `test_comment_names_the_fallback_cases` FAIL; `test_placeholder_value_unchanged` PASSES (it guards against a regression, not new behaviour).

- [ ] **Step 3: Commit the failing tests** — `git commit -m "test(#105): evals"`.

- [ ] **Step 4: Replace `ranking.py:49-51` with the comment under Assumptions.** Nothing else in the file changes.

- [ ] **Step 5: Run the tests and the lint gate**

Run: `uv run pytest tests/unit/test_ranking_placeholder_comment.py -v && uv run ruff check . && uv run mypy src && uv run pytest -q`
Expected: all PASS. `uv run python docs/leccion/check.py` and `uv run python docs/pipeline/check.py` still pass if run (they cite the symbol, which is unchanged).

- [ ] **Step 6: Check the diff is docs-only**

Run: `git diff origin/master --stat -- src tests`
Expected: `src/bot/screener/ranking.py` with comment lines only, and the new test module.

- [ ] **Step 7: Commit** — `git commit -m "docs(#105): PLACEHOLDER_MARGIN_OF_SAFETY comment describes the DCF fallback"`.
