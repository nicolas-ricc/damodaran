# Boards list "cannot be read" among the override refusals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The three analyze boards that list why an override file is refused also name "the file cannot be read" (#227), the text tests require it, and the SVGs plus `rendered.sha256` are re-rendered with d2 v0.9.0.

**Architecture:** Documentation only. `load_override` already raises `ValueError("override file <path> cannot be read: …")` for any `OSError` on read (`src/bot/valuator/assumptions.py`), and `_analyze_one` turns it into "cannot value, exit code 1" while the batch goes on. The `override` decision of `analyze.d2` and the `region_set -> cannot_value` edge of `analyze-dcf.d2` and `analyze-inputs.d2` gain that reason. The edge's first line is the model step label `TheOverrideFileIsInvalid` in `docs/pipeline/models/analyze.view.js` (`tests/unit/test_pipeline_models.py` requires the first line of the edge to equal it), so the label changes there too, and so does the comment above the step in `analyze.tla`, which lists the same reasons. The TLA+ logic is untouched.

**Tech Stack:** d2 v0.9.0 (TALA, pinned by `docs/pipeline/D2_VERSION`), pytest.

**Spec:** GitHub issue #309 (the Agent Brief in the triage comment).

## Global Constraints

- Exact wording on the `override` decision (`analyze.d2`): the reasons line becomes `the file cannot be read (a permission error, or a directory at that path), not valid YAML, not a mapping, an unknown key,`. The rest of the node is unchanged.
- Exact new step label (view.js `TheOverrideFileIsInvalid`, first line of both sub-board edges): `the ticker cannot be valued, exit code 1 [the override file cannot be read, is not valid YAML, not a mapping, has an unknown key or a value that is not a finite number, or its story file is inconsistent]`. The extra lines of the `analyze-inputs.d2` edge are unchanged.
- No change to `load_override` or its message, or to the TLA+ actions (out of scope in the brief).
- Render only with `docs/pipeline/build.sh` and d2 v0.9.0 (`d2 version` → `v0.9.0` on this machine). Never edit an SVG or `rendered.sha256` by hand. PNGs stay git-ignored.
- `uv run pytest -q`, `uv run ruff check . && uv run mypy src` and `python3 docs/pipeline/check.py` pass.

## Review Focus

1. A first line of a sub-board edge that drifts from the view.js label fails `test_pipeline_models` (it matches the `steps` labels). Both boards and view.js must carry the exact same string; Task 2 runs that test.
2. Re-rendering every board must change only the three SVGs whose sources changed. TALA with seed 1 is deterministic here (re-rendering the unchanged `analyze-dcf.d2` reproduced the committed SVG byte for byte), so any other SVG in the diff means a wrong d2 or wrong seed. Task 3 checks `git status`.
3. An SVG that still lacks the new text while the hash is fresh would pass `check.py`. Task 3 adds a test that reads the three SVGs for `cannot be read`.
4. `test_analyze_override_names_every_list_key` finds the one line holding `non-empty list`; the new reason goes on the existing `not valid YAML` line, not on that line.

---

### Task 1: the `override` decision on `analyze.d2`

**Files:**
- Modify: `docs/pipeline/analyze.d2:24`
- Test: `tests/unit/test_pipeline_diagram.py` (`_ANALYZE_TEXT["override"]`, ~line 1619)

**Interfaces:** none.

- [ ] **Step 1 (stage-3 eval, already committed failing):** `_ANALYZE_TEXT["override"]` gains `"the file cannot be read"`.
- [ ] **Step 2:** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "analyze_text and override"` → FAIL, missing `the file cannot be read`.
- [ ] **Step 3:** edit the `override` label per Global Constraints.
- [ ] **Step 4:** same command → PASS; `uv run pytest -q tests/unit/test_pipeline_diagram.py` all pass except `test_svgs_*` checks that depend on Task 3, if any.
- [ ] **Step 5:** commit `docs(#309): the analyze board lists an unreadable override file`.

### Task 2: the `TheOverrideFileIsInvalid` step on the sub-boards and the model view

**Files:**
- Modify: `docs/pipeline/models/analyze.view.js:77`, `docs/pipeline/models/analyze.tla` (comment above `TheOverrideFileIsInvalid`, ~line 151), `docs/pipeline/analyze-dcf.d2:51`, `docs/pipeline/analyze-inputs.d2:61`
- Test: `tests/unit/test_pipeline_subboards.py` (`_ANALYZE_TEXT["analyze-dcf"]` and `["analyze-inputs"]`, ~line 405)

**Interfaces:** the step label in Global Constraints.

- [ ] **Step 1 (stage-3 eval, already committed failing):** both `_ANALYZE_TEXT` lists gain `"the override file cannot be read"`.
- [ ] **Step 2:** `uv run pytest -q tests/unit/test_pipeline_subboards.py` → the two new phrases FAIL.
- [ ] **Step 3:** replace the label in view.js and the first line of both edges with the new label. In the `analyze.tla` comment, add "an unreadable file (OSError on read)" to the reasons `load_override` raises `ValueError` on.
- [ ] **Step 4:** `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_analyze_model_replay.py` → PASS.
- [ ] **Step 5:** commit `docs(#309): the analyze sub-boards list an unreadable override file`.

### Task 3: re-render

**Files:**
- Modify (generated): `docs/pipeline/analyze.svg`, `analyze-dcf.svg`, `analyze-inputs.svg`, `rendered.sha256`
- Test: `tests/unit/test_pipeline_diagram.py`, new `test_unreadable_override_is_rendered`

**Interfaces:** none.

- [ ] **Step 1 (stage-3 eval, already committed failing):** `test_unreadable_override_is_rendered`, parametrised over `analyze`, `analyze-dcf`, `analyze-inputs`: `"cannot be read" in html.unescape((_PIPELINE / f"{stem}.svg").read_text(encoding="utf-8"))`.
- [ ] **Step 2:** run it → FAIL for all three.
- [ ] **Step 3:** `docs/pipeline/build.sh`.
- [ ] **Step 4:** `git status --short docs/pipeline` lists only the three SVGs and `rendered.sha256` (plus the sources of Tasks 1-2 if uncommitted); `python3 docs/pipeline/check.py` exits 0; the new test passes; full suite and lint pass.
- [ ] **Step 5:** commit `docs(#309): re-render the analyze boards`.
