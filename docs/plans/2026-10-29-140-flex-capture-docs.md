# Document bot flex-capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The README's Flex section documents `bot flex-capture` as the validation step, and every "not yet verified; see #110" sentence in the repo points at #111 instead.

**Architecture:** Docs-only. The README section, the `ibkr_flex.py` module docstring, the synthetic fixture's header comment and one `.env.example` comment are rewritten; `tests/unit/test_flex_docs.py` pins the new wording and the absence of the old one. No behaviour changes.

**Tech Stack:** Markdown, Python docstrings, pytest.

**Spec:** GitHub issue #140 (nicolas-ricc/damodaran), "[M5.7b-3] Document bot flex-capture as the Flex validation step and retire the "see #110" wording"; story context in the plan comment of parent #110. Facts about the command come from `src/bot/ingest/ibkr_flex_capture.py` and `flex_capture` in `src/bot/cli.py` (shipped by #139).

## Global Constraints

- New README opening sentence, verbatim: `Written from IBKR's documentation; the parser is validated against a real statement captured with the command below. Known corrections are tracked in #111.`
- Three paths, verbatim: `tests/fixtures/cassettes/ibkr_flex/statement_real.yaml`, `tests/fixtures/ibkr_flex/statement_real_redacted.xml`, `tests/fixtures/ibkr_flex/statement_real_summary.json`.
- Fixture header sentence, verbatim: ``A redacted real sample is captured with `bot flex-capture` into statement_real_redacted.xml; parser corrections land in #111.``
- `grep -n "see #110\|not yet verified" README.md src/bot/ingest/ibkr_flex.py tests/fixtures/ibkr_flex/statement_sample.xml` prints nothing.
- Every claim about the command must match the code (checked in stage 0):
  - run from the repo root; it writes under `Path.cwd()`;
  - missing `BOT_IBKR_FLEX_TOKEN` or `BOT_IBKR_FLEX_QUERY_ID` → stderr one-liner naming both, exit 2, nothing written;
  - `FlexError` → `Flex capture failed: …`, exit 1; token found in the rendered cassette → exit 1, nothing written;
  - all three artefacts are rendered in memory before the first write; the raw statement is never written;
  - cassette: `t` query parameter → `SCRUBBED`, request headers dropped, response headers reduced to `Content-Type`, statement body redacted;
  - redacted XML: every `accountId` → `U0000000` (`acctAlias` emptied); `amount`/`proceeds`/`value`/`quantity` → fakes keeping sign, integer-ness and digit count; symbols, conids, isins, ids, dates, types, descriptions kept; byte-identical on re-run;
  - summary: distinct `CorporateAction.type` / `CashTransaction.type` values with counts, rows parsed vs skipped (skipped keyed by element and type), date window; also printed to stdout.
- Steps 1–3 of the README section and the closing event-mapping paragraph stay as they are.
- `test_no_more_nothing_populates_wording` stays unchanged.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green. Commits: Conventional Commits scoped `(#140)`.

## Review Focus

1. A claim in the new README step that the code does not back (e.g. "two requests" when the client polls `GetStatement` more than once, or "nothing written" on a path that writes). Pinned by the reviewer reading each sentence against `ibkr_flex_capture.py`; the tests can only pin strings.
2. The `ibkr_flex.py` docstring breaks "not yet verified" across a line, so a single-line grep misses it. Pinned by the Task 2 test, which normalises whitespace before asserting absence.
3. Markdown nesting: step 4's bullet list and paragraphs must indent under the numbered item like step 3's code block, or GitHub renders a broken list. Checked by reading the rendered section.

---

### Task 1: README Flex section documents bot flex-capture

**Files:**
- Modify: `README.md` (section `### Corporate actions via Flex Web Service`, around lines 174–203)
- Test: `tests/unit/test_flex_docs.py::test_readme_has_the_flex_section`

**Interfaces:**
- Consumes: the facts in Global Constraints.
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Rewrite the test** (stage 3 commits it failing)

```python
def _flex_section(readme: str) -> str:
    start = readme.index("### Corporate actions via Flex Web Service")
    return readme[start : readme.index("\n### ", start + 1)]


def test_readme_has_the_flex_section() -> None:
    section = _flex_section((ROOT / "README.md").read_text(encoding="utf-8"))
    assert (
        "Written from IBKR's documentation; the parser is validated against a real statement "
        "captured with the command below. Known corrections are tracked in #111." in section
    )
    assert "uv run bot flex-capture" in section
    for path in (
        "tests/fixtures/cassettes/ibkr_flex/statement_real.yaml",
        "tests/fixtures/ibkr_flex/statement_real_redacted.xml",
        "tests/fixtures/ibkr_flex/statement_real_summary.json",
    ):
        assert path in section
    assert "BOT_IBKR_FLEX_TOKEN" in section and "BOT_IBKR_FLEX_QUERY_ID" in section


def test_readme_drops_the_see_110_wording() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "see #110" not in readme
    assert "not yet verified" not in " ".join(readme.split())
```

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_flex_docs.py` — expected FAIL on both tests.

- [ ] **Step 3: Rewrite the README section.** Replace the opening sentence with the verbatim one. After step 3, add step 4, **Validate against the live account**: run `uv run bot flex-capture` from the repo root; one bullet per file (path + what it contains, per Global Constraints); one paragraph saying the cassette and redacted XML are safe to commit (token scrubbed, account ids and amounts redacted), the JSON summary (also printed) is what to paste into the #111 findings, the raw statement is never written; exit code 2 when the settings are missing, 1 when the Flex service fails or the token would leak, nothing written in either case. Indent it under the numbered item like step 3. Keep steps 1–3 and the event-mapping paragraph.

- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_flex_docs.py` — expected PASS.

- [ ] **Step 5: Commit** `docs(#140): document bot flex-capture as the Flex validation step`.

### Task 2: Docstring, fixture header and .env.example point at flex-capture and #111

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py:10-11` (module docstring)
- Modify: `tests/fixtures/ibkr_flex/statement_sample.xml:3-6` (header comment)
- Modify: `.env.example:21` (`BOT_IBKR_FLEX_QUERY_ID` comment)
- Test: `tests/unit/test_flex_docs.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Write the tests** (stage 3 commits them failing)

```python
@pytest.mark.parametrize(
    "path", ["src/bot/ingest/ibkr_flex.py", "tests/fixtures/ibkr_flex/statement_sample.xml"]
)
def test_flex_sources_point_at_flex_capture(path: str) -> None:
    text = " ".join((ROOT / path).read_text(encoding="utf-8").split())
    assert "not yet verified" not in text
    assert "arrives with #110" not in text
    assert "flex-capture" in text
    assert "#111" in text


def test_env_example_points_at_flex_capture() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    (line,) = [entry for entry in lines if "BOT_IBKR_FLEX_QUERY_ID" in entry]
    assert line.endswith("; validate with bot flex-capture")
```

For `ibkr_flex.py` the test reads the module docstring via the file text, which is enough: the docstring is the only place those strings appear.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_flex_docs.py` — expected FAIL.

- [ ] **Step 3: Edit the three files.**
  - Docstring: replace the "Written from IBKR's documentation against a synthetic fixture and not yet verified against a real pull (#110); parser corrections land in #111." paragraph with one saying the parser is validated against the redacted real statement captured by `bot flex-capture` (:mod:`bot.ingest.ibkr_flex_capture`), corrections tracked in #111. Wrap at the file's width.
  - Fixture header: replace the "A redacted real sample arrives with #110; parser corrections found there land in #111." sentence with the verbatim Global Constraints sentence, rewrapped to the comment's width. Leave the "SYNTHETIC statement … (issue #56). It is NOT a real pull" text and the expected-import block alone.
  - `.env.example`: append `; validate with bot flex-capture` to the `BOT_IBKR_FLEX_QUERY_ID` comment.

- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_flex_docs.py`, then the grep from Global Constraints — expected PASS and no output.

- [ ] **Step 5: Run** `uv run ruff check . && uv run mypy src && uv run pytest -q` — expected green.

- [ ] **Step 6: Commit** `docs(#140): point the Flex docstring, fixture header and .env.example at flex-capture`.
