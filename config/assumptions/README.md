# Manual assumption overrides (spec §7.6)

Drop a `<TICKER>.yaml` here (e.g. `AAPL.yaml`) to override DCF assumptions
for that ticker by convention — `bot analyze <TICKER>` and the screener's
second DCF pass both pick it up automatically, with no `--override` flag
needed. See `_EXAMPLE.yaml.example` for the full list of override keys.
