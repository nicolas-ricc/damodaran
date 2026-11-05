# DECL — DECL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 1.35
- **Current price:** 1.20
- **Margin of safety:** 1.13x (around fair value)
- **Story type:** mature-decline
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 66.4%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**mature-decline**

- historical revenue CAGR -5.3% over 3 years
- classified as mature-decline
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | -5.3% | historical_average |
| Operating margin | 12.0% | sector_default_damodaran |
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
| 1 | 966.21M | 115.95M | 91.60M | -26.89M | 118.49M | 108.92M |
| 2 | 915.26M | 109.83M | 86.77M | -25.48M | 112.24M | 94.84M |
| 3 | 867.00M | 104.04M | 82.19M | -24.13M | 106.32M | 82.59M |
| 4 | 821.28M | 98.55M | 77.86M | -22.86M | 100.72M | 71.91M |
| 5 | 777.97M | 93.36M | 73.75M | -21.65M | 95.41M | 62.62M |
| Terminal | — | — | — | — | 1.27B | — |

- **Enterprise value:** 1.25B
- **Equity value:** 1.35B
- **Net debt:** -100.00M

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 1.55 | 1.21 | 0.35 |
| terminal_growth | -1.0pp / +1.0pp | 1.25 | 1.52 | 0.27 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 1.24 | 1.47 | 0.23 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 1.39 | 1.31 | 0.08 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 1.32 | 1.39 | 0.07 |
| sales_to_capital | ×0.8 / ×1.2 | 1.32 | 1.37 | 0.05 |
| tax_rate | -1.0pp / +1.0pp | 1.37 | 1.34 | 0.03 |
### 2-D grid — cost_of_equity (rows) × terminal_growth (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / terminal_growth → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 1.16x | 1.22x | 1.30x | 1.39x | 1.52x |
| -0.5pp | 1.10x | 1.14x | 1.20x | 1.28x | 1.38x |
| +0.0pp | 1.04x | 1.08x | 1.13x | 1.19x | 1.26x |
| +0.5pp | 0.99x | 1.02x | 1.06x | 1.11x | 1.17x |
| +1.0pp | 0.94x | 0.97x | 1.00x | 1.05x | 1.09x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'mature-decline' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | green | terminal value is 66% of enterprise value (<= 80%) |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 15.92 | 10.00 |
| P/E market | 14.12 | 10.00 |
| EV/Sales | 1.23 | 1.20 |
