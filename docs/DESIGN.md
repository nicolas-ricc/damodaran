---
name: Analysis viewer
description: The read-only web viewer of the bot's company analyses, in the Rim theme.
colors:
  paper: "oklch(9% 0.008 75)"
  paper-well: "oklch(12.5% 0.009 75)"
  paper-deep: "oklch(6.5% 0.007 75)"
  ink: "oklch(94% 0.010 80)"
  ink-body: "oklch(84% 0.011 80)"
  muted: "oklch(68% 0.012 80)"
  muted-stroke: "oklch(50% 0.010 80)"
  rule: "oklch(25% 0.010 78)"
  rule-faint: "oklch(16% 0.009 78)"
  ember: "oklch(72% 0.17 45)"
  ember-focus: "oklch(78% 0.15 45)"
  sky: "oklch(74% 0.12 250)"
  verdict-under: "oklch(74% 0.15 150)"
  verdict-fair: "oklch(80% 0.13 85)"
  verdict-over: "oklch(66% 0.19 22)"
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
  filter-chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink-body}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "36px"
  filter-chip-current:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
  filter-chip-hover:
    backgroundColor: "{colors.paper-deep}"
    textColor: "{colors.ink}"
  sort-link:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "4px 0"
  sort-link-current:
    textColor: "{colors.ink}"
  instrument:
    backgroundColor: "{colors.paper-well}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "24px"
  ledger-well:
    backgroundColor: "{colors.paper-well}"
    textColor: "{colors.ink-body}"
    padding: "24px"
---

# Design System: Analysis viewer

## 1. Overview

**Creative North Star: "The Night Ledger"**

The viewer is read at a desk, beside a terminal, late. It lists the companies the bot has analysed and, for each one, shows why it got its verdict. It is an instrument, not a drawing: the hand-drawn kraft system of the explanatory pieces (`docs/plano/DESIGN.md`) stops at its door. What crosses over is the honesty, not the stroke. Every number on the page says where it came from, and the page admits what it does not know.

The system is dark only, by decision, and warm: near-black paper tinted toward the ember accent, three steps of it for depth, no shadows. One grotesk sans carries every label and sentence; a mono carries every figure, date and identifier so that a number is recognisable as a number before it is read. Colour is notation. Green, amber and red belong to verdicts and to nothing else; sky-blue belongs to the intrinsic value; ember belongs to the interface's own state (current, sorted, focused, selected) and to nothing else.

The product brief rejects the fintech dashboard (navy and gold, big metric cards, green lines), the SaaS landing page (gradients, identical cards), the Confluence diagram and the editorial-typographic lane. This system is none of those: it is a ledger beside an instrument, ruled with hairlines, with one lead figure and no ornament.

**Key Characteristics:**
- Dark, warm, flat. Depth from three paper tones and hairline rules, never shadows or blur.
- One sans for words, one mono for figures. The mono is a signal, not a style.
- Colour is semantic: three verdict pigments, one intrinsic blue, one interface ember.
- Charts that do not shrink their text: HTML labels beside scaled SVG, tables where a chart would hide the numbers.
- Everything is a real link to a real page; htmx only makes it faster.

## 2. Colors: Night Paper

Warm near-black surfaces, two inks, five notation colours.

### Primary
- **Ember** (`oklch(72% 0.17 45)`): the interface's own state only: the current filter's inset top line, the sorted column's underline, the selected row's square, the caret. Never on content, never on a verdict.
- **Ember focus** (`oklch(78% 0.15 45)`): the 2px focus ring on every control.

### Secondary
- **Sky** (`oklch(74% 0.12 250)`): the intrinsic value wherever it appears: the dot on the value axis, the band of its range, the driver bars, the intrinsic label.

### Tertiary
- **Verdict green** (`oklch(74% 0.15 150)`): undervalued. The check glyph, the zone past 1.3× on the axis, undervalued grid cells.
- **Verdict amber** (`oklch(80% 0.13 85)`): fair. The open circle.
- **Verdict red** (`oklch(66% 0.19 22)`): overvalued. The hatched gate.

### Neutral
- **Paper** (`oklch(9% 0.008 75)`): the page.
- **Paper well** (`oklch(12.5% 0.009 75)`): the ledger pane and the verdict instrument. Raised by being lighter.
- **Paper deep** (`oklch(6.5% 0.007 75)`): the selected row, the pressed chip.
- **Ink** (`oklch(94% 0.010 80)`): headings, figures, the lead text. 12.7:1 on paper.
- **Ink body** (`oklch(84% 0.011 80)`): body copy. 7.2:1.
- **Muted** (`oklch(68% 0.012 80)`): labels, ledes, sources, column heads. 7.2:1 on paper, 7.0:1 on the well. The floor for any text.
- **Muted stroke** (`oklch(50% 0.010 80)`): hairline strokes and the dashed outline of an unevaluated cell. Never text.
- **Rule** (`oklch(25% 0.010 78)`) and **Rule faint** (`oklch(16% 0.009 78)`): section rules and row rules.

### Named Rules
**The Notation Rule.** A colour means one thing on every screen. Green, amber and red are verdicts; sky is intrinsic value; ember is the interface. If a new element needs colour and none of those meanings fit, it is drawn in ink or muted.

**The Shape-First Rule.** No verdict is told by colour alone. The check, the open circle, the hatched gate and the dash carry the verdict in greyscale; the pigment confirms it.

**The Muted Floor Rule.** `muted` is the lightest colour text may use. `muted-stroke` is for lines. A label that needs to recede goes smaller or lighter in weight, not greyer.

## 3. Typography

**Display Font:** Switzer (with ui-sans-serif, system-ui)
**Body Font:** Switzer (with ui-sans-serif, system-ui)
**Label/Mono Font:** Geist Mono (with ui-monospace)

**Character:** One grotesk with two weights carries the whole tool; the mono appears only where the content is a figure, a date or a code identifier. The contrast between them is the hierarchy: a line set in mono is data, a line set in sans is the sentence about it.

### Hierarchy
- **Display** (500, 2.074rem, 1.05): the ticker in the detail head. The only display-size text on the page.
- **Headline** (500, 1.728rem, 1.05): the lead figure (MoS) in the facts strip, set in mono.
- **Title** (500, 1.2rem, 1.05, -0.03em): section headings, the company name beside the ticker, the DCF summary.
- **Body** (400, 1rem, 1.55): the verdict note, the ledes, flag reasons. Capped at 60ch.
- **Label** (500, 0.875rem): column heads, facts labels, filter chips. Sentence case, never tracked, never uppercase.
- **Figure** (400, mono, tabular lining numerals): every number, date, ratio and identifier.

### Named Rules
**The Mono Means Data Rule.** Geist Mono is never used for a word that is not a value, a date, a ticker or an identifier out of the analysis code. Labels and sentences stay in Switzer.

**The Fixed Scale Rule.** Sizes come from the rem scale (0.875, 1, 1.2, 1.44, 1.728, 2.074). No `clamp()`; the layout reflows structurally instead.

## 4. Elevation

No shadows anywhere. Depth is tonal: the page is paper, the ledger pane and the verdict instrument sit on the lighter well, the selected row and a pressed chip drop to the deeper paper. Hairline rules (1px, `rule` and `rule-faint`) separate sections and rows. Nothing blurs, nothing glows.

### Named Rules
**The Flat Night Rule.** If an element needs to come forward, it gets a lighter surface or a rule above it, never a shadow. If it needs to recede, it gets the deeper paper.

## 5. Components

### Filter chips
- **Shape:** square, hairline border that collapses between neighbours so the row reads as one segmented control; wraps to a second row rather than scrolling.
- **Default:** transparent, ink-body text at label size, a decorative verdict glyph before the word, the count in mono muted.
- **Hover:** paper-deep background, ink text. **Current:** ink text and a 2px ember inset line along the top. **Focus:** the 2px ember ring outside the box. Minimum height 36px; 44px on coarse pointers.

### Sort links
- **Style:** the column head itself, muted, with a 2px transparent underline. **Current:** ink text, ember underline, an arrow glyph in mono after the word.

### Ledger rows
- **Style:** hairline-ruled rows at label size; ticker in ink at 500 weight, figures right-aligned in mono, the verdict and flag glyphs titled for screen readers, a mini value axis after the MoS.
- **Hover:** a faint deep-paper wash. **Selected:** deep paper and a 6px ember square before the ticker.
- **Reflow:** under 700px each row becomes a labelled block; between 1100 and 1599px the name shortens and the story column leaves.

### The instrument (signature)
The verdict block: the glyph and the verdict text, one sentence turning the margin of safety into that verdict, the facts strip (MoS leading, then price, intrinsic, story, date) that reflows five, three, two across on the pane's own width, the story note, and the value axis. The axis is an SVG that scales with non-scaling strokes; its four labels are HTML positioned by percentage so they never shrink.

### Tables as charts
- **Drivers:** a table with the input as a row header, low and high as text cells, and the bar as an SVG track in the middle column; the price line crosses every row.
- **Scenarios:** a table with both axes as real headers and a tinted cell with the verdict glyph in each position.
- **DCF:** the projection table behind a `<details>`, then the totals laid out as a sum from discounted cash flows to one share.

### Section heads
A hairline rule above, the title, an optional count line in muted with its figures in ink-body, then one lede sentence at body size in muted saying what the section shows and how to read it.

### Links and empty states
Links in content are ember and underlined. The empty ledger, the empty filter and the 404 each say what is missing and offer one way forward.

## 6. Do's and Don'ts

### Do:
- **Do** keep every control reachable by keyboard and keep focus on the control that was activated after a swap.
- **Do** set figures, dates and identifiers in Geist Mono with tabular numerals, right-aligned in tables.
- **Do** explain a chart in one sentence under its heading, and name the thresholds the verdict depends on (1.0×, 1.3×).
- **Do** give every verdict a shape and a title as well as a colour.
- **Do** reflow on the detail pane's own width (container queries), not the window's.
- **Do** keep text out of scaled SVG; label with HTML or use a table.

### Don't:
- **Don't** build the fintech dashboard: no navy and gold, no big metric cards, no green lines.
- **Don't** build the SaaS landing page: no gradients, no isometric illustration, no grid of identical cards.
- **Don't** build the Confluence diagram: grey boxes, straight arrows, system type, no hierarchy.
- **Don't** take the editorial-typographic lane: italic serif display, mono labels, rules and monochrome.
- **Don't** use a cream, sand or near-white paper; the viewer is dark only.
- **Don't** use ember on content or on a verdict; it belongs to the interface's state.
- **Don't** use `border-left` or `border-right` wider than 1px as a coloured stripe.
- **Don't** use gradient text, glass, blur, shadows, bounce or elastic easing.
- **Don't** gate any content on an animation; motion is 120 to 220ms, opacity and a 4px rise, and disappears under reduced motion.
- **Don't** ship session notes, provenance comments or unused tokens in the stylesheet.
