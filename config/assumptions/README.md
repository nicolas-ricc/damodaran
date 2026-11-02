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

The story is parsed and validated; the valuation does not read it yet.
