# Analyze: a bad override file is "cannot value", not a crash — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The analyze model and boards say that an invalid override file ends its ticker as `cannot value` (exit code 1, the batch goes on), with every cause listed on `analyze.d2`, and tests keep it that way.

**Architecture:** Most of the issue already landed with #199 (PR #209): the model has no `crashed` phase, `TheOverrideFileIsInvalid` goes to `cannot_value`, `analyze-story.d2` has no `crashed` node, and the inputs and dcf boards draw the step. What is left is the `override` decision on `analyze.d2`, which says "non-number" where the code accepts a finite number or, for `revenue_growth` / `operating_margin`, a non-empty list of them; plus two regression pins. SVGs and `rendered.sha256` come from `docs/pipeline/build.sh` (local d2 v0.9.0) or the `pipeline-render` artifact.

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
`"not valid YAML", "not a mapping", "an unknown key", "a value that is not a finite number", "a non-empty list of them for revenue_growth / operating_margin", "an inconsistent story file", "cannot value, exit code 1"`.

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
Expected: `test_analyze_text[override]` FAILS (missing phrases); `test_analyze_model_and_boards_name_no_crash` PASSES (pin of a fact already true).

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

- [ ] **Step 1:** `docs/pipeline/build.sh` with d2 v0.9.0 on `PATH` (installed with `curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0 --method standalone --prefix ~/.local`); else push and take `pipeline-render` from the `pipeline-diagram` run (`gh run download <id> -n pipeline-render -D <dir>`), copying only `*.svg` and `rendered.sha256`.
- [ ] **Step 2:** `python3 docs/pipeline/check.py` passes; `uv run pytest -q` passes.
- [ ] **Step 3: Commit** `docs(#212): render analyze board`
