# HGRO — HGRO

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 454.20
- **Current price:** 40.00
- **Margin of safety:** 11.35x (potentially undervalued)
- **Story type:** high-growth
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 85.5%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**high-growth**

- historical revenue CAGR 20.0% over 4 years
- company age 10 years
- classified as high-growth
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | 20.0% | story_pattern |
| Operating margin | 15.0% → 12.0% | story_pattern |
| Sales-to-capital | 2.00 | sector_default_damodaran |
| Cost of equity | 10.0% | sector_default_damodaran |
| Pre-tax cost of debt | 6.0% | sector_default_damodaran |
| Equity weight | 76.9% | sector_default_damodaran |
| Debt weight | 23.1% | sector_default_damodaran |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 21.0% | sector_default_damodaran |
| Probability of bankruptcy | 0.0% | rule_based |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 248.83B | 37.32B | 29.49B | 20.74B | 8.75B | 8.04B |
| 2 | 288.65B | 41.13B | 32.49B | 19.91B | 12.59B | 10.64B |
| 3 | 323.28B | 43.64B | 34.48B | 17.32B | 17.16B | 13.33B |
| 4 | 349.15B | 44.52B | 35.17B | 12.93B | 22.24B | 15.88B |
| 5 | 363.11B | 43.57B | 34.42B | 6.98B | 27.44B | 18.01B |
| Terminal | — | — | — | — | 591.61B | — |

- **Enterprise value:** 454.20B
- **Equity value:** 454.20B
- **Net debt:** 0.00

## 5. Sensitivity

### Tornado (±20% per assumption, ranked by impact)

| Assumption | Intrinsic @ -20% | Intrinsic @ +20% | Impact |
|---|---|---|---|
| cost_of_equity | 680.65 | 337.46 | 343.18 |
| operating_margin (yr 1) | 331.26 | 577.13 | 245.87 |
| terminal_growth | 413.23 | 511.16 | 97.92 |
| revenue_growth (yr 1) | 420.41 | 490.64 | 70.23 |
| sales_to_capital | 414.08 | 480.94 | 66.87 |
| tax_rate | 480.73 | 427.02 | 53.71 |
| pretax_cost_of_debt | 477.16 | 433.23 | 43.93 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -20% | -10% | +0% | +10% | +20% |
|---|---|---|---|---|---|
| -20% | 12.52x | 14.77x | 17.02x | 19.26x | 21.51x |
| -10% | 10.00x | 11.82x | 13.65x | 15.47x | 17.30x |
| +0% | 8.28x | 9.82x | 11.35x | 12.89x | 14.43x |
| +10% | 7.04x | 8.37x | 9.69x | 11.02x | 12.35x |
| +20% | 6.10x | 7.27x | 8.44x | 9.60x | 10.77x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | yellow | high-growth story but operating margin 15.0% already exceeds sector 12.0% — little room to improve |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | yellow | terminal value is 85% of enterprise value (> 80%) — valuation is fragile |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 21.90 | 10.00 |
| P/E market | 1.93 | 10.00 |
| EV/Sales | 2.19 | 1.20 |
