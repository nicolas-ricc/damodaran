# Manual assumption overrides (spec §7.6)

Drop a `<TICKER>.yaml` here (e.g. `AAPL.yaml`) to override DCF assumptions
for that ticker by convention — `bot analyze <TICKER>` and the screener's
second DCF pass both pick it up automatically, with no `--override` flag
needed. See `_EXAMPLE.yaml.example` for the full list of override keys.

## Hypergrowth story file

A file with `story_type: hypergrowth` carries the inputs of a Damodaran
hypergrowth story. Three keys are involved:

- `story` — a mapping with the story inputs (`year1_growth`,
  `target_revenue_y10`, `year1_margin`, `target_margin`, `margin_converge_year`,
  `regulatory_drag`, `sales_to_capital`, `wacc_start`, `wacc_terminal`,
  `effective_tax_rate`, `terminal_roic`, `failure_probability`,
  `failure_proceeds_pct_of_value`, `fixed_commitments_pv`, `extra_cash`,
  `governance_discount`). Required keys, ranges and defaults are listed, one
  comment per key, in `_EXAMPLE.yaml.example`.
- `scenarios` — an optional mapping of scenario name to a subset of the story
  keys, merged over the base `story` (for example `worst` and `best`).
- `founded_year` — an integer from 1600 to the current year. Any story type may
  set it.

Money amounts (`target_revenue_y10`, `fixed_commitments_pv`, `extra_cash`) use
the units of `financials_annual`: the raw reporting currency, not millions.
`1011491000000`, not `1011491`.

`load_override` checks the file when it loads and raises a `ValueError` whose
message starts with the file path. `bot analyze` reports it for that ticker and
the batch continues with the others. The rules:

- `story_type: hypergrowth` requires a `story` section.
- `story` requires `story_type: hypergrowth`.
- `scenarios` requires `story`.
- `founded_year` must be an integer from 1600 to the current year (a boolean or
  `2021.5` is refused).
- `story` and every scenario are validated key by key: unknown keys, missing
  required keys, out-of-range values, non-integer `margin_converge_year`,
  booleans, `NaN` and `inf` are refused, and the message names the key.
- `scenarios` must not be empty, each scenario name must be a string and each
  scenario a non-empty mapping.

A valid story file drives the valuation of that ticker (ADR 0009). Without one,
no hypergrowth valuation runs. With `story_type: hypergrowth` and a `story`:

- **Assumptions.** `resolve_assumptions` overlays the story on the resolved
  bundle through `apply_story`, replacing the growth, margin and reinvestment
  assumptions. Its ten-year paths: revenue growth (year 1 `year1_growth`, then
  solved so year-10 revenue meets `target_revenue_y10`), the operating margin
  (`year1_margin` to `target_margin` minus `regulatory_drag`), the WACC
  (`wacc_start` to `wacc_terminal`) and the tax rate. With them come
  `sales_to_capital`, `terminal_roic`, the cost of equity (`wacc_start`, all
  equity, no debt), the failure blend (`failure_probability`,
  `failure_proceeds_pct_of_value`), `fixed_commitments_pv` and `extra_cash`.
  Each such input shows source `story` in the report.
- **Scenarios.** `bot analyze` values `base` and then every entry of
  `scenarios`, in file order, with one plain DCF each. The report shows the
  range next to the tornado.
- **Governance discount.** `governance_discount` never enters the DCF. The
  margin of safety is measured on the intrinsic value after the discount,
  `intrinsic_value * (1 - governance_discount)`. The tornado, the grid and the
  scenarios use the raw value.

## Probability of bankruptcy

A distressed company's `probability_of_bankruptcy` is derived from its interest
coverage via `config/default_spreads.yaml`. A manual `probability_of_bankruptcy`
in the override file wins over the default-spread table.
