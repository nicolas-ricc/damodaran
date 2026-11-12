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

## Acceptance criteria

These come from the triage Agent Brief.

| Criterion | Pinned by |
|---|---|
| The `rank()` docstring no longer mentions "until M4.7" or presents the placeholder as the current behaviour. | `test_rank_docstring_does_not_say_m47_is_pending` |
| It states that the neutral `PLACEHOLDER_MARGIN_OF_SAFETY` applies only when no DCF value is available. | `test_rank_docstring_names_the_dcf_fallback` |
| No code change; `uv run pytest -q` and `uv run ruff check . && uv run mypy src` still pass. | Step 5. `test_rank_docstring_keeps_the_unbounded_ratio` and the untouched `tests/unit/test_screener_ranking.py` guard the rest of the docstring and the behaviour. |

## Exact copy

The current first paragraph of the `rank()` docstring (`src/bot/screener/ranking.py:170-175`):

```
    Value/quality/growth sub-scores are percentiles within ``candidates`` (the
    filtered universe), each in ``[0, 1]``; the margin-of-safety component is the
    candidate's raw, absolute and unbounded ``intrinsic_value / price`` ratio
    (placeholder 0.5 until M4.7). The weighted blend is multiplied by 100: the
    three percentile terms alone stay within 100, but a margin-of-safety ratio
    above 1.0 can lift the final score past 100, so there is no strict ceiling.
```

The parenthetical at `src/bot/screener/ranking.py:173` changes:

| Before | After |
|---|---|
| `(placeholder 0.5 until M4.7)` | `(the neutral :data:`PLACEHOLDER_MARGIN_OF_SAFETY` when no DCF value is available)` |

This is the issue body's suggestion, verbatim: "replace the parenthetical with wording that matches the module docstring, for example "(the neutral :data:`PLACEHOLDER_MARGIN_OF_SAFETY` when no DCF value is available)"". The module docstring (`ranking.py:29-31`) uses the same noun: "the neutral placeholder :data:`PLACEHOLDER_MARGIN_OF_SAFETY` (= 0.5) only when no DCF value is available". The paragraph is rewrapped to the docstring's existing width. Every other sentence of the docstring stays word for word the same.

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
  - `test_rank_docstring_does_not_say_m47_is_pending`: `"M4.7" not in doc`, `"placeholder 0.5" not in doc`. (The stage 6 review dropped a `\buntil\b` ban: it barred an ordinary word from the whole docstring, and `"M4.7"` already covers "until M4.7".).
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

## Assumptions

- **Seam: `rank.__doc__`, not the source text.** `test_ranking_placeholder_comment.py` reads the source file only because a `#:` comment is not in any `__doc__`. For docstrings it already uses `ranking.__doc__` (`test_placeholder_value_unchanged`). The rejected alternative was `inspect.getsource`, which would also match code and comments.
- **No line break inside a backtick role.** The repository builds no Sphinx docs (`pyproject.toml` has no Sphinx dependency), but a role split across lines is still invalid reStructuredText. The rewrap keeps ``:data:`PLACEHOLDER_MARGIN_OF_SAFETY` `` on one line. Ruff's `E501` (selected through `"E"`, `line-length = 100`, `pyproject.toml:57,61`) checks docstring lines too. `W505` is not configured.
- **"until" appears once.** The only match in the current `rank()` docstring is the stale parenthetical (checked by running the regex on `rank.__doc__`), so the regex cannot trip on other prose. The function has no Args/Returns sections.
- **The M4.7 grep is done.** `grep -rn "M4.7" src` finds `ranking.py:28` (the module docstring, which says M4.7 *has* run), `ranking.py:173` (this edit), and `engine.py:85,92,823`. The engine lines describe the wired seam in the present tense and are out of scope ("Other docstrings or comments", Agent Brief).
- **Fix forward.** If Step 5 fails, the implementer fixes the cause and does not loosen a test or reset the branch. This plan was committed on its own in the `plan(#299)` commit, so it is not part of the Step 6 commit.
- **Skill files.** If the `.agents/skills/` files are missing, the steps still run in the order written: test first, then the edit.

## Grilling

- **Rounds:** 1. The plan gained an acceptance-criteria table, the current text and the Assumptions above. No task or step was added or removed, so no second round ran.
- **Griller:** fable. It asked 15 questions.
- **Sources:** 3 ISSUE (Q1, Q2, Q11), 8 CODE (Q3, Q4, Q5, Q6, Q8, Q9, Q10, Q13), 1 DOC (Q15: CONTEXT.md "Commits: Conventional Commits", plus `git log` with `fix(#125)` and `docs(#286)`), and 3 NO SOURCE (Q7, Q12, Q14). All three unsourced questions became technical assumptions.
- **Plan errors corrected:** none. The plan only gained written backing.
- **Follow-up issues opened:** none. **Spec ambiguities:** none.
