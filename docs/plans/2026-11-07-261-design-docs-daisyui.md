# Viewer docs for the DaisyUI synthwave system — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (`.agents/skills/subagent-driven-development/SKILL.md`, per AGENTS.md) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/DESIGN.md`, a new ADR 0011 and the "Visual system" bullet of ADR 0008 describe the DaisyUI synthwave system that ships on `feature/257-viewer-daisyui-search`, with four tests in `tests/unit/test_web_docs.py` pinning it.

**Architecture:** Documentation only. No file under `src/` changes. Tests read the Markdown files from the repo root (`_ROOT` in `tests/unit/test_web_docs.py`) and assert on their text; the DESIGN.md frontmatter is parsed with `yaml.safe_load` (PyYAML is already a dependency, `pyproject.toml:18`).

**Tech Stack:** Markdown with YAML frontmatter, pytest, PyYAML.

**Spec:** issue #261 ("Decisions" 1–5 and "Acceptance criteria" are binding). Background: `docs/superpowers/specs/2026-11-07-viewer-daisyui-search-design.md` §3, §4, §5, §7, and the parent plan comment on #257.

## Global Constraints

- The 20 colour values, verbatim from `src/bot/web/static/theme.css` (identical to spec §3): base-100 `oklch(15% 0.09 281.288)`, base-200 `oklch(20% 0.09 281.288)`, base-300 `oklch(25% 0.09 281.288)`, base-content `oklch(78% 0.115 274.713)`, primary `oklch(71% 0.202 349.761)`, primary-content `oklch(28% 0.109 3.907)`, secondary `oklch(82% 0.111 230.318)`, secondary-content `oklch(29% 0.066 243.157)`, accent `oklch(75% 0.183 55.934)`, accent-content `oklch(26% 0.079 36.259)`, neutral `oklch(45% 0.24 277.023)`, neutral-content `oklch(87% 0.065 274.039)`, info `oklch(74% 0.16 232.661)`, info-content `oklch(29% 0.066 243.157)`, success `oklch(77% 0.152 181.912)`, success-content `oklch(27% 0.046 192.524)`, warning `oklch(90% 0.182 98.111)`, warning-content `oklch(42% 0.095 57.708)`, error `oklch(73.7% 0.121 32.639)`, error-content `oklch(23.501% 0.096 290.329)`.
- DESIGN.md never contains `Rim`, `Night Ledger`, `ember`, `paper-well`, `kraft`.
- ADR 0008 supersession sentence, verbatim, first sentence of the "Visual system" bullet: `Superseded by ADR 0011 (2026-11-07): the viewer is styled with precompiled DaisyUI under the synthwave theme.`
- ADR 0011 Status line, verbatim: `Accepted (2026-11-07). Implemented (2026-11-07, issue #257).`
- ADR format as `docs/adr/0009-*.md`: `# 00NN — <title>`, `## Status`, `## Context`, `## Decision`, `## Consequences`.
- Not changed: `CONTEXT.md`, `README.md`, `.impeccable/`, `docs/plano`, `docs/leccion`, anything under `src/`.
- Commits: Conventional Commits with the `(#261)` scope. `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## ADR number: 0011 (settled on the issue)

`origin/master` already has `docs/adr/0010-flex-web-service-as-the-only-ibkr-source.md` (merged in #264 after the feature branch was cut). The human answered on #261 (nicolas-ricc, 2026-11-08): "**A**: renumber to 0011. The new ADR is `docs/adr/0011-viewer-styled-with-precompiled-daisyui.md`, the ADR 0008 sentence reads \"Superseded by ADR 0011 (2026-11-07): …\", and the tests become `test_adr_0011_*`, globbing `0011-*.md`. Leave the Flex ADR as 0010." Every 0010 the issue body names for the DaisyUI ADR reads 0011 in this plan. On the feature branch 0010 is a gap until the story merges master; that is expected.

## Review Focus

1. **Frontmatter that does not parse** (an unquoted `%` or `:` in a YAML value). Pinned by `test_design_md_frontmatter_parses`.
2. **A dropped or mistyped colour value.** Pinned by `test_design_md_describes_the_daisyui_system`, which iterates the 20 values listed in the test itself.
3. **DESIGN.md §5 naming a class that no template emits.** Not a pytest (the issue asks for a grep, listed in the PR). Task 1 Step 5 runs it.
4. **An old Rim word left in the rewrite** (`ember`, `Night Ledger`, `Rim`). Pinned by the same test; matching is case-sensitive on `Rim` as written so `trim`/`primary` do not trip it (`"Rim"` capitalised).
5. **ADR 0008 losing `Implemented`.** Pinned by the existing `test_adr_0008_is_implemented`.

---

### Task 1: DESIGN.md rewritten for DaisyUI

**Files:**
- Modify: `docs/DESIGN.md` (full rewrite)
- Test: `tests/unit/test_web_docs.py`

**Interfaces:** Produces the `_synthwave_colours() -> dict[str, str]` helper in the test module (role → value, parsed from the `--color-*` declarations of `src/bot/web/static/theme.css`; asserts there are 20), reused by no other task.

- [ ] **Step 1: Write the failing tests**

```python
def _design_frontmatter() -> dict[str, object]:
    text = (_ROOT / "docs" / "DESIGN.md").read_text()
    _, front, _ = text.split("---\n", 2)
    return yaml.safe_load(front)

def _synthwave_colours() -> dict[str, str]:
    css = (_ROOT / "src" / "bot" / "web" / "static" / "theme.css").read_text()
    colours = dict(re.findall(r"--color-([a-z0-9-]+):\s*([^;]+);", css))
    assert len(colours) == 20
    return colours

def test_design_md_frontmatter_parses() -> None:
    colors = _design_frontmatter()["colors"]
    assert isinstance(colors, dict) and len(colors) == 20

def test_design_md_describes_the_daisyui_system() -> None:
    text = (_ROOT / "docs" / "DESIGN.md").read_text()
    assert "synthwave" in text and "DaisyUI" in text and "primary" in text
    for value in _synthwave_colours().values():
        assert value in text
    for word in ("Rim", "Night Ledger", "ember"):
        assert word not in text
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_docs.py -q` — both FAIL (current DESIGN.md has 15 Rim colours and `Night Ledger`).
- [ ] **Step 3: Rewrite `docs/DESIGN.md`** per issue decision 1. Frontmatter: `name: Analysis viewer`; `description` naming DaisyUI and the synthwave theme; `colors:` the 20 roles with quoted values; `typography:` and `spacing:` copied unchanged from today's file; `rounded: none: "0"`; `components:` keys `filter`, `count`, `search`, `table-row`, `flags`, `empty-state`, `facts`, `history`, each a `classes:` string of the DaisyUI classes that ship. Body sections 1–6 as the decision lists. Section 5 names only classes found in `src/bot/web/templates/*.html` or `src/bot/web/svg.py` (the flag tone is written as `badge-{tone}` with the four tones from `FlagView.tone`, `src/bot/web/views.py:148-150`).
- [ ] **Step 4: Run** the tests — PASS.
- [ ] **Step 5: Grep every class of §5** against `src/bot/web/templates/` and `src/bot/web/svg.py`; record the commands and results for the PR.
- [ ] **Step 6: Commit** `docs(#261): DESIGN.md describes the DaisyUI synthwave system`.

### Task 2: ADR 0011 and the ADR 0008 supersession note

**Files:**
- Create: `docs/adr/0011-viewer-styled-with-precompiled-daisyui.md`
- Modify: `docs/adr/0008-read-only-web-viewer.md` (the "Visual system" bullet under Consequences)
- Test: `tests/unit/test_web_docs.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_adr_0011_is_accepted_and_implemented() -> None:
    adrs = list((_ROOT / "docs" / "adr").glob("0011-*.md"))
    assert len(adrs) == 1
    text = adrs[0].read_text()
    for needle in ("Accepted", "Implemented", "vendor_daisyui.sh", "theme.css"):
        assert needle in text

def test_adr_0008_notes_the_supersession() -> None:
    adrs = list((_ROOT / "docs" / "adr").glob("0008-*.md"))
    assert "ADR 0011" in adrs[0].read_text()
```

- [ ] **Step 2: Run** — both FAIL.
- [ ] **Step 3: Write ADR 0011** per issue decision 2: Status line verbatim; Context; Decision; "Alternatives considered" with one paragraph each for the Tailwind standalone CLI, the Node toolchain and the CDN; Consequences (≈1.1 MB uncompressed — `daisyui.css` is 1,142,434 bytes; theme edits go to `theme.css`; upgrade = the two pins in `scripts/vendor_daisyui.sh` + the `VERSIONS` line + run the script; `.impeccable/design.json` still describes the previous system).
- [ ] **Step 4: Prepend the supersession sentence** to the ADR 0008 "Visual system" bullet; keep the rest as history.
- [ ] **Step 5: Run** the tests and the full suite + lint — PASS.
- [ ] **Step 6: Commit** `docs(#261): ADR 0011 for precompiled DaisyUI, ADR 0008 notes the supersession`.

## Grilling

Round 1 of 2 ran: griller `fable`, 15 questions. Status after round 1: **blocked** on Q1 (spec ambiguity). Status after the human answer (2026-11-08): **ok**. No second round: the answer renames a number and changes no step, task or seam.

Sources: 9 CODE/DOC, 3 ISSUE, 3 NO SOURCE (2 technical assumptions, 1 spec ambiguity).

1. **Spec ambiguity (blocks).** CODE: `origin/master:tests/unit/test_flex_docs.py:92-93` has `(path,) = (ROOT / "docs/adr").glob("0010-*.md")`. DOC: `origin/master:docs/adr/0004-tws-api-via-ib-async.md:5` says "Superseded by ADR 0010", and `CONTEXT.md:74` and `README.md:156` also cite ADR 0010 for Flex. ISSUE #261 decisions 2, 3 and 5 require a new `0010-*.md`, the sentence "Superseded by ADR 0010", and a test that asserts exactly one `0010-*.md`. Either choice changes the shipped docs and tests, so it was asked on the issue. **Resolved** — ISSUE (nicolas-ricc, 2026-11-08): "**A**: renumber to 0011." The plan now uses 0011 throughout.
2. Follows from Q1. Once the number is unique, the glob has one match.
3. **Technical assumption.** The docs avoid the words "November", "December", "member" and "remember", because `ember` is a plain substring check (ISSUE decision 5 words it that way). Task 1 Step 4 also greps for `paper-well` and `kraft` (ISSUE decision 1).
4. CODE: `src/bot/web/static/theme.css:4-23` holds the values; the plan list was diffed against it. **Technical assumption:** the test reads the expected values from `theme.css` instead of a literal list, so a theme change makes the docs test fail. (Rejected alternative: a hard-coded list.)
5. CODE: `views.py:148-150` (tone values) and `templates/_rows.html` + `detail.html` (`badge-{{ f.tone }}`). §5 writes `badge-{tone}` and names the four tones. The grep looks for the template literal.
6. CODE: `docs/DESIGN.md:1` is `---`. ISSUE decision 1: "`rounded: none: \"0\"`", which is the nested mapping already in the file.
7. DOC: `docs/adr/0009-*.md` Status "Implemented (2026-11-02, issue #192)". ISSUE decision 2 fixes the Status line verbatim. `test_adr_0008_is_implemented` asserts that `Implemented` appears in the file.
8. ISSUE decision 2 requires "Alternatives considered and rejected, one paragraph each". It goes in as an `##` section between Decision and Consequences.
9. ISSUE decision 3: the sentence goes first in the bullet. The `## Status` line of ADR 0008 is unchanged.
10. ISSUE decision 1 lists "(filter, count, search, table row, flags, empty state, facts, history)".
11. ISSUE decision 1: "`typography:` unchanged from today", "`spacing:` unchanged".
12. CODE: `src/bot/web/static/VERSIONS`. The size was measured with `wc -c` on 876ef89. ISSUE decision 2 says "about 1.1 MB", so the ADR says "about 1.1 MB" and leaves the exact byte count out.
13. ISSUE decisions 2 and 4.
14. CODE: `pyproject.toml:18` lists `pyyaml` under the runtime `dependencies`. The test module adds `import yaml`.
15. Both tasks ship in one PR into `feature/257-viewer-daisyui-search`. The intermediate state never reaches master.

### Assumptions

- The colour test reads the 20 expected values from `theme.css` (Q4); rejected: a hard-coded list in the test.
- The rewritten docs avoid any word containing `ember` (Q3); rejected: a word-boundary match, which the issue does not ask for.

### Issues opened

None.
