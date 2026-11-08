# Impeccable critique and audit fixes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (`.agents/skills/subagent-driven-development/SKILL.md`, per AGENTS.md) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every P0–P2 finding (and the cheap P3s) from the `/impeccable critique` and `/impeccable audit` runs on the site built by `bot site`, on branch `feature/257-viewer-daisyui-search`, so the story #257 can merge.

**Architecture:** Every fix lives in the viewer (`src/bot/web/`): CSS in `static/app.css`, markup in `templates/`, chart markup in `svg.py`, behaviour in `static/viewer.js`, and one new fragment template wired in `site.py`. Nothing outside `src/bot/web/`, its tests and `docs/DESIGN.md` changes. Tests are pytest assertions on the generated site and on the source files (the repo has no JS test runner; `viewer.js` is checked by `node --check` and static greps, and its behaviour by the `agent-browser` script `.scratch/evals-262.md`).

**Tech Stack:** Python 3 / Jinja2 static build, precompiled DaisyUI 5.7.50 (vendored, read-only), htmx 2.0.11 (vendored), vanilla JS, pytest, ruff, mypy.

**Spec:** issue #262 (story #257), `docs/superpowers/specs/2026-11-07-viewer-daisyui-search-design.md` (§3–§6 pin the theme, components and search; this plan does not reopen them), `docs/DESIGN.md`. The findings come from the critique and audit reports, summarised in the register below.

## Global Constraints

- Colours only through DaisyUI variables, `--ink-soft` or `--rule-faint` (`tests/unit/test_web_assets.py::test_css_reads_daisyui_variables_only`): no `oklch(`, `rgb(`, `hsl(`, hex, `white` or `black` in `app.css`, `svg.py`, the templates or `viewer.js`.
- `static/daisyui.css` and `static/theme.css` are not edited. Overrides go in `app.css`.
- No new dependency, no CDN, no build step, no Tailwind utilities beyond those already used (`bg-base-300`, `text-secondary`, `lg:stats-horizontal`).
- Search: "Nothing is written to the URL or storage" (spec §6, under the search behaviour of `viewer.js`; §2 lists "Persisting the search text in the URL" as a non-goal). Navigation URLs are not search state: the ticker links already push `c/<T>.html` (`_rows.html:4`), and the filter and sort links may push their existing `l/<filter>-<sort>-<dir>.html` pages.
- Every filter, sort, "Show all" and ticker link keeps its `href` and works without JavaScript; `#search` keeps `hidden` in the static HTML.
- Text contrast ≥ 4.5:1 (DESIGN.md Contrast Floor Rule); UI component boundaries ≥ 3:1 (WCAG 1.4.11).
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green after every task.

## Findings register

Severity is the synthesis of critique Assessment A (design review), Assessment B (browser evidence) and the audit. Where two runs disagreed, the higher grade was kept. `T#` is the task that fixes the finding.

| ID | Sev | Finding | Task |
|---|---|---|---|
| F1 | P1 | The list pane overflows sideways at ≥1100px. Date is cut at 1440 (634/578px), and Flags and Date are hidden at 1600–1920 (847/644–684px). | T2 |
| F2 | P1 | The scenario grid overflows its half of the pair grid and paints over the Flags badges (75px at 1440). At 390 the last column is clipped. The column heads run together. | T3 |
| F3 | P1 | The facts `.stat-title` labels are 3.93:1 at 12px (DaisyUI's 60% mix). | T1 |
| F4 | P1 | The search field: placeholder 3.08:1, border 1.4:1, and its only label is screen-reader text. | T1 |
| F5 | P1 | At ≤699px the only tap target per row card is the ticker text (the "T" link is 9×30px). | T2 |
| F6 | P2 | The value-axis threshold labels escape the instrument: "fair 1.0×" is cut to "ir 1.0×" at 390, and "undervalued 1.3×" runs off the right edge on overvalued companies. | T3 |
| F7 | P2 | `document.title` stays "Analyses" after an htmx detail swap pushes `/c/<T>.html` (WCAG 2.4.2). | T4 |
| F8 | P2 | No skip link: about 90 Tab stops to reach the detail pane, and `#detail` is not a landmark. | T4 |
| F9 | P2 | Filter and sort do not push their existing `l/…` URLs, so refresh, Back and bookmarks lose them. | T4 |
| F10 | P2 | A deep-linked company (`/c/ABT.html`) is not scrolled into view in the list pane. | T4 |
| F11 | P2 | The drivers chart's "price X" head is centred over the track while the price line is elsewhere. | T3 |
| F12 | P2 | The 12px search input triggers iOS Safari's zoom on focus. | T1 |
| F13 | P2 | The analysis-date buttons (`btn-xs`) set text at 11px. | T1 |
| F14 | P3 | Two focus rings on the search box (DaisyUI `:focus-within` plus the inner `:focus-visible`). Fixed. | T1 |
| F15 | P3 | The facts strip stacks one figure per row at ≤44rem, about 600px on a phone. Fixed: two columns. | T1 |
| F16 | P3 | Screen readers hear the verdict twice per list row (mini value line `aria-label`) and twice per scenario cell (glyph `<title>` plus `.sr`). Fixed. | T3 |
| F17 | P3 | The sort arrow is read as part of the column name ("MoS↓"). Fixed with empty alt text on the generated content. | T4 |
| F18 | P3 | The live announcement doubles the period when the name ends in "." ("Zoetis Inc.."). Fixed. | T4 |
| F19 | P3 | Dead CSS: the `--z-raised` token and the two rules after the reduced-motion `!important` kill. Fixed. | T4 |
| D1 | P3 | Declined: warning flags are the brightest marks in a row. Spec §5 pins solid `badge-{error,warning}` per severity. | — |
| D2 | P3 | Declined: "no verdict 0" is a live filter segment. Spec §5 keeps every filter item a link; the zero is information, and the empty state offers "Show all". | — |
| D3 | P3 | Declined: the no-match row does not name the active filter. Spec §6 fixes that copy verbatim. | — |
| D4 | P3 | Declined: the split pages carry two `h1`s. Each pane has its own top heading and only one pane shows under 1100px; heading navigation still works. | — |
| D5 | P3 | Declined: the mobile cards' figures don't align from card to card, and the flag reasons are indented. Cosmetic; every figure is labelled. | — |
| D6 | P3 | Declined: no `/` shortcut and no arrow keys between rows. That is new interaction outside the story's scope; the skip link (F8) covers the bypass. | — |
| D7 | P3 | Declined: snake_case input names in Drivers and Scenarios. They are the model's assumption keys, shared with the reports and the story file. | — |
| D8 | — | False positive: `/nope` shows Python `http.server`'s 404. GitHub Pages serves `404.html`, which renders correctly. | — |

## Review Focus

- **No JavaScript:** after T4, every filter, sort and "Show all" link still navigates by `href`, the skip link still works (it is a plain fragment link), and `#search` stays hidden. Pinned by the T4 site tests and the no-JS step of the browser script.
- **Back after a pushed filter (F9):** with the history cache off, htmx re-fetches the static page and swaps `<body>`. The scripts are in `<head>` (`base.html:13-14`, `defer`), so nothing re-executes and no listener is registered twice. `htmx:historyRestore` → `initSearch` reveals `#search`, which comes back empty (the query is not kept, as §6 requires). The browser script checks Back after a filter click.
- **A filter that empties the list** swaps in `empty_detail` out of band (`hx-swap-oob="true"`, i.e. outerHTML). The skip link must still point at a `#detail` that exists, and the empty `#detail` must accept focus. Pinned by the T4 test on `empty_detail`.
- **Long values in the list at ≥1600** (two flags, long names, `n/a` MoS): the fit check runs on the real 80-company site with all rows visible, at 1100, 1280, 1440, 1600, 1920 and 768.
- **An overvalued company whose undervalued tick sits near the right edge (FDS), and an undervalued one whose price sits at the left edge (CMCSA):** pinned by the T3 anchor tests with both geometries.

## Assumptions

Technical decisions taken while grilling the plan, each with the alternative it rejects:

- **The filter and sort URL is the `l/` page** (F9). On `/c/ABT.html`, clicking "fair" pushes `/l/fair-mos-desc.html`. Refreshing that URL shows the fair list with its first row's detail, which is what every `l/` page shows (site.py:157-163, `list_page`). A URL that keeps the open company does not exist in the static site, and adding one per company × filter × sort would multiply the pages by 30. Rejected.
- **The htmx history cache is turned off** to honour spec §6 (`historyCacheSize: 0`). Back re-fetches the static page. Rejected alternative: scrubbing the snapshot in `htmx:beforeHistorySave` and re-applying the search afterwards. More code and racy.
- **The layout geometry is checked in a browser only.** The repo has no browser in pytest/CI, so the fit and containment checks of T2/T3 live in the agent-browser script (`.scratch/evals-262.md`, untracked), and the committed tests pin the CSS rules and markup that produce them. Rejected alternative: adding a headless browser to the test suite, a new dependency the spec does not allow.
- **The 16px search text applies on `(pointer: coarse)`, not by width,** because the iOS zoom depends on the device, not the viewport. Rejected: 16px at every width, which would change the desktop `input-sm`.
- **The fair threshold is named on the price label.** This rests on CONTEXT.md's Verdict definition, `>=1.0` around fair value, so `ValueLine.fair == price * MOS_FAIR` (`views.py:129-130`) sits on the price line. The label keeps formatting `MOS_FAIR`, so it stays truthful if the constant moves.
- **The geometry numbers go in the PR description.** The browser script's measured `scrollWidth/clientWidth` at the six widths, and the containment checks of T3, are copied into the PR description, so a reviewer can verify them without `.scratch/`.
- **The arrow fallback** (F17) is generated on the sort `<a>` (`.list thead th[aria-sort] a::after`, app.css:89-91). In a browser without alt-text `content`, the fallback keeps today's behaviour (the arrow is part of the link name); nothing regresses. No browser floor is declared in DESIGN.md or the spec.
- **P3s are declined in the PR description with one line each.** The issue allows it: "A P3 may be declined with one line of reason in the pull request description".

---

### Task 1: Contrast floor and the search control (F3, F4, F12, F13, F14, F15)

**Files:**
- Modify: `src/bot/web/static/app.css`
- Test: `tests/unit/test_web_assets.py`

**Interfaces:**
- Consumes: the `--ink-soft` token (`app.css :root`).
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_web_assets.py`. Each one reads `app.css` and asserts that a rule exists, in the file's existing style (see `test_search_box_width_rule`):
  - `test_facts_labels_meet_the_contrast_floor`: a rule for `.facts .stat-title` sets `color: var(--ink-soft)` and `font-size: var(--text-sm)`.
  - `test_search_placeholder_and_border_meet_the_contrast_floor`: `#search input::placeholder` sets `color: var(--ink-soft)` and `opacity: 1`; `#search` sets a `border-color` built from `var(--color-base-content)` at ≥ 45%.
  - `test_search_draws_one_focus_ring`: `#search input:focus-visible` sets `outline: none`, and `#search:focus-within` sets `outline: 2px solid var(--color-primary)`.
  - `test_search_input_is_16px_on_touch_screens`: inside `@media (pointer: coarse)`, `#search input` sets `font-size: 16px` (covers phones and iPads, both of which zoom on a focused input under 16px).
  - `test_history_dates_are_at_least_12px`: `.history .btn` sets `font-size: var(--text-sm)`.
  - `test_facts_use_two_columns_in_a_narrow_pane`: inside `@container (max-width: 44rem)`, `.facts.stats` sets `grid-template-columns: repeat(2, minmax(0, 1fr))`, and `.facts .lead-figure` spans both columns (`grid-column: 1 / -1`).
- [ ] **Step 2:** `uv run pytest tests/unit/test_web_assets.py -q`. Expected: the six new tests FAIL.
- [ ] **Step 3: Add the rules to `app.css`** next to the rules they amend: the search rules by `#search`, the facts rules in the facts block, the 16px rule in a new `@media (pointer: coarse)` block. In the 44rem container query the one-column rule `.facts.stats { grid-auto-flow: row; }` and the dashed `border-block-end` separator are pinned by `tests/unit/test_web_assets.py:137-141` (`test_detail_facts_rules`); replace those assertions with the two-column ones, and keep the dashed `border-block-end` on every stat but the last. Measured on the shipped theme by the audit: `--ink-soft` is 5.66:1 on base-200 (facts) and 6.14:1 on base-100 (search field). The border expression is exactly `border-color: color-mix(in oklab, var(--color-base-content) 45%, transparent);`; measure it in the browser against base-100 and base-200 and raise the percentage (and the test) until both are ≥ 3:1.
- [ ] **Step 4:** run the tests, then the full gate. Expected: PASS.
- [ ] **Step 5: Commit** `fix(#262): contrast floor and one focus ring on the search control`

### Task 2: The ledger fits its pane; a phone row is one target (F1, F5)

**Files:**
- Modify: `src/bot/web/static/app.css` (the `@media (min-width: 1100px)` column rules and the `@media (max-width: 699px)` block)
- Test: `tests/unit/test_web_assets.py`

**Interfaces:**
- Consumes: the `.list` table markup in `_rows.html` / `_controls.html`, unchanged: column 6 is Intrinsic (`td[data-label="Intrinsic"]`), column 7 is Story (`td[data-label="Story"]`).
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests**:
  - `test_story_column_leaves_the_split_ledger_at_every_width`: the rule hiding `.list th:nth-child(7), .list td[data-label="Story"]` sits under `@media (min-width: 1100px)` with no `max-width`. The facts strip already shows Story.
  - `test_intrinsic_column_leaves_the_split_ledger`: `.list th:nth-child(6), .list td[data-label="Intrinsic"]` are hidden under `@media (min-width: 1100px)`. The facts strip already shows Intrinsic.
  - `test_phone_row_is_one_link`: inside `@media (max-width: 699px)`, `.list tbody tr` has `position: relative` and `.list td.ticker a::after` has `content: ""`, `position: absolute` and `inset: 0`.
- [ ] **Step 2:** run them. Expected: FAIL.
- [ ] **Step 3: Implement** in `app.css`:
  - Move the Story rule and add the Intrinsic rule.
  - Extend the name ellipsis (`max-width: 6rem`) from 1100–1599 to all of ≥1100, then, only if the fit check still overflows, hide `.value-line.mini` at ≥1100 (it is already hidden at 1100–1399, app.css:144). Stop condition: if the check still fails at any width after these four trims, the task has not landed. It goes back through the stage-4 escalation with the measured widths. F1 is P1, so the story does not merge with it open.
  - Make the phone row one link with the `::after` overlay. `.list .ticker { position: relative }` must not apply at ≤699px, or the overlay would anchor to the cell. Keep the selected-row square (`.list tr.selected .ticker::before`) positioned against the row there.
- [ ] **Step 4: Fit check in a real browser.** Rebuild the site and serve it:
  `uv run bot site --out /tmp/site --reports-dir reports --base-url /`, then `python3 -m http.server 8765 -d /tmp/site`.
  At 768, 1100, 1280, 1440, 1600 and 1920 wide, on `/` with no query, run
  `agent-browser eval 'var p=document.querySelector(".list-pane");p.scrollWidth+"/"+p.clientWidth'`.
  Expected: `scrollWidth <= clientWidth` at every width. At 768 use `document.documentElement` instead, since the pane is not the scroller there. At 390, tap the middle of a row card (`agent-browser click` on the row's name cell). Expected: the URL becomes `/c/<TICKER>.html`.
- [ ] **Step 5:** full gate, then commit `fix(#262): the ledger fits its pane and a phone row is one link`

### Task 3: Detail charts stay inside their boxes (F2, F6, F11, F16)

**Files:**
- Modify: `src/bot/web/svg.py` (`value_line_svg`, `scenario_grid_table`, `tornado_table`)
- Modify: `src/bot/web/templates/detail.html` (the scenarios/flags pair)
- Modify: `src/bot/web/static/app.css` (`.value-axis`, `.scenario-grid`, `.tornado .track-head`)
- Test: `tests/unit/test_web_svg.py` (rewrite `test_full_value_line_labels_are_html_outside_the_svg`, lines 84-96, whose label set includes `"fair 1.0×"` and `"price 100.00"`), `tests/unit/test_web_svg_tornado.py`, `tests/unit/test_web_site.py`

**Interfaces:**
- Consumes: `ValueLine.fair == price * MOS_FAIR` (`views.py`), so the fair tick always sits at the price line. `_anchor(x, width, margin)`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests**:
  - `test_fair_threshold_is_named_on_the_price_label` (`test_web_svg.py`): the full axis has no separate "fair 1.0×" tick label. The price label reads `price <p> · fair 1.0×`, because fair is the price by definition.
  - `test_axis_labels_anchor_inside_the_axis` (parametrised over two geometries): CMCSA-like (price at `axis_min`) and FDS-like (an overvalued company whose `undervalued` tick sits within 10% of `axis_max`). A label at x < 30% of the width carries `at-start`, one at x > 70% carries `at-end`, otherwise `at-middle`. Assert this for the undervalued, price and intrinsic labels.
  - `test_mini_value_line_is_decorative`: a `mini=True` SVG has `aria-hidden="true"` and no `role="img"` or `aria-label`, because the verdict cell already names the verdict.
  - `test_scenario_cells_name_the_verdict_once`: every `td.cell` holds a glyph SVG with `aria-hidden="true"` and no `<title>`, plus its `.sr` text.
  - `test_scenario_grid_scrolls_inside_its_section`: `scenario_grid_table` returns the table wrapped in `<div class="scroll">`.
  - `test_drivers_price_head_sits_at_the_price` (`test_web_svg_tornado.py`): the `track-head` cell holds `<span class="track-price at-…" style="margin-left:<pct>%">price <p></span>`. Its percentage is the price's position on the 0–100 track scale, and its anchor comes from `_anchor(px, 100.0, 30.0)`.
  - `test_scenarios_take_the_wide_column` (`test_web_site.py`): in a built detail page, the `.pair-grid` that holds `section.scenarios` also has class `wide-first`.
- [ ] **Step 2:** run them. Expected: FAIL.
- [ ] **Step 3: Implement**:
  - **`value_line_svg`:**
    - Drop the fair tick label.
    - Label the price `price <p> · fair 1.0×`, keeping `MOS_FAIR:.1f` and `×` as today.
    - Anchor every label with `_anchor(x, width, width * 0.3)`.
    - Mini: decorative, i.e. `aria-hidden="true" focusable="false"`.
  - **`scenario_grid_table`:**
    - Cells use `verdict_mark(verdict, decorative=True)`.
    - Wrap the table in `<div class="scroll">`. The existing `.dcf .scroll` rule becomes a shared `.scroll { overflow-x: auto }`.
  - **`tornado_table`:** emit the head span. In CSS, `.tornado .track-head { text-align: left }`; `.track-price { display: inline-block }`; `.track-price.at-middle { transform: translateX(-50%) }`; `.track-price.at-end { transform: translateX(-100%) }`.
  - **`detail.html`:** add `wide-first` to the scenarios/flags `.pair-grid`.
  - **`app.css`:** give the scenario column heads `padding-inline: var(--space-2xs)` so "-1.0pp" and "-0.5pp" no longer touch.
  - The ticks row now holds only the undervalued label; the price label sits in its own row below the SVG (svg.py:149-161 structure), so the two start-anchored labels on a CMCSA-like axis never share a row.
- [ ] **Step 4: Browser check.** Rebuild and serve the site as in Task 2. On `/c/CMCSA.html` and `/c/FDS.html` at 390 and 1440, every `.axis-label`, `.track-price` and the scenario table must have `getBoundingClientRect()` inside its section's rect, the table measured inside its `.scroll` box. At 1440 the scenario table must not intersect `section.flag-list`.
- [ ] **Step 5:** full gate, then commit `fix(#262): detail charts stay inside their boxes`

### Task 4: Navigation state: title, pushed filters, skip link, deep link (F7, F8, F9, F10, F17, F18, F19)

**Files:**
- Create: `src/bot/web/templates/detail_fragment.html`
- Modify: `src/bot/web/site.py` (`_write_company` renders `f/` targets with `detail_fragment.html`; `build` loads it)
- Modify: `src/bot/web/templates/rows_fragment.html`, `_controls.html`, `_rows.html`, `list.html`, `detail.html`, `base.html`
- Modify: `src/bot/web/static/viewer.js`, `src/bot/web/static/app.css`
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_viewer_js.py`, `tests/unit/test_web_assets.py`

**Interfaces:**
- Consumes: `page_title()` (`_controls.html`), `list_href(f, s, d)` (`site.py` env globals). htmx 2.0.11 sets `document.title` from a top-level `<title>` in a swapped fragment (verified in `htmx.min.js`: `o.parentNode===r` → `r.title`).
- Produces: the `.skip` link class; `#detail` as a labelled region.

- [ ] **Step 1: Write the failing tests**:
  - `test_fragments_carry_their_page_title` (`test_web_site.py`):
    - `f/AAA.html` starts with `<title>AAA · <name> · Analyses</title>`, the exact text of the `c/AAA.html` page's `<title>`.
    - `f/AAA/2026-09-01.html` carries the same title as its own page `c/AAA/2026-09-01.html`.
    - `rows/fair-mos-desc.html` starts with `<title>` holding the `<title>` text of `l/fair-mos-desc.html`.
    - `test_fragments_are_not_pages` keeps passing: no `<html`.
  - `test_filter_sort_and_show_all_push_their_list_url`: in `index.html` and in a rows fragment, every `<a>` with `hx-target="#rows"` has `hx-push-url` equal to its own `href`.
  - `test_skip_link_leads_to_the_analysis`:
    - `index.html` and `c/AAA.html` have, as the first element of `<body>` after the defs SVG, `<a class="skip btn btn-sm btn-primary" href="#detail">Skip to analysis</a>`.
    - Both `section#detail` variants carry `tabindex="-1"` and `aria-label="Analysis"`: the one in `list.html` and the `empty_detail` one. An `innerHTML` swap keeps them, and an OOB `empty_detail` swap brings the same pair, so the region's name never depends on which swap ran last.
    - `404.html` has no skip link.
  - `test_viewer_scrolls_the_selected_row_into_the_list_on_load` (`test_web_viewer_js.py`, static grep in the file's style): `viewer.js` defines `revealSelected` and calls it once at load, and it touches `.list-pane` `scrollTop`.
  - `test_announcement_does_not_double_the_period`: `viewer.js` strips a trailing `.` before adding `". "` (a grep for `replace(/\.$/, "")` is enough).
  - `test_sort_arrow_is_not_part_of_the_column_name` (`test_web_assets.py`): each arrow rule declares `content` twice, first the plain fallback and then the alt-text form, e.g. `content: "\2193"; content: "\2193" / "";`, so a browser without alt-text support for `content` keeps the arrow.
  - `test_history_cache_is_off` (`test_web_site.py`): `index.html` `<head>` has `<meta name="htmx-config" content='{"historyCacheSize":0}'>`. With pushed filter URLs, htmx would otherwise snapshot the page into `sessionStorage` (`htmx-history-cache`), including a no-match row quoting the query, which breaks spec §6 "Nothing is written to the URL or storage". With the cache off, Back reloads the pushed page from its static file and fires `htmx:historyRestore` (`initSearch` already listens).
  - `test_no_dead_tokens`: `--z-raised` is absent from `app.css`, and the reduced-motion block has no `#detail, #rows { transition: none; }` and no `#detail.htmx-settling > * { animation: none; }`.
- [ ] **Step 2:** run them. Expected: FAIL.
- [ ] **Step 3: Implement**:
  - **`detail_fragment.html`:** `<title>{{ detail.ticker }} · {{ detail.name }} · Analyses</title>` followed by `{% include "detail.html" %}`. `site.py` writes `f/` targets from it.
  - **`rows_fragment.html`:** first line `<title>{{ page_title() }}</title>`. Import `page_title` there.
  - **`_controls.html`:** filter links, sort links and the `empty_detail` "Show all" link get `hx-push-url="{{ list_href(...) }}"`, the same arguments as their `href`.
  - **`_rows.html`:** the "Show all" link gets `hx-push-url` the same way.
  - **`base.html`:** add the `htmx-config` meta before the scripts; add `{% block skip %}{% endblock %}` right after the defs SVG. `list.html` fills it with the skip link only when `detail` is set. `#detail` and the `empty_detail` section get the attributes above.
  - **`app.css`:**
    - `.skip { position: absolute; left: var(--space-md); top: var(--space-xs); z-index: var(--z-sticky); transform: translateY(-200%); }` and `.skip:focus { transform: none; }`.
    - Under `@media (max-width: 1099px)`: `body.page-list .skip { display: none; }`, because the detail pane is hidden there.
    - `#detail:focus { outline: none; }`: the section is a jump target, not a control.
    - Apply F17 and F19 as the tests pin.
  - **`viewer.js`:**
    - Add `revealSelected()`. At ≥1100px, if `#rows tr.selected` lies outside the `.list-pane`'s visible box, set `pane.scrollTop` so the row sits about a third of the way down. Use the `getBoundingClientRect()` difference, never `scrollIntoView`, which would also scroll the window. Call it once after the first `markSelected()`.
    - In `announceDetail`, strip a trailing `.` from the heading text before appending `". "`.
- [ ] **Step 3b: `docs/DESIGN.md`.** Record in its component sections:
  - the skip link and the `#detail` region;
  - filter and sort pushing their `l/` URLs, and the history cache turned off;
  - the 45% search border and the placeholder on `--ink-soft`;
  - the two-column facts strip in a narrow pane;
  - the shared `.scroll` wrapper of the scenario grid;
  - the ledger dropping Story and Intrinsic beside the detail (≥1100px);
  - the phone row as one link.
- [ ] **Step 4: Browser check** (the search walk-through and navigation part of `.scratch/evals-262.md`):
  - A detail click sets `document.title` to `<T> · <name> · Analyses`.
  - The fair filter pushes `/l/fair-mos-desc.html` and its title. Back returns to `/` with search visible and empty (the query is not kept, spec §6).
  - Loading `/c/ABT.html` at 1440 shows the ABT row inside the list pane.
  - Tab from a fresh load: the first stop is "Skip to analysis", and Enter puts the next Tab inside the detail.
- [ ] **Step 5:** full gate, then commit `fix(#262): title, pushed filters, skip link and deep link follow the reader`

## Grilling

Two rounds, griller model `fable`. Round 1 asked 17 questions and round 2 asked 17, 34 in all.

Every answer is sourced:
- **CODE (24):** `svg.py:80-84`, `:144`, `:149-161`, `:205`; `app.css:10-15`, `:89-91`, `:120`, `:137-144`, `:222`; `_rows.html:4`, `:6`; `_controls.html` `empty_detail`; `base.html:13-14`; `list.html:3`; `site.py:157-163`, `_write_company`; `views.py:129-130`; the vendored `htmx.min.js` history-cache writer (`historyCacheSize<=0` → `sessionStorage.removeItem("htmx-history-cache"); return`); `tests/unit/test_web_assets.py:137-141`; `tests/unit/test_web_svg.py:84-96`.
- **ISSUE (4):** "Fix every P0, P1 and P2 finding", "A P3 may be declined with one line of reason".
- **DOC (4):** spec §2, §5 and §6; CONTEXT.md Verdict.
- **NO SOURCE → technical assumption (2):** the geometry is checked in the browser only, and the 16px text is scoped by `pointer: coarse`.

The plan changed in these places:
- history cache off;
- `pointer: coarse`;
- double `content` declaration for the arrow;
- one `aria-label` on both `#detail` variants;
- DESIGN.md step;
- the stop condition for the ledger trims;
- the tests to rewrite are named.

**Spec ambiguities:** none. **Out-of-scope issues opened:** none.

Result: `ok`.
