---
name: Analysis viewer
description: The read-only web viewer of the bot's company analyses, styled by precompiled DaisyUI under a single custom dark theme, synthwave.
colors:
  base-100: "oklch(15% 0.09 281.288)"
  base-200: "oklch(20% 0.09 281.288)"
  base-300: "oklch(25% 0.09 281.288)"
  base-content: "oklch(78% 0.115 274.713)"
  primary: "oklch(71% 0.202 349.761)"
  primary-content: "oklch(28% 0.109 3.907)"
  secondary: "oklch(82% 0.111 230.318)"
  secondary-content: "oklch(29% 0.066 243.157)"
  accent: "oklch(75% 0.183 55.934)"
  accent-content: "oklch(26% 0.079 36.259)"
  neutral: "oklch(45% 0.24 277.023)"
  neutral-content: "oklch(87% 0.065 274.039)"
  info: "oklch(74% 0.16 232.661)"
  info-content: "oklch(29% 0.066 243.157)"
  success: "oklch(77% 0.152 181.912)"
  success-content: "oklch(27% 0.046 192.524)"
  warning: "oklch(90% 0.182 98.111)"
  warning-content: "oklch(42% 0.095 57.708)"
  error: "oklch(73.7% 0.121 32.639)"
  error-content: "oklch(23.501% 0.096 290.329)"
typography:
  display:
    fontFamily: "Switzer, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.074rem"
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Switzer, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.728rem"
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Switzer, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.2rem"
    fontWeight: 500
    lineHeight: 1.05
  body:
    fontFamily: "Switzer, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Switzer, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.55
  figure:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "1rem"
    fontWeight: 400
    fontVariation: "tabular-nums lining-nums"
rounded:
  none: "0"
spacing:
  2xs: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  2xl: "64px"
  3xl: "96px"
components:
  filter:
    classes: "join btn btn-sm join-item btn-active badge badge-sm badge-ghost"
  count:
    classes: "badge badge-neutral"
  search:
    classes: "input input-sm"
  table-row:
    classes: "table table-sm table-pin-rows selected bg-base-300"
  flags:
    classes: "badge badge-xs badge-sm badge-success badge-warning badge-error badge-ghost"
  empty-state:
    classes: "hero hero-content btn btn-link btn-primary"
  facts:
    classes: "stats stats-vertical lg:stats-horizontal stat stat-title stat-value text-secondary"
  history:
    classes: "join btn btn-xs join-item btn-active"
---

# Design System: Analysis viewer

## 1. Overview

**Creative North Star: "The Synthwave Instrument"**

The viewer is read at a desk, beside a terminal, late. It lists the companies the bot has analysed and, for each one, shows why it got its verdict. It is an instrument, not a drawing: the hand-drawn system of the explanatory pieces (`docs/plano/DESIGN.md`) stops at its door. Every number on the page says where it came from, and the page admits what it does not know.

The system has one component library, one theme and one rule for colour. The library is DaisyUI, vendored as a precompiled stylesheet (ADR 0011), so every control is a DaisyUI component: `navbar`, `join`, `btn`, `badge`, `input`, `table`, `stats`, `hero`, `divider`. The theme is `synthwave`, a single dark theme defined in `static/theme.css` and selected by `data-theme="synthwave"` on the page; no other theme is selected (DaisyUI's built-in `light` and `dark` ship in the stylesheet but are never applied). `static/app.css` holds only what DaisyUI has no component for (the split layout, typography, the charts) and reads DaisyUI variables rather than literal colours. Colour is notation: each DaisyUI role carries one meaning on every screen (section 2).

The system is dark only, by decision. One grotesk sans carries every label and sentence; a mono carries every figure, date and identifier so that a number is recognisable as a number before it is read.

The product brief rejects the fintech dashboard (navy and gold, big metric cards, green lines), the SaaS landing page (gradients, identical cards), the Confluence diagram and the editorial-typographic lane. DaisyUI's stock components are used flat and small (`btn-sm`, `badge-xs`, `table-xs`), with one lead figure and no ornament.

**Key Characteristics:**
- Dark, one theme, radius 0. Depth from three base tones and rules.
- One sans for words, one mono for figures. The mono is a signal, not a style.
- Colour is semantic: three verdict roles, one intrinsic-value role, one interface role.
- Charts that do not shrink their text: HTML labels beside scaled SVG, tables where a chart would hide the numbers.
- Everything is a real link to a real page; htmx only makes it faster.

## 2. Colors: Synthwave

The 20 colour variables of `[data-theme="synthwave"]`, listed in the frontmatter. The roles the viewer uses, and what each means:

| Meaning in the viewer | DaisyUI role | Value |
|---|---|---|
| Interface state: current filter, sorted column, selected row marker, focus ring, caret, primary action | `primary` | `oklch(71% 0.202 349.761)` |
| Intrinsic value: the dot and band on the axis, driver bars, the MoS figure | `secondary` | `oklch(82% 0.111 230.318)` |
| Undervalued; a passed check | `success` | `oklch(77% 0.152 181.912)` |
| Fair; a warning flag | `warning` | `oklch(90% 0.182 98.111)` |
| Overvalued; a failed check | `error` | `oklch(73.7% 0.121 32.639)` |
| Page | `base-100` | `oklch(15% 0.09 281.288)` |
| Ledger well (the list pane) | `base-200` | `oklch(20% 0.09 281.288)` |
| Deep well: the selected row, borders and rules | `base-300` | `oklch(25% 0.09 281.288)` |
| Headings, figures and text | `base-content` | `oklch(78% 0.115 274.713)` |
| Body copy and ledes | `--ink-soft`, derived from `base-content` | 80% `base-content` mixed into `base-100` |
| Row rules | `--rule-faint`, derived from `base-content` | 12% `base-content` over transparent |
| Count badge | `neutral` | `oklch(45% 0.24 277.023)` |

`--ink-soft` and `--rule-faint` are the only two tokens `app.css` derives; everything else is a DaisyUI variable. The remaining roles of the theme (`accent`, `info`, and every `*-content` colour) are defined so that DaisyUI components render correctly, and carry no meaning of their own in the viewer. Each `*-content` colour is the text on its role: `neutral-content` `oklch(87% 0.065 274.039)` on the count badge, `primary-content` `oklch(28% 0.109 3.907)` on the primary button, and likewise `secondary-content` `oklch(29% 0.066 243.157)`, `accent-content` `oklch(26% 0.079 36.259)`, `info-content` `oklch(29% 0.066 243.157)`, `success-content` `oklch(27% 0.046 192.524)`, `warning-content` `oklch(42% 0.095 57.708)` and `error-content` `oklch(23.501% 0.096 290.329)`. `accent` is `oklch(75% 0.183 55.934)` and `info` is `oklch(74% 0.16 232.661)`.

### Named Rules
**The Notation Rule.** A colour means one thing on every screen. Success, warning and error are verdicts; secondary is intrinsic value; primary is the interface. If a new element needs colour and none of those meanings fit, it is drawn in `base-content` or `--ink-soft`.

**The Shape-First Rule.** No verdict is told by colour alone. The check, the open circle, the hatched gate and the dash carry the verdict in greyscale; the pigment confirms it. The hatch pattern of the overvalued glyph strokes with `var(--color-error)`.

**The Contrast Floor Rule.** Text is `base-content` or `--ink-soft`, never lighter than 4.5:1 against its surface. A label that needs to recede goes smaller or lighter in weight, not greyer.

## 3. Typography

**Display Font:** Switzer (with ui-sans-serif, system-ui)
**Body Font:** Switzer (with ui-sans-serif, system-ui)
**Label/Mono Font:** Geist Mono (with ui-monospace)

**Character:** One grotesk with two weights carries the whole tool; the mono appears only where the content is a figure, a date or a code identifier. The contrast between them is the hierarchy: a line set in mono is data, a line set in sans is the sentence about it. DaisyUI does not fix typography, so `app.css` sets the families on `body` and on figures.

### Hierarchy
- **Display** (500, 2.074rem, 1.05): the ticker in the detail head. The only display-size text on the page.
- **Headline** (500, 1.728rem, 1.05): the lead figure (MoS) in the facts strip, set in mono.
- **Title** (500, 1.2rem, 1.05, -0.03em): section headings, the company name beside the ticker, the DCF summary.
- **Body** (400, 1rem, 1.55): the verdict note, the ledes, flag reasons. Capped at 60ch.
- **Label** (500, 0.875rem): column heads, facts labels, filter buttons. Sentence case, never tracked, never uppercase.
- **Figure** (400, mono, tabular lining numerals): every number, date, ratio and identifier.

### Named Rules
**The Mono Means Data Rule.** Geist Mono is never used for a word that is not a value, a date, a ticker or an identifier out of the analysis code. Labels and sentences stay in Switzer.

**The Fixed Scale Rule.** Sizes come from the rem scale (0.875, 1, 1.2, 1.44, 1.728, 2.074). No `clamp()`; the layout reflows structurally instead.

## 4. Elevation and shape

The theme sets these shape variables, and DaisyUI components read them:

- **Radius 0.** `--radius-selector`, `--radius-field` and `--radius-box` are all `0rem`: buttons, badges, inputs and boxes are square.
- **`--border: 1px`.** The border width of buttons, inputs and badges, and of the dashed separators between stacked stats. The viewer's own rules use `--rule-hair` in `app.css`, also 1px.
- **`--depth: 1`.** Scales DaisyUI's relief on buttons (an inset highlight, a text shadow and a small drop shadow) and on inputs (inset shadows). Badges ignore it. It is the only elevation the theme adds.
- **`--noise: 1`.** Turns on DaisyUI's fine grain texture on buttons and badges.

`--size-selector` and `--size-field` are `0.25rem`, the base unit DaisyUI scales its control sizes (`-xs`, `-sm`) from.

Beyond that, depth is tonal: the page is `base-100`, the list pane sits on the lighter `base-200`, and the selected row is set on `base-300`, the lightest of the three. 1px rules separate rows, and DaisyUI's `divider` separates the detail sections. The viewer's own CSS adds no shadow, blur or glow; the only shadows are the depth-scaled ones DaisyUI puts on buttons and inputs.

### Named Rules
**The Flat Well Rule.** If an element needs to come forward, it gets a lighter surface (`base-200`, then `base-300` for the selected row) or a rule above it, never a shadow of its own.

## 5. Components

Each component is the DaisyUI classes that ship in `src/bot/web/templates/` and `src/bot/web/svg.py`. The flag tones `badge-success`, `badge-warning`, `badge-error` and `badge-ghost` are composed as `badge-{{ f.tone }}` from `FlagView.tone` in `src/bot/web/views.py`.

### Header bar
`navbar` with the brand link in `navbar-start` and the company count in `navbar-end` as `badge badge-ghost`.

### Filter
A `join` of `btn btn-sm join-item` links, so the row reads as one segmented control; it wraps to a second row rather than scrolling. Each link is a real `<a>` with `aria-current="page"` on the current one, which also carries `btn-active`. The verdict count inside each link is `badge badge-sm badge-ghost`, set in mono. The current filter reads in `primary`. A filter or sort also pushes its `l/` URL (`hx-push-url` equal to the link's `href`) and the swapped fragment carries a `<title>`, so the address and the tab name follow the reader. The htmx history cache is off (`historyCacheSize: 0`): Back reloads the pushed static page instead of restoring a snapshot, so nothing the reader typed reaches storage.

### Count
`badge badge-neutral`, an `<output>` with `aria-live="polite"` that says how many of the total rows show.

### Search
`input input-sm` on a `<label>`, hidden until the script that filters the rows is running, so without JavaScript the control never appears. It matches ticker, name and industry tags; the tags stay out of the table (a `data-tags` attribute on the row). Its border is `base-content` mixed to about half strength so the box reads as a field on the dark ground, and the placeholder sits on `--ink-soft`.

### Table row
`table table-sm table-pin-rows`: the column heads stay pinned while the rows scroll. The ticker is a link; figures are right-aligned in mono; the verdict and flag glyphs are titled for screen readers, and a decorative mini value axis (hidden from screen readers) follows the MoS. The selected row is `selected bg-base-300`, with a `primary` square before the ticker. Sort links are the column heads themselves, with `aria-sort` on the `<th>` and the current one in `primary`; the arrow is declared with an empty alt text so it is not part of the column's name. Beside the detail (1100px and up) the ledger drops Story and Intrinsic, since the facts strip names both. On a phone the row is one link: the ticker's link stretches over the whole row.

### Flags
In the list, `badge badge-xs badge-{tone}` holding a flag glyph; in the detail pane, `badge badge-sm badge-{tone}` holding the severity word. The tone comes from the flag's severity: `badge-success` for a pass, `badge-warning` for a warning, `badge-error` for a fail, and `badge-ghost` for anything else.

### Empty states and 404
`hero` with `hero-content`. The empty list, the empty filter and the 404 each say what is missing and offer one way forward. The empty list shows the command that fills it (`bot analyze --from-screen`). The empty filter offers `btn btn-link` in the detail hero, and `btn btn-link btn-xs` in the empty row of the list. The 404 page offers `btn btn-primary`.

### Facts
`stats stats-vertical lg:stats-horizontal` holding five `stat` blocks (MoS leading, then price, intrinsic, story, date), each with `stat-title` and `stat-value`. The MoS value is `stat-value text-secondary`, the lead figure of the page. In a narrow pane the strip is two columns, with MoS spanning both.

### Skip link and analysis region
The first stop on every page with an analysis is `skip btn btn-sm btn-primary`, "Skip to analysis", parked above the viewport and brought down on focus. It is hidden under 1100px on the list page, where the detail pane is not shown. `#detail` is a labelled region (`aria-label="Analysis"`, `tabindex="-1"`) so the skip link lands inside it; it takes focus without an outline because it is a jump target, not a control. A page opened on a company scrolls the list pane so the selected row is in view.

### History
`join` of `btn btn-xs join-item` links, one per analysis date, with `btn-active` and `aria-current="page"` on the date shown.

### Section heads and tables
Each section is separated by `divider`, then the title, an optional count line, then one lede sentence saying what the section shows and how to read it. The drivers, scenarios, assumptions and DCF tables are `table table-xs`. The scenario grid and the DCF table share one `.scroll` wrapper, so a table wider than the pane scrolls inside its box rather than the page. The value axis is an SVG that scales with non-scaling strokes; its labels are HTML positioned by percentage so they never shrink.

## 6. Do's and Don'ts

### Do:
- **Do** build a new control from a DaisyUI component before writing CSS; add to `app.css` only what DaisyUI has no component for.
- **Do** read colours from DaisyUI variables (`var(--color-primary)`), never from a literal.
- **Do** keep every control reachable by keyboard and keep focus on the control that was activated after a swap.
- **Do** set figures, dates and identifiers in Geist Mono with tabular numerals, right-aligned in tables.
- **Do** explain a chart in one sentence under its heading, and name the thresholds the verdict depends on (1.0x, 1.3x).
- **Do** give every verdict a shape and a title as well as a colour.
- **Do** reflow on the detail pane's own width (container queries), not the window's.
- **Do** keep text out of scaled SVG; label with HTML or use a table.

### Don't:
- **Don't** build the fintech dashboard: no navy and gold, no big metric cards, no green lines.
- **Don't** build the SaaS landing page: no gradients, no isometric illustration, no grid of identical cards.
- **Don't** build the Confluence diagram: grey boxes, straight arrows, system type, no hierarchy.
- **Don't** take the editorial-typographic lane: italic serif display, mono labels, rules and monochrome.
- **Don't** load a second theme or add a light mode; the viewer is dark only.
- **Don't** use `primary` on content or on a verdict; it belongs to the interface's state.
- **Don't** use `table-zebra`; it fights the selected-row highlight.
- **Don't** use `border-left` or `border-right` wider than 1px as a coloured stripe.
- **Don't** use gradient text, glass, blur, drop shadows, bounce or elastic easing.
- **Don't** gate any content on an animation; motion is 120 to 220ms, opacity and a 4px rise, and disappears under reduced motion.
- **Don't** ship session notes, provenance comments or unused tokens in the stylesheet.
