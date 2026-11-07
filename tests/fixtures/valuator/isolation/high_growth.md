# HGRO — HGRO

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 597.83
- **Current price:** 40.00
- **Margin of safety:** 14.95x (potentially undervalued)
- **Story type:** high-growth
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 74.7%

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
| Revenue growth (yr 1 → yr 10) | 20.0% → 4.0% | story_pattern |
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
| 2 | 294.16B | 43.14B | 34.08B | 22.66B | 11.42B | 9.65B |
| 3 | 342.50B | 49.09B | 38.78B | 24.17B | 14.61B | 11.35B |
| 4 | 392.68B | 54.97B | 43.43B | 25.09B | 18.34B | 13.10B |
| 5 | 443.20B | 60.57B | 47.85B | 25.26B | 22.59B | 14.83B |
| 6 | 492.32B | 65.64B | 51.86B | 24.56B | 27.30B | 16.47B |
| 7 | 538.11B | 69.95B | 55.26B | 22.89B | 32.37B | 17.95B |
| 8 | 578.56B | 73.28B | 57.89B | 20.22B | 37.67B | 19.20B |
| 9 | 611.73B | 75.45B | 59.60B | 16.59B | 43.02B | 20.16B |
| 10 | 635.89B | 76.31B | 60.28B | 12.08B | 48.20B | 20.76B |
| Terminal | — | — | — | — | 1,036.05B | — |

- **Enterprise value:** 597.83B
- **Equity value:** 597.83B
- **Net debt:** 0.00

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 728.24 | 503.83 | 224.41 |
| terminal_growth | -1.0pp / +1.0pp | 540.38 | 685.24 | 144.87 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 529.47 | 666.20 | 136.73 |
| sales_to_capital | ×0.8 / ×1.2 | 534.30 | 640.19 | 105.90 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 562.01 | 636.40 | 74.39 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 624.77 | 572.89 | 51.89 |
| tax_rate | -1.0pp / +1.0pp | 606.62 | 588.99 | 17.63 |
### 2-D grid — cost_of_equity (rows) × terminal_growth (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / terminal_growth → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 15.98x | 16.97x | 18.21x | 19.79x | 21.88x |
| -0.5pp | 14.66x | 15.45x | 16.43x | 17.66x | 19.24x |
| +0.0pp | 13.51x | 14.16x | 14.95x | 15.91x | 17.13x |
| +0.5pp | 12.51x | 13.04x | 13.68x | 14.46x | 15.41x |
| +1.0pp | 11.63x | 12.07x | 12.60x | 13.22x | 13.98x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | yellow | A high-growth story, but the operating margin of 15.0% already exceeds the sector's 12.0%: little room left for the margin to improve. |
| growth_reinvestment | green | Every year the reinvestment growth needs fits within after-tax operating profit (NOPAT). |
| beta_business_risk | unknown | not evaluated: the sector beta, the operating leverage or the company's debt share is missing. |
| terminal_value_share | green | 75% of enterprise value comes from the terminal value, within the 80% ceiling. |
| country_exposure | unknown | not evaluated: it needs revenue by geography and a revenue-weighted equity risk premium (ERP), and no data source supplies either. |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 28.83 | 10.00 |
| P/E market | 1.93 | 10.00 |
| EV/Sales | 2.88 | 1.20 |
