# List pane as DaisyUI components — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The list side of the viewer built by `bot site` (header, verdict filter, count, ledger table, row flags, empty states, 404) is drawn by DaisyUI 5 component classes, and the `app.css` rules that drew those controls by hand are gone.

**Architecture:** Markup-only change in the Jinja templates (`base.html`, `_controls.html`, `_rows.html`, `list.html`, `404.html`), one new property `FlagView.tone` in `views.py` that the row template turns into a `badge-<tone>` class, two one-line changes in `viewer.js` (selection toggles `bg-base-300`; the empty-detail replacement keeps the hero structure), and deletions plus a few small layout rules in `static/app.css`. DaisyUI lives in `@layer daisyui`; `app.css` is unlayered, so the layout rules that survive win without `!important`.

**Tech Stack:** Jinja2 templates, plain CSS, vanilla JS, Python 3 dataclasses, pytest.

**Spec:** issue #259 (child of story #257). Its "Decisions" and "Acceptance criteria" sections are binding. Background: `docs/superpowers/specs/2026-11-07-viewer-daisyui-search-design.md` §5.

## Global Constraints

- Header markup, verbatim: `<header class="navbar">`, `<div class="navbar-start"><a class="brand" href="{{ base_url }}index.html" aria-label="Analyses, all companies">Analyses</a></div>`, `<div class="navbar-end"><span class="badge badge-ghost"><span class="num">{{ total }}</span> companies</span></div>` ("company" when `total == 1`; the `navbar-end` div is still rendered but empty when `total == 0`).
- Filter: `<nav id="filter" class="join" aria-label="Verdict">` (+ `hx-swap-oob="true"` when `oob`); each link `class="btn btn-sm join-item"` plus ` btn-active` on the current one, which alone keeps `aria-current="page"`. `href`, `hx-get`, `hx-target="#rows"`, `hx-swap="outerHTML"`, `hx-indicator="#rows"` unchanged. Count inside each link: `<span class="badge badge-sm badge-ghost num">{{ counts[v] }}</span>`. `join`, not `tabs tabs-box`.
- Count: `<output id="count" class="badge badge-neutral num" aria-live="polite" data-total="{{ total }}"{% if oob %} hx-swap-oob="true"{% endif %}>{{ rows|length }} of {{ total }}</output>`.
- Table: `<table class="table table-sm table-pin-rows list">`; never `table-zebra`. Selected row `<tr class="selected bg-base-300">`.
- Flag tone map, verbatim: `{"pass": "success", "warning": "warning", "fail": "error"}.get(self.severity, "ghost")`. `badge-info` is never emitted.
- `app.css`: no literal colour (`oklch(`, `rgb(`, `hsl(`, hex) — existing test `test_css_reads_daisyui_variables_only`; no `box-shadow: inset`; no `!important` added.
- Out of scope (other children of #257): the search box (#263), the detail pane — `stats`, dividers, `table-xs`, the history `join`, detail flag badges (#260), docs (#261), the impeccable passes (#262).
- Commits use Conventional Commits with the `(#259)` scope. `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Technical assumptions (declared, not in the issue's text)

1. **No `badge-success` in the rows fragment.** The issue's flag criterion also asks for `badge badge-xs badge-success` in `rows/all-mos-desc.html`, but `row_view` keeps only red and yellow flags (`src/bot/web/views.py:321`, pinned by `tests/unit/test_web_views.py::test_row_flags_are_only_red_and_yellow`, which must not be weakened). A green flag can never reach a row. The test instead asserts `badge-error` for the red-flagged `BBB` fixture plus `badge-warning` on a fixture with a yellow flag, and `FlagView.tone` covers `success` in its unit test.
2. **Glyph inside a coloured badge.** The flag glyph strokes in its verdict colour, which is the badge's background (red glyph on `badge-error`). `app.css` gets `.flags .badge .glyph { stroke: currentColor; }` (CSS beats SVG presentation attributes) so the glyph draws in the badge's `-content` colour, plus `.flags .badge { padding-inline: 1px; }` and `.flags .badge .mark { width: 0.75rem; height: 0.75rem; }` so a 16px glyph fits the `badge-xs` (1rem) box; `.flags` keeps `white-space: nowrap` and gains `gap`-free inline layout as today.
3. **Navbar shell rule.** `.bar` goes; one layout rule replaces it so the shell keeps its height and hairline: `.navbar { min-height: var(--bar-height); padding-inline: var(--space-lg); border-bottom: var(--rule-hair) solid var(--color-base-300); }` (`--bar-height` is used by `.split` and `.list-pane`).
4. **Pinned head row on the list well.** `table-pin-rows` paints `thead tr` with `--color-base-100`, a different colour from the list pane's `base-200`. `app.css` adds `.list thead tr { background: var(--color-base-200); }`.
5. **Filter wrap.** `.join` is `inline-flex` without wrap; at 390px five buttons do not fit. `#filter` keeps `display: flex; flex-wrap: wrap; max-width: 100%` (the shared rule with `.history` stays, minus the `padding: 1px 0 0 1px` that only compensated the deleted negative margins). `#filter a .mark` becomes `#filter .mark` (same size).
6. **404 keeps its spacing.** The 404 `main` is `class="hero empty"` (the issue writes `class="hero"`) so it keeps the `.empty` max-width and padding it has today; the acceptance check (`hero`, `btn btn-primary`) holds.
7. **Empty-detail replacement.** `viewer.js` replaces the `.empty-detail` contents with `<div class="hero-content"><p>Pick a company from the list to read its analysis.</p></div>` so the hero structure survives a swap.
8. **`.history a` loses its chip styling now.** The issue deletes the shared `#filter a, .history a` rules; the detail's history links fall back to `.history`/`.history a` (mono, soft colour) until #260 makes them a `join`.

## Review Focus

1. **Exactly one active filter.** `btn-active` and `aria-current="page"` must sit on the same, single link — in the full page and in every OOB `nav#filter` of the fragments. A template that emits `btn-active` from a different condition than `aria-current` would split them. Pinned in Task 2 on `index.html` and `rows/undervalued-mos-desc.html`, and looped over all 30 fragments.
2. **Selection after a swap.** `markSelected` must clear `bg-base-300` from rows it unselects, or two rows look selected after a click. Pinned by the Task 2 static test on the toggle line (same `on` variable as `selected`).
3. **Without JavaScript the filter still navigates.** Every filter link keeps an `href` to an `l/` page that exists. Pinned by the existing `test_links_point_at_files_that_exist` plus the Task 2 `href` assertion.
4. **The `.list` override survives.** DaisyUI's `.list` component is `display: flex`; the table also carries `table`. The existing `test_list_table_overrides_daisyui_list_component` stays green; the `<700px` restack and the `1100–1599px` hiding rules are asserted present in Task 2.
5. **The `none` row and the OOB empty detail in fragments.** The server's no-rows row keeps `td.none` with `colspan="9"`, and the fragment's OOB `#detail` keeps `hx-swap-oob="true"`. Pinned in Task 4 and by the existing `test_empty_filter_swaps_in_an_empty_detail`.

---

### Task 1: `FlagView.tone`

**Files:**
- Modify: `src/bot/web/views.py` (`FlagView`, after `severity`)
- Test: `tests/unit/test_web_views.py`

**Interfaces:**
- Produces: `FlagView.tone -> str` property returning `"success" | "warning" | "error" | "ghost"`.

- [ ] **Step 1: Write the failing test** `test_flag_tone_follows_severity`:
  ```python
  @pytest.mark.parametrize(("color", "tone"), [("green", "success"), ("yellow", "warning"), ("red", "error"), ("unknown", "ghost"), ("purple", "ghost")])
  def test_flag_tone_follows_severity(color: str, tone: str) -> None:
      assert FlagView("x", color, "").tone == tone
  ```
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_views.py -q -k tone`. Expected: FAIL (`AttributeError: ... 'tone'`).
- [ ] **Step 3: Implement** the property with the verbatim map of Global Constraints and a one-line docstring.
- [ ] **Step 4: Run** the Step 2 command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#259): FlagView.tone maps a flag severity to a badge colour`.

### Task 2: Navbar, join filter, count badge, table classes, selected row

**Files:**
- Modify: `src/bot/web/templates/base.html` (header), `_controls.html` (`filter_nav`, `count`), `list.html` (table tag), `_rows.html` (selected `tr`), `static/viewer.js` (`markSelected`), `static/app.css`
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_viewer_js.py`, `tests/unit/test_web_assets.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `#count` carries `data-total` (read by #263). Class `selected bg-base-300` on the selected row.

- [ ] **Step 1: Write the failing tests.** Fixture: the module's `reports` (AAA, BBB red-flagged, CCC).
  - `test_controls_are_daisyui_components` in `test_web_site.py`: on `index.html` — contains `<header class="navbar">`, `class="navbar-start"`, `class="navbar-end"`, `<span class="badge badge-ghost"><span class="num">3</span> companies</span>`; contains `<output id="count" class="badge badge-neutral num" aria-live="polite" data-total="3"`; contains `<table class="table table-sm table-pin-rows list">`; `"table-zebra"` absent from every HTML file.
  - `test_filter_is_a_join_with_one_active_link`: helper `_filter_links(html) -> list[str]` returning the `<a ...>` opening tags inside `<nav id="filter" ...>…</nav>` (regex, `re.S`). Assert the nav opening tag contains `class="join"`. For `index.html` (current: `all`) and `rows/undervalued-mos-desc.html` (current: `undervalued`): 5 links; each has `href="`, `hx-get="`, `hx-target="#rows"`, and `join-item` in its class; exactly one contains `aria-current="page"`, it is the one containing `btn-active`, and its `href` contains `/<current>-mos-desc.html`. Then loop every `rows/*.html`: exactly one link has `btn-active` and it is the one with `aria-current="page"`. Each fragment still contains `id="count"` with `hx-swap-oob="true"`.
  - `test_selected_row_is_highlighted`: `c/AAA.html` contains `<tr class="selected bg-base-300">` exactly once and the regex `<tr class="selected bg-base-300">\s*<td class="ticker"><a href="/c/AAA.html"` matches; `rows/all-mos-desc.html` contains no `selected`.
  - `test_mark_selected_toggles_the_highlight` in `test_web_viewer_js.py`: script contains `row.classList.toggle("selected", on);` and `row.classList.toggle("bg-base-300", on);`.
  - `test_hand_drawn_controls_are_gone` in `test_web_assets.py`: `app.css` contains none of `.bar {`, `.bar .note`, `.brand {`, `#filter a`, `#count {`, `box-shadow: inset`, `.list tr.selected td`; and still contains `[hidden] { display: none !important; }`, `.sr {`, `.split {`, `body.page-list .detail-pane { display: none; }`, `@media (max-width: 699px)`, `@media (min-width: 1100px) and (max-width: 1599px)`, `.list tr.selected .ticker::before`, `.list thead th[aria-sort] a { border-bottom-color: var(--color-primary); }`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_viewer_js.py tests/unit/test_web_assets.py -q`. Expected: the five new tests FAIL, the rest PASS.
- [ ] **Step 3: Templates.** Apply the header, filter, count and table markup of Global Constraints. In `_rows.html` the selected row's `tr` gets `class="selected bg-base-300"` (unselected rows get no class attribute, as today). The verdict glyph and label inside each filter link are unchanged.
- [ ] **Step 4: `viewer.js`.** In `markSelected`, add `row.classList.toggle("bg-base-300", on);` right after the `selected` toggle.
- [ ] **Step 5: `app.css`.** Delete `.bar`, `.brand`, `.bar .note`, `.bar .note .num`, `#count`, every `#filter a…` / `.history a…` rule of the old chip (base, `:hover`, `:active`, `:focus-visible`, `[aria-current]`, the coarse-pointer `@media`), `#filter a .num`, `.list tr.selected td`, and `#filter a` from the reduced-motion list. Add the rules of technical assumptions 3, 4 and 5. Keep everything else.
- [ ] **Step 6: Run** the Step 2 command, then `uv run pytest -q`. Expected: PASS (existing `test_ids_are_unique_per_page`, `test_count_reads_n_of_total`, `test_list_table_overrides_daisyui_list_component` included).
- [ ] **Step 7: Commit** `feat(#259): navbar, join filter, count badge and DaisyUI table on the list pane`.

### Task 3: Row flags as tone badges

**Files:**
- Modify: `src/bot/web/templates/_rows.html` (flags cell), `static/app.css` (`.flags`)
- Test: `tests/unit/test_web_site.py`

**Interfaces:**
- Consumes: `FlagView.tone` (Task 1), `FlagView.severity`, `FlagView.label`, `flag_mark(color, name)`.

- [ ] **Step 1: Write the failing test** `test_flags_are_badges_by_tone`: build the module `reports`; `rows/all-mos-desc.html` contains `<span class="badge badge-xs badge-error" title="fail: `; `badge-info` absent from every HTML file. Then a second build from a fresh reports dir with `make_sidecar("DDD")` whose `narrative_flags[3]["color"] = "yellow"`: its `rows/all-mos-desc.html` contains `<span class="badge badge-xs badge-warning" title="warning: `. The existing `test_marks_pair_colour_with_a_title` (`<title>fail: ` in rows) must still pass.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py -q -k "badges or marks_pair"`. Expected: the new test FAILS.
- [ ] **Step 3: Template.** The flags cell, verbatim: `<td class="flags">{% for f in r.flags %}<span class="badge badge-xs badge-{{ f.tone }}" title="{{ f.severity }}: {{ f.label }}">{{ flag_mark(f.color, f.name) }}</span>{% endfor %}</td>`.
- [ ] **Step 4: CSS.** Add the three rules of technical assumption 2.
- [ ] **Step 5: Run** the Step 2 command. Expected: PASS.
- [ ] **Step 6: Commit** `feat(#259): row flags are DaisyUI badges coloured by severity`.

### Task 4: Hero empty states and 404

**Files:**
- Modify: `src/bot/web/templates/list.html` (empty list), `_controls.html` (`empty_detail`), `_rows.html` (no-rows row link), `404.html`, `static/viewer.js` (empty-detail replacement), `static/app.css`
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_viewer_js.py`, `tests/unit/test_web_assets.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Keeps the selector `#detail .empty-detail` that `viewer.js` uses.

- [ ] **Step 1: Write the failing tests.**
  - `test_empty_states_are_heroes`: build from `tmp_path / "missing"` → `index.html` contains `<main class="hero empty">`, `<div class="hero-content">` and `No analyses yet`. Build the module `reports` → `l/fair-mos-desc.html` contains `<div class="hero empty-detail">`, `No company is fair yet` and `<a class="btn btn-link" href="/l/all-mos-desc.html"`; `rows/fair-mos-desc.html` contains `<td colspan="9" class="none">` and `<a class="btn btn-link btn-xs" href="/l/all-mos-desc.html"`, and still `id="detail" hx-swap-oob="true"`; `404.html` contains `<main class="hero empty">` and `<a class="btn btn-primary" href="/index.html">Show all companies</a>`.
  - `test_empty_detail_replacement_keeps_the_hero` in `test_web_viewer_js.py`: script contains `<div class="hero-content"><p>Pick a company from the list to read its analysis.</p></div>`.
  - Extend `test_hand_drawn_controls_are_gone`: `app.css` contains none of `.empty a`, `.empty-detail a`, `.list .none a`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_viewer_js.py tests/unit/test_web_assets.py -q -k "hero or hand_drawn or empty"`. Expected: the new/extended tests FAIL.
- [ ] **Step 3: Templates.** Empty list: `<main class="hero empty"><div class="hero-content"><div>` + the existing `h1` and two `p` unchanged + `</div></div></main>`. `empty_detail`: keep the `<section id="detail"…>` wrapper; inside, `<div class="hero empty-detail"><div class="hero-content"><div><p>No company is {{ filter_label[f] }} yet.</p><a class="btn btn-link" href=… hx-get=… hx-target="#rows" hx-swap="outerHTML" hx-indicator="#rows">Show all companies</a></div></div></div>` (`href`/`hx-get` as today). No-rows row: the link gains `class="btn btn-link btn-xs"` as its first attribute. 404: `<main class="hero empty"><div class="hero-content"><div>` + existing `h1` and first `p` + `<a class="btn btn-primary" href="{{ base_url }}index.html">Show all companies</a>` + `</div></div></main>`.
- [ ] **Step 4: `viewer.js`.** The replacement string becomes technical assumption 7's markup.
- [ ] **Step 5: `app.css`.** Delete `.empty a`, `.empty-detail a`, `.list .none a`. Keep `.split, .empty`, `.empty`, `.empty h1`, `.empty p`, `.empty-detail`, `.empty-detail p:first-child`, `.list .none`.
- [ ] **Step 6: Run** the Step 2 command, then `uv run ruff check . && uv run mypy src && uv run pytest -q`. Expected: PASS.
- [ ] **Step 7: Build and read by eye:** `uv run bot site --out /tmp/site --reports-dir reports --base-url /`, then read `/tmp/site/index.html`, `/tmp/site/404.html`, one `/tmp/site/c/<TICKER>.html`.
- [ ] **Step 8: Commit** `feat(#259): hero empty states and 404 with DaisyUI buttons`.
