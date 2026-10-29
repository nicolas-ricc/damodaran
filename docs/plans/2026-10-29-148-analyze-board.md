# Analyze board (#148) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw `docs/pipeline/analyze.d2`, the board that shows how `bot analyze` values one company (Capa C): inputs, story-type classification, each assumption's resolution chain with its source label, the two-stage discounted cash flow (DCF), sensitivity, the five narrative flags, margin of safety and verdict, sanity check, and the three report files. CI renders it to `analyze.svg`; `pipeline.d2` links it.

**Architecture:** One new d2 board pulling the shared classes with `...@classes`. Top level: the command and its two selection decisions, files, a `duckdb` container with the six tables read, the three outputs, then nine containers in pipeline order (`inputs`, `story_type`, `assumptions`, `dcf`, `sensitivity`, `narrative_flags`, `verdict`, `sanity_check`, `reports`), then the edges. Every name from the code is cited by a directive in a d2 line comment. Tests in `tests/unit/test_pipeline_diagram.py` pin required citations, node keys and classes, formulas, threshold directions (evaluated against the code at equality), source labels, report sections (against the template) and gap notes. Rendering happens only in the `pipeline-diagram` workflow (no d2 locally).

**Tech Stack:** d2 v0.9.0 + TALA (CI only), Python 3 / pytest, `docs/pipeline/check.py` (stdlib).

**Spec:** GitHub issue #148 (child of story #144), its "Inherited decisions" section, and `docs/pipeline/README.md` (directive syntax).

## Global Constraints

- Board file: `docs/pipeline/analyze.d2`; first line `...@classes`; then `direction: down`; imports no other board; `class:` is a node's first attribute.
- Only the nine classes of `classes.d2`. No new shapes, no styles.
- A note is a child of the node it annotates, label `|md ... |`. A `gap` note is a single-line `|md Gap: ... |`; its directives trail the closing `| {class: gap}` on the same line (as `pipeline.d2` does for `fx_gap`).
- English; domain words exactly as in `CONTEXT.md` (story type, margin of safety, verdict, sector benchmark, valuation currency, ...). Story types and source labels are written exactly as their enum values (`high-growth`, `sector_default_damodaran`, ...).
- Formulas in plain math with Unicode operators (`×`, `÷`, `−`, `≤`, `≥`, `Σ`), never function names.
- Every acronym is a key of `_ACRONYMS` or `_ACRONYMS_EXEMPT` and its expansion appears earlier in the board or on the same line. The board must not write `PV`, `TV`, `CV`, `CAPM`, `IPO`, `NULL`, `NONE` (spell them out in lower case: "present value", "coefficient of variation", "none").
- Directives live in `#` comments trailing the line whose visible text they check, never inside `|md ... |`. A `@param` / `@const` value must be visible on that same source line (so a multi-line label stays one source line with `\n`). Directive arguments fully qualified. No `@` starting a word anywhere else.
- Label lines about 70 characters at most, broken with `\n` inside double quotes; never put an acronym right after `\n` (start the line with a lower-case word or a digit).
- Every edge carries a label. Edges are declared at top level, after all nodes, with dotted paths.
- Do not touch `src/`. Never hand-write or edit an SVG or `rendered.sha256`.
- Quality bar: `uv run ruff check . && uv run mypy src && uv run pytest -q` green, and the `pipeline-diagram` workflow green on the head commit.
- Commits: board work `docs(#144): ...` (story convention); pipeline stages `test(#148)`, `fix(#148)`, `chore(#148)`.

## Review Focus

1. **A threshold drawn with the wrong direction** (`Altman Z < 1.81` strict but `interest coverage ≤ 1.0` inclusive; `CAGR ≥ 15%`, `age ≤ 25`, `CAGR ≤ −1%`, `coefficient of variation ≥ 0.50`; flags all strict: `> 80%`, `> 0.90`, `< 1.0`, `> 1.5`, `> 40%`, `> 50%`, `> 300 bps`). Pinned by `test_analyze_directions_match_code`: each comparison evaluated in the code exactly at its threshold, and the board's operator must be inclusive exactly when the code fires at equality.
2. **A constant changed in the code without the board.** `@const` directives + `_REQUIRED_CONSTS["analyze"]`; `test_every_directive_is_valid` names the constant.
3. **A source label missing from a resolution chain** (e.g. the tax chain's country step yields `sector_default_damodaran`, not a country label; the cyclical margin yields `historical_average`). Pinned by `_ANALYZE_TEXT` per assumption node and `@enum bot.valuator.assumptions.AssumptionSource`.
4. **The report sections drifting from the template.** `test_analyze_report_sections_match_template` reads the `## N. title` headings of `analysis.md.j2`.
5. **A d2 syntax error only CI sees.** Copy syntax only from `screen.d2` / `refresh.d2`, which render; the controller reads `--log-failed`.

---

## Acronyms (test machinery change, Task 1)

`_ACRONYM_RE` today matches `\b[A-Z][A-Z0-9]+\b|\bMoS\b`, so `P/E`, `P/BV`, `D/E` are invisible to it and listing them in `_ACRONYMS` would be dead entries. Change: build the regex so that every `_ACRONYMS` key containing `/` is matched first as a whole token (`(?<![\w/])(?:P/BV|P/E|D/E)(?![\w/])`, longest first), then the existing alternatives. The first-use search in `test_acronyms_are_expanded` uses the same lookarounds for slash keys instead of `\b`. Add to `_ACRONYMS`:

- `NOPAT`: net operating profit after tax
- `FCFF`: free cash flow to the firm
- `ERP`: equity risk premium
- `GDP`: gross domestic product
- `P/E`: price to earnings
- `P/BV`: price to book value
- `D/E`: debt to equity

Two existing boards then fail the expansion rule and get a minimal wording fix (no other change):
- `refresh.d2` `damodaran.derive` label: `D/E = w ÷ (1 − w)` → `debt-to-equity D/E = w ÷ (1 − w)` (the `_REFRESH_TEXT` phrase `D/E = w ÷ (1 - w)` still matches).
- `screen.d2` `snapshot.ratios.formulas`: `- P/E = close ÷ EPS, ...` → `- price-to-earnings P/E = close ÷ EPS, ...`; `- P/BV = close ÷ BV per share, ...` → `- price-to-book-value P/BV = close ÷ BV per share, ...` (the `_SCREEN_TEXT` phrases still match).

(The expansion comparison lower-cases and turns `-` into spaces, so `price-to-earnings` matches `price to earnings`.)

## Node map (all tasks use these exact keys)

Source order (the acronym test reads top to bottom): `cli`, `tickers`, `override`, files, `duckdb`, outputs, the nine containers in the order below, then edges.

**Top level**
- `cli` (step) `@symbol bot.cli.analyze`: `"bot analyze TICKER ... or --from-screen\nvalue each company by discounted cash flow (DCF), one report set per ticker"`. Note `cli.errors` (md list): unknown ticker: exit code 2; cannot value: exit code 1; the batch goes on after a failure; the command exits with the worst code.
- `tickers` (decision) `@symbol bot.cli.analyze`: `"which tickers?\ntickers given: those\n--from-screen: passed candidates of the latest screener_candidates run\n(newest created_at), by rank\nno run, or no passed candidate: exit code 2"`.
- `override` (decision) `@symbol bot.valuator.assumptions.conventional_override_path`: `"which override file?\n--override path (only with exactly one ticker)\nelse config/assumptions/TICKER.yaml when it exists, else none"`.
- Files (class `file`): `override_yaml` `"config/assumptions/TICKER.yaml, manual overrides"` `# @file config/assumptions @symbol bot.valuator.assumptions.conventional_override_path`; `example_yaml` `"config/assumptions/_EXAMPLE.yaml.example, every override key"` `# @file config/assumptions/_EXAMPLE.yaml.example`; `template` `"src/bot/reporting/templates/analysis.md.j2"` `# @file src/bot/reporting/templates/analysis.md.j2`.
- `duckdb` container `"DuckDB (bot.duckdb)"`, one `store` child per table, each `# @table <name>`: `screener_candidates`, `companies`, `financials_annual`, `prices_daily`, `damodaran_industry`, `damodaran_country`.
- Outputs (class `output`): `report_md` `"reports/YYYY-MM-DD/analysis/TICKER.md"`, `report_html` `"reports/YYYY-MM-DD/analysis/TICKER.html"`, `report_json` `"reports/YYYY-MM-DD/analysis/TICKER.json, read by the site"`.

**`inputs`** `"1. inputs of one company"`
- `load` (step) `@symbol bot.valuator.analysis.load_valuation_input`: companies row (name, country, currency, industry_damodaran, ipo_date); the newest non-restated financials_annual row; oldest-first revenue, net income and earnings before interest and taxes (EBIT) histories, empty years dropped; newest prices_daily close; sector pe, ev_sales, op_margin, beta_levered from the newest damodaran_industry row of (industry, region). Note `load.exact_region` (md): the sector multiples here (sanity check, flags) take the company's own dataset region only; the assumptions use the cross-region fallback.
- `region` (decision) `@symbol bot.reference.regions.dataset_region`: `"dataset region\nfrom the country's grouping in its newest damodaran_country row\nunknown: US"`.
- `derived` (step) `@symbol bot.valuator.analysis.analyze @symbol bot.reference.sectors.is_cyclical`: `"derived signals\nnet debt = total debt − cash, a missing term counts as 0;\nboth missing: net debt taken as 0 in the DCF\ninterest coverage = EBIT ÷ interest expense;\nempty when interest expense is 0 or missing\nage = whole years since ipo_date\ncyclical sector = industry_damodaran in the cyclical list (exact match)"` (EBIT is expanded on `inputs.load`, its first use).
- Gap `derived.age` (on one line, trailing `# @symbol bot.ingest.sec_edgar.parse_submissions_info`): `Gap: age comes from ipo_date, which only Financial Modeling Prep fills. Verified: the Securities and Exchange Commission (SEC) Electronic Data Gathering, Analysis, and Retrieval (EDGAR) parser parse_submissions_info always sets ipo_date to none, so under the default provider age is unknown and every company counts as young.`

**`story_type`** `"2. story type: first rule that matches wins"` (container label line trails `# @symbol bot.valuator.story_types.classify @enum bot.valuator.story_types.StoryType`)
- `distressed` (decision) `@const bot.valuator.story_types._DISTRESS_ALTMAN_Z @const bot.valuator.story_types._DISTRESS_INTEREST_COVERAGE`: `"distressed: Altman Z < 1.81 or interest coverage ≤ 1.0"`. Gap `distressed.altman`: `Gap: Altman Z is read by the classifier but computed nowhere, and analyze never passes it; only interest coverage can make a company distressed.`
- `cyclical` (decision) `@symbol bot.valuator.story_types._earnings_cv @const bot.valuator.story_types._CYCLICAL_EARNINGS_CV`: `"cyclical: cyclical sector and coefficient of variation ≥ 0.50\ncoefficient of variation = standard deviation ÷ |mean| of net income\n(population standard deviation; fewer than 2 years or mean 0: not cyclical)"`.
- `high_growth` (decision) `@symbol bot.valuator.story_types._cagr @const bot.valuator.story_types._HIGH_GROWTH_CAGR @const bot.valuator.story_types._MATURE_AGE_YEARS`: `"high-growth: revenue compound annual growth rate (CAGR) ≥ 15% and age ≤ 25 years\nCAGR = (last ÷ first)^(1 ÷ (years − 1)) − 1\nunknown age counts as young\nfewer than 2 years, or first or last ≤ 0: mature-stable"`.
- `mature_decline` (decision) `@const bot.valuator.story_types._DECLINE_CAGR`: `"mature-decline: CAGR ≤ −1%"`.
- `mature_stable` (decision): `"mature-stable: every other company"`.
- `manual` (decision) `@symbol bot.valuator.assumptions.resolve_assumptions`: `"story_type in the override file?\nyes: it replaces the classifier's story type\nan unknown label: logged, and no story branch applies to the assumptions"`. Note `manual.reasons` (md): the report gives the reasons: revenue CAGR over the years, the age, the classifier's story type; with an override, a line naming what the classifier would have said.

**`assumptions`** `"3. assumptions: the first source that yields a value wins"` (container label line trails `# @symbol bot.valuator.assumptions.resolve_assumptions @const bot.valuator.assumptions._HORIZON @enum bot.valuator.assumptions.AssumptionSource`, and shows `5`: the horizon, e.g. `"... ; paths over 5 years"`)
- `sector_row` (step) `@symbol bot.valuator.assumptions._load_sector_with_fallback`: `"sector row: newest damodaran_industry row for (industry, region)\nnone: the newest row of that industry in any region\nsector label = sector_default_damodaran,\nor sector_default_damodaran_cross_region when another region's row is used"`.
- `growth` (step) `@symbol bot.valuator.assumptions._resolve_revenue_growth @const bot.valuator.assumptions._DEFAULT_GDP_NOMINAL`: `"revenue growth g_t, a 5-year path\n1. manual: list, or one value repeated → manual\n2. high-growth with history: straight line from the mean historical growth\nto nominal gross domestic product (GDP) growth 4% → story_pattern\n3. mean historical growth, repeated → historical_average\n4. nominal GDP growth 4% each year → rule_based\nhistorical growth = mean of (revenue_t − revenue_t−1) ÷ revenue_t−1, zero bases skipped, ≥ 2 years"`. Gap `growth.consensus`: `Gap: spec §7.3 starts revenue growth from analyst consensus converging to nominal GDP by year 10; there is no consensus layer (AssumptionSource has no analyst_consensus) and the horizon is 5 years.`
- `margin` (step) `@symbol bot.valuator.assumptions._resolve_operating_margin @const bot.valuator.assumptions._MIN_CYCLE_YEARS`: `"operating margin, a 5-year path\n1. manual → manual\n2. high-growth: straight line from the latest EBIT ÷ revenue to the sector op_margin → story_pattern\n3. cyclical with ≥ 4 years: mean of the yearly EBIT ÷ revenue → historical_average\n4. sector op_margin each year → sector label\nno sector op_margin: unresolved"`.
- `sales_to_capital` (step) `@symbol bot.valuator.assumptions.resolve_assumptions`: `"sales-to-capital: manual → manual; sector sales_to_capital → sector label; else unresolved"`. Gap `sales_to_capital.story`: `Gap: spec §7.1 varies reinvestment by story type (high early for high-growth, minimal for mature-decline); sales-to-capital and terminal growth follow the same rule for every story type.`
- `discount_rates` (step) `@symbol bot.valuator.assumptions.resolve_assumptions`: `"cost of equity and pre-tax cost of debt, each:\nmanual → manual; sector cost_of_equity / cost_of_debt → sector label; else unresolved"`.
- `weights` (step) `@symbol bot.valuator.assumptions._resolve_weights`: `"equity and debt weights\n1. manual: one given, the other = 1 − it; both given must sum to 1, else cannot value → manual\n2. sector debt-to-equity (D/E): debt weight = D/E ÷ (1 + D/E), equity weight = 1 − debt weight → sector label\n3. else unresolved"`. Gap `weights.company`: `Gap: spec §7.3 builds the discount rate from the company's capital structure and the country equity risk premium; the code uses the sector's D/E and the sector cost of equity.` (No `ERP` token here; its expansion comes on `narrative_flags.country_exposure`.)
- `terminal_growth` (step) `@symbol bot.valuator.assumptions._resolve_terminal_growth`: `"terminal growth g_terminal\n1. manual → manual\n2. country risk-free rate known: min(risk-free rate, nominal GDP growth 4%) → rule_based\n3. else nominal GDP growth 4% → rule_based"`. (`_DEFAULT_GDP_NOMINAL` is cited on `growth`; no second directive needed.)
- `tax` (step) `@symbol bot.valuator.assumptions._resolve_tax_rate @const bot.valuator.assumptions._DEFAULT_TAX_RATE`: `"tax rate\n1. manual → manual\n2. sector tax_rate → sector label\n3. country tax_rate (newest damodaran_country row) → sector_default_damodaran\n4. else 25% → rule_based"`.
- `bankruptcy` (step) `@symbol bot.valuator.assumptions.resolve_assumptions`: `"probability of bankruptcy p and distress value per share\nmanual → manual; else 0 → rule_based"`. Gap `bankruptcy.manual_only`: `Gap: spec §7.3 derives the probability of bankruptcy of a distressed company from its rating or Altman Z; p and the distress value only come from a manual override, otherwise both are 0.`
- `sources` (note, md list; its `@enum bot.valuator.assumptions.AssumptionSource` goes on the `assumptions` container label line, since a multi-line md block cannot carry a trailing directive): the seven source labels and their meaning: `manual` (override file), `story_pattern` (path built for the story type), `historical_average` (the company's own history), `sector_default_damodaran` (sector or country row of the company's region), `sector_default_damodaran_cross_region` (another region's sector row), `rule_based` (fixed rule or default), `unresolved` (no source: cannot value).

**`dcf`** `"4. two-stage discounted cash flow"` (container label line trails `# @symbol bot.valuator.dcf.dcf`)
- `guard` (decision) `@const bot.valuator.analysis.MIN_PLAUSIBLE_SHARES @const bot.valuator.analysis.MAX_PLAUSIBLE_SHARES`: `"can it be valued?\nlatest revenue present, 1,000,000 ≤ diluted shares ≤ 100,000,000,000,\nno assumption unresolved\nno: cannot value, exit code 1"`.
- `wacc` (step) `@symbol bot.valuator.dcf._wacc`: `"weighted average cost of capital (WACC)\n= equity weight × cost of equity + debt weight × pre-tax cost of debt × (1 − tax)"`.
- `converges` (decision): `"g_terminal < WACC?\nno: cannot value, exit code 1"`.
- `years` (step): `"for t = 1 … N (N = length of the growth path, 5 unless a manual list differs;\nthe margin path is cut or extended with its last value to N)\nrevenue_t = revenue_t−1 × (1 + g_t), revenue_0 = latest revenue\nEBIT_t = revenue_t × margin_t\nnet operating profit after tax (NOPAT)_t = EBIT_t × (1 − tax)\nreinvestment_t = (revenue_t − revenue_t−1) ÷ sales-to-capital\nfree cash flow to the firm (FCFF)_t = NOPAT_t − reinvestment_t\npresent value_t = FCFF_t ÷ (1 + WACC)^t"`.
- `terminal` (step): `"terminal year N + 1: revenue = revenue_N × (1 + g_terminal), margin_N\nFCFF_N+1 by the same formulas\nterminal value = FCFF_N+1 ÷ (WACC − g_terminal)\npresent value of terminal value = terminal value ÷ (1 + WACC)^N"`.
- `ev` (step): `"enterprise value (EV) = Σ present value_t + present value of terminal value\nterminal value share = present value of terminal value ÷ EV (0 when EV = 0)"`.
- `equity` (step): `"equity = EV − net debt + adjustments\ngoing-concern value per share = equity ÷ diluted shares"`. Gap `equity.adjustments`: `Gap: spec §7.2 adjusts equity for minority interests and cross-holdings; adjustments has no input path (not filled by the pipeline, not an override key), so it is always 0.`
- `blend` (step): `"intrinsic value per share = (1 − p) × going-concern value per share\n+ p × distress value per share"`.

**`sensitivity`** `"5. sensitivity"`
- `tornado` (step) `@symbol bot.valuator.sensitivity.tornado @const bot.valuator.sensitivity._TORNADO_LOW @const bot.valuator.sensitivity._TORNADO_HIGH @enum bot.valuator.sensitivity.SensitivityAxis`: `"tornado: each axis × 0.8 and × 1.2, one at a time\naxes: revenue_growth, operating_margin (every year scaled), tax_rate,\nsales_to_capital, terminal_growth, cost_of_equity, pretax_cost_of_debt\nswing = |intrinsic value at × 1.2 − intrinsic value at × 0.8|, widest first\nan end with g_terminal ≥ WACC: no value, ranked last"`.
- `grid` (step) `@symbol bot.valuator.sensitivity.grid_2d @const bot.valuator.sensitivity._GRID_MULTIPLIERS`: `"5 × 5 grid on the two widest tornado axes\nmultipliers 0.8, 0.9, 1.0, 1.1, 1.2 on each\ncell = intrinsic value ÷ price (margin of safety); no price: intrinsic value\na cell with g_terminal ≥ WACC: empty"`.

**`narrative_flags`** `"6. narrative flags: five checks for a human, not in any ranking"` (container label line trails `# @symbol bot.valuator.narrative_flags.narrative_flags @enum bot.valuator.narrative_flags.FlagColor`); every flag is a `decision`:
- `story_margin` `@symbol bot.valuator.narrative_flags.story_margin_flag`: `"story margin\nstory type not high-growth: green\ncompany or sector margin missing: unknown\ncompany EBIT ÷ revenue (latest year) > sector op_margin: yellow\nelse green"`.
- `growth_reinvestment` `@symbol bot.valuator.narrative_flags.growth_reinvestment_flag @const bot.valuator.narrative_flags._STRETCHED_REINVESTMENT_RATE`: `"growth funded by reinvestment\nany year with FCFF < 0, or reinvestment > 0 with NOPAT ≤ 0: red\nhighest reinvestment ÷ NOPAT over years with NOPAT > 0 is > 0.90: yellow\nelse green"`.
- `beta_business_risk` `@symbol bot.valuator.narrative_flags.beta_business_risk_flag @symbol bot.valuator.analysis._operating_leverage @const bot.valuator.narrative_flags._DEFENSIVE_BETA @const bot.valuator.narrative_flags._HIGH_OPERATING_LEVERAGE @const bot.valuator.narrative_flags._HIGH_FINANCIAL_LEVERAGE`: `"beta vs business risk\nsector beta_levered < 1.0 and operating leverage > 1.5 and company debt weight > 40%: yellow\none of the three missing: unknown; else green\noperating leverage = %ΔEBIT ÷ %ΔRevenue, last two years\ncompany debt weight = total debt ÷ (total debt + total equity)"`.
- `terminal_value_share` `@symbol bot.valuator.narrative_flags.terminal_value_share_flag @const bot.valuator.narrative_flags._TERMINAL_VALUE_SHARE_CEILING`: `"terminal value share > 80%: yellow\nelse green"`.
- `country_exposure` `@symbol bot.valuator.narrative_flags.country_exposure_flag @const bot.valuator.narrative_flags._FOREIGN_REVENUE_MAJORITY @const bot.valuator.narrative_flags._ERP_GAP_THRESHOLD`: `"country exposure\nforeign revenue share > 50% and weighted equity risk premium (ERP)\n− listing-country ERP > 300 bps: red\nan input missing: unknown; else green"`. Gap `country_exposure.always_unknown`: `Gap: analyze never supplies the foreign revenue share or the two ERPs (no ingest path has revenue by geography), so this flag is always unknown.`

**`verdict`** `"7. margin of safety and verdict"`
- `mos` (step) `@symbol bot.valuator.analysis.analyze`: `"margin of safety (MoS) = intrinsic value per share ÷ latest close\nno price, or price ≤ 0: none"`.
- `words` (decision) `@symbol bot.reporting.analysis_report.margin_verdict @const bot.web.views.MOS_UNDERVALUED @const bot.web.views.MOS_FAIR`: `"verdict\nMoS ≥ 1.3: potentially undervalued\nMoS ≥ 1.0: around fair value\nMoS < 1.0: potentially overvalued\nno MoS: n/a"`.

**`sanity_check`** `"8. sanity check"`
- `multiples` (step) `@symbol bot.valuator.analysis._sanity_check`: `"implied multiples next to the sector's; decides nothing\nimplied price-to-earnings (P/E) = price ÷ earnings per share (EPS), EPS = net income ÷ diluted shares;\nonly with a price, net income > 0 and shares > 0; vs sector pe\nimplied EV ÷ sales = EV ÷ revenue, revenue > 0; vs sector ev_sales"`.

**`reports`** `"9. reports, written to reports/YYYY-MM-DD/analysis/"`
- `markdown` (step) `@symbol bot.reporting.analysis_report.render_analysis`: `"markdown report from analysis.md.j2, eight sections:\n1. executive summary, 2. story type + auto-assignment reasons, 3. assumptions,\n4. DCF detail, 5. sensitivity, 6. narrative flags, 7. manual overrides,\n8. sanity check vs sector multiples"`.
- `html` (step) `@symbol bot.reporting.html.render_analysis_html`: `"HTML report: the markdown report plus the tornado chart and the grid heatmap,\ninlined, no external assets"`.
- `json` (step) `@symbol bot.reporting.analysis_json.render_analysis_json @const bot.reporting.analysis_json.SCHEMA_VERSION`: `"JSON sidecar: schema_version 1, generated_on, verdict, the whole analysis"`.

**Edges (all labelled), at least:**
- `duckdb.screener_candidates -> tickers` ("passed candidates of the latest run, by rank"); `cli -> tickers` ("tickers or --from-screen"); `tickers -> override` ("each ticker"); `override_yaml -> override` ("file of the ticker, if present"); `example_yaml -> override_yaml` ("copy and fill in"); `override -> inputs.load` ("ticker and override file").
- `duckdb.companies -> inputs.load` ("company row"); `duckdb.financials_annual -> inputs.load` ("annual rows"); `duckdb.prices_daily -> inputs.load` ("newest close"); `duckdb.damodaran_industry -> inputs.load` ("sector multiples"); `duckdb.damodaran_country -> inputs.region` ("country grouping"); `inputs.load -> inputs.region` ("country"); `inputs.region -> inputs.derived` ("dataset region"); `inputs.derived -> story_type.distressed` ("signals").
- Story chain: `story_type.distressed -> story_type.cyclical` ("no"), `story_type.cyclical -> story_type.high_growth` ("no"), `story_type.high_growth -> story_type.mature_decline` ("no"), `story_type.mature_decline -> story_type.mature_stable` ("no"); each of the five `-> story_type.manual` ("classifier's story type" / "yes"); `override_yaml -> story_type.manual` ("story_type key").
- `story_type.manual -> assumptions` ("story type"); `override_yaml -> assumptions` ("manual values"); `duckdb.damodaran_industry -> assumptions.sector_row` ("sector rows"); `duckdb.damodaran_country -> assumptions.terminal_growth` ("risk-free rate"); `duckdb.damodaran_country -> assumptions.tax` ("country tax rate"); `duckdb.financials_annual -> assumptions.growth` ("revenue history"); `duckdb.financials_annual -> assumptions.margin` ("EBIT and revenue history"); `assumptions.sector_row -> assumptions.margin` / `-> assumptions.sales_to_capital` / `-> assumptions.discount_rates` / `-> assumptions.weights` / `-> assumptions.tax` ("sector row and label").
- `assumptions -> dcf.guard` ("resolved assumptions"); `inputs.derived -> dcf.guard` ("latest revenue, diluted shares, net debt"); `dcf.guard -> dcf.wacc` ("yes"); `dcf.wacc -> dcf.converges` ("WACC"); `dcf.converges -> dcf.years` ("yes"); `dcf.years -> dcf.terminal` ("revenue_N, margin_N"); `dcf.terminal -> dcf.ev` ("present value of terminal value"); `dcf.years -> dcf.ev` ("present value_t"); `dcf.ev -> dcf.equity` ("EV"); `dcf.equity -> dcf.blend` ("going-concern value per share").
- `dcf -> sensitivity.tornado` ("the DCF re-run per scenario"); `sensitivity.tornado -> sensitivity.grid` ("two widest axes"); `dcf -> narrative_flags` ("yearly figures, terminal value share"); `inputs.derived -> narrative_flags.beta_business_risk` ("histories and balance sheet"); `dcf.blend -> verdict.mos` ("intrinsic value per share"); `verdict.mos -> verdict.words` ("MoS"); `dcf.ev -> sanity_check.multiples` ("EV"); `verdict.words -> reports` ("verdict"); `sensitivity -> reports` / `narrative_flags -> reports` / `sanity_check -> reports` ("results"); `template -> reports.markdown` ("layout"); `reports.markdown -> reports.html` ("markdown"); `reports.markdown -> report_md` ("markdown file"); `reports.html -> report_html` ("HTML file"); `reports.json -> report_json` ("JSON file").

---

### Task 1: Acronym machinery, command, files, stores, outputs, inputs and story type

**Files:**
- Create: `docs/pipeline/analyze.d2`
- Modify: `docs/pipeline/refresh.d2` (one label), `docs/pipeline/screen.d2` (two note lines) — see "Acronyms".
- Test: `tests/unit/test_pipeline_diagram.py` (written and committed in stage 3, including the `_ACRONYM_RE` change and the new `_ACRONYMS` entries; listed here for ownership).

**Interfaces:**
- Consumes (tests, from stage 3): `_analyze() -> str`, `_analyze_block(key: str) -> str`, `_ANALYZE_NODES: list[tuple[str, str]]`, `_ANALYZE_TEXT: dict[str, list[str]]`, `_ANALYZE_DIRECTIONS`, plus the existing `_check()`, `_block()`, `_node_class()`, `_edge_line()`.
- Produces: the top-level nodes, `duckdb`, outputs, `inputs.*`, `story_type.*` keys of the node map.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_diagram.py` — Expected: the stage-3 analyze tests FAIL (no `analyze.d2`); `test_acronyms_are_expanded` FAILS on `refresh.d2: D/E` and `screen.d2: P/E`, `P/BV`.
- [ ] **Step 2:** Apply the two wording fixes to `refresh.d2` and `screen.d2`.
- [ ] **Step 3:** Write `analyze.d2`: `...@classes`, `direction: down`, top level, `duckdb`, outputs, `inputs`, `story_type`, and the edges among them.
- [ ] **Step 4:** Run the file — Expected: PASS for `test_acronyms_are_expanded`, `test_every_directive_is_valid`, `test_every_edge_is_labelled`, `test_gap_notes_start_with_gap`, every parametrized case keyed under the top level, `inputs.*`, `story_type.*`, the story-type cases of `test_analyze_directions_match_code`, `test_analyze_story_type_order`, `test_analyze_ipo_date_gap_is_current`; the rest still FAIL.
- [ ] **Step 5: Commit** `docs(#144): analyze board — command, inputs and story type`.

### Task 2: Assumptions

**Files:** Modify `docs/pipeline/analyze.d2`.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "assumptions or sources"` — Expected: FAIL.
- [ ] **Step 2:** Add the `assumptions` container (nodes, gaps, `sources` note) and its edges.
- [ ] **Step 3:** Run the file — Expected: the Task 1 PASS set plus every case keyed under `assumptions.*` and `test_analyze_assumption_sources`.
- [ ] **Step 4: Commit** `docs(#144): analyze board — assumption resolution`.

### Task 3: DCF and sensitivity

**Files:** Modify `docs/pipeline/analyze.d2`.

- [ ] **Step 1:** Run `-k "dcf or sensitivity"` — Expected: FAIL.
- [ ] **Step 2:** Add `dcf` and `sensitivity` with their gaps and edges.
- [ ] **Step 3:** Run the file — Expected: plus every case keyed under `dcf.*`, `sensitivity.*`.
- [ ] **Step 4: Commit** `docs(#144): analyze board — DCF and sensitivity`.

### Task 4: Flags, verdict, sanity check, reports and the overview link

**Files:** Modify `docs/pipeline/analyze.d2`, `docs/pipeline/pipeline.d2` (add `link: "./analyze.svg"` as the `analyze` node's second attribute, after `class: step`).

- [ ] **Step 1:** Run `-k "flags or verdict or sanity or reports or link or required"` — Expected: FAIL.
- [ ] **Step 2:** Add `narrative_flags`, `verdict`, `sanity_check`, `reports`, the remaining edges and the link.
- [ ] **Step 3:** Run the file — every test PASS except `test_check_py_exits_zero` and `test_each_board_has_a_rendered_svg` (no `analyze.svg` yet, so the link target is also missing).
- [ ] **Step 4: Commit** `docs(#144): analyze board — flags, verdict, sanity check and reports, linked from the overview`.
- [ ] **Step 5:** Mutation drill on the committed board: edit `80%` to `85%`, run `-k every_directive` — Expected: FAIL naming `_TERMINAL_VALUE_SHARE_CEILING`; restore with `git checkout docs/pipeline/analyze.d2`.

### Task 5: Render through CI and commit the render (controller, needs push)

- [ ] Push; find the `pipeline-diagram` run whose `headSha` equals `git rev-parse HEAD`; `gh run watch <id> --exit-status`.
- [ ] Build failure: `gh run view <id> --log-failed`, fix the `.d2` line d2 names, push again.
- [ ] Build green: `gh run download <id> -n pipeline-render -D /tmp/render`; copy `*.svg` and `rendered.sha256` into `docs/pipeline/`; look at `/tmp/render/analyze.png`; fix unreadable layout in the source (then re-render); commit `docs(#144): render analyze, pipeline, refresh, screen`; push; the run on that commit must be fully green.
- [ ] `python3 docs/pipeline/check.py` exits 0; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Tests written in stage 3 (all in `tests/unit/test_pipeline_diagram.py`)

- `_REQUIRED_*["analyze"]`: symbols (the 32 of the issue), tables (the 6), files (`config/assumptions`, `config/assumptions/_EXAMPLE.yaml.example`, `src/bot/reporting/templates/analysis.md.j2`), consts (6 story-type thresholds, `_HORIZON`, `_MIN_CYCLE_YEARS`, `_DEFAULT_GDP_NOMINAL`, `_DEFAULT_TAX_RATE`, the two share bounds, `_TORNADO_LOW`, `_TORNADO_HIGH`, `_GRID_MULTIPLIERS`, the 7 flag thresholds, `MOS_UNDERVALUED`, `MOS_FAIR`, `SCHEMA_VERSION`), enums (`StoryType`, `AssumptionSource`, `FlagColor`, `SensitivityAxis`).
- `test_analyze_nodes(key, cls)` over `_ANALYZE_NODES` (every key of the node map with its class, gaps and notes included).
- `test_analyze_text(key)` over `_ANALYZE_TEXT`: the formulas and chains of the node map, e.g. `dcf.wacc`: `equity weight × cost of equity + debt weight × pre-tax cost of debt × (1 - tax)`; `dcf.years`: `revenue_t = revenue_t-1 × (1 + g_t)`, `EBIT_t = revenue_t × margin_t`, `EBIT_t × (1 - tax)`, `(revenue_t - revenue_t-1) ÷ sales-to-capital`, `NOPAT_t - reinvestment_t`, `÷ (1 + WACC)^t`; `dcf.terminal`: `FCFF_N+1 ÷ (WACC - g_terminal)`, `÷ (1 + WACC)^N`; `dcf.ev`: `Σ present value_t + present value of terminal value`, `present value of terminal value ÷ EV`; `dcf.equity`: `EV - net debt + adjustments`, `equity ÷ diluted shares`; `dcf.blend`: `(1 - p) × going-concern value per share`, `p × distress value per share`; assumption chains with their labels (`growth`: `manual`, `story_pattern`, `historical_average`, `rule_based`, `4%`; `margin`: `story_pattern`, `historical_average`, `sector label`, `unresolved`, `≥ 4 years`; `weights`: `D/E ÷ (1 + D/E)`, `1 - it`, `sum to 1`; `terminal_growth`: `min(risk-free rate, nominal GDP growth 4%)`; `tax`: `25%`, `country tax_rate`, `sector_default_damodaran`; `sector_row`: `sector_default_damodaran_cross_region`, `any region`; `bankruptcy`: `0`, `manual`); sensitivity (`× 0.8`, `× 1.2`, `0.8, 0.9, 1.0, 1.1, 1.2`, `5 × 5`, `two widest`); flags and verdict phrases; sanity (`price ÷ earnings per share`, `EV ÷ revenue`, `decides nothing`); `inputs.derived`: `EBIT ÷ interest expense`, `total debt - cash`; `story_type.*` comparisons; `tickers`: `--from-screen`, `by rank`, `exit code 2`; `dcf.guard`: `1,000,000 ≤ diluted shares ≤ 100,000,000,000`, `exit code 1`.
- `test_analyze_directions_match_code` (parametrized `(node, phrase, op, fires_at_equality)`): story types via `classify` with `ClassificationFinancials` at the threshold (Altman Z = 1.81 → not distressed, `<`; coverage = 1.0 → distressed, `≤`; age = 25 with high growth → high-growth, `≤`; CAGR / coefficient of variation / decline at a dyadic threshold set with `monkeypatch.setattr` on the module constant (0.5 with revenues (1, 1.5); 0.5 with earnings (1, 3); −0.5 with revenues (2, 1)), `≥`, `≥`, `≤`); flags via the flag functions at equality (terminal value share 0.8, `>`; reinvestment ÷ NOPAT = 0.9 (0.9 ÷ 1.0), `>`; beta 1.0 / operating leverage 1.5 / debt weight 0.4 each at equality with the other two firing, `<` / `>` / `>`; foreign share 0.5 with a 1.0 ERP gap, `>`; ERP gap 0.03 is not dyadic: monkeypatch `_ERP_GAP_THRESHOLD` to 0.25 with ERPs (0.5, 0.25), `>`). Asserts the phrase is in the node's block and `fires == (op in "≤≥")`.
- `test_analyze_story_type_order`: the five story-type decisions appear in the order distressed, cyclical, high-growth, mature-decline, mature-stable, and the four `"no"` edges chain them.
- `test_analyze_story_priority_matches_classify`: the board's order is the code's: `classify` on a company that is both distressed (coverage 0.5) and high-growth (revenues (1, 2), cyclical sector, volatile earnings (1, 3)) returns `distressed`; without the distress signal, `cyclical`; with a non-cyclical sector, `high-growth`; revenues (2, 1) → `mature-decline`; one revenue year → `mature-stable`.
- `test_analyze_inclusive_bounds`: `dcf.guard` shows `1,000,000 ≤ diluted shares ≤ 100,000,000,000` (the code: `MIN_PLAUSIBLE_SHARES <= shares <= MAX_PLAUSIBLE_SHARES`); `dcf.converges` shows `g_terminal < WACC` and `dcf.dcf` raises `ValueError` at terminal growth = WACC (both 0.5, weights (1, 0), cost of equity 0.5, a one-year path); `verdict.words` thresholds are already pinned by `test_verdict_thresholds_match_margin_verdict`.
- `test_analyze_assumption_sources`: every `AssumptionSource` value appears inside the `assumptions` container block.
- `test_analyze_report_sections_match_template`: the titles of the `## N. title` headings of `analysis.md.j2` (lower-cased) are all in `reports.markdown`'s block, and there are eight.
- `test_analyze_gap_notes`: the eight gap keys hold their facts (`distressed.altman`: `Altman Z`, `computed nowhere`; `bankruptcy.manual_only`: `manual override`; `country_exposure.always_unknown`: `always unknown`; `growth.consensus`: `analyst consensus`, `analyst_consensus`; `sales_to_capital.story`: `sales-to-capital and terminal growth`; `equity.adjustments`: `minority interests`, `cross-holdings`, `no input path`; `derived.age`: `ipo_date`, `Verified`, `parse_submissions_info`; `weights.company`: `capital structure`).
- `test_analyze_ipo_date_gap_is_current`: `parse_submissions_info("T", {})` returns `ipo_date is None`; the gap `inputs.derived.age` exists exactly when it does (like `test_estado_default_provider_gap_is_current`).
- `test_analyze_flow_edges`: the edges `duckdb.screener_candidates -> tickers`, `override -> inputs.load`, `inputs.derived -> story_type.distressed`, `story_type.manual -> assumptions`, `assumptions -> dcf.guard`, `dcf.blend -> verdict.mos`, `verdict.mos -> verdict.words`, `reports.markdown -> report_md`, `reports.html -> report_html`, `reports.json -> report_json` exist.
- `test_pipeline_links_the_analyze_board`: `_block(_overview(), "analyze")` has a line `link: "./analyze.svg"`.

## Acceptance criteria → tasks

- AC1 (SVG rendered with d2 v0.9.0 + TALA, workflow green, link, hash): Task 4 link + `test_pipeline_links_the_analyze_board`; Task 5.
- AC2 (story chain, resolution chains with source labels, DCF formulas, sensitivity parameters, five flags with thresholds and colours, verdict thresholds, sanity ratios as plain math): `_ANALYZE_TEXT`, `test_analyze_directions_match_code`, `test_analyze_story_type_order`, `test_analyze_assumption_sources`, the `@enum` directives.
- AC3 (seven gap notes, `ipo_date` verified): `test_analyze_gap_notes`, `test_analyze_ipo_date_gap_is_current` (an eighth gap, `weights.company`, is extra).
- AC4 (citations, `_REQUIRED_*["analyze"]`, check.py 0, diagram tests green): `test_required_citations_present`, `test_every_directive_is_valid`, `test_check_py_exits_zero`.
- AC5 (acronyms incl. EBIT, NOPAT, FCFF, EPS, EV, ERP, CAGR, GDP, P/E, D/E on this board; EBITDA, ROIC, ROE, P/BV already listed and used on the screen board; quality bar): `test_acronyms_are_expanded` with the slash-acronym regex; Task 5 last step.

## Manual verification (goes in the PR)

- Open `analyze.svg` and trace one imaginary ticker: classify it, resolve its assumptions, compute year 1 by hand with the formulas on the board, read its verdict.

## Assumptions

- **Slash acronyms are made visible to the acronym test** (see "Acronyms") rather than added as dead dict entries; the two older boards get the minimal expansion fix this forces.
- **`config/assumptions/<TICKER>.yaml` is cited as `@file config/assumptions`** (the directory exists; the per-ticker file is a pattern) plus `@symbol conventional_override_path`. That is the third of the "three files" of the issue's `@file` requirement.
- **Resolution chains are `step` nodes**, not `decision`s: they pick a source, they do not keep, drop or classify a company. The decisions are the story types, `tickers`, `override`, `dcf.guard`, `dcf.converges`, the five flags and `verdict.words`.
- **The issue's "4% flat" fallback is `gdp_nominal`**, which `analyze` always passes as `_DEFAULT_GDP_NOMINAL` = 0.04 (`analysis.py`); the board shows 4% and cites the assumptions-module constant.
- **The sector multiples of the sanity check and the flags are exact-region only** (`_load_sector_multiples`), unlike the assumptions' cross-region fallback: drawn as a note on `inputs.load`, not a gap (no spec or plan states otherwise).
- **An eighth gap (`weights.company`)** records `estado.py` `a-wacc` (weights from the sector D/E, not the company's) against spec §7.3.
- **The stage-3 `test(#148): evals` commit is red on purpose** (the tests precede the board; the stricter acronym regex fails `refresh.d2` / `screen.d2` until Task 1). **Intermediate commits are red on purpose**; only the head commit must be green (issue: "The staleness step is expected to fail on a push whose SVGs are not yet committed").
- **Every SVG in the artifact is copied**, including unchanged boards: the artifact renders every board and `rendered.sha256` covers all sources.

## Grilling

- Rounds: 1 (the revision adds two tests and fixes three wordings and one step order; no task, seam or file changed, so no second round).
- Questions: 18. Sources: CODE 14, ISSUE 2, NO SOURCE 2 (technical assumptions), out of scope 0.
  - Q1 CODE `docs/pipeline/check.py` `renderings()`/`shown()`/`normalize()`: plain, thousands separators, K/M/B for exact multiples, `×100` + `%` (rounded to 9 places, so 0.15 → `15%`), bps for |value| < 1 (0.03 → `300 bps`), U+2212 mapped to `-`, tuples need every element. Exercised today: `refresh.d2` tuples (`_SHARE_SCALE_FACTORS`), `screen.d2` `21%`, `100M`, `−200 bps`.
  - Q2 NO SOURCE → technical assumption: the stage-3 commit is red by design (pipeline stage 3 "Commit the failing tests"); recorded under Assumptions.
  - Q3 CODE `src/bot/valuator/story_types.py` `_is_distressed`/`_is_cyclical`/`classify` and `narrative_flags.py` `country_exposure_flag` compare against the module names inside the function bodies (no default arguments), so `monkeypatch.setattr` takes effect.
  - Q4 CODE `tests/unit/test_pipeline_diagram.py` `_directive_problem`: `@enum` members are checked with `_shown_in_board` (whole board); `check.py` ignores `@enum`. DOC `docs/pipeline/README.md`: "`@enum` | Enum whose member values appear on the board".
  - Q5 CODE `src/bot/reporting/analysis_report.py` `margin_verdict` holds literal 1.3 / 1.0; `test_verdict_thresholds_match_margin_verdict` pins them to `bot.web.views.MOS_*`. `@const` is resolved by pytest import, not by `check.py` (`_directive_problem`).
  - Q6 CODE `story_types.py` `classify` order distressed → cyclical → growth/decline/stable; **added** `test_analyze_story_priority_matches_classify`.
  - Q7 CODE `analysis.py` `MIN_PLAUSIBLE_SHARES <= shares <= MAX_PLAUSIBLE_SHARES`; `dcf.py` `terminal_growth >= wacc` raises; `analysis.py` MoS needs `current_price > 0.0`; `latest.interest_expense` truthiness; **added** `test_analyze_inclusive_bounds`, guard wording now `1,000,000 ≤ diluted shares ≤ 100,000,000,000`.
  - Q8 ISSUE: the required `@symbol` list names `_operating_leverage`, `_sanity_check`, `is_cyclical`, `conventional_override_path`; `test_required_citations_present` checks a subset (required − cited), so extras are allowed. Eighth gap: ISSUE "where they disagree, the diagram shows what the code does and adds a note of class `gap`"; source `docs/plano/estado.py` `a-wacc`.
  - Q9 CODE `analysis.md.j2` headings: `1. Executive summary`, `2. Story type + auto-assignment reasons`, `3. Assumptions`, `4. DCF detail`, `5. Sensitivity`, `6. Narrative flags`, `7. Manual overrides`, `8. Sanity check vs sector multiples`; no Jinja inside them.
  - Q10 CODE `src/bot/ingest/sec_edgar.py:139-162` `parse_submissions_info(ticker: str, submissions: dict[str, Any])` reads with `.get` and sets `ipo_date=None`; `{}` works.
  - Q11 NO SOURCE → fixed: commit first, then the drill, restored by `git checkout`.
  - Q12 CODE no test enforces line length; the 70-character rule is a layout guideline for labels, gap notes are single md lines as on `screen.d2` (`ranking.metrics.spec_scores`).
  - Q13 CODE `_ACRONYMS_EXEMPT` holds `TICKER`, `YYYY`, `MM`, `DD`, `HTML`, `JSON`; `EV` is in `_ACRONYMS` and expanded on `dcf.ev`, before `sanity_check`; `DuckDB` is mixed case, not matched.
  - Q14 CODE `analysis.py` `_latest_from_row` (net debt, a missing term = 0, both missing = none) and `analyze` (`net_debt ... else 0.0`, interest coverage, age from `ipo_date`): two paths; wording fixed.
  - Q15 CODE `src/bot/cli.py:418-440` (query inside `analyze`); `tests/unit/test_cli_analyze.py:299` asserts "did not leave any candidates".
  - Q16 CODE `src/bot/cli.py:442-445` `exit_code = max(...)`; `tests/unit/test_cli_analyze.py:404-408` (MCD fails, AAPL succeeds, exit code 1).
  - Q17 CODE `docs/pipeline/build.sh` last line hashes `cat ./*.d2` (sources); `.github/workflows/pipeline-diagram.yml` `on: [push, workflow_dispatch]`, no path filter. ISSUE: "d2 ≥ v0.9.0 bundles the TALA layout engine: open source, no separate plugin, no licence key".
  - Q18 CODE `src/bot/valuator/assumptions.py:84-102` `AssumptionSource`: seven members, no `analyst_consensus`.
- Assumptions added: red stage-3 commit (Q2).
- Issues opened: none.
- Result: ok.
