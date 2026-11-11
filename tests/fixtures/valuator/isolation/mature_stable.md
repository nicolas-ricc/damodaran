# AAPL — Apple Inc

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 141.67
- **Current price:** 150.00
- **Margin of safety:** 0.94x (potentially overvalued)
- **Story type:** mature-stable
- **WACC (computed from the components in §3):** 8.1% (equity 83.3% / debt 16.7%)
- **Terminal value share of EV:** 67.8%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**mature-stable**

- historical revenue CAGR 4.2% over 3 years
- classified as mature-stable
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1 → yr 10) | 4.2% → 4.0% | historical_average |
| Operating margin | 28.0% | sector_default_damodaran |
| Sales-to-capital | 2.50 | sector_default_damodaran |
| Cost of equity | 9.0% | sector_default_damodaran |
| Pre-tax cost of debt | 4.5% | sector_default_damodaran |
| Equity weight | 83.3% | sector_default_damodaran |
| Debt weight | 16.7% | sector_default_damodaran |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 21.0% | country_default_damodaran |
| Probability of bankruptcy | 0.0% | rule_based |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 448.09B | 125.46B | 99.12B | 7.24B | 91.88B | 85.00B |
| 2 | 466.81B | 130.71B | 103.26B | 7.49B | 95.77B | 81.97B |
| 3 | 486.18B | 136.13B | 107.54B | 7.75B | 99.79B | 79.02B |
| 4 | 506.22B | 141.74B | 111.97B | 8.01B | 103.96B | 76.15B |
| 5 | 526.93B | 147.54B | 116.56B | 8.29B | 108.27B | 73.37B |
| 6 | 548.35B | 153.54B | 121.29B | 8.57B | 112.73B | 70.67B |
| 7 | 570.48B | 159.73B | 126.19B | 8.85B | 117.34B | 68.06B |
| 8 | 593.33B | 166.13B | 131.25B | 9.14B | 122.10B | 65.52B |
| 9 | 616.94B | 172.74B | 136.47B | 9.44B | 127.02B | 63.06B |
| 10 | 641.31B | 179.57B | 141.86B | 9.75B | 132.11B | 60.67B |
| Terminal | — | — | — | — | 3,315.11B | — |

- **Enterprise value:** 2,245.93B
- **Equity value:** 2,195.93B
- **Net debt:** 50.00B

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 178.23 | 117.36 | 60.86 |
| terminal_growth | -1.0pp / +1.0pp | 123.23 | 171.85 | 48.61 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 131.18 | 153.05 | 21.87 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 136.11 | 147.23 | 11.12 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 146.44 | 137.20 | 9.24 |
| sales_to_capital | ×0.8 / ×1.2 | 138.97 | 143.48 | 4.51 |
| tax_rate | -1.0pp / +1.0pp | 143.38 | 139.96 | 3.42 |
### 2-D grid — cost_of_equity (rows) × terminal_growth (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / terminal_growth → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 0.99x | 1.08x | 1.19x | 1.34x | 1.56x |
| -0.5pp | 0.90x | 0.97x | 1.05x | 1.17x | 1.32x |
| +0.0pp | 0.82x | 0.88x | 0.94x | 1.03x | 1.15x |
| +0.5pp | 0.76x | 0.80x | 0.86x | 0.92x | 1.01x |
| +1.0pp | 0.70x | 0.74x | 0.78x | 0.84x | 0.90x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| growth_reinvestment | green | Every year the reinvestment growth needs fits within after-tax operating profit (NOPAT). |
| beta_business_risk | unknown | not evaluated: the sector beta, the operating leverage or the company's debt share is missing. |
| terminal_value_share | green | 68% of enterprise value comes from the terminal value, within the 80% ceiling. |
| country_exposure | unknown | not evaluated: it needs revenue by geography and a revenue-weighted equity risk premium (ERP), and no data source supplies either. |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 21.96 | 22.00 |
| P/E market | 23.25 | 22.00 |
| EV/Sales | 5.22 | 5.00 |
