# Vendor DaisyUI 5.7.50, the synthwave theme, and the viewer palette swap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The viewer built by `bot site` loads a vendored, pinned DaisyUI 5.7.50 stylesheet and a custom `synthwave` theme, and every colour in `app.css`, `svg.py` and the templates reads a DaisyUI variable. Controls keep their current shapes.

**Architecture:** `scripts/vendor_daisyui.sh` downloads the precompiled `daisyui.css` and checks its SHA-256 before writing `src/bot/web/static/daisyui.css`. A test keeps the script pins, the file and `VERSIONS` in agreement. `static/theme.css` holds one `[data-theme="synthwave"]` block. `base.html` loads `daisyui.css`, `theme.css`, `app.css` in that order. `app.css` loses its Rim colour tokens and reads DaisyUI roles, plus two derived tokens. `svg.py` constants point at the same roles. `_copy_static` already copies the whole `static/` tree, so it does not change.

**Tech Stack:** bash, curl, sha256sum, shellcheck (from the venv), Jinja2 templates, plain CSS, pytest.

**Spec:** issue #258 (child of story #257). The issue's "Decisions" and "Acceptance criteria" sections are binding. Background: `docs/superpowers/specs/2026-11-07-viewer-daisyui-search-design.md` §3–§4.

## Global Constraints

- DaisyUI pin: version `5.7.50`, URL `https://cdn.jsdelivr.net/npm/daisyui@5.7.50/daisyui.css`, 1,142,434 bytes, SHA-256 `6a2cf91a0e9a7da09cf8109c45c3fae171e8967122576043f2b94da47fdf6b64`, MIT. The file's first line contains `daisyUI 5.7.50`. Verified by download on 2026-11-07.
- `VERSIONS` line, verbatim, after the htmx line: `daisyui 5.7.50 (MIT License) https://daisyui.com`.
- The theme variables are the 28 of spec §3, verbatim (copied in Task 2).
- No `!important` is added to override DaisyUI. Ours are unlayered and its rules are layered, so ours win.
- Out of scope (later children of #257): DaisyUI component classes in templates (#259, #263, #260), `docs/DESIGN.md`/ADR 0010/ADR 0008 (#261), `.impeccable/`, `docs/plano`, `docs/leccion`.
- Commits follow Conventional Commits with the `(#258)` scope.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Review Focus

1. **Hatch pattern colour.** The overvalued glyph's `#hatch` stroke in `base.html` must become `var(--color-error)`. If it is left alone it points at a deleted token and the hatch turns black or invisible. Pinned by the "no Rim token anywhere" test in Task 3 (templates are scanned).
2. **Rim tokens hiding in `color-mix()`/`outline`.** `--color-muted-2` (scenario-grid `.cell-none` outline) and `--color-paper` inside the `color-mix()` scenario tints are easy to miss. A missed one resolves to nothing and the cell loses its tint. Pinned by the Task 3 token-absence test, which checks the names as substrings, not only as declarations.
3. **The theme must not be beaten by DaisyUI's light `:root`.** DaisyUI's `@layer base` sets light colours on `:root`. Our `[data-theme="synthwave"]` block must be unlayered, and `<html>` must carry `data-theme="synthwave"`. Pinned by the Task 2 tests (`data-theme` on `<html>` in the built index; `theme.css` contains no `@layer`).
4. **Script writes a bad file on hash mismatch.** When the download differs, the script must leave the existing `daisyui.css` untouched and exit 1. Pinned by a Task 1 test that runs the script with a fake `curl` on `PATH` serving other bytes, then asserts exit code 1, both hashes on output, and the vendored file unchanged. This needs no network.
5. **Remote fetches from the vendored CSS.** `daisyui.css` contains `http://www.w3.org/2000/svg` namespaces inside data URIs, so a blanket `https?://` ban would fail. The test asserts no `@import` and no `url(http` (also `url("http`/`url('http`). Pinned in Task 1.

---

### Task 1: Vendor script, vendored file, VERSIONS line

**Files:**
- Create: `scripts/vendor_daisyui.sh` (mode 755)
- Create: `src/bot/web/static/daisyui.css` (produced by the script, committed)
- Modify: `src/bot/web/static/VERSIONS`
- Modify: `tests/integration/test_scripts.py` (`SCRIPTS` list gains `"vendor_daisyui.sh"`)
- Create: `tests/unit/test_web_theme.py` (vendoring tests)
- Create: `tests/integration/test_vendor_daisyui.py` (mismatch test with a fake `curl`)

**Interfaces:**
- Produces: `scripts/vendor_daisyui.sh [VERSION]`. Its pins match the regex `^DAISYUI_(VERSION|SHA256)="([^"]+)"` (multiline). The output path is `src/bot/web/static/daisyui.css`, relative to the repo root resolved from the script's own location (as `sync_master.sh` does with `readlink -f "$0"`), so it works from any cwd. The env var `DAISYUI_OUT`, when set, overrides the output path; the tests use it.
- Test helper in `test_web_theme.py`: `_pins() -> dict[str, str]` returning `{"VERSION": ..., "SHA256": ...}` parsed from the script.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_web_theme.py`:
  - `test_vendored_daisyui_matches_the_script_pin`: `hashlib.sha256(daisyui.css bytes).hexdigest() == _pins()["SHA256"]`; the first line of the file contains `f"daisyUI {_pins()['VERSION']}"`; `VERSIONS` text contains `f"daisyui {_pins()['VERSION']} (MIT License) https://daisyui.com"`.
  - `test_daisyui_css_fetches_nothing_remote`: the text contains no `@import`, and `re.search(r"url\(\s*['\"]?https?:", css)` is `None`.
  - In `tests/integration/test_scripts.py`, add `"vendor_daisyui.sh"` to `SCRIPTS`. That gives the existing executable + shellcheck test.
  - In `tests/integration/test_vendor_daisyui.py`, `test_mismatched_download_writes_nothing(tmp_path)`. Put a fake `curl` in a tmp `bin/` **prepended** to the inherited `PATH` (the script still needs the real `sha256sum`, `mktemp`, `cp`, `readlink`); it scans its argv for `-o` writes `b"not daisyui"` to the path after its `-o` argument. Set `DAISYUI_OUT=tmp_path/"daisyui.css"`, pre-filled with `b"old"`. Run the script and assert: `returncode == 1`; stdout+stderr contains both `6a2cf9…` (the expected hash) and `sha256(b"not daisyui")`; the out file still reads `b"old"`.
  - Also `test_matching_download_writes_the_file(tmp_path)`. The fake `curl` copies the committed `daisyui.css` to its `-o` target. Assert exit 0, the out file is byte-identical to the committed file, and stdout contains the out path.
- [ ] **Step 2: Run them to verify they fail.** Run `uv run pytest tests/unit/test_web_theme.py tests/integration/test_vendor_daisyui.py tests/integration/test_scripts.py -q -k "daisyui or vendor"`. Expected: FAIL (script and file missing).
- [ ] **Step 3: Write `scripts/vendor_daisyui.sh`.** It uses `set -euo pipefail`. The header comment says that upgrading means editing `DAISYUI_VERSION` and `DAISYUI_SHA256`, running the script, and editing the `VERSIONS` line. It holds the two pins on their own lines, and `VERSION="${1:-$DAISYUI_VERSION}"`. It downloads with `curl -fsSL "https://cdn.jsdelivr.net/npm/daisyui@${VERSION}/daisyui.css" -o "$tmp"`, where `$tmp` comes from `mktemp` with an `EXIT` trap to remove it. It computes `sha256sum "$tmp" | cut -d' ' -f1`. On a mismatch it prints `expected <pin>` and `actual <hash>` to stderr and exits 1. Otherwise it `cp`s the temp file to the output path and prints the path. Run `chmod +x`.
- [ ] **Step 4: Run the script** (`scripts/vendor_daisyui.sh`, network). Expected output: the path `src/bot/web/static/daisyui.css`. `sha256sum` of the file equals the pin. Then append the `VERSIONS` line after the htmx line.
- [ ] **Step 5: Run the Step 2 command.** Expected: PASS.
- [ ] **Step 6: Commit.** `git add scripts/vendor_daisyui.sh src/bot/web/static/daisyui.css src/bot/web/static/VERSIONS tests/...` then `git commit -m "feat(#258): vendor DaisyUI 5.7.50 with a pinned SHA-256"`.

### Task 2: The synthwave theme and the stylesheet order

**Files:**
- Create: `src/bot/web/static/theme.css`
- Modify: `src/bot/web/templates/base.html` (`<html>` attribute, stylesheet links, `#hatch` stroke)
- Modify: `tests/unit/test_web_theme.py`
- Modify: `tests/unit/test_web_assets.py` (`test_nothing_is_loaded_from_a_cdn` covers `theme.css`)

**Interfaces:**
- Consumes: `src/bot/web/static/daisyui.css` from Task 1.
- Produces: the CSS variables `--color-base-100/200/300`, `--color-base-content`, `--color-primary`, `--color-secondary`, `--color-success`, `--color-warning`, `--color-error` (and the rest of the 28), active under `<html data-theme="synthwave">`. Task 3 reads them.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_web_theme.py`:
  - `_THEME_VARS: tuple[tuple[str, str], ...]` holds the 28 pairs below, typed into the test (not read from the file).
  - `test_theme_css_defines_every_synthwave_variable`: the text contains `[data-theme="synthwave"]` and `color-scheme: dark`; for each pair, `f"{name}: {value};"` is in the text; `"@layer"` is not in the text.
  - `test_built_index_uses_the_theme_and_links_in_order(tmp_path)`: build a site with `bot.web.site.build` over one sidecar from `tests.web_sidecars` (`make_sidecar`/`write_sidecar`, as `tests/unit/test_web_site.py`'s `reports` fixture does) into `tmp_path/"site"`, with base url `"/"`. Assert `'<html lang="en" data-theme="synthwave">'` is in `index.html`. The `href` positions of `/static/daisyui.css`, `/static/theme.css`, `/static/app.css` are strictly increasing. `out/"static"/"daisyui.css"` and `out/"static"/"theme.css"` are files.
  - In `test_web_assets.py::test_nothing_is_loaded_from_a_cdn`, the scanned list (both the `@import` check and the `https?://` check) becomes `app.css`, `theme.css`, the templates.

  The 28 pairs, verbatim from spec §3:
  ```
  --color-base-100: oklch(15% 0.09 281.288)
  --color-base-200: oklch(20% 0.09 281.288)
  --color-base-300: oklch(25% 0.09 281.288)
  --color-base-content: oklch(78% 0.115 274.713)
  --color-primary: oklch(71% 0.202 349.761)
  --color-primary-content: oklch(28% 0.109 3.907)
  --color-secondary: oklch(82% 0.111 230.318)
  --color-secondary-content: oklch(29% 0.066 243.157)
  --color-accent: oklch(75% 0.183 55.934)
  --color-accent-content: oklch(26% 0.079 36.259)
  --color-neutral: oklch(45% 0.24 277.023)
  --color-neutral-content: oklch(87% 0.065 274.039)
  --color-info: oklch(74% 0.16 232.661)
  --color-info-content: oklch(29% 0.066 243.157)
  --color-success: oklch(77% 0.152 181.912)
  --color-success-content: oklch(27% 0.046 192.524)
  --color-warning: oklch(90% 0.182 98.111)
  --color-warning-content: oklch(42% 0.095 57.708)
  --color-error: oklch(73.7% 0.121 32.639)
  --color-error-content: oklch(23.501% 0.096 290.329)
  --radius-selector: 0rem
  --radius-field: 0rem
  --radius-box: 0rem
  --size-selector: 0.25rem
  --size-field: 0.25rem
  --border: 1px
  --depth: 1
  --noise: 1
  ```
- [ ] **Step 2: Run them to verify they fail.** Run `uv run pytest tests/unit/test_web_theme.py tests/unit/test_web_assets.py -q`. Expected: the theme tests FAIL (no `theme.css`, no `data-theme`).
- [ ] **Step 3: Write `theme.css`.** A two-line comment containing no URL, since the no-CDN test scans it for `https?://` (the viewer's single theme, from the DaisyUI generator, see `docs/DESIGN.md`), then one block: `[data-theme="synthwave"] {`, `color-scheme: dark;`, the 28 lines as `  --name: value;`, `}`.
- [ ] **Step 4: Edit `base.html`.** Change `<html lang="en">` (line 2) to `<html lang="en" data-theme="synthwave">`. The existing `app.css` link (line 10) is replaced, not duplicated. After the two font preloads, add three `<link rel="stylesheet">` tags for `{{ base_url }}static/daisyui.css`, then `theme.css`, then `app.css`. Set the `#hatch` `<line>` `stroke="var(--color-error)"`.
- [ ] **Step 5: Run the Step 2 command.** Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat(#258): synthwave theme and DaisyUI stylesheet order"`.

### Task 3: app.css and svg.py read DaisyUI variables only

**Files:**
- Modify: `src/bot/web/static/app.css`
- Modify: `src/bot/web/svg.py:28-36`
- Modify: `tests/unit/test_web_assets.py` (replace `test_css_uses_the_design_tokens`)
- Modify: `tests/unit/test_web_theme.py`
- Modify: `tests/unit/test_web_svg.py` (add the role assertions)

**Interfaces:**
- Consumes: the theme variables from Task 2.
- Produces: `app.css` `:root` tokens `--ink-soft` and `--rule-faint` (later children use them). `svg.py` `_INK`, `_SOFT`, `_INTRINSIC`, `_VERDICT_COLOR` with the values below.

- [ ] **Step 1: Write the failing tests.**
  - `test_web_assets.py`: replace `test_css_uses_the_design_tokens` with `test_css_reads_daisyui_variables_only`. It asserts that `app.css` has no `oklch(`, `rgb(`, `hsl(`, and no `re.search(r"#[0-9a-fA-F]{3,8}\b", css)`. It asserts `"--ink-soft:"` and `"--rule-faint:"` are in the text; `--ink-soft:` is followed by `color-mix(in oklab, var(--color-base-content) 80%, var(--color-base-100))`, and `--rule-faint:` by `color-mix(in oklab, var(--color-base-content) 12%, transparent)`. It keeps the existing asserts: no `Hallmark`, and `prefers-reduced-motion`, `tabular-nums`, `@font-face`, `[hidden]` present.
  - `test_web_theme.py`: `test_no_rim_token_survives`. For each of `--color-paper`, `--color-ink`, `--color-muted`, `--color-rule`, `--color-accent`, `--color-focus`, `--color-under`, `--color-fair`, `--color-over`, the name does not occur as a substring in `app.css`, `svg.py`, or any `templates/*.html`. Note that `--color-accent` is also a DaisyUI theme variable; that is fine, because the test does not scan `theme.css`.
  - `test_web_svg.py`: `test_svg_reads_daisyui_roles`. Check that `verdict_mark(Verdict.UNDERVALUED)` contains `var(--color-success)`, FAIR contains `var(--color-warning)`, and OVERVALUED contains `var(--color-error)`. `value_line_svg(_vl(), mini=False)` must contain `var(--color-secondary)` and `var(--color-base-content)`. `verdict_mark(Verdict.NA)` must contain `var(--ink-soft)`.
- [ ] **Step 2: Run them to verify they fail.** Run `uv run pytest tests/unit/test_web_assets.py tests/unit/test_web_theme.py tests/unit/test_web_svg.py -q`. Expected: the three new tests FAIL.
- [ ] **Step 3: Edit `app.css`.**
  - In `:root`, delete the three colour comments and every `--color-*` line. Keep `color-scheme: dark`, the spacing, type, easing, duration, container, z-index, font and `--rule-hair` tokens. Add the two derived tokens, with the exact values from Step 1.
  - Replace every reference: `--color-paper`→`--color-base-100`, `--color-paper-2`→`--color-base-200`, `--color-paper-3`→`--color-base-300`, `--color-ink` and `--color-ink-2`→`--color-base-content`, `--color-muted` and `--color-muted-2`→`--ink-soft`, `--color-rule`→`--color-base-300`, `--color-rule-2`→`--rule-faint`, `--color-accent` and `--color-focus`→`--color-primary`, `--color-accent-2`→`--color-secondary`, `--color-under`→`--color-success`, `--color-fair`→`--color-warning`, `--color-over`→`--color-error`.
  - Replace the longest names first (`-2`/`-3` suffixes before the bare names), so that `--color-paper-2` does not become `--color-base-100-2`.
  - Change the header comment to say that the viewer is styled by DaisyUI under its single synthwave theme (`theme.css`; see `docs/DESIGN.md`), dark only, and that this file holds layout, typography and what DaisyUI has no component for.
- [ ] **Step 4: Edit `svg.py`.** Set `_INK = "var(--color-base-content)"`, `_SOFT = "var(--ink-soft)"` and `_INTRINSIC = "var(--color-secondary)"`. Set `_VERDICT_COLOR` to `var(--color-success)`, `var(--color-warning)` and `var(--color-error)`; NA stays `_SOFT`.
- [ ] **Step 5: Run the Step 2 command, then the full gate.** Run `uv run pytest tests/unit/test_web_assets.py tests/unit/test_web_theme.py tests/unit/test_web_svg.py -q`, then `uv run ruff check . && uv run mypy src && uv run pytest -q`. Expected: all green.
- [ ] **Step 6: Build and look.** Run `uv run bot site --out /tmp/site --reports-dir reports --base-url /`. Check that `head -15 /tmp/site/index.html` shows the `data-theme` attribute and the three links in order, and that `/tmp/site/static/` lists `daisyui.css` and `theme.css`.
- [ ] **Step 7: Render check.** Serve `/tmp/site` with `python3 -m http.server -d /tmp/site 8000` and run the stage-3 browser script `.scratch/evals-258.md`. Expected: the computed `background-color` of `body` is synthwave base-100; the hatch and the verdict glyphs are coloured; the layout matches the pre-change build, with no shape regression from DaisyUI's base reset (see Assumptions). Fix a visible regression with an unlayered rule in `app.css`.
- [ ] **Step 8: Commit.** `git commit -m "feat(#258): viewer palette reads DaisyUI variables"`.

## Assumptions

These technical decisions were taken during plan review. The issue gives no source for them, and any of the options satisfies it.

1. **`DAISYUI_OUT` env override in the script.** It is a test seam, so the fake-`curl` tests never touch the committed file. Rejected: running the script against the real path inside a temporary copy of the repo, which is heavier for the same coverage.
2. **No separate test pins the literal issue values.** The issue's criterion is that the file, `VERSIONS` and the script agree with the script's own pins. A second test that hard-codes `5.7.50` would mean an upgrade edits four places instead of three. Rejected: `test_script_pins_are_the_issue_values`.
3. **DaisyUI's `@layer base` reset is accepted.** The issue says the file has "no preflight", but its `@layer base` carries a minimal reset alongside the themes:
   - `*{margin:0;padding:0;border:0 solid}`
   - `h1..h6{font-size:inherit;font-weight:inherit}`
   - `menu,ol,ul{list-style:none}`
   - `svg{display:block;vertical-align:middle}`
   - `:root{background-color:var(--root-bg)}` and a scrollbar colour

   Every viewer element whose shape depends on these (`h1`, `h2`, `.facts dd`, `.flag-list ul`, `.value-axis`, `.totals`, `.mark`, `.dcf summary`) already has an explicit unlayered rule in `app.css`, and that rule wins. The render check (Task 3 Step 7) catches anything missed; a regression is fixed in `app.css`, not by dropping the reset. Rejected: stripping the reset from the vendored file, which would break the byte-for-byte reproduction criterion.
4. **Precedence is verified in a browser, not only by proxy.** The unit tests check that the block is unlayered and that `data-theme` is present. The stage-3 `agent-browser` script reads the computed `background-color` of `body`, which proves the synthwave values win at render time.

## Grilling

- Rounds: 1. The revisions were local edits, not a new seam, so there was no second round.
- Questions: 16.
- Answers by source:
  - ISSUE: Q1, Q8, Q9, Q10 (the decision text, part of the answer), Q16 (the VERSIONS line, part of the answer).
  - CODE: Q2 (`site.py:76-78`, `test_web_site.py:49-50`), Q4 (`base.html:10`), Q5, Q6, Q7, Q12, Q14, Q16 (`test_web_assets.py:39`).
  - DOC: Q15 (AGENTS.md skills list).
  - NO SOURCE: Q3, Q10 (in part), Q11, Q13. They became technical assumptions 1–4.
- Spec ambiguities: none. Out of scope: none, so no follow-up issue was opened.
