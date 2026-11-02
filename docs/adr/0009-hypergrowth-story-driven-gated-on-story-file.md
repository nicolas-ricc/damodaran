# 0009 — Hypergrowth: a story-driven valuation, gated on the story file

## Status

Accepted (2026-11-02). Implemented (2026-11-02, issue #192).

The code is in src/bot/valuator/: story_types.py, assumptions.py, hypergrowth.py, dcf.py,
sensitivity.py, narrative_flags.py and analysis.py.

## Context

Damodaran valued Anthropic at its October 2026 IPO in "The Anthropic Prospectus arrives"
(https://aswathdamodaran.blogspot.com/2026/10/the-anthropic-prospectus-arrives-ipo.html).
The valuation is driven by a story, not by history: the S-1 is "a kindergartner's report
card". Each DCF input answers one question: year-10 revenue (the market times the company's
share), the target operating margin (mass market against premium), sales to capital (the cost
of compute), the cost of capital, the failure risk from the compute commitments and the
regulatory drag. His base case is equity of $1,475,406M, $447.34 a share. Governance (five
share classes, founders keep 50.1% of the vote) stays outside the DCF and becomes a larger
discount before buying.

The bot could not express that valuation:

- **The classifier made such a company `distressed`.** Before this change `classify()`
  checked distress first, and negative EBIT puts interest coverage at or below
  `_DISTRESS_INTEREST_COVERAGE` whatever the cash balance.
- **`high-growth` is too broad.** It needs only a 15% CAGR and an age of 25 years or less.
  A TAM-driven story applied to every 15% grower would be wrong.
- **Age came from the IPO date** (`ipo_date`), so any fresh listing looked young.
- **The DCF could not carry the method.** The horizon was five years, the WACC one scalar,
  the distress recovery a per-share amount instead of a share of value, and nothing held
  fixed commitments as debt or extra cash such as IPO proceeds.
- **The screener excludes these companies**: it asks for five years of history, positive
  operating cash flow in four of them and a ROIC above the sector WACC. That is intended.
  They enter only through `bot analyze <TICKER>`.

Every other story type must keep valuing exactly as before.
`tests/unit/test_valuator_isolation_golden.py` pins that.

## Decision

A new story type, `hypergrowth`, valued by Damodaran's method. It runs only from a
story file that sets `story_type: hypergrowth` and carries a `story` section. The classifier's
signals never gate the valuation: they colour the `hypergrowth_story` flag. The method is
never applied automatically.

- **Two keys.** The classifier signals and the story file are separate keys. The classifier
  assigns `StoryType.HYPERGROWTH` by a rule that runs before distress and needs all four
  signals: last-year revenue growth of at least 50% (`_HYPERGROWTH_LAST_YEAR_GROWTH`), a
  revenue CAGR of at least 40% over the available history, two points being enough
  (`_HYPERGROWTH_CAGR`), an operating margin below the sector median, and a real company age
  of at most 15 years, or unknown (`_HYPERGROWTH_MAX_AGE_YEARS`). The real age comes from
  `founded_year`, not from the IPO date, which still feeds the `high-growth` rule. The
  valuation runs only when the override file sets `story_type: hypergrowth` and has a
  `story` section; the signals alone never start it.
- **Fallback.** A candidate with signals but no story file is valued as `high-growth` (unless
  the override file sets another `story_type`) and raises a red `hypergrowth_story` flag: the
  default valuation is not reliable. A story file without signals is valued as hypergrowth,
  with a yellow flag; both present is green.
- **Story file.** `config/assumptions/<TICKER>.yaml` gains three keys and a new `story_type`
  value: `story_type: hypergrowth` (required with `story`), `founded_year`, a `story` mapping
  and an optional `scenarios` mapping. `story` takes the fields of `StoryInputs`, with these
  defaults when optional: `year1_growth`, `target_revenue_y10`, `year1_margin`,
  `target_margin`, `sales_to_capital` and `wacc_start` are required; `margin_converge_year` 5,
  `regulatory_drag` 0.0, `wacc_terminal` the sector WACC, `effective_tax_rate` 0.0,
  `terminal_roic` none, `failure_probability` 0.0, `failure_proceeds_pct_of_value` 0.0,
  `fixed_commitments_pv` 0.0, `extra_cash` 0.0 and `governance_discount` 0.0. Money amounts
  (`target_revenue_y10`, `fixed_commitments_pv`, `extra_cash`) are in the
  raw reporting currency of `financials_annual`, not millions. Unknown keys, out-of-range values,
  `story_type: hypergrowth` without `story`, `story` without `story_type: hypergrowth`, and
  `scenarios` without `story` are `ValueError`s, so the batch fails that ticker alone.
- **Ten-year paths** (`hypergrowth.HORIZON = 10`), built from the story:
  - Growth: year 1 is `year1_growth`. Years 2 to 5 share one rate, solved by bisection so that
    year-10 revenue equals `target_revenue_y10`. Years 6 to 10 fade linearly to the terminal
    growth.
  - Margin: `year1_margin` in year 1. From year 2 the margin is
    `year1_margin + (target_margin - regulatory_drag - year1_margin) * t / margin_converge_year`,
    so it reaches the drag-adjusted target in `margin_converge_year` and stays flat after.
  - WACC: `wacc_start` in years 1 to 5, then linear to `wacc_terminal` (default: the sector
    WACC) in year 10.
  - Tax: `effective_tax_rate` in years 1 to 5, then linear to the marginal rate in year 10.
- **DCF extensions, all optional.** `wacc_path` replaces the scalar WACC and discounts with a
  cumulative factor. `tax_rate_path` sets the tax of the explicit years. `terminal_roic` sets
  the terminal reinvestment to `g / ROIC`; without it the terminal reinvestment stays
  `ΔRevenue / sales_to_capital`. `distress_proceeds_pct` makes the failure blend work on
  enterprise value. `Financials.fixed_commitments` and `extra_cash` enter the equity bridge.
  Every default reproduces the old maths bit for bit.
- **Failure blend on enterprise value.** With `distress_proceeds_pct` set, the enterprise value
  is `(1 - p) * EV + p * proceeds_pct * EV` before the bridge, as Damodaran weights the
  operating assets. `distress_value_per_share` is ignored in that case.
- **Commitments as debt, extra cash as cash.** `fixed_commitments_pv` (the PV of the compute
  commitments) is added to debt in the bridge. `extra_cash` (the IPO proceeds) is added to
  cash.
- **Governance outside the DCF.** `governance_discount` never enters the DCF. The margin of
  safety is measured on `intrinsic_value * (1 - governance_discount)`
  (`intrinsic_value_after_governance`). The tornado, the grid and the scenarios use the raw
  value.
- **Scenarios.** Each entry of `scenarios` overrides fields of `story`. `scenario_range` runs
  one plain DCF per case: `base` first, then the file order. `base` is reserved. The report
  shows the range next to the tornado, in the sensitivity section.
- **Three flags.** `hypergrowth_story` (above). `hypergrowth_revenue_scale` is yellow when the
  year-10 revenue exceeds the largest company's revenue today (`_LARGEST_COMPANY_REVENUE`,
  750e9). `hypergrowth_terminal_roic` is yellow when the terminal ROIC exceeds twice the
  sector ROIC (`_ROIC_SECTOR_MULTIPLE`, 2.0), and unknown when either ROIC is missing or the
  sector ROIC is not positive. The last two run only for the `hypergrowth` story type.
- **Sensitivity.** The cost-of-equity axis scales `wacc_path` along with the scalar, so the
  tornado and the grid move the whole path. The cost-of-debt axis is skipped when the path is
  set (`active_axes`): the path replaces the built-up WACC.
- **Screener untouched.** The screener keeps excluding these companies. `bot analyze <TICKER>`
  is the only way in.

## Consequences

- The method is never applied automatically. No story file, no hypergrowth valuation, only a
  red flag and the `high-growth` default.
- Calibration against Damodaran's base case, asserted in
  `tests/unit/test_hypergrowth_calibration.py:110-161` (the computed values were re-run on
  commit 90f717c during plan review): equity 1,473,576 against his 1,475,406, and 446.79 a
  share against 447.34. The test allows 1% on both. Two deviations explain the gap: the
  same-year reinvestment (his sheet reinvests one year ahead), and the worst case, which uses
  a 10-point regulatory drag (0.10) instead of his 15 points because that reproduces his
  figure. Worst case: -371,991 against -373,000. Best case: 4,076,137 against 4,040,000.
  The test allows 5% on both.
- Sidecars stay at `schema_version` 1. The new fields are additive and have defaults, so older
  sidecars still load. ADR 0008 says any change to the sidecar shape means a bump; this ADR
  keeps version 1 because the fields are additive with defaults, and so narrows that rule.
- The reports show the story inputs with source `story`, the scenario range, and both values,
  the intrinsic value and the value after the governance discount.
- The pipeline boards (`docs/pipeline/analyze.d2`, `analyze-story.d2`) name the hypergrowth
  rule only on their labels. Issue #199 draws the story branch and the model.
- A story file is an input the user writes, so its quality is the valuation's quality. The
  flags exist to say when the story asks for too much, not to correct it.
