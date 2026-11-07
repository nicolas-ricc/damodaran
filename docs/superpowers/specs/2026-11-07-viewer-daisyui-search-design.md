# Analysis viewer: DaisyUI restyle and company search

**Date:** 2026-11-07
**Status:** approved design, pending implementation
**Scope:** the read-only web viewer built by `bot site` (`src/bot/web/`). Nothing else.

## 1. Goal

Replace the viewer's hand-written "Rim" visual system with DaisyUI 5 components under a
single dark theme (the user's synthwave variant), so every control on the site comes from
one component library, and add a search box that filters the company list by ticker or
name as the reader types.

Success looks like:

- Every visible control (bar, filter tabs, table, badges, count, empty state, inputs) is a
  DaisyUI component styled by the theme variables, not by bespoke rules.
- The list can be narrowed by typing part of a ticker or a name, combined with the verdict
  filter, with the count and a screen-reader announcement following along.
- `bot site` is still pure Python over committed files. No Node, no build step, no CDN.
- The site passes an impeccable `critique` and `audit` with every finding resolved.

## 2. Non-goals

- The per-company HTML reports written by `bot analyze` under `reports/<date>/`.
- `docs/plano/` and `docs/leccion/` (they keep their own hand-drawn system).
- A theme switcher, light mode, or more than one theme.
- Persisting the search text in the URL, or a server-side search.
- Tailwind utilities. The precompiled DaisyUI CSS is used alone.

## 3. Assets and vendoring

- `src/bot/web/static/daisyui.css`: the precompiled DaisyUI 5 stylesheet, downloaded
  from the pinned release (the npm package's `daisyui.css`, which includes the component
  classes and the built-in light/dark themes). A new `scripts/vendor_daisyui.sh` downloads
  it for a given version, verifies a SHA-256 recorded in the script, and writes the file.
  `static/VERSIONS` gains a line for DaisyUI (version, licence, URL), like the htmx line.
- `src/bot/web/static/theme.css`: the custom theme, as DaisyUI documents for the
  precompiled build: a `[data-theme="synthwave"]` block setting `color-scheme: dark` and
  these variables, taken verbatim from the theme the user chose in the generator:

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

- `base.html` sets `<html lang="en" data-theme="synthwave">` and links, in order,
  `daisyui.css`, `theme.css`, `app.css`. No other theme is loaded or selectable.
- The Switzer and Geist Mono fonts stay vendored and preloaded. `app.css` keeps the
  `@font-face` rules and sets `font-family` on `body` and on figures (`.num`, `code`,
  tabular numerals), because DaisyUI does not fix typography.
- `_copy_static` in `site.py` already copies the whole `static/` tree; nothing to change
  there beyond the new files being present.

## 4. Semantic colour map

DaisyUI's roles replace the Rim notation one to one:

| Meaning in the viewer | Rim token (removed) | DaisyUI role |
|---|---|---|
| Interface state: current filter, sorted column, selected row, focus ring, caret | ember / ember-focus | `primary` |
| Intrinsic value: dot, band, driver bars, label | sky | `secondary` |
| Undervalued | verdict green | `success` |
| Fair | verdict amber | `warning` |
| Overvalued | verdict red | `error` |
| Page, ledger well, deep well | paper / paper-well / paper-deep | `base-100` / `base-200` / `base-300` |
| Headings and figures, body copy, labels | ink / ink-body / muted | `base-content` at 100%, and `base-content` at reduced opacity for body and labels, never below 4.5:1 |
| Rules | rule / rule-faint | `base-300` and `base-content` at low opacity |

`app.css` and `svg.py` read `var(--color-success)` etc. The `hatch` pattern for the
overvalued glyph keeps its stroke on `var(--color-error)`.

## 5. Templates: what becomes a DaisyUI component

- **Header bar**: `navbar` with the brand link in `navbar-start` and the company count in
  `navbar-end` as a `badge badge-ghost`.
- **Verdict filter**: `tabs tabs-box` (or `join` of `btn btn-sm`; the implementer picks
  the one that reads best after `shape`). Each item stays an `<a>` with its `href`,
  `hx-get`, `hx-target="#rows"` and `aria-current="page"` exactly as today; the active one
  carries `tab-active` / `btn-active`. The per-verdict count inside each item is a small
  `badge`.
- **Search**: see section 6.
- **Count**: the `<output id="count">` becomes a `badge badge-neutral`, still `aria-live`.
- **Table**: `table table-sm table-pin-rows` with `table-zebra` off (zebra fights the
  selected-row highlight). The selected row uses `bg-base-300` plus the `primary` square
  glyph before the ticker, as today. No coloured side-stripe border or inset shadow on the
  row: impeccable bans that pattern.
  Sortable column heads keep their `<a>` with `aria-sort` on the `<th>`.
- **Verdict glyphs and value sparkline**: unchanged SVG, recoloured through the map above.
- **Flags**: `badge badge-xs` per flag, coloured by the flag's severity (`badge-error`,
  `badge-warning`, `badge-info`), keeping the `title` and `sr` text.
- **Empty list state** ("No analyses yet") and **empty detail** ("No company is X yet"):
  `hero` body with a `btn btn-link` for the "Show all" action. The `code` sample keeps the
  mono font.
- **Detail pane**: the facts strip becomes a `stats stats-vertical lg:stats-horizontal`
  block; the lead figure is `stat-value text-secondary`. The drivers and scenario grids
  stay plain tables with the `table table-xs` classes. Section rules use `divider`.
- **404**: `hero` with a `btn btn-primary` back link.

What stays in `app.css` because DaisyUI has no component for it: the split grid
(list pane sticky at ≥1100px, detail pane beside it), the `body.page-list` /
`body.page-detail` switching under 1100px, the container queries inside the detail pane,
the `.sr` utility, the htmx `htmx-request` indicator styles, the focus handling, the value
axis and the SVG sizes. Each rule that survives must read a DaisyUI variable, never a
literal colour.

## 6. Search

**Markup** (in `_controls.html`, rendered inside `list-controls` beside the filter):

```html
<label class="input input-sm" id="search" hidden>
  <span class="sr">Search by ticker or name</span>
  <input type="search" autocomplete="off" spellcheck="false" placeholder="Ticker or name" aria-controls="rows">
</label>
```

It is `hidden` in the static HTML and `viewer.js` removes the attribute on load, so a
browser without JavaScript never shows a control that cannot work. Filter and sort links
keep working without JavaScript as they do today.

**Behaviour** (`viewer.js`):

- On `input`, normalise the query (trim, case-fold). For each `tr` in `#rows`, read the
  ticker cell and the name cell; the row is shown when either contains the query as a
  substring, and hidden with the `hidden` attribute otherwise. Empty query shows all rows.
- The verdict filter remains an htmx swap of `#rows`; after `htmx:afterSettle` on `#rows`,
  the current query is applied again to the new rows, so filter and search compose as AND
  and the search survives a sort or filter change.
- `#count` shows `<visible> of <total>` where `<total>` is the site-wide total already in
  the template, and `<visible>` counts rows not hidden. Because `#count` is `aria-live`,
  screen readers hear the new count; no second announcement is made.
- When no row matches, an inert `tr` with a `td colspan="9"` is appended (one, reused)
  reading `No company matches "<query>".` with a `btn btn-link btn-xs` "Clear search" that
  empties the input and refocuses it. The existing "No company is X yet" row from the
  server is left alone.
- The row selection marker (`markSelected`) ignores hidden rows; the selected company can
  be hidden by the search, which is fine.
- Pressing Escape in the input clears it (native `type="search"` behaviour in most
  browsers; `viewer.js` also handles it explicitly so it is consistent).
- Nothing is written to the URL or storage.

## 7. Documentation

- `docs/DESIGN.md` is rewritten for the new system: the theme variables above as the
  colour tokens, the semantic map of section 4, the typography (unchanged), radius 0,
  and the component list of section 5 expressed as DaisyUI classes. The "Night Ledger"
  north star paragraph is replaced by one that describes this system in its own terms.
- New ADR `docs/adr/0010-viewer-styled-with-precompiled-daisyui.md`: decision to vendor
  the precompiled DaisyUI CSS with a single custom theme; alternatives considered
  (Tailwind standalone with a build step, full Node toolchain, CDN) and why each was
  rejected (build step and binary to maintain; a second ecosystem in a Python repo; a
  browser-side compiler and a runtime external dependency). Consequences: the whole
  component CSS ships even when unused; theme changes are edits to `theme.css`;
  upgrading DaisyUI is `scripts/vendor_daisyui.sh <version>` plus a `VERSIONS` line.
- `docs/adr/0008-read-only-web-viewer.md`: the "Visual system" bullet gets a one-line
  note that it is superseded by ADR 0010.
- `CONTEXT.md` needs no change (no new domain term).

## 8. Testing

- Existing `tests/web_sidecars.py` keeps passing.
- New assertions on the generated site: `index.html` has `data-theme="synthwave"` on
  `<html>` and links `daisyui.css`, `theme.css`, `app.css` in that order; `static/`
  in the output contains `daisyui.css` and `theme.css`; `index.html` contains the search
  `label#search` with its `sr` text and `hidden` attribute; each filter link still has
  `href` and `hx-get`; `theme.css` contains every variable of section 3 (a test that reads
  the list from the test, so a dropped variable fails).
- `scripts/vendor_daisyui.sh` is not run in CI; a test asserts the vendored
  `daisyui.css` SHA-256 matches the one in the script, so a hand edit of the vendored
  file is caught.
- Manual, in the PR description: screenshots of index and a detail page at 390px and
  1440px, with and without a search query, and one with JavaScript disabled.

## 9. Process requirements for the implementing agent

- Run `/impeccable shape` on the viewer before writing code, to plan the layout and
  component choices within this spec (not to reopen the scope).
- After implementation, run `/impeccable critique` and `/impeccable audit` on the
  generated site (`bot site --out site`, served locally). Every P0/P1/P2 finding is fixed
  in the same branch; a P3 may be rejected with one line of reason in the PR. No
  follow-up issue is opened for anything found by these passes.
- `ruff`, `mypy` and `pytest` green, as CI already requires.
