# Detail pane as DaisyUI components — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (`.agents/skills/subagent-driven-development/SKILL.md`, per AGENTS.md) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The detail pane of the site built by `bot site` (`f/<TICKER>.html` fragments and the `#detail` section of `c/<TICKER>.html`) is drawn with DaisyUI components: a `stats` facts strip, `divider` section rules, a `join` of `btn btn-xs` history links, `table table-xs` tables and severity `badge`s in the flag list.

**Architecture:** Markup changes live in `src/bot/web/templates/detail.html` and the two table builders of `src/bot/web/svg.py`. `src/bot/web/static/app.css` (unlayered, so every rule in it beats the layered `daisyui.css`) loses the hand-drawn rules the components replace and keeps or adjusts only the layout rules that make the tables into charts. `src/bot/web/static/viewer.js` follows the MoS to its new node.

**Tech Stack:** Jinja2 templates, Python string builders (`svg.py`), plain CSS over vendored DaisyUI 5.7.50, vanilla JS, pytest. Node is used only by the existing `node --check` test.

**Spec:** issue #260 (child of story #257). Its "Decisions" and "Acceptance criteria" sections are binding and quoted verbatim below where they pin a string. Background: `docs/superpowers/specs/2026-11-07-viewer-daisyui-search-design.md` §5 ("Detail pane").

## Global Constraints

- `app.css` stays free of literal colours (`oklch(`, `rgb(`, `hsl(`, hex) and of `box-shadow: inset` (existing `test_css_reads_daisyui_variables_only`, `test_hand_drawn_controls_are_gone`).
- Every `href`, `hx-get`, `hx-target="#detail"`, `hx-swap="innerHTML settle:220ms"`, `hx-push-url`, `hx-indicator="#detail"` and `aria-current="page"` on the history links stays exactly as today.
- Every existing cell class (`cell cell-undervalued`, `cell-none`, `num`, `low`, `high`, `track`, `track-head`, `shock`, `src`, `axis`, `corner`) and every `scope` stays.
- Unchanged: the verdict line (`p.verdict` with the glyph and `.verdict-text`), `.instrument` with `background: var(--color-base-200)`, the value axis, the `pair-grid` container queries, the DCF `<details>` and its totals.
- Out of scope (other children of #257): `docs/DESIGN.md`, ADR 0010 and the ADR 0008 note (#261); the impeccable passes and screenshots (#262). The list pane is untouched.
- Commits use Conventional Commits with the `(#260)` scope. `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Assumptions (declared, not in the issue's text; rejected alternative in brackets)

1. **The `.history` rule shrinks to font-family only.** The issue says "Delete the `.history a` rules in `app.css` (keep `.history { font-family: var(--font-mono); }`)". Today's rule is `.history { gap: var(--space-2xs) var(--space-sm); font-family: var(--font-mono); }`. The gap goes, because `join-item`s are meant to touch, and the rule becomes exactly `.history { font-family: var(--font-mono); }`. `tests/unit/test_web_assets.py::test_list_pane_rules_restore_what_daisyui_overrides` (from #259) pins the old string, so it is updated to the new one. The shared `#filter, .history { display: flex; flex-wrap: wrap; … }` rule stays, so a long history still wraps. [Rejected: keeping the gap. It splits the join into loose buttons.]
2. **The table rows keep the pane's type size.** DaisyUI's `.table-xs :not(thead,tfoot) tr { font-size: .6875rem }` puts the font size on the `tr`, so the existing `.tornado { font-size: var(--text-sm) }` on the table no longer reaches the cells (11px instead of 14px). This is the same fight #259 settled for the list with `.list tbody tr { font-size: inherit; }`. One rule, `.table-xs tr { font-size: inherit; }`, restores it for all four tables. [Rejected: accepting 11px. The issue says `table-xs` is there to tighten padding, not to shrink the text.]
3. **The scenario grid cells lose DaisyUI's row rule.** `.table :where(thead tr :is(td,th), tbody tr:not(:last-child) :is(td,th))` draws a 5% bottom border under every cell, which would cut through the tinted squares. `.scenario-grid th, .scenario-grid td` gains `border: 0`. The tornado and DCF cells already set their own `border-bottom`, and the assumptions cells already set `border: 0`.
4. **The DCF divider sits on its summary.** The divider before `<details class="dcf">` is a direct child of `#detail`, so `#detail > * + * { margin-top: var(--space-2xl); }` would put 64px between the rule and the summary. `#detail > .divider + .dcf { margin-top: 0; }` keeps the pair together, so the divider takes the section gap, as the in-section dividers do. The issue's "`.divider { margin: 0 0 var(--space-xs); }` is the only override" is read as "the only override of the divider component". This rule overrides the pane's spacing, not the divider. [Rejected: putting the divider inside `<details>`. The issue says "before `<details class="dcf">`".]
5. **The facts strip keeps its distance from the verdict note.** The old `.facts { margin: var(--space-lg) 0 0; padding-top; border-top }` loses its border and padding, and `margin-top: var(--space-lg)` stays as `.facts { margin-top: var(--space-lg); }`. No other spacing on `.stat` changes; any further tuning belongs to the #262 critique. *Measured after implementation (commit 3f42f13):* DaisyUI's 2rem values with 1.5rem stat padding put the horizontal strip up to 126px past the instrument at 1440px (MCK). So `.facts { max-width: 100%; }`, `.facts .stat { padding-inline: var(--space-md); }`, `.facts .stat-value.num { font-size: var(--text-xl); }` and `.facts .lead-figure .stat-value { font-size: var(--text-3xl); }` (the size hierarchy from before this branch) were added. In stage 6 the review restored `.facts time { font-family: var(--font-mono); }`, because dates are mono per `docs/DESIGN.md`.
6. **"`fail` follows `badge badge-sm badge-error`" means the badge's own text.** The test reads `<span class="badge badge-sm badge-error">fail</span>` inside `section.flag-list`.
7. **Tasks run strictly in order, 1 → 5.** All five edit `detail.html` and `app.css`, and Task 2's `.facts` assertion reads the rule Task 1 leaves. A task whose commit is reverted reverts every later task too. The red intermediate commits stay local: the branch is pushed only after the full suite is green, and CI (`.github/workflows/site.yml:23`) runs `pytest` only on what is pushed.
8. **Table heads stay `nowrap`.** DaisyUI's `.table :where(thead,tfoot)` sets `white-space: nowrap; font-size: .875rem; font-weight: 600` and a 60% colour. Every `<th>` in the tornado and DCF heads sets its own weight and colour (`.tornado thead th`, `.dcf th`), as do the scenario-grid `th` (`.scenario-grid th`, `thead .axis`). `.875rem` is `--text-sm`. Only `nowrap` reaches them. The heads are short labels, and the scenario axis label wrapping at 390px is left to the #262 critique. *Measured after implementation (commit 3f42f13):* `nowrap` widened the scenario grid from 355px to 372px, so `.scenario-grid thead { white-space: normal; }` was added. `.table` also dropped the assumption rows from 16px to 14px, which `.assumptions-table { font-size: var(--text-md); }` restores. In stage 6, `.history .btn { font-weight: 400; }` was added, because Geist Mono ships only at weight 400 and `.btn`'s 600 would otherwise be synthesised.
9. **The stage-3 evals come first.** They are written before any implementation, in a separate `test(#260): evals` commit. Each task's Step 1 checks that its tests exist and fail; if any are absent, the implementer writes them as listed.

## Review Focus

1. **11px table text** (assumption 2): the drivers, scenario, assumptions and DCF rows would shrink silently. Pinned in Task 4 (`.table-xs tr { font-size: inherit; }` present).
2. **Faint lines through the scenario cells** (assumption 3). Pinned in Task 4 (`border: 0` in the `.scenario-grid th, .scenario-grid td` rule).
3. **An older analysis date marks the right link.** On `f/AAA/2026-09-01.html`, exactly one link has `btn-active` and `aria-current="page"`, and it is the `2026-09-01` one. Pinned in Task 3.
4. **The full page carries the same detail as the fragment.** `c/AAA.html` has the `stats` strip, the `history join` and the `table table-xs` tables, and `test_ids_are_unique_per_page` still passes. Pinned in Tasks 1, 3 and 4.
5. **The DCF rule floating 64px above its summary** (assumption 4). Pinned in Task 2 (`#detail > .divider + .dcf { margin-top: 0; }` present).

---

### Task 1: Facts strip as `stats`

**Files:**
- Modify: `src/bot/web/templates/detail.html` (the `<dl class="facts">` block)
- Modify: `src/bot/web/static/app.css` (the `.facts` rules and the two `@container (min-width: 28rem|44rem)` blocks that reflow it)
- Modify: `src/bot/web/static/viewer.js` (`announceDetail`)
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_assets.py`, `tests/unit/test_web_viewer_js.py`

**Interfaces:**
- Produces: `#detail .facts .lead-figure .stat-value` holds the MoS text. `viewer.js` reads it.

- [ ] **Step 1: Failing tests** (from the evals commit):
  - `test_web_site.py::test_detail_facts_are_stats`: for `f/AAA.html` and `c/AAA.html`, the page contains `class="stats stats-vertical lg:stats-horizontal facts"`; `html.count('class="stat ') + html.count('class="stat"') == 5` (five `.stat` blocks, never counting `stat-title`/`stat-value`); `html.count('class="stat lead-figure"') == 1`; `'<div class="stat-value text-secondary num">' in html`; `html.count('class="stat-value word') == 2` (Story is `stat-value word story`, Date is `stat-value word`, and the Date value contains `<time datetime="2026-10-01">`). No built HTML file contains `<dl class="facts">`.
  - `test_web_assets.py::test_detail_facts_rules`: `app.css` contains `.facts .stat-value { font-weight: 500; letter-spacing: -0.03em; }`, `.facts .stat-value.word { font-size: var(--text-lg); }`, and an `@container (max-width: 44rem) {` block with `.facts.stats { grid-auto-flow: row; }` and `.facts.stats .stat:not(:last-child) { border-inline-end: none; border-block-end: var(--border) dashed var(--rule-faint); }`. It no longer contains `.facts dd`, `.facts dt`, `.facts > div`, `@container (min-width: 28rem)` or `@container (min-width: 44rem)`.
  - `test_web_viewer_js.py::test_announce_reads_the_stat_value`: the script contains `"#detail .facts .lead-figure .stat-value"` and not `.lead-figure dd`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_assets.py tests/unit/test_web_viewer_js.py -q`. Expected: the three tests FAIL.
- [ ] **Step 3: Implement.** In `detail.html`, replace the `<dl>` with `<div class="stats stats-vertical lg:stats-horizontal facts">` holding five `<div class="stat">` blocks in the issue's order. Each block is `<div class="stat-title">…</div><div class="stat-value …">…</div>`. Use the issue's MoS block verbatim: `<div class="stat lead-figure"><div class="stat-title"><abbr title="Margin of safety: intrinsic value divided by price">MoS</abbr></div><div class="stat-value text-secondary num">{{ detail.mos }}</div></div>`. Price and Intrinsic use `stat-value num` with today's expressions, Story uses `stat-value word story`, and Date uses `stat-value word` with today's `<time>`. In `app.css`, delete every `.facts …` rule and both `@container (min-width: 28rem)` / `(min-width: 44rem)` blocks, which contain only `.facts` rules. Then add `.facts { margin-top: var(--space-lg); }` (assumption 5), the three rules from Step 1 and the `max-width: 44rem` container block, verbatim. In `viewer.js`, change the selector.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#260): facts strip as DaisyUI stats`.

### Task 2: Section rules as `divider`

**Files:**
- Modify: `src/bot/web/templates/detail.html`
- Modify: `src/bot/web/static/app.css` (`.head-row`, `.dcf summary`)
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_assets.py`

- [ ] **Step 1: Failing tests:**
  - `test_web_site.py::test_detail_sections_are_divided`: `f/AAA.html` has `count('<div class="divider" aria-hidden="true"></div>') >= 5`. In `f/AAA.html` every `<div class="head-row">` is directly preceded (after stripping whitespace) by that divider, and so is `<details class="dcf">`. `f/CCC.html` has fewer dividers than `f/AAA.html`.
  - `test_web_assets.py::test_detail_rules_have_no_top_borders`: for each selector `.head-row`, `.facts` and `.dcf summary`, the rule body found by `re.search(r"(?m)^" + re.escape(sel) + r" \{([^}]*)\}", css)` is not `None` (all three are written `<selector> {` at column 0 today, `app.css`) and has no `border-top`. `.divider { margin: 0 0 var(--space-xs); }` and `#detail > .divider + .dcf { margin-top: 0; }` are present.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_assets.py -q`. Expected: the two tests FAIL.
- [ ] **Step 3: Implement.** Put `<div class="divider" aria-hidden="true"></div>` immediately before each `<div class="head-row">` (Drivers, Scenarios, Flags, Assumptions, Sanity) and before `<details class="dcf">`. In `app.css`, drop `border-top` from `.head-row` and `.dcf summary`, keeping their other declarations. Add the two rules from Step 1.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#260): section rules as DaisyUI dividers`.

### Task 3: History nav as a `join`

**Files:**
- Modify: `src/bot/web/templates/detail.html` (`nav.history`)
- Modify: `src/bot/web/static/app.css` (`.history`, `.history a`)
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_assets.py`

- [ ] **Step 1: Failing tests:**
  - `test_web_site.py::test_detail_history_is_a_join`: `f/AAA.html` and `c/AAA.html` contain `<nav class="history join" aria-label="Analysis date">`. Each has 2 matches of `class="btn btn-xs join-item`, and exactly one link carries both `btn-active` and `aria-current="page"`, the `2026-10-01` link (regex over each `<a …>2026-10-01</a>` tag). On `f/AAA/2026-09-01.html`, the active link is `2026-09-01`. Every history link keeps `href="/c/AAA…"`, `hx-get="/f/AAA…"`, `hx-target="#detail"`, `hx-swap="innerHTML settle:220ms"`, `hx-push-url=` and `hx-indicator="#detail"`. `f/BBB.html` has no `class="history`.
  - `test_web_assets.py`: `test_list_pane_rules_restore_what_daisyui_overrides` expects `.history { font-family: var(--font-mono); }` in place of the old `.history { gap: …; font-family: … }` string. The new `test_history_link_rules_are_gone` asserts `.history a` is not in `app.css`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_assets.py -q`. Expected: those tests FAIL.
- [ ] **Step 3: Implement.** `<nav class="history join" aria-label="Analysis date">`. Each `<a>` gains `class="btn btn-xs join-item{% if d == detail.date %} btn-active{% endif %}"` as its first attribute, and every other attribute stays as it is. In `app.css`, delete `.history a { … }` and replace the `.history { … }` rule with `.history { font-family: var(--font-mono); }` (assumption 1).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#260): history dates as a DaisyUI join`.

### Task 4: Tables as `table table-xs`

**Files:**
- Modify: `src/bot/web/svg.py` (`tornado_table`, `scenario_grid_table`: the opening `<table` tag only)
- Modify: `src/bot/web/templates/detail.html` (assumptions and DCF `<table>`)
- Modify: `src/bot/web/static/app.css`
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_svg.py`, `tests/unit/test_web_assets.py`

- [ ] **Step 1: Failing tests:**
  - `test_web_site.py::test_charts_are_tables_with_html_labels`: the two `<table class="tornado"` / `<table class="scenario-grid"` assertions become `<table class="table table-xs tornado" aria-label="Drivers">` and `<table class="table table-xs scenario-grid" aria-label="Scenarios `. The rest stays.
  - `test_web_site.py::test_detail_tables_are_daisyui_tables`: `f/AAA.html` and `c/AAA.html` contain `<table class="table table-xs assumptions-table">` and `<table class="table table-xs">` (the DCF), and no `<table>` without a class remains in either detail.
  - `test_web_svg.py::test_tables_are_daisyui_tables`: `str(tornado_table(_bars(), price=100.0)).startswith('<table class="table table-xs tornado" aria-label="Drivers">')` and `str(scenario_grid_table(_grid())).startswith('<table class="table table-xs scenario-grid" aria-label="Scenarios 10/24">')`. The existing scope, cell-class, `aria-label`, no-`<text>` and no-literal-colour tests stay unchanged and must pass.
  - `test_web_assets.py::test_detail_table_rules_restore_what_daisyui_overrides`: `app.css` contains `.table-xs tr { font-size: inherit; }`, `.scenario-grid { width: auto;` with `border-spacing: 2px;` in the same rule, `.scenario-grid th, .scenario-grid td { padding: 0; border: 0;`, `.tornado td.track { width: 100%;` and `.assumptions tr { display: grid;`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_svg.py tests/unit/test_web_svg_tornado.py tests/unit/test_web_assets.py -q`. Expected: the new and updated tests FAIL.
- [ ] **Step 3: Implement.** In `svg.py`, change the two class strings and nothing else. In `detail.html`, the assumptions `<table>` becomes `<table class="table table-xs assumptions-table">` and the DCF `<table>` becomes `<table class="table table-xs">`. In `app.css`, add `.table-xs tr { font-size: inherit; }` (assumption 2) and `border: 0;` to the `.scenario-grid th, .scenario-grid td` rule (assumption 3). Keep `.tornado`, `.scenario-grid`, `.assumptions` and `.dcf` as they are otherwise.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#260): detail tables as DaisyUI table-xs`.

### Task 5: Flag list as severity badges

**Files:**
- Modify: `src/bot/web/templates/detail.html` (the `section.flag-list` `<li>`)
- Modify: `src/bot/web/static/app.css` (`.flag-list .severity`, `.flag-list .flag-not-evaluated .severity`)
- Test: `tests/unit/test_web_site.py`, `tests/unit/test_web_assets.py`

**Interfaces:**
- Consumes: `FlagView.tone` (`src/bot/web/views.py:148`): `success` / `warning` / `error` / `ghost`. `FlagView.severity`, `.label`, `.detail`.

- [ ] **Step 1: Failing tests:**
  - `test_web_site.py::test_detail_flags_are_badges`: in `f/BBB.html`, the slice from `<section class="flag-list">` to its `</section>` contains `<span class="badge badge-sm badge-error">fail</span>` and no `class="mark"`. Every `<li class="flag flag-…">` in it starts with `<span class="badge badge-sm badge-` followed by its `<span class="id">` and `<span class="reason">`. No `class="severity"` is left in it.
  - `test_web_assets.py::test_flag_severity_colours_are_gone`: `app.css` has no `.flag-list .severity` and no `.flag-not-evaluated .severity`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_site.py tests/unit/test_web_assets.py -q`. Expected: those tests FAIL.
- [ ] **Step 3: Implement.** Each `<li class="flag flag-{{ f.severity | replace(" ", "-") }}">` holds exactly `<span class="badge badge-sm badge-{{ f.tone }}">{{ f.severity }}</span> <span class="id">{{ f.label }}</span> <span class="reason">{{ f.detail }}</span>`. Delete the two `.severity` rules. The row-cell flags in `_rows.html` keep their glyph.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#260): detail flags as severity badges`.

### Final check

- [ ] `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- [ ] Build the real site with `uv run bot site --out /tmp/site --reports-dir reports --base-url /`, then read one `f/<TICKER>.html` and one `c/<TICKER>.html`. The new markup is there, no `<dl class="facts">` remains, and there are no unclassed `<table>`s in the detail.

## Grilling

- Rounds: 1 (the answers added declarations and test details but left the steps and seams unchanged, so no second round).
- Questions: 18. Answers by source: CODE 14, ISSUE 2, NO SOURCE 2 (both technical assumptions, now numbered 7 and 8 above).
- Answers that corrected the plan: Q10 (ordering, assumption 7), Q7 (table heads, assumption 8), Q12 (the regex must match, Task 2 Step 1), Q9 (red commits stay local, assumption 7).
- Answers that confirmed the plan:
  - `lg:stats-horizontal` exists in the vendored file.
  - `daisyui.css` is fully layered (`@layer base`, `daisyui.*`, `utilities`) and loaded before `theme.css` and `app.css` (`base.html:10-12`).
  - The list table is `table table-sm` (`list.html:20`), so `.table-xs tr` never reaches it.
  - The `pair-grid` container query is `@container (min-width: 46rem)` (`app.css:236`). The 28rem and 44rem `min-width` blocks hold only `.facts` rules (`app.css:181-197`).
  - The DaisyUI row border is on cells, `:is(td,th)`.
  - `detail.date` and the history entries are both `dt.date` (`views.py:214, 231`).
  - `mos` is `"n/a"` without a value (`views.py:421`), so the announcer is unchanged.
  - `badge-ghost` is vendored, and `tone` is pinned by `tests/unit/test_web_views.py::test_flag_tone_follows_severity`.
- Spec ambiguities: none. Follow-up issues opened: none.
