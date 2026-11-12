# Every assumption source has a worded glossary term Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `source_term(s.value)` returns a worded label and a non-empty description for every member `s` of `AssumptionSource`, and `SOURCES` holds no key outside those values.

**Architecture:** Data-only change to the `SOURCES` table in `src/bot/web/glossary.py`: five terms are added, and the never-emitted `override` key becomes `manual`. The glossary tests in `tests/unit/test_web_glossary.py` iterate `AssumptionSource` instead of a literal tuple, so a source added to the enum without a term fails the suite. `source_term`, `_fallback` and the other tables do not change.

**Tech Stack:** Python 3.12, pytest, mypy `--strict`, ruff.

**Spec:** GitHub issue #315 (nicolas-ricc/damodaran), "Viewer glossary has no worded term for most assumption sources", in particular the triage Agent Brief comment.

## Global Constraints

- `AssumptionSource` (StrEnum, `src/bot/valuator/assumptions.py:107`) is the only source of truth for source keys. It has nine values: `manual`, `sector_default_damodaran`, `sector_default_damodaran_cross_region`, `country_default_damodaran`, `rule_based`, `historical_average`, `story_pattern`, `story`, `unresolved`.
- Each term must pass the existing `_is_worded` check: a non-empty label with no `snake_case` word, and a description that ends with `.` and is longer than 20 characters. It must also pass `test_glossary_has_no_leftover_identifier`, so neither the label nor the description may contain a `[a-z]+_[a-z_]+` word.
- The cross-region term says the sector median came from a different Damodaran region than the company's own. The `unresolved` term says no value was produced.
- Out of scope: which sources the valuator emits, how `_fallback` handles unknown names (`test_unknown_names_fall_back_to_words_without_a_description` stays as it is), and the `INPUTS` and `FLAGS` tables.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits use Conventional Commits with the `(#315)` scope.

## Exact copy

Labels stay lower case, like the existing source labels. The four existing terms (`sector_default_damodaran`, `country_default_damodaran`, `historical_average`, `rule_based`) keep their key and their text.

| Key | Label | Description |
|---|---|---|
| `manual` (replaces `override`) | `manual override` | `Written by hand in the company's assumptions file.` (unchanged text) |
| `sector_default_damodaran_cross_region` | `sector default (Damodaran, other region)` | `Damodaran's industry average for this company's sector, taken from a different region than the company's own because its own region has no data.` |
| `story_pattern` | `story pattern` | `A path the company's story type draws from its own history and its sector, such as growth fading to the terminal rate.` |
| `story` | `story file` | `Written by hand in the story section of the company's assumptions file.` |
| `unresolved` | `unresolved` | `No value was produced: no source had the data, so the model shows a gap instead of a number.` |

`SOURCES` follows the declaration order of `AssumptionSource`.

## Review Focus

- **A new `AssumptionSource` member shipped without a term.** This is the regression the issue is about. Pinned by `test_every_source_has_a_worded_term` (it iterates the enum) and by `test_sources_are_keyed_by_assumption_source` (set equality).
- **A stale key left in `SOURCES` (`override`).** Pinned by `test_sources_are_keyed_by_assumption_source`. Nothing reads `override`: `source_term` is called only from `src/bot/web/views.py:96` and `:364-366`, with the stored `source` of each assumption.
- **The detail page for a manual value.** It used to show the fallback "manual" with no tooltip. It now shows `manual override` with a description. Pinned by `test_manual_source_is_worded_as_an_override`.
- **Existing viewer tests that match on source labels.** `tests/unit/test_web_views.py:196` (`"sector default"`) and `tests/unit/test_web_site.py:629` (`sector default (Damodaran)</abbr>`) must still pass. The cross-region label starts with `sector default (Damodaran` too, which keeps it consistent for a reader. Checked by the full suite.
- **The cross-region and unresolved wording the brief pins.** Pinned by `test_cross_region_source_names_another_region` and `test_unresolved_source_says_no_value`.

---

### Task 1: Every assumption source has a worded term

**Files:**
- Modify: `src/bot/web/glossary.py:120-142` (the `SOURCES` table)
- Test: `tests/unit/test_web_glossary.py`

**Interfaces:**
- Consumes: `bot.valuator.assumptions.AssumptionSource`, plus the existing `bot.web.glossary.SOURCES`, `source_term` and `Term`.
- Produces: nothing new. `SOURCES: dict[str, Term]` keeps its type.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_web_glossary.py`. Import `AssumptionSource` from `bot.valuator.assumptions`.
  - Replace the body of `test_every_source_has_a_worded_term` with: `for source in AssumptionSource: assert source.value in glossary.SOURCES, source` and then `_is_worded(source_term(source.value))`.
  - `test_sources_are_keyed_by_assumption_source`: `assert set(glossary.SOURCES) == {s.value for s in AssumptionSource}`.
  - `test_manual_source_is_worded_as_an_override`: `assert source_term(AssumptionSource.MANUAL) == Term("manual override", "Written by hand in the company's assumptions file.")`.
  - `test_cross_region_source_names_another_region`: the description of `source_term(AssumptionSource.SECTOR_DEFAULT_DAMODARAN_CROSS_REGION)` contains `"different region"` and `"company's own"`.
  - `test_unresolved_source_says_no_value`: the description of `source_term(AssumptionSource.UNRESOLVED)` starts with `"No value was produced"`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_web_glossary.py -q`
Expected: the five tests above FAIL (missing keys, an extra `override` key, empty descriptions). The other tests in the module PASS.

- [ ] **Step 3: Implement** by editing `SOURCES` in `src/bot/web/glossary.py` to match the "Exact copy" table: rename `override` to `manual`, add the four new terms, and order the entries as the enum declares them. Do not change the comment line above `SOURCES` or the other tables.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_web_glossary.py tests/unit/test_web_views.py tests/unit/test_web_site.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint and types**

Run: `uv run ruff check . && uv run mypy src`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/bot/web/glossary.py tests/unit/test_web_glossary.py
git commit -m "feat(#315): every assumption source has a worded glossary term"
```
