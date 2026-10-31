# Analyze model (TLA+, TLC-checked) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/pipeline/models/analyze.{tla,cfg,view.js}`: a TLC-checked model of one ticker through one `bot analyze` run, from the ticker list to its verdict and reports. Its phases and steps are what the analyze sub-boards (#170) will draw.

**Architecture:** One `phase` variable holds the reader's state; the other variables exist only because a rule needs them. Every environment outcome is a named action; `Next` is their disjunction plus `Done`. Groups are the seven sub-board stems. CI (`pipeline-diagram` / job `models`) runs TLC through the pinned statechart skill. That run is the gate, because the sandbox has no Java.

**Tech Stack:** TLA+ / TLC 1.7.4 via the statechart skill at `STATECHART_COMMIT`, ES module view, pytest.

**Spec:** issue #169 (body), parent story #161 (plan comment: decisions 6, 7, 9), `docs/pipeline/models/README.md` (conventions), `docs/pipeline/models/site.*` (worked example), `docs/pipeline/analyze.d2` (every formula and threshold with citations).

## Global Constraints

- Files: `docs/pipeline/models/analyze.tla`, `analyze.cfg`, `analyze.view.js`. First line `---- MODULE analyze ----`. No other file under `docs/pipeline/models/` changes, unless a rule breaks (then the README table changes too).
- No file under `src/` or `docs/pipeline/*.d2` changes.
- Groups are exactly `analyze-inputs`, `analyze-story`, `analyze-assumptions`, `analyze-dcf`, `analyze-sensitivity`, `analyze-flags`, `analyze-verdict`. Colors come from `blue orange purple yellow teal tan pink`.
- Title: `export const title = "analyze: one ticker through bot analyze";`
- The maps `states`, `steps`, `groups` are plain `const` (not exported), with one `key: "value",` entry per line. The only exports are `state`, `step`, `group`, `colors`, `title`, written exactly as in `site.view.js`.
- `.tla` comment convention: `\*` only for a rule's reader sentence (and `\* broken: #n`); every action and every rule has a `(* ... *)` citation of the code on the line(s) above it (for a rule: above its `\*` sentence). Definitions are separated by blank lines.
- **No `EXTENDS`** (strings and booleans only). Also avoid `Cardinality` and `<=>`: the #167 run found that SANY's XML export, which the skill uses, fails on `FiniteSets`. Use `=` between booleans, and write "at most one" as `\A a, b \in S : a = b`.
- Each action has exactly one `phase = "<from>"` line and one `phase' = "<to>"` line, in that order. The #164 sub-board tests parse them.
- Labels: the reader's words, no `_`, no camelCase, no action names. Expand each acronym at its first use: discounted cash flow (DCF), weighted average cost of capital (WACC), margin of safety (MoS), gross domestic product (GDP), earnings before interest and taxes (EBIT), debt-to-equity (D/E). Conditions go in `[brackets]` at the end of a step label.
- State budget: at most 500 distinct states (the chart budget); the target is about 300. Group budget: at most 20 model steps whose source or target phase is in the group. The #170 sub-board adds its stores and must stay at 24 or fewer.

## Model design (the decisions the implementer cannot make alone)

### Variables (Init value first)

| Variable | Values | Needed by rule |
| --- | --- | --- |
| `phase` | the phases below; Init `"asked"` | all |
| `batch` | `"going"`, `"stopped"` | j |
| `exitCode` | `"none"`, `"0"`, `"1"`, `"2"` | c, d, j, k |
| `storyTypes` | `{}`, `{"classifier"}`, `{"override"}` | e |
| `overrideStory` | `"unread"`, `"absent"`, `"given"` | e |
| `currency` | `"unread"`, `"covered"`, `"uncovered"` | f |
| `tgSource` | `"unread"`, `"manual"`, `"rule based"`, `"unresolved"` | f |
| `unresolved` | `FALSE`, `TRUE` (some assumption has no source) | b |
| `shares` | `"unread"`, `"plausible"`, `"implausible"` | d |
| `gVsWacc` | `"unknown"`, `"below"`, `"at or above"` | c |
| `valued` | `FALSE`, `TRUE` (the DCF gave an intrinsic value) | a, b, c, d, h, i |
| `flags` | subset of `FlagNames` = `{"story margin", "reinvestment", "beta", "terminal value share", "country"}` | h |
| `margin` | `"unread"`, `"no price"`, `"below 1.0"`, `"1.0 to under 1.3"`, `"1.3 or more"` | g |
| `verdict` | `"none"`, `"n/a"`, `"potentially overvalued"`, `"around fair value"`, `"potentially undervalued"` | a, g |
| `reports` | subset of `{"markdown", "HTML", "JSON"}` | i |

`EndPhases == {"command_stops", "not_found", "cannot_value", "crashed", "reported"}`.

The model does not track which of the five story types a company holds. `storyTypes` records who set it (`"classifier"` or `"override"`). The story-dependent sources (the story-pattern growth and margin paths, the cycle-average margin, the story-margin flag) are therefore unguarded actions: their story condition is written in the step label. Rule (e) needs only "exactly one, and the override's replaces the classifier's". Keeping the five types would multiply every later state by 6 and break the 500-state budget (counted below). The override file's presence is not tracked either: the manual actions are always enabled, and their labels say "[set in the override file]".

### Phases, groups and actions

Format: `Action: from → to (variable changes) — "step label" — code citation`. Every action not listed as changing a variable leaves it unchanged. `Done` keeps everything unchanged in an end phase, with the label `"the run of this ticker ends"`.

**analyze-inputs** (phases `asked`, `command_stops`, `chosen`, `override_picked`, `not_found`, `loaded`, `region_set`, `signals`)
- `TheTickersAreGiven`: asked → chosen — "the ticker is named on the command line" — `cli.analyze`: `tickers` argument.
- `TheLatestScreenListsIt`: asked → chosen — "the latest screen lists it as a passed candidate [--from-screen]" — `cli.analyze`: `SELECT ticker ... WHERE passed AND run_id = ? ORDER BY rank`.
- `TheArgumentsAreRefused`: asked → command_stops (batch' = "stopped", exitCode' = "2") — "the command stops, exit code 2 [tickers with --from-screen, neither, or --override without exactly one ticker]" — `cli.analyze` lines 405-415.
- `TheScreenLeftNoCandidate`: asked → command_stops (batch' = "stopped", exitCode' = "2") — "the command stops, exit code 2 [--from-screen, and no screen run or no passed candidate]" — `cli.analyze`: `latest_run is None` / `not rows` → `typer.Exit(code=2)`.
- `TheOverrideFlagNamesTheFile`: chosen → override_picked — "the override file is the one --override names [exactly one ticker]" — `cli.analyze` `override` option; `_analyze_one`.
- `TheTickersFileExists`: chosen → override_picked — "the override file is config/assumptions/TICKER.yaml [it exists]" — `assumptions.conventional_override_path`.
- `NoOverrideFile`: chosen → override_picked — "no override file [no --override, no TICKER.yaml]" — `conventional_override_path` returns None.
- `TheTickerIsUnknown`: override_picked → not_found (exitCode' = "2") — "the ticker is skipped, exit code 2 [not in companies, or no annual financials]" — `analysis._load_company` / `_load_latest_financials` raise `LookupError`; `_analyze_one` returns 2.
- `TheCompanyIsLoaded`: override_picked → loaded — "the company, its newest annual figures, history, close and sector row are loaded" — `analysis.load_valuation_input`.
- `ItsOwnDatasetRegion`: loaded → region_set — "the dataset region is its own [China, India, Japan]" — `regions.dataset_region` `COUNTRY_REGION_OVERRIDES`.
- `RegionFromItsCountryGrouping`: loaded → region_set — "the dataset region comes from its country's grouping" — `dataset_region` `GEOGRAPHIC_TO_DATASET_REGION`.
- `RegionDefaultsToUs`: loaded → region_set — "the dataset region is US [grouping unknown]" — `dataset_region` returns `DEFAULT_DATASET_REGION`.
- `TheSignalsAreDerived`: region_set → signals — "net debt, interest coverage, age and the cyclical sector are derived" — `analysis.analyze` (age, `interest_coverage`, `is_cyclical`); `_latest_from_row` (net debt).

**analyze-story** (phases `not_distressed`, `not_cyclical`, `not_high_growth`, `classified`, `crashed`, `story_set`)
- `ItIsDistressed`: signals → classified (storyTypes' = {"classifier"}) — "the classifier says distressed [interest coverage at most 1.0]" — `story_types.classify` / `_is_distressed`.
- `ItIsNotDistressed`: signals → not_distressed — "not distressed [interest coverage above 1.0 or unknown]".
- `ItIsCyclical`: not_distressed → classified (storyTypes' = {"classifier"}) — "the classifier says cyclical [cyclical sector and earnings variation at least 0.50]" — `_is_cyclical`.
- `ItIsNotCyclical`: not_distressed → not_cyclical — "not cyclical [otherwise]".
- `ItIsHighGrowth`: not_cyclical → classified (storyTypes' = {"classifier"}) — "the classifier says high-growth [revenue growth at least 15% a year and age at most 25 years]" — `classify` `_HIGH_GROWTH_CAGR`, `_MATURE_AGE_YEARS`.
- `ItIsNotHighGrowth`: not_cyclical → not_high_growth — "not high-growth [otherwise]".
- `ItIsInDecline`: not_high_growth → classified (storyTypes' = {"classifier"}) — "the classifier says mature-decline [revenue growth at most −1% a year]" — `_DECLINE_CAGR`.
- `ItIsMatureStable`: not_high_growth → classified (storyTypes' = {"classifier"}) — "the classifier says mature-stable [every other company]".
- `TheOverrideFileIsInvalid`: classified → cannot_value (exitCode' = "1") — "the ticker cannot be valued, exit code 1 [the override file is not a mapping or has an unknown key]" — `assumptions._load_override` raises `ValueError`; `_analyze_one` returns 1.
- `TheOverrideFileIsNotYaml`: classified → crashed (batch' = "stopped", exitCode' = "1") — "the command crashes, exit code 1 [the override file is not valid YAML]" — `assumptions._load_override` `yaml.safe_load` raises `yaml.YAMLError` (an `Exception`, not a `ValueError`); `_analyze_one` catches only `LookupError` and `ValueError`, so it leaves the `for ticker` loop of `cli.analyze`.
- `NoManualStoryType`: classified → story_set (overrideStory' = "absent") — "the classifier's story type stands [no story type in the override file]" — `_resolve_story_type`.
- `TheOverrideSetsTheStoryType`: classified → story_set (overrideStory' = "given", storyTypes' = {"override"}) — "the override file's story type replaces it [story type set in the file; an unknown label drives no branch]" — `_resolve_story_type` (manual wins); `resolve_assumptions` `_STORY_TYPE_VALUES`.

**analyze-assumptions** (phases `sector_read`, `currency_read`, `growth_set`, `margin_set`, `scalars_set`, `weights_set`, `tg_set`)
- `TheSectorRowIsFound`: story_set → sector_read — "the sector row is found [its region's, else another region's]" — `assumptions._load_sector_with_fallback`, `_pick_sector`.
- `NoSectorRow`: story_set → sector_read — "no sector row [industry absent from every region]" — `_pick_sector` returns `(None, False)`.
- `TheCurrencyIsCovered`: sector_read → currency_read (currency' = "covered") — "the valuation currency is in the currency table" — `load_assumption_inputs`, `_currency_rates`.
- `TheCurrencyIsUncovered`: sector_read → currency_read (currency' = "uncovered") — "the valuation currency is not in the currency table" — `_currency_rates` returns `None` rates; `_warn_uncovered`.
- `GrowthIsResolved`: currency_read → growth_set — "revenue growth gets a source [manual, story pattern, history, or nominal gross domestic product (GDP) growth]" — `_resolve_revenue_growth`.
- `GrowthIsUnresolved`: currency_read → growth_set (unresolved' = TRUE), guard `currency = "uncovered"` — "revenue growth is unresolved [no history and an uncovered currency]" — `_resolve_revenue_growth` returns UNRESOLVED when `gdp is None`.
- `MarginIsResolved`: growth_set → margin_set — "operating margin gets a source [manual, story pattern, cycle average, or sector]" — `_resolve_operating_margin`.
- `MarginIsUnresolved`: growth_set → margin_set (unresolved' = TRUE) — "operating margin is unresolved [no sector operating margin]".
- `ScalarsAreResolved`: margin_set → scalars_set — "sales-to-capital and the costs of equity and debt get a source [manual or sector]" — `_resolve_sector_scalar`.
- `AScalarIsUnresolved`: margin_set → scalars_set (unresolved' = TRUE) — "sales-to-capital or a cost of capital is unresolved [not in the file nor the sector row]".
- `WeightsAreResolved`: scalars_set → weights_set — "the equity and debt weights get a source [manual, or the sector's debt-to-equity (D/E)]" — `_resolve_weights`.
- `WeightsAreUnresolved`: scalars_set → weights_set (unresolved' = TRUE) — "the weights are unresolved [no manual weight, no sector debt-to-equity (D/E)]".
- `TheManualWeightsDoNotSumToOne`: scalars_set → cannot_value (exitCode' = "1") — "the ticker cannot be valued, exit code 1 [both weights set by hand and not summing to 1]" — `_resolve_weights` raises `ValueError`.
- `TerminalGrowthIsManual`: weights_set → tg_set (tgSource' = "manual") — "terminal growth is set by hand [in the override file]" — `_resolve_terminal_growth` manual branch.
- `TerminalGrowthFromTheCurrency`: weights_set → tg_set (tgSource' = "rule based"), guard `currency = "covered"` — "terminal growth is the lower of the currency's risk-free rate and nominal gross domestic product (GDP) growth [covered currency]" — `_resolve_terminal_growth` `min(rates.risk_free_rate, rates.nominal_gdp_growth)`.
- `TerminalGrowthIsUnresolved`: weights_set → tg_set (tgSource' = "unresolved", unresolved' = TRUE), guard `currency = "uncovered"` — "terminal growth is unresolved [uncovered currency, not set by hand]" — `_resolve_terminal_growth` `rates is None`.

**analyze-dcf** (phases `ready`, `shares_ok`, `resolved`, `cannot_value`, `wacc_computed`, `projected`, `terminal_valued`, `ev_found`, `equity_found`, `valued`)
- `TaxAndBankruptcyAreSet`: tg_set → ready — "tax rate and bankruptcy odds are set [manual, sector, country, or 25%; bankruptcy manual or 0]" — `_resolve_tax_rate`, `_resolve_probability_of_bankruptcy`, `_resolve_distress_value_per_share`.
- `NoLatestRevenue`: ready → cannot_value (exitCode' = "1") — "the ticker cannot be valued, exit code 1 [no revenue in the newest year]" — `analysis.analyze` `latest.revenue is None`.
- `TheSharesAreImplausible`: ready → cannot_value (shares' = "implausible", exitCode' = "1") — "the ticker cannot be valued, exit code 1 [diluted shares missing or outside 1,000,000 to 100,000,000,000]" — `analyze` `MIN_PLAUSIBLE_SHARES` / `MAX_PLAUSIBLE_SHARES`.
- `TheSharesArePlausible`: ready → shares_ok (shares' = "plausible") — "the diluted shares are plausible".
- `AnAssumptionIsUnresolved`: shares_ok → cannot_value (exitCode' = "1"), guard `unresolved` — "the ticker cannot be valued, exit code 1 [an assumption is unresolved]" — `Assumptions.to_dcf_assumptions` / `_require` raise `ValueError`.
- `EveryAssumptionHasASource`: shares_ok → resolved, guard `~unresolved` — "every assumption has a source".
- `SalesToCapitalIsNotPositive`: resolved → cannot_value (exitCode' = "1") — "the ticker cannot be valued, exit code 1 [sales-to-capital at most 0, or an empty growth path]" — `dcf.dcf` (`horizon == 0`, `sales_to_capital <= 0.0`).
- `TheWaccIsComputed`: resolved → wacc_computed — "the weighted average cost of capital (WACC) is computed" — `dcf._wacc`.
- `TerminalGrowthReachesTheWacc`: wacc_computed → cannot_value (gVsWacc' = "at or above", exitCode' = "1") — "the ticker cannot be valued, exit code 1 [terminal growth at or above the WACC]" — `dcf.dcf` `terminal_growth >= wacc`.
- `TerminalGrowthIsBelowTheWacc`: wacc_computed → projected (gVsWacc' = "below") — "the years are projected [terminal growth below the WACC]" — `dcf.dcf` loop.
- `TheTerminalValueIsComputed`: projected → terminal_valued — "the terminal value is computed".
- `TheEnterpriseValueIsSummed`: terminal_valued → ev_found — "the enterprise value is summed".
- `TheEquityIsFound`: ev_found → equity_found — "equity and the going-concern value per share are found".
- `TheValueIsBlended`: equity_found → valued (valued' = TRUE) — "the intrinsic value per share blends going concern and distress".

**analyze-sensitivity** (phases `tornado_done`, `grid_done`)
- `TheTornadoIsRun`: valued → tornado_done — "each assumption is moved to 0.8 and 1.2 times, one at a time" — `sensitivity.tornado`.
- `TheGridIsRun`: tornado_done → grid_done — "a five by five grid crosses the two widest axes" — `sensitivity.grid_2d`, `analysis._two_widest_axes`.

**analyze-flags** (phases `story_margin_checked`, `reinvestment_checked`, `beta_checked`, `tv_share_checked`, `country_checked`). Every flag action adds its name to `flags` and is enabled only when `valued`.
- From grid_done → story_margin_checked: `StoryMarginGreen` "story margin is green [not high-growth, or company margin at most the sector's]", `StoryMarginYellow` "story margin is yellow [high-growth and company margin above the sector's]", `StoryMarginUnknown` "story margin is unknown [a margin missing]" — `narrative_flags.story_margin_flag`.
- story_margin_checked → reinvestment_checked: `ReinvestmentRed` "reinvestment is red [a year with negative free cash flow, or reinvestment without profit]", `ReinvestmentYellow` "reinvestment is yellow [reinvestment above 90% of after-tax operating profit]", `ReinvestmentGreen` "reinvestment is green [otherwise]" — `growth_reinvestment_flag`.
- reinvestment_checked → beta_checked: `BetaYellow` "beta is yellow [sector beta below 1.0, operating leverage above 1.5, debt above 40%]", `BetaUnknown` "beta is unknown [one of the three missing]", `BetaGreen` "beta is green [otherwise]" — `beta_business_risk_flag`.
- beta_checked → tv_share_checked: `TerminalShareYellow` "terminal value share is yellow [above 80% of the enterprise value]", `TerminalShareGreen` "terminal value share is green [otherwise]" — `terminal_value_share_flag`.
- tv_share_checked → country_checked: `CountryUnknown` "country exposure is unknown [no revenue by geography is supplied]" — `country_exposure_flag`; `analysis.analyze` leaves `erp_weighted` / `erp_listing` unset.

**analyze-verdict** (phases `verdict_given`, `sanity_checked`, `reported`). Each verdict action sets `margin` and `verdict` together; `verdict' = MarginVerdict(m)`, a CASE that mirrors `margin_verdict`.
- country_checked → verdict_given: `TheMarginIsAtLeastOnePointThree` "the verdict reads the margin of safety (MoS) [MoS 1.3 or more]", `TheMarginIsFromOneToOnePointThree` "the verdict reads the margin of safety (MoS) [MoS from 1.0 to under 1.3]", `TheMarginIsBelowOne` "the verdict reads the margin of safety (MoS) [MoS below 1.0]", `TheTickerHasNoPrice` "the verdict reads the margin of safety (MoS) [no close, or a close at most 0]" — `analysis.analyze` `margin_of_safety`; `analysis_report.margin_verdict`.
- `TheMultiplesAreCompared`: verdict_given → sanity_checked — "implied price-to-earnings and enterprise value to sales are set beside the sector's" — `analysis._sanity_check`.
- `TheReportsAreWritten`: sanity_checked → reported (reports' = {"markdown", "HTML", "JSON"}, exitCode' = "0") — "the markdown, HTML and JSON reports are written" — `cli._analyze_one` (three `write_text` calls after `render_*`).

### Rules (each `INVARIANT`, name and reader sentence fixed; citation above)

| Id | Name | Reader sentence | Body |
| --- | --- | --- | --- |
| a | `VerdictOnlyIfValued` | Every company that gets a verdict was valued by the discounted cash flow (DCF). | `verdict # "none" => valued` |
| b | `UnresolvedNeverValued` | A company with an unresolved assumption is never valued and gets no verdict and no report. | `unresolved => (~valued /\ verdict = "none" /\ reports = {})` |
| c | `TerminalGrowthAtTheWaccStops` | Terminal growth at or above the weighted average cost of capital (WACC) stops the valuation. | `gVsWacc = "at or above" => (~valued /\ phase = "cannot_value" /\ exitCode = "1")` |
| d | `ImplausibleSharesStop` | Diluted shares outside the plausible range stop the valuation. | `shares = "implausible" => (~valued /\ phase = "cannot_value" /\ exitCode = "1")` |
| e | `OneStoryType` | A manual story type replaces the classifier's, and exactly one story type holds. | `(overrideStory # "unread" => (storyTypes = {"classifier"} \/ storyTypes = {"override"})) /\ (overrideStory = "given" => storyTypes = {"override"}) /\ (overrideStory = "absent" => storyTypes = {"classifier"}) /\ (valued => overrideStory # "unread")` |
| f | `UncoveredCurrencyLeavesTerminalGrowthUnresolved` | An uncovered valuation currency leaves terminal growth unresolved unless the override file gives it. | `(currency = "uncovered" /\ tgSource # "unread" /\ tgSource # "manual") => tgSource = "unresolved"` plus `tgSource = "rule based" => currency = "covered"` |
| g | `VerdictFromTheMargin` | The verdict is n/a exactly when there is no price; otherwise it is one of three words, by the thresholds 1.3 and 1.0. | `verdict # "none" => (verdict = ThresholdVerdict(margin) /\ ((verdict = "n/a") = (margin = "no price")))` with `ThresholdVerdict` written from CONTEXT.md "Verdict" |
| h | `FlagsAfterTheDcfNotInTheVerdict` | The narrative flags are computed after the DCF, and the verdict reads the margin of safety alone. | `(flags # {} => valued) /\ (verdict # "none" => (flags = FlagNames /\ verdict = ThresholdVerdict(margin)))` |
| i | `ReportsTogetherOnlyWhenValued` | The markdown, HTML and JSON reports are written together, and only for a valued company. | `reports # {} => (reports = {"markdown", "HTML", "JSON"} /\ valued /\ verdict # "none")` |
| j | `UnknownTickerSkippedBatchGoesOn` | An unknown ticker, or one without annual financials, ends before any valuation with exit code 2, and the batch goes on. | `phase = "not_found" => (exitCode = "2" /\ ~valued /\ storyTypes = {} /\ batch = "going")` |
| k | `OnlyTheCommandStopsTheBatch` | Only refused arguments or an empty screen stop the whole command; a failing ticker never does. | `batch = "stopped" => (phase = "command_stops" /\ storyTypes = {})` |
| l | `CannotValueMeansNoReport` | A company that cannot be valued exits with code 1 and gets no report. | `phase = "cannot_value" => (exitCode = "1" /\ ~valued /\ reports = {} /\ verdict = "none")` |

Citations, as `(* Cites: ... *)` above each rule's sentence: a `cli._analyze_one` (`render_*` only after `run_analysis` returns) and `analysis.analyze` (`margin_of_safety` built from `dcf_result`); b `to_dcf_assumptions` / `_require`; c `dcf.dcf` `terminal_growth >= wacc` raises; d `analysis.analyze` share bounds; e `_resolve_story_type` and `analyze` (`story_type = assumptions.story_type or auto_story.value`); f `_resolve_terminal_growth`; g `margin_verdict`, `views.MOS_UNDERVALUED` / `MOS_FAIR`; h `analyze` (`narrative_flags` after `dcf`, `margin_of_safety` from `dcf_result` and the price only); i `_analyze_one` (three writes in a row, after a successful `run_analysis`); j `_analyze_one` `except LookupError: return 2` inside the `for ticker` loop of `cli.analyze`; k `cli.analyze` (`typer.Exit(code=2)` only before the loop, `max` of exit codes inside it); l `_analyze_one` `except ValueError: return 1` before any write.

### State budget (worked estimate, story kept as 2 values)

inputs 8; story 7; assumptions about 50 (`unresolved` × `currency` × `tgSource`); dcf about 70 plus about 57 `cannot_value` variants; sensitivity 12; flags 30; verdict 3 phases × 4 margins × 6 = 72. Total about 306. With the five story types kept, the estimate passes 600: this is why the model does not keep them.

## Review Focus

1. **The CI report:** TLC must reach every phase. If a phase is unreachable because a guard is too strict, the chart drops it silently. Test: `test_analyze_every_phase_is_reachable` walks `_transitions("analyze")` from `asked` and asserts that every `states` key is reached.
2. **A rule that holds only vacuously** (for example a variable never set to the value its antecedent names). Test: `test_analyze_rule_antecedents_are_set`. It asserts that some action sets `gVsWacc' = "at or above"`, `shares' = "implausible"`, `unresolved' = TRUE`, `currency' = "uncovered"`, `batch' = "stopped"`, `overrideStory' = "given"`, and that every value of `margin` except `"unread"` is set.
3. **Sub-board budget:** a group with more than 20 model steps cannot become a sub-board of 24 arrows or fewer once its stores are added. Test: `test_analyze_groups_fit_a_subboard`.
4. **The SANY XML export failure** (#167): the model must not use `EXTENDS`, `Cardinality` or `<=>`. Test: `test_analyze_avoids_what_sany_export_rejects`.
5. **The citation convention:** an action without a `(* ... *)` line above it. Test: `test_analyze_actions_are_cited`.

---

### Task 1: the analyze model (`analyze.tla`, `analyze.cfg`, `analyze.view.js`)

**Files:**
- Create: `docs/pipeline/models/analyze.tla`, `docs/pipeline/models/analyze.cfg`, `docs/pipeline/models/analyze.view.js`
- Test: `tests/unit/test_pipeline_models.py`. The generic tests already apply to every `*.tla` stem. The analyze evals are written and committed by the pipeline's evals stage (`test(#169): evals`) before Task 1 starts, so Step 1 collects them and they fail on the missing files: a real FAIL, not exit 5.

**Interfaces:**
- Consumes: the helpers `_map`, `_definitions`, `_invariants`, `_transitions`, `_text` in `tests/unit/test_pipeline_models.py`.
- Produces: the phases, actions, variables and rule names above, verbatim. #170 draws them.

- [ ] **Step 1: The evals fail.** Run `uv run pytest -q tests/unit/test_pipeline_models.py -k analyze`. Expected: FAIL (the files are missing).

  The evals (written in the evals stage, in `tests/unit/test_pipeline_models.py`):
  - `test_analyze_model_exists`: `"analyze" in _STEMS`.
  - `test_analyze_groups`: `set(_map("analyze", "groups").values())` equals the seven groups, and `len(_invariants("analyze")) >= 8`.
  - `test_analyze_rules`: the `.cfg` INVARIANTs include the twelve names above.
  - `test_analyze_every_phase_is_reachable`, `test_analyze_rule_antecedents_are_set`, `test_analyze_groups_fit_a_subboard` (for each group, `sum(1 for a, (s, t) in _transitions("analyze").items() if groups[s] == g or groups[t] == g) <= 20`), `test_analyze_avoids_what_sany_export_rejects`, `test_analyze_actions_are_cited`: as in Review Focus.
  - `test_analyze_end_phases`: the `EndPhases ==` line lists exactly `command_stops`, `not_found`, `cannot_value`, `crashed`, `reported`.

- [ ] **Step 2: Write `analyze.tla`.** The header comment `(* One ticker through one run of `bot analyze` ... *)`, then `VARIABLES`, `vars`, `FlagNames`, `EndPhases`, `MarginVerdict(m)` (mirrors `margin_verdict`), `ThresholdVerdict(m)` (CONTEXT.md bands), `Init`, the actions in the order above, `Done`, `Next` (one action per `\/` line, ending with `Done`), `Spec`, then the twelve rules. Every action lists all the other variables in `UNCHANGED << ... >>`.

- [ ] **Step 3: Write `analyze.cfg`.** `SPECIFICATION Spec`, then one `INVARIANT <name>` line per rule, in table order.

- [ ] **Step 4: Write `analyze.view.js`.** `states` has one entry per phase, in reader's words, for example `asked: "the ticker is asked for"`, `cannot_value: "the ticker cannot be valued (exit code 1)"`, `reported: "the reports are written"`. `steps` has the labels above, plus `Done: "the run of this ticker ends"`. `groups` maps each phase to its group. Colors: inputs `blue`, story `purple`, assumptions `orange`, dcf `teal`, sensitivity `yellow`, flags `pink`, verdict `tan`.

- [ ] **Step 5: Run the tests.** `uv run pytest -q tests/unit/test_pipeline_models.py`. Expected: all pass, including the generic `[analyze]` cases.

- [ ] **Step 6: Commit.** `git add docs/pipeline/models/analyze.* && git commit -m "docs(#169): analyze model"`

### Task 2: TLC in CI until the report reads as required

**Files:**
- Modify (only if the run says so): `docs/pipeline/models/analyze.tla`, `analyze.view.js`; on a real bug, also `analyze.cfg` and `docs/pipeline/models/README.md` (broken rule protocol)

**Interfaces:**
- Consumes: Task 1's files; the `models` job; the artifact `pipeline-models`.

- [ ] **Step 1: Push and watch.** `git push -u origin HEAD`. Then run `id=$(gh run list --repo nicolas-ricc/damodaran --branch "$(git branch --show-current)" --workflow pipeline-diagram --limit 1 --json databaseId --jq '.[0].databaseId')` and `gh run watch "$id" --repo nicolas-ricc/damodaran --exit-status || true`, both in the foreground.
- [ ] **Step 2: Read the artifact.** If `gh run list` returns no id yet, run it again until the push's run shows up. `models` uploads `pipeline-models` with `if: always()` (`.github/workflows/pipeline-diagram.yml`), so a red job still has the artifact. Check that the report's line `TLC reached N states` has N ≤ 500, and that every `states` label of `analyze.view.js` appears in `chart.mmd`: this confirms TLC itself reached every phase, which the regex reachability test, blind to guards, cannot.
- [ ] **Step 2b:** Run `gh run download "$id" --repo nicolas-ricc/damodaran -n pipeline-models -D /tmp/models-<n>`. Then read `analyze/report.md` and `analyze/chart.mmd`, and `analyze/tlc.out` on an error. Expected: `## Rules that hold` lists at least 8 rules, there is no `breaks`, `Rules not checked` or `TLC stopped` section, `chart.mmd` exists, and the state count is at most 500.
- [ ] **Step 3: Fix and repeat.** A parse error or an unreachable phase means the model is wrong: fix it, run the tests, commit `fix(#169): ...`, and go back to Step 1. Budget: six push-watch-fix cycles. After that the stage is declared stuck and documented on the issue. A broken rule follows the protocol in `docs/pipeline/models/README.md`: replay it as a pytest against the real code; if the code behaves as the path shows, open a `bug` issue, move the rule to `\* broken: #n`, and add a row to the README table.
- [ ] **Step 4: Done** when the run on the head commit is green in both jobs (`render` and `models`).

## Citations for steps listed without one above

`ItIsNotDistressed`, `ItIsNotCyclical`, `ItIsNotHighGrowth`, `ItIsMatureStable`: `story_types.classify` (the `if` chain at lines 186-202). `MarginIsUnresolved`: `_resolve_operating_margin` (`sector_margin is None` → UNRESOLVED). `AScalarIsUnresolved`: `_resolve_sector_scalar` (`value is None` → UNRESOLVED). `WeightsAreUnresolved`: `_resolve_weights`, last return. `TheSharesArePlausible`: `analysis.analyze` (the share bounds pass). `EveryAssumptionHasASource`: `Assumptions.to_dcf_assumptions` returns. `TheTerminalValueIsComputed`, `TheEnterpriseValueIsSummed`, `TheEquityIsFound`, `TheValueIsBlended`: `dcf.dcf` body after the yearly loop (terminal year, `enterprise_value`, equity per share, the `probability_of_bankruptcy` blend).

## Assumptions

Technical decisions taken during grilling. Each satisfies the issue, and the rejected alternative is named.

1. **Story recorded by who set it, not by which type** (rejected: all five types). Keeping the five types would multiply later states by 6 and break the 500-state chart budget. Story-dependent sources stay as unguarded steps, with their condition in brackets.
2. **Over-approximations accepted.** Rejected alternative: a variable per data presence, which would multiply states. The sector row, the history and the override file are not variables. So `MarginIsUnresolved`, `AScalarIsUnresolved` and `WeightsAreUnresolved` can follow a found sector row, which the code allows (a NULL column in a found row). `GrowthIsUnresolved` is guarded by the uncovered currency only, and the manual actions are always enabled. No rule's antecedent becomes reachable only through a path the code cannot take: `unresolved` is reachable through `TerminalGrowthIsUnresolved`, which follows the code exactly.
3. **Rules c, d, j, k and l hold by construction today.** They are kept as regression guards against later model edits, and as the sentences the sub-boards show. For example, c breaks if `TerminalGrowthReachesTheWacc` stops setting the exit code, or if a later edit lets `projected` follow it. Rejected alternative: dropping them, but the issue asks for c and d by name.
4. **`MarginVerdict` (mirrors the code, in descending `>=` order) and `ThresholdVerdict` (CONTEXT.md bands as a lookup) are written separately.** With string bands they agree by construction. Rule g checks that each verdict action uses the band it names and that `n/a` goes with no price only. Rejected alternative: integer margins, which need `EXTENDS Naturals` and risk the SANY export.
5. **`storyTypes` is a set**, so the rule can say "exactly one" literally (a singleton), and a model edit that unions instead of replacing breaks it. Rejected alternative: a string, which cannot hold two types at all.
6. **File-system failures are left out**, as in the site model. A failed write is follow-up #178.
7. **`Done` has no `phase'` pair**: `_transitions` in `tests/unit/test_pipeline_models.py` skips `Done`, as in `site.tla`.
8. **`cannot_value` sits in analyze-dcf** and is entered from the story and assumptions groups. #164 allows a node from another group's board, linked to its own board (`test_neighbour_nodes_link_their_subboard`; `docs/pipeline/site-scan.d2` line 30).

9. **Every CASE has an `OTHER` arm** (`MarginVerdict`, `ThresholdVerdict` → `"none"`), as in `site.tla`, so TLC never aborts on `margin = "unread"` whatever its evaluation order.
10. **An acronym is expanded in every label that uses it**: a chart label is read alone, and `site.view.js` expands MoS in each of its margin labels.
11. **`test_analyze_actions_are_cited` exempts `Done`**, as `_transitions` does; `Done` cites nothing in the code (`site.tla` precedent).
12. **Rule k is expected to break.** `TheOverrideFileIsNotYaml` models what the code does with a malformed YAML override: an uncaught `yaml.YAMLError` ends the batch. When TLC reports the break, Task 2 follows the protocol: a replay test `tests/unit/test_analyze_model_replay.py` (committed, because it proves a bug), a `bug` issue, `\* broken: #n` above k, k removed from the `.cfg`, and a README row. The rule is not weakened. Twelve rules minus k still leaves eleven that hold, at least 8.
13. **The dcf board attaches no store**: in `docs/pipeline/analyze.d2` its edges come only from the assumptions and the inputs, so its 17 model steps fit under 24.

## Grilling

Round 1: 18 questions. Sources: ISSUE 5, CODE 9, DOC 2, NO SOURCE 7 → technical assumptions 6 (listed above), out of scope 1 (#178), spec ambiguities 0. Round 2: 15 questions. Sources: CODE 9 (order `analysis.py:662-720`; every stop is a `ValueError` caught by `cli.py:479`; `_load_override` is called in `resolve_assumptions` (`assumptions.py:735`), after `classify` (`analysis.py:651`); an unknown label is warned and passed through (`assumptions.py:737-743`, `analysis.py:660`); a missing override file gives `{}` (`assumptions.py:654`); `on: [push, workflow_dispatch]` has no filter), DOC 2 (CONTEXT.md "Verdict": `>=1.3` / `>=1.0` / `<1.0` / `n/a`; README conventions, no type invariant required), NO SOURCE 4 → technical assumptions 9-11 and 13. Finding: a malformed YAML override crashes the batch. It is modelled as `TheOverrideFileIsNotYaml` (assumption 12, broken rule protocol); it is not a separate follow-up.
Round 1 changes: `TheArgumentsAreRefused` was added and rule k widened; the reachability check against `chart.mmd` and a budget of six CI cycles were added; the citations were completed.
