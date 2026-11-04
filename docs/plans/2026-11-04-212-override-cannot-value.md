# Analyze: a bad override file is "cannot value", not a crash — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The analyze model and boards say that an invalid override file ends its ticker as `cannot value` (exit code 1, the batch goes on), with every cause listed on `analyze.d2`, and tests keep it that way.

**Architecture:** Most of the issue already landed with #199 (PR #209): the model has no `crashed` phase, `TheOverrideFileIsInvalid` goes to `cannot_value`, `analyze-story.d2` has no `crashed` node, and the inputs and dcf boards draw the step. What is left is the `override` decision on `analyze.d2`, which says "non-number" where the code accepts a finite number or, for `revenue_growth` / `operating_margin`, a non-empty list of them; plus two regression pins. SVGs and `rendered.sha256` come from the `pipeline-render` artifact of the `pipeline-diagram` workflow (local d2 install is not permitted in this run).

**Tech Stack:** d2 v0.9.0 (TALA), pytest, `docs/pipeline/check.py`, TLC in the `models` CI job.

**Spec:** issue #212 (with its Agent Brief comment); conventions in `docs/pipeline/README.md` and `docs/pipeline/models/README.md`.

## Global Constraints

- No change under `src/` (issue: "Any change to `src/`" is out of scope; models README: "Model work never changes the pipeline code").
- #184 (unreadable override file, `OSError`) and #185 (render errors escaping the batch) are not modelled here.
- Never edit an SVG or `rendered.sha256` by hand.
- Keep every phrase already pinned by `_ANALYZE_TEXT["override"]` (`--override`, `exactly one ticker`, `config/assumptions/TICKER.yaml`, `before the signals`).
- Digits on board labels need a `@const`/`@param` citation; the new wording carries none.

## Decisions taken here

1. **Acceptance criterion 1 already holds** (`grep -ri crash docs/pipeline/models docs/pipeline/analyze*.d2` is empty on `master`). It becomes a test so it stays true.
2. **Acceptance criterion 4 already holds**: `tests/unit/test_cli_analyze.py::test_analyze_malformed_override_fails_its_ticker_and_continues_batch[not-yaml]` runs `bot analyze AAPL MSFT` with an invalid YAML `AAPL.yaml`, asserts exit code 1, `AAPL: cannot value`, `MSFT.md` written. No new CLI test.
3. **The model is not touched.** Its step label already lists the causes and matches the inputs and dcf boards (`test_step_labels_are_drawn`). TLC runs in CI on the unchanged model; `TLA_SHA256` is the hash of `tla2tools.jar` at `TLA_VERSION` (models README, "Files"), which does not change, so it stays as is.
4. **Only `analyze.d2` changes wording.** The list nuance goes on the stage board's `override` decision, which the issue names; the sub-board edge labels stay equal to the model's step label.

## Review Focus

1. The `override` label must still render: d2 double-quoted labels with `/` and `_` are fine, but a stray `"` breaks the board — `check.py` parses it.
2. `revenue_growth` / `operating_margin` are the only list keys (`_OVERRIDE_PATH_KEYS` in `src/bot/valuator/assumptions.py`); the label must not suggest other keys take lists.
3. A rendered SVG out of date with the source fails CI's "committed render is current" step: commit SVGs and hash together.

---

### Task 1: Pin the override causes and the absence of a crash, then fix `analyze.d2`

**Files:**
- Modify: `tests/unit/test_pipeline_diagram.py` (`_ANALYZE_TEXT["override"]`)
- Modify: `tests/unit/test_pipeline_models.py` (new test)
- Modify: `docs/pipeline/analyze.d2:24` (the `override` node label)

**Interfaces:**
- Consumes: `_ANALYZE_TEXT` / `test_analyze_text` (normalised substring match on the node block); `_MODELS` path in `test_pipeline_models.py`.
- Produces: nothing for later tasks besides the edited `analyze.d2`.

- [ ] **Step 1: Write the failing tests**

Append to `_ANALYZE_TEXT["override"]`:
`"not valid YAML", "not a mapping", "an unknown key", "a value that is not a finite number", "a non-empty list of them for revenue_growth / operating_margin", "an inconsistent story file", "cannot value, exit code 1"`. Each phrase sits inside one line of the new label: `test_analyze_text` matches the raw d2 source after `check.normalize`, which collapses whitespace but not the literal `\n`.

Also in `tests/unit/test_pipeline_diagram.py`, so a new list key cannot drift silently:

```python
def test_analyze_override_names_every_list_key() -> None:
    """The override decision names exactly the keys that take a per-year list (#212)."""
    from bot.valuator.assumptions import _OVERRIDE_PATH_KEYS

    line = next(l for l in _analyze_block("override").split("\\n") if "non-empty list" in l)
    assert set(re.findall(r"[a-z]+_[a-z_]+", line)) == set(_OVERRIDE_PATH_KEYS)
```

In `tests/unit/test_pipeline_models.py`:

```python
def test_analyze_model_and_boards_name_no_crash() -> None:
    """A bad override file is cannot value, not a crash (#180, #212)."""
    paths = [*_MODELS.glob("analyze.*"), *_MODELS.parent.glob("analyze*.d2")]
    assert paths
    hits = [p.name for p in paths if "crash" in p.read_text().lower()]
    assert hits == []
```

- [ ] **Step 2: Run them**

Run: `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "analyze_text and override" tests/unit/test_pipeline_models.py -k "no_crash or analyze_text"`
Expected: `test_analyze_text[override]` and `test_analyze_override_names_every_list_key` FAIL; `test_analyze_model_and_boards_name_no_crash` PASSES (pin of a fact already true).

- [ ] **Step 3: Rewrite the last line of the `override` label in `docs/pipeline/analyze.d2`**

Replace `any invalid file (not YAML, not a mapping, unknown key, non-number, inconsistent story file): cannot value, exit code 1` with
`any invalid file: cannot value, exit code 1, and the batch goes on\nnot valid YAML, not a mapping, an unknown key,\na value that is not a finite number (or a non-empty list of them for revenue_growth / operating_margin),\nor an inconsistent story file`.

- [ ] **Step 4: Run the tests and the board check**

Run: `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_subboards.py` — expected PASS except SVG/hash freshness checks, which Task 2 settles.
Run: `python3 docs/pipeline/check.py` — expected: only a `rendered.sha256` mismatch.

- [ ] **Step 5: Commit** `docs(#212): analyze board lists every invalid override cause`

### Task 2: Render

**Files:**
- Modify: `docs/pipeline/*.svg` (at least `analyze.svg`), `docs/pipeline/rendered.sha256`

- [ ] **Step 1:** push the branch; wait for the `pipeline-diagram` run of that commit (`render` job uploads `pipeline-render` even when its freshness step fails); `gh run download <id> -n pipeline-render -D <dir>`; copy only `*.svg` and `rendered.sha256` into `docs/pipeline/`. One render path only, so the committed SVGs are the CI's own bytes.
- [ ] **Step 2:** `python3 docs/pipeline/check.py` passes; `uv run pytest -q` passes.
- [ ] **Step 3: Commit** `docs(#212): render analyze board`

## Assumptions

1. **The model's step label keeps "a value that is not a finite number" without the list nuance** (rejected: adding the nuance to `analyze.view.js` and the inputs/dcf edges). An empty list or a list for a scalar key is still "a value that is not a finite number" for the ticker; the stage board carries the detail the issue asks for, and the sub-board edges stay equal to the model's label (`tests/unit/test_pipeline_models.py:547` `test_step_labels_are_drawn`).
2. **No new CLI test per cause** (rejected: one CLI parameter per cause). Every cause raises `ValueError` from `load_override` (`src/bot/valuator/assumptions.py:718-746`) and one handler turns it into `cannot value` (`src/bot/cli.py:486-488`). The CLI test already runs five causes (`tests/unit/test_cli_analyze.py:416-424`: not YAML, empty value, list for a number, NaN, non-string key); not a mapping, unknown key and the story file are covered at `load_override` (`tests/unit/test_valuator_assumptions.py:762`, `:946`).
3. **Render from CI only** (rejected: local d2). Local install was refused by this run's permissions; CI's `render` job is the reference anyway (`docs/pipeline/README.md` "Rendering happens in the `pipeline-diagram` workflow").
4. **Task 1 commits with `rendered.sha256` stale** (rejected: one commit). No pre-commit hook exists; CI's render job is what produces the fix, and Task 2 follows on the same branch before the PR.

## Grilling

- Rounds: 1 (plan changes were local: one test added, one render path removed; no second round).
- Questions: 17. Sources: ISSUE 3, CODE 11, DOC 3, NO SOURCE 4 (all technical assumptions, above).
- Spec ambiguities: none. Out-of-scope follow-ups: none (#184 and #185 already exist).
