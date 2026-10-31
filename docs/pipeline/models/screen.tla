---- MODULE screen ----
(* One company, from the companies table through the coverage gate, the quality, value and trap
   rules, the ranking and the second pass, to the screener_candidates table and the shortlist report,
   in one run of `bot screen`. The rule counts and rule (l) are those of the default preset,
   config/presets/damodaran_value.yaml, as on the screen board. *)
VARIABLES phase, mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed,
          valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported,
          outcomes

vars == << phase, mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* The coverage reasons of src/bot/screener/engine.py CoverageReason. *)
Reasons == {"industry_unmapped", "benchmark_missing", "currency_uncovered"}

(* The three rule layers evaluate_company runs: quality gates, value indicators, trap detectors. *)
Layers == {"quality", "value", "traps"}

EndPhases == {"cut", "reported", "rejected_saved"}

Init ==
  /\ phase = "listed"
  /\ mapped = FALSE
  /\ currency = "unread"
  /\ capInUsd = "unread"
  /\ bench = "unread"
  /\ reasons = {}
  /\ layersRun = {}
  /\ qualityFailed = FALSE
  /\ valueOutcome = "unrun"
  /\ trapsOutcome = "unrun"
  /\ recorded = {}
  /\ inPercentiles = FALSE
  /\ kept = FALSE
  /\ dcf = "not_run"
  /\ margin = "none"
  /\ row = "none"
  /\ reported = FALSE
  /\ outcomes = {}

(* src/bot/screener/engine.py: run_screen reads _load_companies, _load_all_annual and _load_latest_prices; the company has industry_damodaran *)
TheScreenLoadsAMappedCompany ==
  /\ phase = "listed"
  /\ phase' = "loaded"
  /\ mapped' = TRUE
  /\ UNCHANGED << currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen reads _load_companies, _load_all_annual and _load_latest_prices; industry_damodaran is None *)
TheScreenLoadsAnUnmappedCompany ==
  /\ phase = "listed"
  /\ phase' = "loaded"
  /\ mapped' = FALSE
  /\ UNCHANGED << currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _load_reporting_currencies, normalize_currency; load_currency_table has the currency *)
ItsCurrencyIsCovered ==
  /\ phase = "loaded"
  /\ phase' = "currency_read"
  /\ currency' = "covered"
  /\ UNCHANGED << mapped, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _load_reporting_currencies, normalize_currency; load_currency_table lacks the currency, or it is missing *)
ItsCurrencyIsUncovered ==
  /\ phase = "loaded"
  /\ phase' = "currency_read"
  /\ currency' = "uncovered"
  /\ UNCHANGED << mapped, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _resolve_region; bot.reference.regions.dataset_region *)
RegionFromItsOwnDataset ==
  /\ phase = "currency_read"
  /\ phase' = "region_set"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _resolve_region; bot.reference.regions.dataset_region *)
RegionFromItsCountryGrouping ==
  /\ phase = "currency_read"
  /\ phase' = "region_set"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _resolve_region returns DEFAULT_REGION *)
RegionDefaultsToUs ==
  /\ phase = "currency_read"
  /\ phase' = "region_set"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _resolve_tax_rate returns the country rate when it is within 0 to 1;
   build_company_data calls it only when return on invested capital (ROIC) can be computed.
   The model keeps the order of the screen board; the step changes only phase. *)
TaxFromItsCountry ==
  /\ phase = "region_set"
  /\ phase' = "tax_set"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _resolve_tax_rate returns DEFAULT_TAX_RATE *)
TaxDefaultsTo21 ==
  /\ phase = "region_set"
  /\ phase' = "tax_set"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: build_company_data *)
TheRatiosAreComputed ==
  /\ phase = "tax_set"
  /\ phase' = "ratios"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _market_cap_usd calls bot.utils.fx.to_usd, or passes the cap through
   unchanged when it has no currency or no date *)
TheCapIsConvertedToUsd ==
  /\ phase = "ratios"
  /\ phase' = "cap_in_usd"
  /\ capInUsd' = "usd"
  /\ UNCHANGED << mapped, currency, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: _market_cap_usd returns None on LookupError, or when there is no market cap *)
TheCapHasNoUsdRate ==
  /\ phase = "ratios"
  /\ phase' = "cap_in_usd"
  /\ capInUsd' = "none"
  /\ UNCHANGED << mapped, currency, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen calls load_industry_benchmarks (industry_damodaran, else the provider industry) before the gate *)
TheBenchmarkHasAWaccRow ==
  /\ phase = "cap_in_usd"
  /\ phase' = "benchmark_looked"
  /\ bench' = "with_wacc"
  /\ UNCHANGED << mapped, currency, capInUsd, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen calls load_industry_benchmarks before the gate *)
TheBenchmarkHasNoWacc ==
  /\ phase = "cap_in_usd"
  /\ phase' = "benchmark_looked"
  /\ bench' = "no_wacc"
  /\ UNCHANGED << mapped, currency, capInUsd, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen calls load_industry_benchmarks before the gate *)
ThereIsNoBenchmarkRow ==
  /\ phase = "cap_in_usd"
  /\ phase' = "benchmark_looked"
  /\ bench' = "none"
  /\ UNCHANGED << mapped, currency, capInUsd, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen, `if row.industry_damodaran is None` *)
TheIndustryIsUnmapped ==
  /\ phase = "benchmark_looked"
  /\ ~mapped
  /\ phase' = "rejected_coverage"
  /\ reasons' = {"industry_unmapped"}
  /\ outcomes' = outcomes \cup {"rejected_by_coverage"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported >>

(* src/bot/screener/engine.py: run_screen, `elif benchmarks is None or benchmarks.wacc is None` *)
TheBenchmarkIsMissing ==
  /\ phase = "benchmark_looked"
  /\ mapped /\ bench # "with_wacc"
  /\ phase' = "rejected_coverage"
  /\ reasons' = {"benchmark_missing"}
  /\ outcomes' = outcomes \cup {"rejected_by_coverage"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported >>

(* src/bot/screener/engine.py: run_screen, the `else` branch after the benchmark checks *)
TheBenchmarkIsUsable ==
  /\ phase = "benchmark_looked"
  /\ mapped /\ bench = "with_wacc"
  /\ phase' = "benchmarked"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen, `if ccy not in table` *)
TheCurrencyIsUncovered ==
  /\ phase = "benchmarked"
  /\ currency = "uncovered"
  /\ phase' = "rejected_coverage"
  /\ reasons' = {"currency_uncovered"}
  /\ outcomes' = outcomes \cup {"rejected_by_coverage"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported >>

(* src/bot/screener/engine.py: run_screen, `screened += 1` *)
TheCurrencyIsCovered ==
  /\ phase = "benchmarked"
  /\ currency = "covered"
  /\ phase' = "measured"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, the quality loop; MinMarketCap needs a market cap *)
EveryQualityGatePasses ==
  /\ phase = "measured"
  /\ capInUsd = "usd"
  /\ phase' = "quality_passed"
  /\ layersRun' = layersRun \cup {"quality"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, the quality loop; MinMarketCap fails on a missing cap *)
AQualityGateFails ==
  /\ phase = "measured"
  /\ phase' = "quality_failed"
  /\ layersRun' = layersRun \cup {"quality"}
  /\ qualityFailed' = TRUE
  /\ recorded' = recorded \cup {"quality"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, valueOutcome, trapsOutcome, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, the value loop, `any_value = True` *)
AValueIndicatorPasses ==
  /\ phase \in {"quality_passed", "quality_failed"}
  /\ phase' = "value_passed"
  /\ layersRun' = layersRun \cup {"value"}
  /\ valueOutcome' = "passed"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, the value loop appends a failed indicator even after one passed; `passed` depends on any_value only *)
AValueIndicatorPassesAnotherFails ==
  /\ phase \in {"quality_passed", "quality_failed"}
  /\ phase' = "value_passed"
  /\ layersRun' = layersRun \cup {"value"}
  /\ valueOutcome' = "passed"
  /\ recorded' = recorded \cup {"value"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, trapsOutcome, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, `elif not result.skipped: failed_gates.append` *)
NoValueIndicatorPasses ==
  /\ phase \in {"quality_passed", "quality_failed"}
  /\ phase' = "value_failed"
  /\ layersRun' = layersRun \cup {"value"}
  /\ valueOutcome' = "failed"
  /\ recorded' = recorded \cup {"value"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, trapsOutcome, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, a skipped indicator appends nothing *)
EveryValueIndicatorIsSkipped ==
  /\ phase \in {"quality_passed", "quality_failed"}
  /\ phase' = "value_skipped"
  /\ layersRun' = layersRun \cup {"value"}
  /\ valueOutcome' = "skipped"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, the trap loop *)
EveryTrapDetectorPasses ==
  /\ phase \in {"value_passed", "value_failed", "value_skipped"}
  /\ phase' = "traps_passed"
  /\ layersRun' = layersRun \cup {"traps"}
  /\ trapsOutcome' = "passed"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, valueOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company, trap loop `else: failed_gates.append(detector.name)` *)
ATrapDetectorFails ==
  /\ phase \in {"value_passed", "value_failed", "value_skipped"}
  /\ phase' = "traps_failed"
  /\ layersRun' = layersRun \cup {"traps"}
  /\ trapsOutcome' = "failed"
  /\ recorded' = recorded \cup {"traps"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, qualityFailed, valueOutcome, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen, `if not verdict.passed: rejected.append(...)` *)
TheCompanyIsRejected ==
  /\ phase \in {"traps_passed", "traps_failed"}
  /\ qualityFailed \/ valueOutcome # "passed" \/ trapsOutcome # "passed"
  /\ phase' = "rejected_rules"
  /\ outcomes' = outcomes \cup {"rejected_by_rules"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported >>

(* src/bot/screener/engine.py: run_screen, `pending.append` and `candidates.append` *)
TheCompanySurvives ==
  /\ phase = "traps_passed"
  /\ ~qualityFailed /\ valueOutcome = "passed" /\ trapsOutcome = "passed"
  /\ phase' = "survivor"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: evaluate_company builds the _Verdict with _quality_metric and _growth_metric (via cagr); run_screen carries them into Candidate for survivors only *)
TheMetricsAreComputed ==
  /\ phase = "survivor"
  /\ phase' = "metrics"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/ranking.py: _percentiles over all candidates *)
TheMetricsBecomePercentiles ==
  /\ phase = "metrics"
  /\ phase' = "percentiles"
  /\ inPercentiles' = TRUE
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/ranking.py: rank with PLACEHOLDER_MARGIN_OF_SAFETY *)
TheFirstPassScoresIt ==
  /\ phase = "percentiles"
  /\ phase' = "first_ranked"
  /\ margin' = "placeholder"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen, `if top is not None` is false *)
NoTopIsGiven ==
  /\ phase = "first_ranked"
  /\ phase' = "kept"
  /\ kept' = TRUE
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen, `first_pass[:top]` holds it *)
TheTopKeepsIt ==
  /\ phase = "first_ranked"
  /\ phase' = "kept"
  /\ kept' = TRUE
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/engine.py: run_screen, `first_pass[:top]` drops it *)
TheTopCutsIt ==
  /\ phase = "first_ranked"
  /\ phase' = "cut"
  /\ outcomes' = outcomes \cup {"cut"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported >>

(* src/bot/screener/engine.py: _batch_dcf_margins returns a margin *)
TheDcfValuesIt ==
  /\ phase = "kept"
  /\ phase' = "valued"
  /\ dcf' = "valued"
  /\ margin' = "real"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, row, reported, outcomes >>

(* src/bot/screener/engine.py: _batch_dcf_margins gives None, so PLACEHOLDER_MARGIN_OF_SAFETY stays *)
TheDcfCannotValueIt ==
  /\ phase = "kept"
  /\ phase' = "unvalued"
  /\ dcf' = "failed"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, margin, row, reported, outcomes >>

(* src/bot/screener/ranking.py: rescore_with_margins *)
TheScoreIsReblended ==
  /\ phase \in {"valued", "unvalued"}
  /\ phase' = "rescored"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, reported, outcomes >>

(* src/bot/screener/persist.py: persist_candidates, the shortlist loop, passed TRUE *)
ItsShortlistRowIsSaved ==
  /\ phase = "rescored"
  /\ phase' = "saved"
  /\ row' = "passed"
  /\ outcomes' = outcomes \cup {"persisted"}
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, reported >>

(* src/bot/reporting/screen_report.py: render_markdown and render_csv over result.shortlist *)
TheReportListsIt ==
  /\ phase = "saved"
  /\ phase' = "reported"
  /\ reported' = TRUE
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, row, outcomes >>

(* src/bot/screener/persist.py: persist_candidates, the rejected loop, passed FALSE *)
ItsRejectionIsSaved ==
  /\ phase \in {"rejected_coverage", "rejected_rules"}
  /\ phase' = "rejected_saved"
  /\ row' = "failed"
  /\ UNCHANGED << mapped, currency, capInUsd, bench, reasons, layersRun, qualityFailed, valueOutcome, trapsOutcome, recorded, inPercentiles, kept, dcf, margin, reported, outcomes >>

Done ==
  /\ phase \in EndPhases
  /\ UNCHANGED vars

Next ==
  TheScreenLoadsAMappedCompany
  \/ TheScreenLoadsAnUnmappedCompany
  \/ ItsCurrencyIsCovered
  \/ ItsCurrencyIsUncovered
  \/ RegionFromItsOwnDataset
  \/ RegionFromItsCountryGrouping
  \/ RegionDefaultsToUs
  \/ TaxFromItsCountry
  \/ TaxDefaultsTo21
  \/ TheRatiosAreComputed
  \/ TheCapIsConvertedToUsd
  \/ TheCapHasNoUsdRate
  \/ TheBenchmarkHasAWaccRow
  \/ TheBenchmarkHasNoWacc
  \/ ThereIsNoBenchmarkRow
  \/ TheIndustryIsUnmapped
  \/ TheBenchmarkIsMissing
  \/ TheBenchmarkIsUsable
  \/ TheCurrencyIsUncovered
  \/ TheCurrencyIsCovered
  \/ EveryQualityGatePasses
  \/ AQualityGateFails
  \/ AValueIndicatorPasses
  \/ AValueIndicatorPassesAnotherFails
  \/ NoValueIndicatorPasses
  \/ EveryValueIndicatorIsSkipped
  \/ EveryTrapDetectorPasses
  \/ ATrapDetectorFails
  \/ TheCompanyIsRejected
  \/ TheCompanySurvives
  \/ TheMetricsAreComputed
  \/ TheMetricsBecomePercentiles
  \/ TheFirstPassScoresIt
  \/ NoTopIsGiven
  \/ TheTopKeepsIt
  \/ TheTopCutsIt
  \/ TheDcfValuesIt
  \/ TheDcfCannotValueIt
  \/ TheScoreIsReblended
  \/ ItsShortlistRowIsSaved
  \/ TheReportListsIt
  \/ ItsRejectionIsSaved
  \/ Done

Spec == Init /\ [][Next]_vars

(* Cites: run_screen: `if row.industry_damodaran is None` rejects before the gate; evaluate_company runs only after it. *)
\* A company without a Damodaran industry never reaches a rule and leaves as industry_unmapped, whatever its sector benchmark.
UnmappedLeavesAsUnmapped ==
  ~mapped => (layersRun = {} /\ reasons \subseteq {"industry_unmapped"})

(* Cites: run_screen: `elif benchmarks is None or benchmarks.wacc is None` rejects before evaluate_company. *)
\* A company without a sector benchmark weighted average cost of capital (WACC) never reaches a rule.
NoWaccNoRule ==
  bench # "with_wacc" => layersRun = {}

(* Cites: run_screen: `if ccy not in table` rejects before evaluate_company, after the industry and benchmark checks. *)
\* A company whose valuation currency (its reporting currency) is uncovered never reaches a rule, and leaves as currency_uncovered when no earlier reason applies.
UncoveredCurrencyNoRule ==
  currency = "uncovered" =>
    (layersRun = {} /\ ((reasons # {} /\ mapped /\ bench = "with_wacc") => reasons = {"currency_uncovered"}))

(* Cites: run_screen: one if / elif / else chain gives one CoverageReason per rejected company. *)
\* A company rejected by the coverage gate has exactly one reason.
OneCoverageReason ==
  (("rejected_by_coverage" \in outcomes) = (reasons # {})) /\ (\A r1, r2 \in reasons : r1 = r2)

(* Cites: evaluate_company: the quality, value and trap loops all run and append each failed rule to failed_gates. *)
\* Every layer runs on a measured company, even after a failed gate, so the failed rules of every layer are recorded.
EveryLayerRecorded ==
  ("traps" \in layersRun \/ "rejected_by_rules" \in outcomes \/ phase = "survivor" \/ inPercentiles) =>
    (layersRun = Layers /\ (qualityFailed => "quality" \in recorded)
      /\ (valueOutcome = "failed" => "value" \in recorded)
      /\ (trapsOutcome = "failed" => "traps" \in recorded))

(* Cites: run_screen: `if not verdict.passed: rejected.append(...)`; only candidates reach rank. *)
\* A failed quality gate, no passing value indicator, or a failed trap detector rejects the company, and it is never ranked.
FailedLayerRejects ==
  (qualityFailed \/ valueOutcome \in {"failed", "skipped"} \/ trapsOutcome = "failed") =>
    (~inPercentiles /\ ~kept /\ row # "passed")

(* Cites: run_screen: `candidates.append` only for a passed verdict; ranking._percentiles runs over candidates. *)
\* Only a company that passed all three layers enters the percentiles.
OnlySurvivorsInPercentiles ==
  inPercentiles =>
    (layersRun = Layers /\ ~qualityFailed /\ valueOutcome = "passed" /\ trapsOutcome = "passed")

(* Cites: run_screen: _batch_dcf_margins runs over first_pass[:top]; persist_candidates saves result.shortlist. *)
\* The second pass values only survivors kept on the shortlist, and a survivor cut by the top N is neither valued nor saved.
CutNeitherValuedNorSaved ==
  (dcf # "not_run" => (kept /\ inPercentiles))
    /\ (phase = "cut" => (dcf = "not_run" /\ row = "none" /\ ~reported))

(* Cites: _batch_dcf_margins gives None, which keeps PLACEHOLDER_MARGIN_OF_SAFETY; rescore_with_margins, persist_candidates and render_markdown still take the company. *)
\* A kept survivor that cannot be valued keeps the placeholder margin of safety, and is still saved and reported.
UnvaluedKeepsPlaceholder ==
  (dcf = "failed" => margin = "placeholder")
    /\ ((kept /\ phase \in EndPhases) => (row = "passed" /\ reported))

(* Cites: persist_candidates: the rejected loop saves passed FALSE; render_markdown and render_csv read result.shortlist only. *)
\* A rejected company is saved with passed set to false, and is not in the report.
RejectedSavedAsFailed ==
  ((outcomes \cap {"rejected_by_coverage", "rejected_by_rules"} # {} /\ phase \in EndPhases) => row = "failed")
    /\ (row = "failed" => ~reported)

(* Cites: run_screen: a company is rejected by the gate, rejected by the rules, cut by first_pass[:top], or on the shortlist, never two. *)
\* A company reaches at most one end: rejected by the coverage gate, rejected by the rules, cut, or saved on the shortlist.
OneEndOnly ==
  \A o1, o2 \in outcomes : o1 = o2

(* Cites: _market_cap_usd returns None; MinMarketCap fails on a missing cap in the quality loop. *)
\* A company whose market cap has no value in US dollars (USD) fails the quality gates.
NoUsdCapFailsQuality ==
  (capInUsd = "none" /\ "quality" \in layersRun) => qualityFailed

(* Cites: evaluate_company: a skipped value indicator appends nothing to failed_gates. *)
\* When every value indicator is skipped, the company is rejected with no failed value rule recorded.
SkippedValueRecordsNothing ==
  valueOutcome = "skipped" => "value" \notin recorded

====
