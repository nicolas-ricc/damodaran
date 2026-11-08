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
- **Comment extraction.** The test reads `ranking.py` as text (repo precedent for source-as-text tests: `tests/unit/test_mos_thresholds.py:13`, `tests/unit/test_revenue_cagr_single_source.py`), asserts exactly one line starts at column 0 with `PLACEHOLDER_MARGIN_OF_SAFETY = `, and collects the contiguous column-0 `#:` lines directly above it. It asserts at least one was found, strips the `#:` prefix and joins them with whitespace collapsed. Assertions run on that string, so line wrapping does not matter. The path is anchored on the test file (`Path(__file__).resolve().parents[2]`), as in `test_mos_thresholds.py:13` and the #291 fixture-path fix.
- **Pinned phrases are the composed text.** The tests assert the exact phrases of the comment above ("DCF cannot value", "caller passes no margin", "neither rewards nor penalises", "ADR 0006"). A later rewording has to update the test too. That is the same trade-off #78 made (`test_readme_dev_docs.py` pins "not enforced", "whole tree"). The new text contains no `until` substring.
- **"Default when a caller passes no margin" is literal.** `Candidate.margin_of_safety: float = PLACEHOLDER_MARGIN_OF_SAFETY` (`ranking.py:124`) is a dataclass field default. `run_screen(valuator=None)` maps every shortlisted ticker to `None`, and then to the placeholder (`engine.py:969-974`).
- **"Stays in the shortlist" is sourced.** `engine.py:971-974` replaces a `None` margin with the placeholder, and `rescore_with_margins` (`ranking.py:219-240`) filters nothing. `_dcf_margin_of_safety`'s docstring (`engine.py:93-98`) says the fallback applies "rather than dropping the candidate from the shortlist".
- **Gates.** CI (`.github/workflows/site.yml:34,88-90`) runs `docs/pipeline/check.py`, `ruff check .`, `mypy src`, `pytest -q`. `docs/leccion/check.py` runs inside the suite via `tests/unit/test_leccion.py`. `E501` is ignored (`pyproject.toml:60`). Line length is 100.
- **Red evals commit.** Committing the failing tests first follows repo precedent (`6c2dc27 test(#92): evals`) and the pipeline running this issue. The branch is red only between Step 3 and Step 7, and it is never merged in that state.
- **Plan location `docs/plans/`.** Recent issue plans live there (`docs/plans/2026-11-08-78-readme-ruff-format.md`, `2026-11-08-293-source-cosmetics.md`).

## Review Focus

1. The comment block detached from the constant (blank line inserted, or `#` instead of `#:`) so Sphinx and readers lose it: the helper requires contiguous `#:` lines directly above the assignment and asserts it found some. Pinned in Task 1 (`_placeholder_comment`).
2. The value silently changed while rewording: pinned by `test_placeholder_value_unchanged` (`== 0.5`, and the module docstring itself, read through `ranking.__doc__`, still says `(= 0.5)`).
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

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_ranking_placeholder_comment.py`, module docstring `"""The PLACEHOLDER_MARGIN_OF_SAFETY comment describes the DCF fallback (#105)."""`, `_RANKING = Path(__file__).resolve().parents[2] / "src" / "bot" / "screener" / "ranking.py"`, imports `from bot.screener import ranking` and `from bot.screener.ranking import PLACEHOLDER_MARGIN_OF_SAFETY`, and a typed helper `_placeholder_comment() -> str` as described under Assumptions (asserts exactly one assignment line and a non-empty comment).

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
    assert ranking.__doc__ is not None
    assert "(= 0.5)" in " ".join(ranking.__doc__.split())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ranking_placeholder_comment.py -v`
Expected: `test_comment_does_not_say_m47_is_pending` and `test_comment_names_the_fallback_cases` FAIL; `test_placeholder_value_unchanged` PASSES (it guards against a regression, not new behaviour).

- [ ] **Step 3: Commit the failing tests** — `git commit -m "test(#105): evals"`.

- [ ] **Step 4: Replace `ranking.py:49-51` with the comment under Assumptions.** Nothing else in the file changes.

- [ ] **Step 5: Run the tests and the lint gate**

Run: `uv run pytest tests/unit/test_ranking_placeholder_comment.py -v && uv run ruff check . && uv run mypy src && uv run pytest -q`
Expected: all PASS. Then `python3 docs/pipeline/check.py` (CI step, `site.yml:34`) passes; the symbol it cites is unchanged.

- [ ] **Step 6: Check the diff is docs-only**

Run: `git diff origin/master --stat`
Expected: exactly three files. This plan, `src/bot/screener/ranking.py` (comment lines only, checked with `git diff origin/master -- src`), and the new test module.

- [ ] **Step 7: Commit** — `git commit -m "docs(#105): PLACEHOLDER_MARGIN_OF_SAFETY comment describes the DCF fallback"`.

## Grilling

- Rounds: 1. The plan was revised without adding or removing a step or changing the seam, so there was no second round. Griller model: fable. A first dispatch received an empty plan because of a prompt templating error on my side and was discarded.
- Questions: 17.
- Sources: CODE 11 (Q2, Q3, Q5, Q8, Q9, Q10, Q14, Q15, Q16, Q17, Q11 via `.github/workflows/site.yml`), ISSUE 1 (Q4, from the brief's desired behaviour: "neither rewarding nor penalising", "a caller passes no margin", "per ADR 0006"), NO SOURCE 5.
- Technical assumptions, decided and declared above:
  - The new test module is allowed under "No test changes" (Q1).
  - The tests pin the exact composed phrases (Q4).
  - The comment is extracted from column-0 lines, and the helper asserts exactly one assignment and at least one comment line (Q5, Q6).
  - No `until` substring appears in the new text (Q7).
  - The red evals commit follows repo precedent (Q12).
  - The diff check covers the whole tree (Q13).
- Spec ambiguities: none.
- Out of scope: `ranking.py:169`, in the `rank()` docstring, still says "(placeholder 0.5 until M4.7)". Found while answering Q15. Opened as #299.
- Plan revisions:
  - The value test reads `ranking.__doc__` instead of the whole file (Q9).
  - The helper's preconditions are spelled out (Q5, Q6).
  - The diff check runs over the whole tree (Q13).
  - The CI gates are named (Q11).
  - The "default" and "stays in the shortlist" claims are sourced (Q2, Q3, Q8, Q14).

Result: `ok`.
