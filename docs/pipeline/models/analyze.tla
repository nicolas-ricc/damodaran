---- MODULE analyze ----
(* One ticker through one run of `bot analyze`, from the command line to the three
   reports: the inputs, the story type, the assumptions, the discounted cash flow
   (DCF), the sensitivity runs, the narrative flags and the verdict. *)

VARIABLES phase, batch, exitCode, storyTypes, overrideStory, currency,
          tgSource, unresolved, shares, gVsWacc, valued, flags,
          margin, verdict, reports

vars == << phase, batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* The narrative flags the analysis computes after the DCF, one name each. *)
FlagNames == {"story margin", "reinvestment", "beta", "terminal value share", "country"}

EndPhases == {"command_stops", "not_found", "cannot_value", "crashed", "reported"}

(* margin_verdict in src/bot/reporting/analysis_report.py: the margin of safety bands, tested in descending order. *)
MarginVerdict(m) ==
  CASE m = "no price" -> "n/a"
    [] m = "1.3 or more" -> "potentially undervalued"
    [] m = "1.0 to under 1.3" -> "around fair value"
    [] m = "below 1.0" -> "potentially overvalued"
    [] OTHER -> "none"

(* The rule of CONTEXT.md "Verdict", from the margin of safety itself: 1.3 or more, 1.0 or more, below 1.0, n/a without a price. *)
ThresholdVerdict(m) ==
  CASE m = "1.3 or more" -> "potentially undervalued"
    [] m = "1.0 to under 1.3" -> "around fair value"
    [] m = "below 1.0" -> "potentially overvalued"
    [] m = "no price" -> "n/a"
    [] OTHER -> "none"

Init ==
  /\ phase = "asked"
  /\ batch = "going"
  /\ exitCode = "none"
  /\ storyTypes = {}
  /\ overrideStory = "unread"
  /\ currency = "unread"
  /\ tgSource = "unread"
  /\ unresolved = FALSE
  /\ shares = "unread"
  /\ gVsWacc = "unknown"
  /\ valued = FALSE
  /\ flags = {}
  /\ margin = "unread"
  /\ verdict = "none"
  /\ reports = {}

(* src/bot/cli.py: analyze, the `tickers` argument *)
TheTickersAreGiven ==
  /\ phase = "asked"
  /\ phase' = "chosen"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/cli.py: analyze, `SELECT ticker ... WHERE passed AND run_id = ? ORDER BY rank` *)
TheLatestScreenListsIt ==
  /\ phase = "asked"
  /\ phase' = "chosen"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/cli.py: analyze, argument checks (lines 405-415) raise typer.Exit(code=2) before the loop *)
TheArgumentsAreRefused ==
  /\ phase = "asked"
  /\ phase' = "command_stops"
  /\ batch' = "stopped"
  /\ exitCode' = "2"
  /\ UNCHANGED << storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/cli.py: analyze, `latest_run is None` / `not rows` raise typer.Exit(code=2) *)
TheScreenLeftNoCandidate ==
  /\ phase = "asked"
  /\ phase' = "command_stops"
  /\ batch' = "stopped"
  /\ exitCode' = "2"
  /\ UNCHANGED << storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/cli.py: analyze, the `override` option; _analyze_one *)
TheOverrideFlagNamesTheFile ==
  /\ phase = "chosen"
  /\ phase' = "override_picked"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: conventional_override_path *)
TheTickersFileExists ==
  /\ phase = "chosen"
  /\ phase' = "override_picked"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: conventional_override_path returns None *)
NoOverrideFile ==
  /\ phase = "chosen"
  /\ phase' = "override_picked"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: _load_company / _load_latest_financials raise LookupError; src/bot/cli.py: _analyze_one returns 2 *)
TheTickerIsUnknown ==
  /\ phase = "override_picked"
  /\ phase' = "not_found"
  /\ exitCode' = "2"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: load_valuation_input *)
TheCompanyIsLoaded ==
  /\ phase = "override_picked"
  /\ phase' = "loaded"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/regions.py: dataset_region, COUNTRY_REGION_OVERRIDES *)
ItsOwnDatasetRegion ==
  /\ phase = "loaded"
  /\ phase' = "region_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/regions.py: dataset_region, GEOGRAPHIC_TO_DATASET_REGION *)
RegionFromItsCountryGrouping ==
  /\ phase = "loaded"
  /\ phase' = "region_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/regions.py: dataset_region returns DEFAULT_DATASET_REGION *)
RegionDefaultsToUs ==
  /\ phase = "loaded"
  /\ phase' = "region_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: analyze (age, interest_coverage, is_cyclical); _latest_from_row (net debt) *)
TheSignalsAreDerived ==
  /\ phase = "region_set"
  /\ phase' = "signals"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, _is_distressed *)
ItIsDistressed ==
  /\ phase = "signals"
  /\ phase' = "classified"
  /\ storyTypes' = {"classifier"}
  /\ UNCHANGED << batch, exitCode, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, the `if` chain (lines 186-202) *)
ItIsNotDistressed ==
  /\ phase = "signals"
  /\ phase' = "not_distressed"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, _is_cyclical *)
ItIsCyclical ==
  /\ phase = "not_distressed"
  /\ phase' = "classified"
  /\ storyTypes' = {"classifier"}
  /\ UNCHANGED << batch, exitCode, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, the `if` chain (lines 186-202) *)
ItIsNotCyclical ==
  /\ phase = "not_distressed"
  /\ phase' = "not_cyclical"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, _HIGH_GROWTH_CAGR, _MATURE_AGE_YEARS *)
ItIsHighGrowth ==
  /\ phase = "not_cyclical"
  /\ phase' = "classified"
  /\ storyTypes' = {"classifier"}
  /\ UNCHANGED << batch, exitCode, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, the `if` chain (lines 186-202) *)
ItIsNotHighGrowth ==
  /\ phase = "not_cyclical"
  /\ phase' = "not_high_growth"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, _DECLINE_CAGR *)
ItIsInDecline ==
  /\ phase = "not_high_growth"
  /\ phase' = "classified"
  /\ storyTypes' = {"classifier"}
  /\ UNCHANGED << batch, exitCode, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/story_types.py: classify, the `if` chain (lines 186-202) *)
ItIsMatureStable ==
  /\ phase = "not_high_growth"
  /\ phase' = "classified"
  /\ storyTypes' = {"classifier"}
  /\ UNCHANGED << batch, exitCode, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _load_override raises ValueError; src/bot/cli.py: _analyze_one returns 1 *)
TheOverrideFileIsInvalid ==
  /\ phase = "classified"
  /\ phase' = "cannot_value"
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _load_override, yaml.safe_load raises yaml.YAMLError (an Exception, not a ValueError); _analyze_one catches only LookupError and ValueError, so the error leaves the `for ticker` loop of cli.analyze *)
TheOverrideFileIsNotYaml ==
  /\ phase = "classified"
  /\ phase' = "crashed"
  /\ batch' = "stopped"
  /\ exitCode' = "1"
  /\ UNCHANGED << storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: _resolve_story_type *)
NoManualStoryType ==
  /\ phase = "classified"
  /\ phase' = "story_set"
  /\ overrideStory' = "absent"
  /\ UNCHANGED << batch, exitCode, storyTypes, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: _resolve_story_type (manual wins); assumptions.py: resolve_assumptions, _STORY_TYPE_VALUES *)
TheOverrideSetsTheStoryType ==
  /\ phase = "classified"
  /\ phase' = "story_set"
  /\ overrideStory' = "given"
  /\ storyTypes' = {"override"}
  /\ UNCHANGED << batch, exitCode, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _load_sector_with_fallback, _pick_sector *)
TheSectorRowIsFound ==
  /\ phase = "story_set"
  /\ phase' = "sector_read"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _pick_sector returns (None, False) *)
NoSectorRow ==
  /\ phase = "story_set"
  /\ phase' = "sector_read"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: load_assumption_inputs, _currency_rates *)
TheCurrencyIsCovered ==
  /\ phase = "sector_read"
  /\ phase' = "currency_read"
  /\ currency' = "covered"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _currency_rates returns None rates; _warn_uncovered *)
TheCurrencyIsUncovered ==
  /\ phase = "sector_read"
  /\ phase' = "currency_read"
  /\ currency' = "uncovered"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_revenue_growth *)
GrowthIsResolved ==
  /\ phase = "currency_read"
  /\ phase' = "growth_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_revenue_growth returns UNRESOLVED when `gdp is None` *)
GrowthIsUnresolved ==
  /\ phase = "currency_read"
  /\ phase' = "growth_set"
  /\ currency = "uncovered"
  /\ unresolved' = TRUE
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_operating_margin *)
MarginIsResolved ==
  /\ phase = "growth_set"
  /\ phase' = "margin_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_operating_margin, `sector_margin is None` gives UNRESOLVED *)
MarginIsUnresolved ==
  /\ phase = "growth_set"
  /\ phase' = "margin_set"
  /\ unresolved' = TRUE
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_sector_scalar *)
ScalarsAreResolved ==
  /\ phase = "margin_set"
  /\ phase' = "scalars_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_sector_scalar, `value is None` gives UNRESOLVED *)
AScalarIsUnresolved ==
  /\ phase = "margin_set"
  /\ phase' = "scalars_set"
  /\ unresolved' = TRUE
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_weights *)
WeightsAreResolved ==
  /\ phase = "scalars_set"
  /\ phase' = "weights_set"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_weights, the last return *)
WeightsAreUnresolved ==
  /\ phase = "scalars_set"
  /\ phase' = "weights_set"
  /\ unresolved' = TRUE
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_weights raises ValueError; src/bot/cli.py: _analyze_one returns 1 *)
TheManualWeightsDoNotSumToOne ==
  /\ phase = "scalars_set"
  /\ phase' = "cannot_value"
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_terminal_growth, manual branch *)
TerminalGrowthIsManual ==
  /\ phase = "weights_set"
  /\ phase' = "tg_set"
  /\ tgSource' = "manual"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_terminal_growth, min(rates.risk_free_rate, rates.nominal_gdp_growth) *)
TerminalGrowthFromTheCurrency ==
  /\ phase = "weights_set"
  /\ phase' = "tg_set"
  /\ currency = "covered"
  /\ tgSource' = "rule based"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_terminal_growth, `rates is None` *)
TerminalGrowthIsUnresolved ==
  /\ phase = "weights_set"
  /\ phase' = "tg_set"
  /\ currency = "uncovered"
  /\ tgSource' = "unresolved"
  /\ unresolved' = TRUE
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: _resolve_tax_rate, _resolve_probability_of_bankruptcy, _resolve_distress_value_per_share *)
TaxAndBankruptcyAreSet ==
  /\ phase = "tg_set"
  /\ phase' = "ready"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: analyze, `latest.revenue is None` raises ValueError *)
NoLatestRevenue ==
  /\ phase = "ready"
  /\ phase' = "cannot_value"
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: analyze, MIN_PLAUSIBLE_SHARES / MAX_PLAUSIBLE_SHARES *)
TheSharesAreImplausible ==
  /\ phase = "ready"
  /\ phase' = "cannot_value"
  /\ shares' = "implausible"
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: analyze, the share bounds pass *)
TheSharesArePlausible ==
  /\ phase = "ready"
  /\ phase' = "shares_ok"
  /\ shares' = "plausible"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: Assumptions.to_dcf_assumptions / _require raise ValueError *)
AnAssumptionIsUnresolved ==
  /\ phase = "shares_ok"
  /\ phase' = "cannot_value"
  /\ unresolved
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/assumptions.py: Assumptions.to_dcf_assumptions returns *)
EveryAssumptionHasASource ==
  /\ phase = "shares_ok"
  /\ phase' = "resolved"
  /\ ~unresolved
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, `horizon == 0` and `sales_to_capital <= 0.0` raise ValueError *)
SalesToCapitalIsNotPositive ==
  /\ phase = "resolved"
  /\ phase' = "cannot_value"
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: _wacc *)
TheWaccIsComputed ==
  /\ phase = "resolved"
  /\ phase' = "wacc_computed"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, `terminal_growth >= wacc` raises ValueError *)
TerminalGrowthReachesTheWacc ==
  /\ phase = "wacc_computed"
  /\ phase' = "cannot_value"
  /\ gVsWacc' = "at or above"
  /\ exitCode' = "1"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, the yearly loop *)
TerminalGrowthIsBelowTheWacc ==
  /\ phase = "wacc_computed"
  /\ phase' = "projected"
  /\ gVsWacc' = "below"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, the terminal year after the yearly loop *)
TheTerminalValueIsComputed ==
  /\ phase = "projected"
  /\ phase' = "terminal_valued"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, enterprise_value *)
TheEnterpriseValueIsSummed ==
  /\ phase = "terminal_valued"
  /\ phase' = "ev_found"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, equity and value per share *)
TheEquityIsFound ==
  /\ phase = "ev_found"
  /\ phase' = "equity_found"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/dcf.py: dcf, the probability_of_bankruptcy blend *)
TheValueIsBlended ==
  /\ phase = "equity_found"
  /\ phase' = "valued"
  /\ valued' = TRUE
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, flags, margin, verdict, reports >>

(* src/bot/valuator/sensitivity.py: tornado *)
TheTornadoIsRun ==
  /\ phase = "valued"
  /\ phase' = "tornado_done"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/sensitivity.py: grid_2d; src/bot/valuator/analysis.py: _two_widest_axes *)
TheGridIsRun ==
  /\ phase = "tornado_done"
  /\ phase' = "grid_done"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: story_margin_flag *)
StoryMarginGreen ==
  /\ phase = "grid_done"
  /\ phase' = "story_margin_checked"
  /\ valued
  /\ flags' = flags \cup {"story margin"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: story_margin_flag *)
StoryMarginYellow ==
  /\ phase = "grid_done"
  /\ phase' = "story_margin_checked"
  /\ valued
  /\ flags' = flags \cup {"story margin"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: story_margin_flag *)
StoryMarginUnknown ==
  /\ phase = "grid_done"
  /\ phase' = "story_margin_checked"
  /\ valued
  /\ flags' = flags \cup {"story margin"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: growth_reinvestment_flag *)
ReinvestmentRed ==
  /\ phase = "story_margin_checked"
  /\ phase' = "reinvestment_checked"
  /\ valued
  /\ flags' = flags \cup {"reinvestment"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: growth_reinvestment_flag *)
ReinvestmentYellow ==
  /\ phase = "story_margin_checked"
  /\ phase' = "reinvestment_checked"
  /\ valued
  /\ flags' = flags \cup {"reinvestment"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: growth_reinvestment_flag *)
ReinvestmentGreen ==
  /\ phase = "story_margin_checked"
  /\ phase' = "reinvestment_checked"
  /\ valued
  /\ flags' = flags \cup {"reinvestment"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: beta_business_risk_flag *)
BetaYellow ==
  /\ phase = "reinvestment_checked"
  /\ phase' = "beta_checked"
  /\ valued
  /\ flags' = flags \cup {"beta"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: beta_business_risk_flag *)
BetaUnknown ==
  /\ phase = "reinvestment_checked"
  /\ phase' = "beta_checked"
  /\ valued
  /\ flags' = flags \cup {"beta"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: beta_business_risk_flag *)
BetaGreen ==
  /\ phase = "reinvestment_checked"
  /\ phase' = "beta_checked"
  /\ valued
  /\ flags' = flags \cup {"beta"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: terminal_value_share_flag *)
TerminalShareYellow ==
  /\ phase = "beta_checked"
  /\ phase' = "tv_share_checked"
  /\ valued
  /\ flags' = flags \cup {"terminal value share"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: terminal_value_share_flag *)
TerminalShareGreen ==
  /\ phase = "beta_checked"
  /\ phase' = "tv_share_checked"
  /\ valued
  /\ flags' = flags \cup {"terminal value share"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/narrative_flags.py: country_exposure_flag; analysis.analyze leaves erp_weighted / erp_listing unset *)
CountryUnknown ==
  /\ phase = "tv_share_checked"
  /\ phase' = "country_checked"
  /\ valued
  /\ flags' = flags \cup {"country"}
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, margin, verdict, reports >>

(* src/bot/valuator/analysis.py: analyze, margin_of_safety; src/bot/reporting/analysis_report.py: margin_verdict *)
TheMarginIsAtLeastOnePointThree ==
  /\ phase = "country_checked"
  /\ phase' = "verdict_given"
  /\ margin' = "1.3 or more"
  /\ verdict' = MarginVerdict("1.3 or more")
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, reports >>

(* src/bot/valuator/analysis.py: analyze, margin_of_safety; src/bot/reporting/analysis_report.py: margin_verdict *)
TheMarginIsFromOneToOnePointThree ==
  /\ phase = "country_checked"
  /\ phase' = "verdict_given"
  /\ margin' = "1.0 to under 1.3"
  /\ verdict' = MarginVerdict("1.0 to under 1.3")
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, reports >>

(* src/bot/valuator/analysis.py: analyze, margin_of_safety; src/bot/reporting/analysis_report.py: margin_verdict *)
TheMarginIsBelowOne ==
  /\ phase = "country_checked"
  /\ phase' = "verdict_given"
  /\ margin' = "below 1.0"
  /\ verdict' = MarginVerdict("below 1.0")
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, reports >>

(* src/bot/valuator/analysis.py: analyze, margin_of_safety; src/bot/reporting/analysis_report.py: margin_verdict *)
TheTickerHasNoPrice ==
  /\ phase = "country_checked"
  /\ phase' = "verdict_given"
  /\ margin' = "no price"
  /\ verdict' = MarginVerdict("no price")
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, reports >>

(* src/bot/valuator/analysis.py: _sanity_check *)
TheMultiplesAreCompared ==
  /\ phase = "verdict_given"
  /\ phase' = "sanity_checked"
  /\ UNCHANGED << batch, exitCode, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict, reports >>

(* src/bot/cli.py: _analyze_one, three write_text calls after render_* *)
TheReportsAreWritten ==
  /\ phase = "sanity_checked"
  /\ phase' = "reported"
  /\ reports' = {"markdown", "HTML", "JSON"}
  /\ exitCode' = "0"
  /\ UNCHANGED << batch, storyTypes, overrideStory, currency, tgSource, unresolved, shares, gVsWacc, valued, flags, margin, verdict >>

Done ==
  /\ phase \in EndPhases
  /\ UNCHANGED vars

Next ==
  TheTickersAreGiven
  \/ TheLatestScreenListsIt
  \/ TheArgumentsAreRefused
  \/ TheScreenLeftNoCandidate
  \/ TheOverrideFlagNamesTheFile
  \/ TheTickersFileExists
  \/ NoOverrideFile
  \/ TheTickerIsUnknown
  \/ TheCompanyIsLoaded
  \/ ItsOwnDatasetRegion
  \/ RegionFromItsCountryGrouping
  \/ RegionDefaultsToUs
  \/ TheSignalsAreDerived
  \/ ItIsDistressed
  \/ ItIsNotDistressed
  \/ ItIsCyclical
  \/ ItIsNotCyclical
  \/ ItIsHighGrowth
  \/ ItIsNotHighGrowth
  \/ ItIsInDecline
  \/ ItIsMatureStable
  \/ TheOverrideFileIsInvalid
  \/ TheOverrideFileIsNotYaml
  \/ NoManualStoryType
  \/ TheOverrideSetsTheStoryType
  \/ TheSectorRowIsFound
  \/ NoSectorRow
  \/ TheCurrencyIsCovered
  \/ TheCurrencyIsUncovered
  \/ GrowthIsResolved
  \/ GrowthIsUnresolved
  \/ MarginIsResolved
  \/ MarginIsUnresolved
  \/ ScalarsAreResolved
  \/ AScalarIsUnresolved
  \/ WeightsAreResolved
  \/ WeightsAreUnresolved
  \/ TheManualWeightsDoNotSumToOne
  \/ TerminalGrowthIsManual
  \/ TerminalGrowthFromTheCurrency
  \/ TerminalGrowthIsUnresolved
  \/ TaxAndBankruptcyAreSet
  \/ NoLatestRevenue
  \/ TheSharesAreImplausible
  \/ TheSharesArePlausible
  \/ AnAssumptionIsUnresolved
  \/ EveryAssumptionHasASource
  \/ SalesToCapitalIsNotPositive
  \/ TheWaccIsComputed
  \/ TerminalGrowthReachesTheWacc
  \/ TerminalGrowthIsBelowTheWacc
  \/ TheTerminalValueIsComputed
  \/ TheEnterpriseValueIsSummed
  \/ TheEquityIsFound
  \/ TheValueIsBlended
  \/ TheTornadoIsRun
  \/ TheGridIsRun
  \/ StoryMarginGreen
  \/ StoryMarginYellow
  \/ StoryMarginUnknown
  \/ ReinvestmentRed
  \/ ReinvestmentYellow
  \/ ReinvestmentGreen
  \/ BetaYellow
  \/ BetaUnknown
  \/ BetaGreen
  \/ TerminalShareYellow
  \/ TerminalShareGreen
  \/ CountryUnknown
  \/ TheMarginIsAtLeastOnePointThree
  \/ TheMarginIsFromOneToOnePointThree
  \/ TheMarginIsBelowOne
  \/ TheTickerHasNoPrice
  \/ TheMultiplesAreCompared
  \/ TheReportsAreWritten
  \/ Done

Spec == Init /\ [][Next]_vars

(* Cites: src/bot/cli.py _analyze_one calls render_* only after run_analysis returns; analysis.analyze builds margin_of_safety from dcf_result. *)
\* Every company that gets a verdict was valued by the discounted cash flow (DCF).
VerdictOnlyIfValued ==
  verdict # "none" => valued

(* Cites: assumptions.py Assumptions.to_dcf_assumptions and _require raise ValueError on an unresolved assumption. *)
\* A company with an unresolved assumption is never valued and gets no verdict and no report.
UnresolvedNeverValued ==
  unresolved => (~valued /\ verdict = "none" /\ reports = {})

(* Cites: dcf.py dcf raises ValueError when terminal_growth >= wacc. *)
\* Terminal growth at or above the weighted average cost of capital (WACC) stops the valuation.
TerminalGrowthAtTheWaccStops ==
  gVsWacc = "at or above" => (~valued /\ phase = "cannot_value" /\ exitCode = "1")

(* Cites: analysis.py analyze: MIN_PLAUSIBLE_SHARES and MAX_PLAUSIBLE_SHARES bound the diluted shares, else ValueError. *)
\* Diluted shares outside the plausible range stop the valuation.
ImplausibleSharesStop ==
  shares = "implausible" => (~valued /\ phase = "cannot_value" /\ exitCode = "1")

(* Cites: analysis.py _resolve_story_type, and analyze: story_type = assumptions.story_type or auto_story.value. *)
\* A manual story type replaces the classifier's, and exactly one story type holds.
OneStoryType ==
  (overrideStory # "unread" => (storyTypes = {"classifier"} \/ storyTypes = {"override"}))
  /\ (overrideStory = "given" => storyTypes = {"override"})
  /\ (overrideStory = "absent" => storyTypes = {"classifier"})
  /\ (valued => overrideStory # "unread")

(* Cites: assumptions.py _resolve_terminal_growth: rates is None gives UNRESOLVED unless the override file sets it. *)
\* An uncovered valuation currency leaves terminal growth unresolved unless the override file gives it.
UncoveredCurrencyLeavesTerminalGrowthUnresolved ==
  ((currency = "uncovered" /\ tgSource # "unread" /\ tgSource # "manual") => tgSource = "unresolved")
  /\ (tgSource = "rule based" => currency = "covered")

(* Cites: analysis_report.py margin_verdict; views.py MOS_UNDERVALUED and MOS_FAIR; CONTEXT.md "Verdict". *)
\* The verdict is n/a exactly when there is no price; otherwise it is one of three words, by the thresholds 1.3 and 1.0.
VerdictFromTheMargin ==
  verdict # "none" => (verdict = ThresholdVerdict(margin) /\ ((verdict = "n/a") = (margin = "no price")))

(* Cites: analysis.py analyze: narrative_flags run after dcf; margin_of_safety is built from dcf_result and the price only. *)
\* The narrative flags are computed after the DCF, and the verdict reads the margin of safety alone.
FlagsAfterTheDcfNotInTheVerdict ==
  (flags # {} => valued)
  /\ (verdict # "none" => (flags = FlagNames /\ verdict = ThresholdVerdict(margin)))

(* Cites: cli.py _analyze_one: three write_text calls in a row, after a successful run_analysis. *)
\* The markdown, HTML and JSON reports are written together, and only for a valued company.
ReportsTogetherOnlyWhenValued ==
  reports # {} => (reports = {"markdown", "HTML", "JSON"} /\ valued /\ verdict # "none")

(* Cites: cli.py _analyze_one: except LookupError returns 2, inside the for ticker loop of analyze. *)
\* An unknown ticker, or one without annual financials, ends before any valuation with exit code 2, and the batch goes on.
UnknownTickerSkippedBatchGoesOn ==
  phase = "not_found" => (exitCode = "2" /\ ~valued /\ storyTypes = {} /\ batch = "going")

(* Cites: cli.py analyze: typer.Exit(code=2) only before the loop; inside it the exit code is the max of the tickers' codes. *)
\* Only refused arguments or an empty screen stop the whole command; a failing ticker never does.
\* broken: #180
OnlyTheCommandStopsTheBatch ==
  batch = "stopped" => (phase = "command_stops" /\ storyTypes = {})

(* Cites: cli.py _analyze_one: except ValueError returns 1 before any write. *)
\* A company that cannot be valued exits with code 1 and gets no report.
CannotValueMeansNoReport ==
  phase = "cannot_value" => (exitCode = "1" /\ ~valued /\ reports = {} /\ verdict = "none")

====
