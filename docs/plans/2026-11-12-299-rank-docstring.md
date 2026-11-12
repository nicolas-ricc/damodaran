# The rank() docstring names the DCF fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `rank()` docstring in `src/bot/screener/ranking.py` no longer says the margin of safety is a placeholder "until M4.7". It says the neutral `PLACEHOLDER_MARGIN_OF_SAFETY` applies only when no DCF value is available, which matches the module docstring.

**Architecture:** A docstring-only edit to `bot.screener.ranking.rank`, pinned by one new test module that reads `rank.__doc__`. It follows the pattern of `tests/unit/test_ranking_placeholder_comment.py` (#105). No code changes.

**Tech Stack:** Python 3.12, pytest.

**Spec:** GitHub issue #299 (nicolas-ricc/damodaran), "rank() docstring still says the margin of safety is a placeholder until M4.7", the triage Agent Brief comment in particular.

## Global Constraints

- Documentation only, with no change in behaviour (issue body: "This is documentation only, with no change in behaviour").
- Out of scope: any behaviour change to ranking or to `run_screen`, and every other docstring or comment. The `#:` comment on the constant was handled in #105.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Ruff's line length applies to the rewrapped docstring.
- Commits use Conventional Commits with the `(#299)` scope.

## Exact copy

The parenthetical at `src/bot/screener/ranking.py:173` changes:

| Before | After |
|---|---|
| `(placeholder 0.5 until M4.7)` | `(the neutral :data:`PLACEHOLDER_MARGIN_OF_SAFETY` when no DCF value is available)` |

This is the wording the issue suggests. The paragraph is rewrapped to the docstring's existing width. Every other sentence of the docstring stays word for word the same.

## Review Focus

- **The two other sentences that carry meaning.** These are "raw, absolute and unbounded" and "there is no strict ceiling". Rewrapping must not drop or reword them. Pinned by `test_rank_docstring_keeps_the_unbounded_ratio`.
- **The value 0.5 left in prose.** The docstring names the constant, not its value, so the two cannot drift apart. The module docstring keeps `(= 0.5)`, and `test_ranking_placeholder_comment.py::test_placeholder_value_unchanged` already pins that. Pinned by `test_rank_docstring_does_not_say_m47_is_pending` (no `placeholder 0.5`).
- **Behaviour.** No behaviour changes. The existing `tests/unit/test_screener_ranking.py` stays green without edits.

---

### Task 1: The rank() docstring names the DCF fallback

**Files:**
- Create: `tests/unit/test_rank_docstring.py`
- Modify: `src/bot/screener/ranking.py:170-176` (the first paragraph of the `rank()` docstring)

**Interfaces:**
- Consumes: `bot.screener.ranking.rank` (already exists).
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_rank_docstring.py`. Module docstring: `"""The rank() docstring describes the DCF fallback, not a pending M4.7 (#299)."""`. Add a helper `_doc() -> str` that returns `rank.__doc__` with whitespace collapsed (`" ".join(doc.split())`), after it asserts `rank.__doc__ is not None`.
  - `test_rank_docstring_does_not_say_m47_is_pending`: `"M4.7" not in doc`, `re.search(r"\buntil\b", doc, re.IGNORECASE) is None`, `"placeholder 0.5" not in doc`.
  - `test_rank_docstring_names_the_dcf_fallback`: `"the neutral :data:`PLACEHOLDER_MARGIN_OF_SAFETY` when no DCF value is available" in doc`.
  - `test_rank_docstring_keeps_the_unbounded_ratio`: `"raw, absolute and unbounded ``intrinsic_value / price`` ratio" in doc` and `"there is no strict ceiling" in doc`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_rank_docstring.py -q`
Expected: the first two tests FAIL, and `test_rank_docstring_keeps_the_unbounded_ratio` passes.

- [ ] **Step 3: Apply the edit in "Exact copy"** and rewrap the paragraph to the docstring's existing width.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_rank_docstring.py tests/unit/test_ranking_placeholder_comment.py tests/unit/test_screener_ranking.py -q`
Expected: all tests PASS.

- [ ] **Step 5: Full suite and lint**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: everything green.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_rank_docstring.py src/bot/screener/ranking.py
git commit -m "docs(#299): rank() docstring names the DCF fallback"
```
