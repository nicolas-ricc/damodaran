# Refresh model (TLA+) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/pipeline/models/refresh.{tla,cfg,view.js}`, a TLC-checked model of one ticker going through one `bot refresh --all` run (Damodaran datasets, SEC EDGAR fundamentals and facts, end-of-day prices, foreign exchange rates). Its five groups are the refresh sub-boards of #166.

**Architecture:** A single `phase` variable carries the reader's state through five groups in run order: `refresh-damodaran`, `refresh-fundamentals`, `refresh-facts` (one fact of the ticker, nested inside the fundamentals import as a flat stretch of `phase` values), `refresh-prices`, `refresh-fx`. A few small flag variables carry what the rules read. A handover step resets the flags of the stage it leaves, so the state count stays well under the chart budget of 500. Each rule is an `INVARIANT` with a `(* Cites: ... *)` line and a `\*` reader's sentence. CI's `models` job is the only TLC run.

**Tech Stack:** TLA+ / TLC 1.7.4, the statechart skill pinned at `4dd1d058`, an ES-module view, pytest convention tests, the GitHub Actions `pipeline-diagram` workflow.

**Spec:** issue #165 (body), parent story #161. Conventions: `docs/pipeline/models/README.md`, `site.tla`/`site.view.js` as the worked example, `tests/unit/test_pipeline_models.py`.

## Global Constraints

- Files: `docs/pipeline/models/refresh.tla` (first line `---- MODULE refresh ----`), `refresh.cfg`, `refresh.view.js`. No other new file in `docs/pipeline/models/`.
- No file under `src/` and no `docs/pipeline/*.d2` changes. No pipeline code changes.
- `Next == A1 \/ ... \/ Done`; `Done == phase \in EndPhases /\ UNCHANGED vars`; `Spec == Init /\ [][Next]_vars`. `.cfg` is `SPECIFICATION Spec` and then one `INVARIANT <Name>` line per rule. Deadlock checking stays on.
- `\*` comments are used only for a rule's reader's sentence and for `\* broken: #n`. Each action carries a `(* <file>: <code it mirrors> *)` comment. Each rule carries a `(* Cites: ... *)` line directly above its `\*` sentence.
- View: `const states = {`, `const steps = {`, `const groups = {` (not exported, one `key: "value",` per line), then exactly the five exports from `site.view.js` with `title = "refresh: one ticker through bot refresh"`. Labels contain no `_`, no camelCase and no action name. Acronyms are expanded at first use, and a condition goes at the end of a step label in `[brackets]`.
- Groups are exactly `refresh-damodaran` (blue), `refresh-fundamentals` (orange), `refresh-facts` (purple), `refresh-prices` (teal) and `refresh-fx` (yellow). A group stays at 24 arrows or fewer, counting its steps plus the stores and services its sub-board attaches.
- Fewer than 500 distinct states. Estimate: about 170.

### Declared modelling decisions (technical assumptions)

1. **SEC EDGAR providers only** (edgar-tiingo is the default, edgar-stooq the alternative; ADR 0007). The Financial Modeling Prep (FMP) provider is left out. Its statements skip the facts path (`edgar_base.py`), and its bars carry their own market cap (`fmp.py` `marketCap`, `current_market_cap`). So rule (k) is read as "under a SEC EDGAR provider". Under these providers `fx_rates` returns `[]` for any currency (`edgar_base.py` `fx_rates`), so the FX group has no rate-limit or failure path.
2. **Run flags are chosen at the step where they act**, not in `Init`. Choosing `--force` is the step "the ticker is fetched [... or --force]", and `--only-missing` is part of the prices listing steps. This keeps the Damodaran states from multiplying.
3. **A handover resets the flags of the stage it leaves.** The Damodaran flags reset when fundamentals start. The fundamentals and facts flags reset when prices start. When the fact path hands back to the import, only the fact flags that rule (h) reads are kept. Every rule reads its flags only while its own stage runs.
4. **Left out:** a database write failure inside a transaction, the region check (it refuses before any source runs), an empty universe file, both Damodaran sides empty at once, and the per-ticker refresh_log row. The run's status thresholds (5% / 25%) concern the whole universe, not the one ticker, so the model counts an outcome without computing them. A prices fetch that returns no new bar, which counts the ticker as imported with 0 rows, is also left out.
5. **An invalid mapping stops the command.** `load_industry_mapping` raises `ValueError` inside `refresh_universe`. Nothing in `_refresh_fmp_universe` or `refresh` catches it, so prices and FX never run. `mapping_refused` is an end phase.

## Assumptions

Decided during grilling (technical; the rejected alternative is in brackets):

- A1. **The model follows a ticker with at least one fact.** A company-facts document with no accepted fact is imported with a company row and no financials (`import_company` writes whatever `parse_company_facts` returns). That path is left out [rejected: an extra arrow `fetching→ticker_counted` "imported, no rows"].
- A2. **The rules mirror the code's structure, so most hold by construction.** What TLC checks is reachability over the whole graph. Rule (a) holds only if no path from `damodaran_failed` reaches a write, (e) only if no path from `mapping_refused` reaches prices, and (m) checks the stage order on every path. The rules are also the sentences the sub-boards show (#166). [rejected: modelling the code more loosely so that rules can break; that would describe a pipeline that does not exist.]
- A3. **Several arrows on one edge, each with its own label, are acceptable.** `site.view.js` already has four labels on `renderable→row`, and its CI is green. The shared-label rule applies only where two actions mean the same thing to the reader.
- A4. **Stores per sub-board are the `refresh.d2` nodes of that sub-flow.** Damodaran has 4 (Damodaran site, `damodaran_industry`, `damodaran_country`, `refresh_log`), fundamentals 8, facts 0 or 1, prices 6, FX 3. #166 owns the final choice. With these counts every group is at 24 or fewer.
- A5. **A replay test** for a broken rule lives in `tests/unit/test_refresh_replay_<rule>.py`. It is committed only when it proves a real code bug, and is otherwise discarded (issue: "not committed if it only proves the model wrong").
- A6. **`stagesDone` also records "damodaran".** It costs no states, because each phase has exactly one `stagesDone` value. It keeps the stage order readable in TLC traces.

## Review Focus

1. A phase that some combination of flags leaves with no enabled step is a deadlock: TLC fails `NoDeadlock`, and CI reports `breaks`. Check every guard on `rowKind`. `row_labelled` and `fact_derived` must each have a step for `"year"` and one for `"quarter"`.
2. Every `states` key must be a phase that some action can reach, and every phase an action sets must be a `states` key. Otherwise `state()` returns `undefined` and the chart draws an unlabelled state.
3. Two actions that share an arrow (same source, same target) must have the identical label, or the chart draws two arrows. This applies to `TheCheckFindsNoNewerStoredFiling` with `TheRunHasForce`, `TheCheckIsRateLimited` with `AnEarlierTickerHitTheLimit`, the two `TheInstantJoins*`, and the two price deferrals.
4. Each `UNCHANGED` list must name every variable the action does not set, or TLC stops ("TLC stopped") because a primed variable is undefined.
5. Rules are on the CI report: at least 10 under `## Rules that hold`, and no `breaks`, `Rules not checked` or `TLC stopped` section. A rule that breaks follows the broken rule protocol and is never weakened.

---

### Task 1: the refresh model

**Files:**
- Create: `docs/pipeline/models/refresh.tla`, `refresh.cfg`, `refresh.view.js`
- Modify: `docs/pipeline/models/README.md`: in "Files", replace "`site` is the first stage modelled." with "`site` and `refresh` are modelled."
- Test: `tests/unit/test_pipeline_models.py` (stage-3 evals, already committed)

**Interfaces:**
- Produces: the phase keys, action names and rule names below. #166 draws its sub-boards from them, and Task 2 reads the CI report by these names.

**Variables** (all initial values in brackets):
`phase` ["started"]; `stagesDone` [{}] ⊆ {"damodaran","fundamentals","prices"};
Damodaran: `dDegraded` [FALSE], `dCoreFailed` [FALSE], `dIndustry` ["kept"] ∈ {"kept","replaced"}, `dCountry` ["kept"], `dEmpty` ["none"] ∈ {"none","industry","country"}, `dStatus` ["none"] ∈ {"none","success","partial","error"};
fundamentals: `mappingInvalid` [FALSE], `force` [FALSE], `latestStored` [FALSE], `fRateLimit` ["none"] ∈ {"none","this ticker","earlier ticker"}, `fLater` ["waiting"] ∈ {"waiting","deferred"}, `fOutcome` ["none"] ∈ {"none","imported","skipped","failed","deferred"}, `companyWritten` [FALSE], `financialsWritten` [FALSE], `industryDamodaran` ["none"] ∈ {"none","set","empty"}, `unmapped` [FALSE];
facts: `factKind` ["none"] ∈ {"none","duration","instant","other"}, `rowKind` ["none"] ∈ {"none","year","quarter"}, `fiscalYear` ["none"] ∈ {"none","set"}, `otherCounts` ["unknown"] ∈ {"unknown","under three","three or more"}, `sharesRescaled` [FALSE], `factInRow` [FALSE];
prices: `barCurrent` [FALSE], `requested` [FALSE], `newestAge` ["unknown"] ∈ {"unknown","7 days or less","older"}, `shares` ["unknown"] ∈ {"unknown","found","failed"}, `marketCap` [FALSE], `pRateLimit` ["none"], `pLater` ["waiting"], `pOutcome` ["none"] ∈ {"none","left out","skipped","imported","failed","deferred"};
FX: `fxCurrencies` ["unknown"] ∈ {"unknown","only USD","others"}, `fxCalled` [FALSE], `fxStatus` ["none"] ∈ {"none","success"}.

`EndPhases == {"mapping_refused", "fx_done"}`. Define `PricePhases` as the five prices phases and `FxPhases` as the three FX phases.

**Phases, states labels and groups** (key: label):

| group | phase: label |
| --- | --- |
| refresh-damodaran | started: "the refresh command starts with --all"; downloaded: "the Damodaran files are downloaded"; industry_read: "the industry files are read"; merged: "one row per industry"; country_read: "the country rows are read"; derived: "the derived columns are filled in"; damodaran_written: "the Damodaran tables are written"; damodaran_failed: "the Damodaran run fails and writes nothing" |
| refresh-fundamentals | mapping_loading: "the industry mapping is loaded"; mapping_refused: "the command stops: the industry mapping is invalid"; ticker_checked: "the ticker waits for the latest-filing check"; fetching: "the company facts and submissions of the ticker are fetched"; facts_parsed: "the facts of the ticker are parsed into rows"; ticker_counted: "the fundamentals outcome of the ticker is counted" |
| refresh-facts | fact_read: "one fact of the ticker is read"; fact_in_period: "the fact belongs to a year or quarter row"; fact_chosen: "the fact fills its column for that period end"; fact_derived: "the aggregates of the row are derived"; row_labelled: "the row has its fiscal year"; fact_in_row: "the row of the fact is ready to write"; fact_dropped: "the fact is dropped" |
| refresh-prices | price_listing: "the prices stage lists the tickers"; price_listed: "the ticker is on the price list"; price_queued: "the ticker waits its turn, stalest first"; bars_fetched: "the new daily bars of the ticker arrive"; price_counted: "the price outcome of the ticker is counted" |
| refresh-fx | fx_listing: "the foreign exchange (FX) stage lists the listing currencies other than the US dollar (USD)"; fx_requested: "the rates of a currency are requested"; fx_done: "the refresh command ends" |

**Actions** (`from → to`, the variables each one sets, its step label, and the code it cites):

refresh-damodaran (`damodaran.py` `import_damodaran`, `_import_files_into_run`):
- `AllEightFilesDownload` started→downloaded. Label: "the eight files download". Cites the `download_dataset` calls.
- `AnotherFileFailsToDownload` started→downloaded, dDegraded. Label: "the files download without one of the six others [its download fails]". Cites `except` → `unavailable.append`.
- `ACoreFileFailsToDownload` started→damodaran_failed, dCoreFailed, dStatus "error". Label: "the run stops [wacc.xls or ctryprem.xls fails to download]". Cites the outer `except` with `status_override = "error"`, which skips `_import_files_into_run`.
- `TheIndustryFilesAreRead` downloaded→industry_read. Label: "the industry files are read".
- `AnotherFileFailsToParse` downloaded→industry_read, dDegraded. Label: "the industry files are read without one of the six others [it cannot be read]". Cites `degraded.append`.
- `TheWaccFileFailsToParse` downloaded→damodaran_failed, dCoreFailed, dStatus "error". Label: "the run stops [wacc.xls cannot be read]". Cites the first `parse_industry_xls`, which raises before `transaction`.
- `TheIndustryFilesAreMerged` industry_read→merged. Label: "the industry files are joined on the industry name [the earlier file wins a shared column]". Cites `merge_industry_datasets`.
- `TheCountrySheetIsRead` merged→country_read. Label: "the country risk sheet is read". Cites `parse_country_xls`.
- `TheCountryFileFailsToParse` merged→damodaran_failed, dCoreFailed, dStatus "error". Label: "the run stops [ctryprem.xls cannot be read]". Cites `parse_country_xls`, which raises before `transaction`, and the `except` around `_import_files_into_run` in `import_damodaran` that sets `status_override = "error"`.
- `TheColumnsAreDerived` country_read→derived. Label: "debt-to-equity, unlevered beta and country tax rates are filled in". Cites `derive_industry_columns`, `parse_country_tax_rates`.
- `BothSidesAreWritten` derived→damodaran_written, dIndustry/dCountry "replaced", dStatus = IF dDegraded THEN "partial" ELSE "success". Label: "both tables are replaced for the year in one transaction [industry and country rows exist]".
- `TheIndustrySideIsEmpty` derived→damodaran_written, dEmpty "industry", dCountry "replaced", dStatus "partial". Label: "only the country table is replaced, the run is partial [no industry rows]". Cites `upsert_industry_rows` `if not rows: return 0` before its `DELETE`.
- `TheCountrySideIsEmpty`: the mirror of the previous one. Label: "only the industry table is replaced, the run is partial [no country rows]".
- `FundamentalsStartAfterTheWrite` damodaran_written→mapping_loading and `FundamentalsStartAfterTheFailure` damodaran_failed→mapping_loading. Both add "damodaran" to stagesDone and reset the Damodaran flags. Labels: "the fundamentals stage starts" and "the fundamentals stage starts [a Damodaran failure does not stop the command]". Cites `cli.py` `refresh`: `exit_code = max(...)`, then `if fmp:`.

refresh-fundamentals (`universe.py` `refresh_universe`, `_run_bulk_refresh`, `_refresh_one`, `_should_skip`, `import_company`, `_company_row`; `industry_mapping.py` `load_industry_mapping`):
- `TheMappingIsInvalid` mapping_loading→mapping_refused, mappingInvalid. Label: "the load fails [a target outside the Damodaran industry list, or a duplicate label]". Cites the `ValueError` raises, which nothing in `refresh` catches.
- `TheMappingLoads` mapping_loading→ticker_checked. Label: "the mapping is loaded once for the run".
- `TheLatestFilingIsStored` ticker_checked→ticker_counted, latestStored, fOutcome "skipped". Label: "the ticker is skipped, nothing imported [its latest filing is already stored, no --force]". Cites `_should_skip`: `remote_latest <= local_latest`.
- `TheCheckFindsNoNewerStoredFiling` ticker_checked→fetching and `TheRunHasForce` ticker_checked→fetching (sets force). Both use the same label: "the ticker is fetched [a newer filing, none stored, the check fails, or --force]".
- `TheCheckIsRateLimited` (fRateLimit "this ticker") and `AnEarlierTickerHitTheLimit` (fRateLimit "earlier ticker") ticker_checked→ticker_counted. Both set fOutcome "deferred" and fLater "deferred". Same label: "the ticker and every later one are deferred, not failed [the rate limit is hit, by this or an earlier ticker]". Cites `_run_bulk_refresh` `rate_limited`, and `refresh_run` re-raising `ProviderRateLimitError`.
- `TheFetchIsRateLimited` fetching→ticker_counted, with the same flags as `TheCheckIsRateLimited`. Label: "the ticker and every later one are deferred, not failed [the fetch hits the rate limit]".
- `TheFetchFails` fetching→ticker_counted, fOutcome "failed". Label: "the ticker fails and the run goes on [the facts cannot be fetched]".
- `TheFactsArrive` fetching→fact_read. Label: "the import reads the facts one by one".
- `TheIndustryIsMapped` facts_parsed→ticker_counted, companyWritten, financialsWritten, industryDamodaran "set", fOutcome "imported". Label: "the company, its financials and its filings are written in one transaction [its industry label is mapped]".
- `TheIndustryIsUnmapped` facts_parsed→ticker_counted, with the same writes, unmapped, industryDamodaran "empty". Label: "the company is written with no Damodaran industry, with its financials and filings [its industry label is unmapped]". Cites `_company_row` `mapping.resolve` → `None` plus the warning.
- `PricesStart` ticker_counted→price_listing. Adds "fundamentals" to stagesDone and resets the fundamentals and facts flags. Label: "the prices stage starts". Cites `cli.py` `if prices:` after `if fmp:`.

refresh-facts (`sec_edgar.py` `parse_company_facts`, `_collect_period_rows`, `_derive_financial_fields`, `_label_rows`, `_fiscal_quarter_key`, `_rescale_shares_diluted`):
- `TheFactSpansAYear` fact_read→fact_in_period, factKind "duration", rowKind "year". Label: "the fact counts for a year [a duration of 350 to 380 days from a 10-K]".
- `TheFactSpansAQuarter`: the same with rowKind "quarter". Label: "the fact counts for a quarter [a duration of 80 to 100 days from a 10-Q, in a column stored quarterly]".
- `TheInstantJoinsAYearRow` / `TheInstantJoinsAQuarterRow` fact_read→fact_in_period, factKind "instant". Same label: "the fact joins the row ending on its date [an instant on a year or quarter end]".
- `TheFactFitsNoPeriod` fact_read→fact_dropped, factKind "other". Label: "the fact is dropped [any other span, form or date]".
- `TheConceptWinsTheColumn` fact_in_period→fact_chosen. Label: "its concept fills the column [the first concept in the list with a fact for that end]".
- `AnEarlierConceptFilledIt` fact_in_period→fact_dropped. Label: "the fact is not used [an earlier concept already fills that end]".
- `TheAggregatesAreDerived` fact_chosen→fact_derived. Label: "earnings before interest, taxes, depreciation and amortization (EBITDA), free cash flow and working capital are derived [when not reported and their inputs exist]".
- `TheYearIsLabelled` fact_derived→row_labelled (guard rowKind "year"), fiscalYear "set". Label: "the row takes the calendar year of its end [a year row]".
- `TheQuarterIsCounted` (guard "quarter"), fiscalYear "set". Label: "the quarter is numbered from the nearest year end [a year end within 380 days]".
- `TheQuarterTakesItsFilingLabel` (guard "quarter"), fiscalYear "set". Label: "the quarter takes the label of the filing that first reported it [no year end near it]".
- `TheQuarterHasNoLabel` fact_derived→fact_dropped (guard "quarter"). Label: "the row is dropped [a quarter with no year end and no filing label]".
- `TwoRowsShareALabel` fact_derived→fact_dropped (any rowKind). Label: "the row is dropped [a later period end has the same label]".
- `TheShareCountIsRescaled` row_labelled→fact_in_row (guard "year"), otherCounts "three or more", sharesRescaled, factInRow. Label: "the diluted share count is multiplied by a million or a thousand [a whole scale off the median of three or more other counts]".
- `TheShareCountFitsItsPeers` (guard "year"), otherCounts "three or more", factInRow. Label: "the share count is kept [in scale with three or more other counts]".
- `TooFewOtherShareCounts` (guard "year"), otherCounts "under three", factInRow. Label: "the share count is kept [fewer than three other counts]".
- `TheQuarterRowIsReady` (guard "quarter"), factInRow. Label: "the quarter row is kept as is [a quarter row]".
- `TheFactJoinsItsRow` fact_in_row→facts_parsed. Resets factKind, otherCounts and sharesRescaled, and keeps rowKind, fiscalYear and factInRow. Label: "the import goes on with the row".
- `TheImportGoesOnWithoutIt` fact_dropped→facts_parsed. Resets all facts flags. Label: "the import goes on without the fact".

refresh-prices (`universe.py` `refresh_prices`, `_last_weekday_before`, `_stale_first`, `_refresh_one_price`; `edgar_base.py` `_stamp_market_cap`, `_FRESH_DAYS = 7`):
- `TheTickerAlreadyHasAPrice` price_listing→price_counted, pOutcome "left out". Label: "the ticker is left out, no request [--only-missing and it already has a price]".
- `TheTickerIsListed` price_listing→price_listed. Label: "the ticker is listed [no --only-missing, or no price yet]".
- `TheNewestBarIsCurrent` price_listed→price_counted, barCurrent, pOutcome "skipped". Label: "the ticker is skipped, no request [its newest bar is on or after the last weekday before today]".
- `TheTickerIsBehind` price_listed→price_queued. Label: "the ticker is queued [no bar yet, or an older newest bar]".
- `ThePriceFetchIsRateLimited` (requested, pRateLimit "this ticker") and `AnEarlierPriceFetchHitTheLimit` (pRateLimit "earlier ticker") price_queued→price_counted. Both set pOutcome "deferred" and pLater "deferred". Same label: "the ticker and every later one are deferred, not failed [the rate limit is hit, by this or an earlier ticker]".
- `ThePriceFetchFails` price_queued→price_counted, requested, pOutcome "failed". Label: "the ticker fails and the run goes on [the bars cannot be fetched]".
- `TheBarsArrive` price_queued→bars_fetched, requested. Label: "only the bars after the newest stored one are fetched".
- `TheNewestBarGetsAMarketCap` bars_fetched→price_counted, newestAge "7 days or less", shares "found", marketCap, pOutcome "imported". Label: "the bars are stored, the newest with market cap = close × shares outstanding [newest bar at most 7 days old, shares found]".
- `TheNewestBarIsTooOld`: newestAge "older", "imported". Label: "the bars are stored without market cap [the newest bar is more than 7 days old]".
- `TheSharesLookupFails`: newestAge "7 days or less", shares "failed", "imported". Label: "the bars are stored without market cap [the shares lookup fails]".
- `TheSharesLookupIsRateLimited`: newestAge "7 days or less", pRateLimit "this ticker", pOutcome "deferred", pLater "deferred". Label: "the ticker and every later one are deferred, not failed [the shares lookup hits the rate limit]". Cites `_stamp_market_cap` `except ProviderRateLimitError: raise`.
- `FxStarts` price_counted→fx_listing. Adds "prices" to stagesDone and resets the price flags. Label: "the foreign exchange stage starts".

refresh-fx (`universe.py` `refresh_fx`, `distinct_non_usd_currencies`; `fx.py` `import_fx_rates`; `edgar_base.py` `fx_rates`):
- `OnlyUsdIsListed` fx_listing→fx_done, fxCurrencies "only USD", fxStatus "success". Label: "the run succeeds with no provider call [every listing currency is USD]". Cites `refresh_fx`: an empty list gives `total=0`, and `_resolve_status(0.0)` is "success".
- `AnotherCurrencyIsListed` fx_listing→fx_requested, fxCurrencies "others", fxCalled. Label: "each other currency is requested in turn [a listing currency other than USD]".
- `TheProviderHasNoRates` fx_requested→fx_done, fxStatus "success". Label: "nothing is stored and the run succeeds [the SEC EDGAR providers supply no rates]".
- `Done`. Label: "the run ends".

**Rules** (name: reader's sentence, then the formula):
- (a) `CoreFileFailureWritesNothing`: "A failed wacc.xls or ctryprem.xls writes nothing to the Damodaran tables." `dCoreFailed => (dIndustry = "kept" /\ dCountry = "kept" /\ dStatus = "error")`
- (b) `EmptySideKeepsItsRows`: "An empty industry or country side never deletes the stored rows of that side." `(dEmpty = "industry" => dIndustry = "kept") /\ (dEmpty = "country" => dCountry = "kept")`
- (c) `StoredFilingIsSkipped`: "A ticker whose latest filing is already stored is skipped and writes no financials, unless the run has --force." `latestStored => (~force /\ fOutcome = "skipped" /\ ~financialsWritten)`
- (d) `UnmappedIndustryStillImported`: "An unmapped industry label leaves the Damodaran industry empty, but the company is still imported." `unmapped => (industryDamodaran = "empty" /\ companyWritten /\ fOutcome = "imported")`
- (e) `InvalidMappingImportsNothing`: "A mapping that fails validation imports no ticker, and prices and foreign exchange never run." `mappingInvalid => (fOutcome = "none" /\ ~companyWritten /\ ~financialsWritten /\ phase \notin PricePhases \cup FxPhases)`
- (f) `RateLimitDefersTheRest`: "A rate-limited ticker is deferred, never counted as failed, and every later ticker is deferred too." `fRateLimit # "none" => (fOutcome \in {"none","deferred"} /\ fLater = "deferred")`
- (g) `FactOutsideAPeriodIsDropped`: "A fact that is neither a year or quarter duration nor an instant on a period end is dropped." `factKind = "other" => (~factInRow /\ phase \notin {"fact_in_period","fact_chosen","fact_derived","row_labelled","fact_in_row"})`
- (h) `AnnualRowHasAFiscalYear`: "A year row written to the annual financials always has a fiscal year." `(rowKind = "year" /\ factInRow /\ financialsWritten) => fiscalYear = "set"`
- (i) `RescaleNeedsThreeOtherCounts`: "A share count is rescaled only when at least three other counts are positive." `sharesRescaled => otherCounts = "three or more"`
- (j) `CurrentTickerIsNotRequested`: "A ticker whose newest bar is on or after the last weekday is not requested." `barCurrent => ~requested`
- (k) `MarketCapNeedsAFreshBarAndShares`: "Under a SEC EDGAR provider, a bar gets a market cap only when it is at most 7 days old and the shares lookup succeeded." `marketCap => (newestAge = "7 days or less" /\ shares = "found")`
- (l) `UsdOnlyFxCallsNoProvider`: "A foreign exchange run with no listing currency other than USD calls no provider and succeeds." `fxCurrencies = "only USD" => (~fxCalled /\ fxStatus = "success")`
- (m) `StagesRunInOrder`: "In a --all run, prices run only after fundamentals, and foreign exchange only after prices." `(phase \in PricePhases => "fundamentals" \in stagesDone) /\ (phase \in FxPhases => "prices" \in stagesDone)`
- extra `PriceRateLimitDefersTheRest`: "A ticker whose prices hit the rate limit is deferred, never counted as failed, and every later ticker is deferred too." `pRateLimit # "none" => (pOutcome \in {"none","deferred"} /\ pLater = "deferred")`

- [ ] **Step 1: Evals fail.** Run `uv run pytest -q tests/unit/test_pipeline_models.py -k refresh`. Expected: FAIL. The stage-3 evals are explicit `test_refresh_*` tests that read `refresh.*` (groups, rule names, title). They fail with FileNotFoundError, not "no tests collected": `_STEMS` is discovered from `*.tla`, so the parametrized tests alone would collect nothing for `refresh`.
- [ ] **Step 2: Write `refresh.tla`** in the shape of `site.tla`, from the tables above: the variables, `vars`, `EndPhases`, `PricePhases` and `FxPhases`, an `Init`, one action per row in table order, then `Done`, `Next` (every action, `Done` last), `Spec` and the 14 rules. Each rule is preceded by its `(* Cites: ... *)` line and then its `\*` sentence. A definition is never preceded by a blank `\*` line.
- [ ] **Step 3: Write `refresh.cfg`**: `SPECIFICATION Spec` plus 14 `INVARIANT` lines in rule order. **Write `refresh.view.js`** in the shape of `site.view.js` with the tables above.
- [ ] **Step 4: Update the models README line.**
- [ ] **Step 5: Run** `uv run pytest -q tests/unit/test_pipeline_models.py`, expecting PASS, then `uv run pytest -q`, expecting PASS.
- [ ] **Step 6: Commit** `docs(#165): refresh model, cfg and view`.

### Task 2: TLC in CI until green (controller session: needs push and `gh`)

**Files:** `docs/pipeline/models/refresh.*`, and on a real code bug `docs/pipeline/models/README.md` (the Known broken rules table).

- [ ] **Step 1:** Push the branch. Get the run with `id=$(gh run list --branch agent/165-refresh-model --workflow pipeline-diagram --limit 1 --json databaseId --jq '.[0].databaseId')`, then `gh run watch "$id" --exit-status`.
- [ ] **Step 2:** Run `gh run download "$id" -n pipeline-models -D /tmp/models-<n>` and read `refresh/report.md`, `refresh/chart.mmd` and `refresh/tlc.out`.
- [ ] **Step 3:** Fix parse errors, deadlocks and labels in the model or the view. For a rule that breaks, replay the path as a pytest against the code. If the model is wrong, fix the model. If the code really breaks the rule, open a `bug` issue, add `\* broken: #n`, remove the rule from the `.cfg` and add a README table row.
- [ ] **Step 4:** Check the state count in `report.md` and `tlc.out`, and that `refresh/chart.mmd` exists. `check.sh` checks neither: above 500 states, the launcher writes no chart and still passes.
- [ ] **Step 5:** Repeat until the head commit's run is green in both jobs, and `report.md` has `## Rules that hold` with at least 10 names and no `breaks`, `Rules not checked` or `TLC stopped`, and `chart.mmd` exists.
- [ ] **Step 6:** Commit each fix as `fix(#165): <what TLC showed>`.

## Grilling

- Rounds: 1 (the revision changed no step or seam, so there was no second round). Griller model: fable.
- Questions: 18. Sources: CODE 14, ISSUE 3, DOC 1, NO SOURCE 4 (A1, A3, A4, A6 → technical assumptions).
- Answers in brief:
  - Q1: CODE `src/bot/config.py:25`, default `data_provider`. `cli.py:67-91` `_make_provider` builds the provider for `_refresh_fmp_universe`, whose name is historical.
  - Q2: CODE `damodaran.py:870-887`, where `except Exception` sets `status_override = "error"`, and `cli.py:200-218`, which returns 1 and does not raise.
  - Q3: A2.
  - Q4: A3.
  - Q5: CODE `cli.py:184-196`: `_open_db`, then the sources in order, with no earlier mapping load.
  - Q6: CODE `tests/unit/test_pipeline_models.py` `_STEMS = sorted(p.stem for p in _MODELS.glob("*.tla"))`. Step 1 fixed.
  - Q7: A4.
  - Q8: Task 2 Step 4 added. ISSUE: "the chart budget is 500 states".
  - Q9: A1.
  - Q10: CODE `universe.py` `_should_skip`: `except Exception: ... return False`, so the ticker is imported.
  - Q11: CODE `fx.py:147-158` with `upsert_fx_rates` `if not rates`: an empty result is a success with 0 rows, so the currency is counted "imported" and the status is success. `distinct_non_usd_currencies` excludes `currency IS NULL`, so a NULL currency is not listed: `OnlyUsdIsListed` when it is the only one.
  - Q12: CODE `damodaran.py` `_import_files_into_run`: `if empty_sides: reasons.append(...)`, then `if reasons: status_override = "partial"`, whether or not the run is degraded.
  - Q13: CODE `universe.py` `_run_bulk_refresh`: `for index, item in enumerate(items, start=1)` with `rate_limited`, a sequential loop.
  - Q14: CODE `sec_edgar.py:346` `_rescale_shares_diluted(ticker, annual_rows)`, annual only. `shares_diluted` is `WeightedAverageNumberOfDilutedSharesOutstanding`, a duration fact.
  - Q15: ISSUE: "The sandbox has no Java and refuses to run downloaded binaries … CI is the gate."
  - Q16: A5, ISSUE "not committed if it only proves the model wrong".
  - Q17: DOC `docs/pipeline/models/README.md:20`, verbatim. Nothing else lists the models.
  - Q18: A6.
- Spec ambiguities: none. Out of scope (follow-up issues): none.
- Status: ok.
