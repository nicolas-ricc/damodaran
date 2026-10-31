---- MODULE refresh ----
(* One ticker through one `bot refresh --all` run: the Damodaran datasets, the SEC EDGAR
   fundamentals and their facts, the end-of-day prices, then the foreign exchange rates. *)

VARIABLES phase, stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry,
          dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit,
          fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped,
          factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow,
          barCurrent, requested, newestAge, shares, marketCap, pRateLimit,
          pLater, pOutcome, fxCurrencies, fxCalled, fxStatus

vars == << phase, stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* The command ends here: the mapping is refused, or the last stage is done. *)
EndPhases == {"mapping_refused", "fx_done"}

(* The phases of the prices stage. *)
PricePhases == {"price_listing", "price_listed", "price_queued", "bars_fetched", "price_counted"}

(* The phases of the foreign exchange stage. *)
FxPhases == {"fx_listing", "fx_requested", "fx_done"}

Init ==
  /\ phase = "started"
  /\ stagesDone = {}
  /\ dDegraded = FALSE
  /\ dCoreFailed = FALSE
  /\ dIndustry = "kept"
  /\ dCountry = "kept"
  /\ dEmpty = "none"
  /\ dStatus = "none"
  /\ mappingInvalid = FALSE
  /\ force = FALSE
  /\ latestStored = FALSE
  /\ fRateLimit = "none"
  /\ fLater = "waiting"
  /\ fOutcome = "none"
  /\ companyWritten = FALSE
  /\ financialsWritten = FALSE
  /\ industryDamodaran = "none"
  /\ unmapped = FALSE
  /\ factKind = "none"
  /\ rowKind = "none"
  /\ fiscalYear = "none"
  /\ otherCounts = "unknown"
  /\ sharesRescaled = FALSE
  /\ factInRow = FALSE
  /\ barCurrent = FALSE
  /\ requested = FALSE
  /\ newestAge = "unknown"
  /\ shares = "unknown"
  /\ marketCap = FALSE
  /\ pRateLimit = "none"
  /\ pLater = "waiting"
  /\ pOutcome = "none"
  /\ fxCurrencies = "unknown"
  /\ fxCalled = FALSE
  /\ fxStatus = "none"

(* src/bot/ingest/damodaran.py: import_damodaran: every download_dataset call (wacc.xls, ctryprem.xls and the six others) returns a file *)
AllEightFilesDownload ==
  /\ phase = "started"
  /\ phase' = "downloaded"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: import_damodaran: `except` around a download of one of the six others, `unavailable.append(dataset.key)`; the run goes on degraded *)
AnotherFileFailsToDownload ==
  /\ phase = "started"
  /\ phase' = "downloaded"
  /\ dDegraded' = TRUE
  /\ UNCHANGED << stagesDone, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: import_damodaran: the outer `except` sets `run.status_override = "error"` and skips _import_files_into_run, so nothing is written *)
ACoreFileFailsToDownload ==
  /\ phase = "started"
  /\ phase' = "damodaran_failed"
  /\ dCoreFailed' = TRUE
  /\ dStatus' = "error"
  /\ UNCHANGED << stagesDone, dDegraded, dIndustry, dCountry, dEmpty, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: _import_files_into_run: parse_industry_xls reads wacc.xls and each other file *)
TheIndustryFilesAreRead ==
  /\ phase = "downloaded"
  /\ phase' = "industry_read"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: _import_files_into_run: a parse of one of the six others fails, `degraded.append(dataset.key)` *)
AnotherFileFailsToParse ==
  /\ phase = "downloaded"
  /\ phase' = "industry_read"
  /\ dDegraded' = TRUE
  /\ UNCHANGED << stagesDone, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: _import_files_into_run: the first parse_industry_xls (wacc.xls) raises before `transaction`; import_damodaran sets `status_override = "error"` *)
TheWaccFileFailsToParse ==
  /\ phase = "downloaded"
  /\ phase' = "damodaran_failed"
  /\ dCoreFailed' = TRUE
  /\ dStatus' = "error"
  /\ UNCHANGED << stagesDone, dDegraded, dIndustry, dCountry, dEmpty, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: merge_industry_datasets joins on the industry name, the earlier dataset wins a shared column *)
TheIndustryFilesAreMerged ==
  /\ phase = "industry_read"
  /\ phase' = "merged"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: parse_country_xls reads ctryprem.xls *)
TheCountrySheetIsRead ==
  /\ phase = "merged"
  /\ phase' = "country_read"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: parse_country_xls raises before `transaction`; the `except` around _import_files_into_run in import_damodaran sets `status_override = "error"` *)
TheCountryFileFailsToParse ==
  /\ phase = "merged"
  /\ phase' = "damodaran_failed"
  /\ dCoreFailed' = TRUE
  /\ dStatus' = "error"
  /\ UNCHANGED << stagesDone, dDegraded, dIndustry, dCountry, dEmpty, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: derive_industry_columns (debt-to-equity, unlevered beta), parse_country_tax_rates *)
TheColumnsAreDerived ==
  /\ phase = "country_read"
  /\ phase' = "derived"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: _import_files_into_run: upsert_industry_rows and upsert_country_rows replace the year inside one `transaction`; a degraded run is "partial" *)
BothSidesAreWritten ==
  /\ phase = "derived"
  /\ phase' = "damodaran_written"
  /\ dIndustry' = "replaced"
  /\ dCountry' = "replaced"
  /\ dStatus' = IF dDegraded THEN "partial" ELSE "success"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dEmpty, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: upsert_industry_rows: `if not rows: return 0` before its DELETE; _import_files_into_run: `if empty_sides:` then `status_override = "partial"` *)
TheIndustrySideIsEmpty ==
  /\ phase = "derived"
  /\ phase' = "damodaran_written"
  /\ dCountry' = "replaced"
  /\ dEmpty' = "industry"
  /\ dStatus' = "partial"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/damodaran.py: upsert_country_rows: `if not rows: return 0` before its DELETE; _import_files_into_run: `if empty_sides:` then `status_override = "partial"` *)
TheCountrySideIsEmpty ==
  /\ phase = "derived"
  /\ phase' = "damodaran_written"
  /\ dIndustry' = "replaced"
  /\ dEmpty' = "country"
  /\ dStatus' = "partial"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dCountry, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/cli.py: refresh, `exit_code = max(...)` of the Damodaran result, then `if fmp:`; the Damodaran flags are reset here *)
FundamentalsStartAfterTheWrite ==
  /\ phase = "damodaran_written"
  /\ phase' = "mapping_loading"
  /\ stagesDone' = stagesDone \cup {"damodaran"}
  /\ dDegraded' = FALSE
  /\ dCoreFailed' = FALSE
  /\ dIndustry' = "kept"
  /\ dCountry' = "kept"
  /\ dEmpty' = "none"
  /\ dStatus' = "none"
  /\ UNCHANGED << mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/cli.py: refresh, `exit_code = max(...)` keeps the error code and goes on to `if fmp:`; a Damodaran failure does not stop the command *)
FundamentalsStartAfterTheFailure ==
  /\ phase = "damodaran_failed"
  /\ phase' = "mapping_loading"
  /\ stagesDone' = stagesDone \cup {"damodaran"}
  /\ dDegraded' = FALSE
  /\ dCoreFailed' = FALSE
  /\ dIndustry' = "kept"
  /\ dCountry' = "kept"
  /\ dEmpty' = "none"
  /\ dStatus' = "none"
  /\ UNCHANGED << mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/industry_mapping.py: load_industry_mapping raises ValueError (target outside the Damodaran industry list, duplicate label); nothing in refresh catches it *)
TheMappingIsInvalid ==
  /\ phase = "mapping_loading"
  /\ phase' = "mapping_refused"
  /\ mappingInvalid' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: refresh_universe loads the mapping once, before _run_bulk_refresh *)
TheMappingLoads ==
  /\ phase = "mapping_loading"
  /\ phase' = "ticker_checked"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _should_skip, `remote_latest <= local_latest` (no --force) *)
TheLatestFilingIsStored ==
  /\ phase = "ticker_checked"
  /\ phase' = "ticker_counted"
  /\ latestStored' = TRUE
  /\ fOutcome' = "skipped"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, fRateLimit, fLater, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _should_skip returns False: a newer filing, no stored filing, or `except Exception` on the check *)
TheCheckFindsNoNewerStoredFiling ==
  /\ phase = "ticker_checked"
  /\ phase' = "fetching"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _refresh_one / _should_skip: with --force the check is not made *)
TheRunHasForce ==
  /\ phase = "ticker_checked"
  /\ phase' = "fetching"
  /\ force' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _should_skip re-raises ProviderRateLimitError; _refresh_one re-raises it (`except ProviderRateLimitError: raise`); _run_bulk_refresh sets `rate_limited` *)
TheCheckIsRateLimited ==
  /\ phase = "ticker_checked"
  /\ phase' = "ticker_counted"
  /\ fRateLimit' = "this ticker"
  /\ fLater' = "deferred"
  /\ fOutcome' = "deferred"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _run_bulk_refresh: `if rate_limited:` defers every later item *)
AnEarlierTickerHitTheLimit ==
  /\ phase = "ticker_checked"
  /\ phase' = "ticker_counted"
  /\ fRateLimit' = "earlier ticker"
  /\ fLater' = "deferred"
  /\ fOutcome' = "deferred"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _refresh_one: `except ProviderRateLimitError` while fetching; _run_bulk_refresh sets `rate_limited` *)
TheFetchIsRateLimited ==
  /\ phase = "fetching"
  /\ phase' = "ticker_counted"
  /\ fRateLimit' = "this ticker"
  /\ fLater' = "deferred"
  /\ fOutcome' = "deferred"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: import_company folds a fetch error into a non-success result, which _refresh_one maps to "failed" (`if result.is_success() ... else`); the loop goes on *)
TheFetchFails ==
  /\ phase = "fetching"
  /\ phase' = "ticker_counted"
  /\ fOutcome' = "failed"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: parse_company_facts walks the company facts one fact at a time *)
TheFactsArrive ==
  /\ phase = "fetching"
  /\ phase' = "fact_read"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: import_company writes the company row (_company_row, mapping.resolve returns a Damodaran industry), the financials and the filings in one transaction *)
TheIndustryIsMapped ==
  /\ phase = "facts_parsed"
  /\ phase' = "ticker_counted"
  /\ fOutcome' = "imported"
  /\ companyWritten' = TRUE
  /\ financialsWritten' = TRUE
  /\ industryDamodaran' = "set"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _company_row, `mapping.resolve` returns None and logs a warning; import_company still writes the rows *)
TheIndustryIsUnmapped ==
  /\ phase = "facts_parsed"
  /\ phase' = "ticker_counted"
  /\ fOutcome' = "imported"
  /\ companyWritten' = TRUE
  /\ financialsWritten' = TRUE
  /\ industryDamodaran' = "empty"
  /\ unmapped' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/cli.py: refresh, `if prices:` after `if fmp:`; the fundamentals and facts flags are reset here *)
PricesStart ==
  /\ phase = "ticker_counted"
  /\ phase' = "price_listing"
  /\ stagesDone' = stagesDone \cup {"fundamentals"}
  /\ mappingInvalid' = FALSE
  /\ force' = FALSE
  /\ latestStored' = FALSE
  /\ fRateLimit' = "none"
  /\ fLater' = "waiting"
  /\ fOutcome' = "none"
  /\ companyWritten' = FALSE
  /\ financialsWritten' = FALSE
  /\ industryDamodaran' = "none"
  /\ unmapped' = FALSE
  /\ factKind' = "none"
  /\ rowKind' = "none"
  /\ fiscalYear' = "none"
  /\ otherCounts' = "unknown"
  /\ sharesRescaled' = FALSE
  /\ factInRow' = FALSE
  /\ UNCHANGED << dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows, a duration of 350 to 380 days from a 10-K *)
TheFactSpansAYear ==
  /\ phase = "fact_read"
  /\ phase' = "fact_in_period"
  /\ factKind' = "duration"
  /\ rowKind' = "year"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows, a duration of 80 to 100 days from a 10-Q in a column stored quarterly *)
TheFactSpansAQuarter ==
  /\ phase = "fact_read"
  /\ phase' = "fact_in_period"
  /\ factKind' = "duration"
  /\ rowKind' = "quarter"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows, an instant fact on the end of a year row *)
TheInstantJoinsAYearRow ==
  /\ phase = "fact_read"
  /\ phase' = "fact_in_period"
  /\ factKind' = "instant"
  /\ rowKind' = "year"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows, an instant fact on the end of a quarter row *)
TheInstantJoinsAQuarterRow ==
  /\ phase = "fact_read"
  /\ phase' = "fact_in_period"
  /\ factKind' = "instant"
  /\ rowKind' = "quarter"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows skips any other span, form or date *)
TheFactFitsNoPeriod ==
  /\ phase = "fact_read"
  /\ phase' = "fact_dropped"
  /\ factKind' = "other"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows, the first concept in the list with a fact for that end fills the column *)
TheConceptWinsTheColumn ==
  /\ phase = "fact_in_period"
  /\ phase' = "fact_chosen"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _collect_period_rows, a concept earlier in the list already filled that end *)
AnEarlierConceptFilledIt ==
  /\ phase = "fact_in_period"
  /\ phase' = "fact_dropped"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _derive_financial_fields derives EBITDA, free cash flow and working capital when not reported and their inputs exist *)
TheAggregatesAreDerived ==
  /\ phase = "fact_chosen"
  /\ phase' = "fact_derived"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _label_rows, a year row takes the calendar year of its end *)
TheYearIsLabelled ==
  /\ phase = "fact_derived"
  /\ rowKind = "year"
  /\ phase' = "row_labelled"
  /\ fiscalYear' = "set"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _label_rows, _fiscal_quarter_key numbers the quarter from a year end within 380 days *)
TheQuarterIsCounted ==
  /\ phase = "fact_derived"
  /\ rowKind = "quarter"
  /\ phase' = "row_labelled"
  /\ fiscalYear' = "set"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _label_rows, a quarter with no year end near it takes the fiscal label of the filing that first reported it *)
TheQuarterTakesItsFilingLabel ==
  /\ phase = "fact_derived"
  /\ rowKind = "quarter"
  /\ phase' = "row_labelled"
  /\ fiscalYear' = "set"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _label_rows drops a quarter with no year end and no filing label *)
TheQuarterHasNoLabel ==
  /\ phase = "fact_derived"
  /\ rowKind = "quarter"
  /\ phase' = "fact_dropped"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _label_rows keeps one row per label: `by_key[key] = end` in sorted order keeps the later end, so a row is dropped when a later period end has the same label *)
TwoRowsShareALabel ==
  /\ phase = "fact_derived"
  /\ phase' = "fact_dropped"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _rescale_shares_diluted(ticker, annual_rows): a count a whole scale off the median of three or more other positive counts is multiplied by a million or a thousand *)
TheShareCountIsRescaled ==
  /\ phase = "row_labelled"
  /\ rowKind = "year"
  /\ phase' = "fact_in_row"
  /\ otherCounts' = "three or more"
  /\ sharesRescaled' = TRUE
  /\ factInRow' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _rescale_shares_diluted: the count is in scale with the median, so it is kept *)
TheShareCountFitsItsPeers ==
  /\ phase = "row_labelled"
  /\ rowKind = "year"
  /\ phase' = "fact_in_row"
  /\ otherCounts' = "three or more"
  /\ factInRow' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, sharesRescaled, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: _rescale_shares_diluted: fewer than three other positive counts, nothing is rescaled *)
TooFewOtherShareCounts ==
  /\ phase = "row_labelled"
  /\ rowKind = "year"
  /\ phase' = "fact_in_row"
  /\ otherCounts' = "under three"
  /\ factInRow' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, sharesRescaled, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: parse_company_facts: _rescale_shares_diluted gets the annual rows only, so a quarter row is kept as is *)
TheQuarterRowIsReady ==
  /\ phase = "row_labelled"
  /\ rowKind = "quarter"
  /\ phase' = "fact_in_row"
  /\ factInRow' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: parse_company_facts returns the row to import_company *)
TheFactJoinsItsRow ==
  /\ phase = "fact_in_row"
  /\ phase' = "facts_parsed"
  /\ factKind' = "none"
  /\ otherCounts' = "unknown"
  /\ sharesRescaled' = FALSE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, rowKind, fiscalYear, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/sec_edgar.py: parse_company_facts returns without the dropped fact *)
TheImportGoesOnWithoutIt ==
  /\ phase = "fact_dropped"
  /\ phase' = "facts_parsed"
  /\ factKind' = "none"
  /\ rowKind' = "none"
  /\ fiscalYear' = "none"
  /\ otherCounts' = "unknown"
  /\ sharesRescaled' = FALSE
  /\ factInRow' = FALSE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: refresh_prices, `if only_missing:` drops tickers that already have any stored price before any request *)
TheTickerAlreadyHasAPrice ==
  /\ phase = "price_listing"
  /\ phase' = "price_counted"
  /\ pOutcome' = "left out"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: refresh_prices lists the ticker (no --only-missing, or no stored price) *)
TheTickerIsListed ==
  /\ phase = "price_listing"
  /\ phase' = "price_listed"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: refresh_prices, newest stored bar `d >= cutoff` with `cutoff = _last_weekday_before(today)`: the ticker is current and skipped without a request *)
TheNewestBarIsCurrent ==
  /\ phase = "price_listed"
  /\ phase' = "price_counted"
  /\ barCurrent' = TRUE
  /\ pOutcome' = "skipped"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, requested, newestAge, shares, marketCap, pRateLimit, pLater, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _stale_first orders the tickers with no bar or an older newest bar, stalest first *)
TheTickerIsBehind ==
  /\ phase = "price_listed"
  /\ phase' = "price_queued"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _refresh_one_price: `except ProviderRateLimitError` re-raises; the bulk loop sets `rate_limited` *)
ThePriceFetchIsRateLimited ==
  /\ phase = "price_queued"
  /\ phase' = "price_counted"
  /\ requested' = TRUE
  /\ pRateLimit' = "this ticker"
  /\ pLater' = "deferred"
  /\ pOutcome' = "deferred"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, newestAge, shares, marketCap, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _run_bulk_refresh, `if rate_limited:` defers every later ticker without a request *)
AnEarlierPriceFetchHitTheLimit ==
  /\ phase = "price_queued"
  /\ phase' = "price_counted"
  /\ pRateLimit' = "earlier ticker"
  /\ pLater' = "deferred"
  /\ pOutcome' = "deferred"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: the price refresh_run folds a fetch error into a non-success result, which _refresh_one_price maps to "failed"; the loop goes on *)
ThePriceFetchFails ==
  /\ phase = "price_queued"
  /\ phase' = "price_counted"
  /\ requested' = TRUE
  /\ pOutcome' = "failed"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, newestAge, shares, marketCap, pRateLimit, pLater, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: _refresh_one_price fetches from the day after the newest stored bar *)
TheBarsArrive ==
  /\ phase = "price_queued"
  /\ phase' = "bars_fetched"
  /\ requested' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/edgar_base.py: _stamp_market_cap, newest bar at most _FRESH_DAYS = 7 old and the shares lookup succeeds: market cap = close x shares *)
TheNewestBarGetsAMarketCap ==
  /\ phase = "bars_fetched"
  /\ phase' = "price_counted"
  /\ newestAge' = "7 days or less"
  /\ shares' = "found"
  /\ marketCap' = TRUE
  /\ pOutcome' = "imported"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, pRateLimit, pLater, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/edgar_base.py: _stamp_market_cap, newest bar more than _FRESH_DAYS = 7 old: no market cap *)
TheNewestBarIsTooOld ==
  /\ phase = "bars_fetched"
  /\ phase' = "price_counted"
  /\ newestAge' = "older"
  /\ pOutcome' = "imported"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, shares, marketCap, pRateLimit, pLater, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/edgar_base.py: _stamp_market_cap, the shares lookup fails with another error: bars are kept without market cap *)
TheSharesLookupFails ==
  /\ phase = "bars_fetched"
  /\ phase' = "price_counted"
  /\ newestAge' = "7 days or less"
  /\ shares' = "failed"
  /\ pOutcome' = "imported"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, marketCap, pRateLimit, pLater, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/edgar_base.py: _stamp_market_cap, `except ProviderRateLimitError: raise` *)
TheSharesLookupIsRateLimited ==
  /\ phase = "bars_fetched"
  /\ phase' = "price_counted"
  /\ newestAge' = "7 days or less"
  /\ pRateLimit' = "this ticker"
  /\ pLater' = "deferred"
  /\ pOutcome' = "deferred"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, shares, marketCap, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/cli.py: refresh, `if fx:` after `if prices:`; the price flags are reset here *)
FxStarts ==
  /\ phase = "price_counted"
  /\ phase' = "fx_listing"
  /\ stagesDone' = stagesDone \cup {"prices"}
  /\ barCurrent' = FALSE
  /\ requested' = FALSE
  /\ newestAge' = "unknown"
  /\ shares' = "unknown"
  /\ marketCap' = FALSE
  /\ pRateLimit' = "none"
  /\ pLater' = "waiting"
  /\ pOutcome' = "none"
  /\ UNCHANGED << dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, fxCurrencies, fxCalled, fxStatus >>

(* src/bot/ingest/universe.py: refresh_fx: distinct_non_usd_currencies is empty, total=0 and _resolve_status(0.0) is "success"; no provider call *)
OnlyUsdIsListed ==
  /\ phase = "fx_listing"
  /\ phase' = "fx_done"
  /\ fxCurrencies' = "only USD"
  /\ fxStatus' = "success"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCalled >>

(* src/bot/ingest/universe.py: refresh_fx, distinct_non_usd_currencies lists a currency other than USD; _refresh_one_currency calls fx_rates *)
AnotherCurrencyIsListed ==
  /\ phase = "fx_listing"
  /\ phase' = "fx_requested"
  /\ fxCurrencies' = "others"
  /\ fxCalled' = TRUE
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxStatus >>

(* src/bot/ingest/edgar_base.py: fx_rates returns [] for any currency; src/bot/utils/fx.py upsert_fx_rates: `if not rates` stores nothing and import_fx_rates counts a success *)
TheProviderHasNoRates ==
  /\ phase = "fx_requested"
  /\ phase' = "fx_done"
  /\ fxStatus' = "success"
  /\ UNCHANGED << stagesDone, dDegraded, dCoreFailed, dIndustry, dCountry, dEmpty, dStatus, mappingInvalid, force, latestStored, fRateLimit, fLater, fOutcome, companyWritten, financialsWritten, industryDamodaran, unmapped, factKind, rowKind, fiscalYear, otherCounts, sharesRescaled, factInRow, barCurrent, requested, newestAge, shares, marketCap, pRateLimit, pLater, pOutcome, fxCurrencies, fxCalled >>

Done ==
  /\ phase \in EndPhases
  /\ UNCHANGED vars

Next ==
  AllEightFilesDownload
  \/ AnotherFileFailsToDownload
  \/ ACoreFileFailsToDownload
  \/ TheIndustryFilesAreRead
  \/ AnotherFileFailsToParse
  \/ TheWaccFileFailsToParse
  \/ TheIndustryFilesAreMerged
  \/ TheCountrySheetIsRead
  \/ TheCountryFileFailsToParse
  \/ TheColumnsAreDerived
  \/ BothSidesAreWritten
  \/ TheIndustrySideIsEmpty
  \/ TheCountrySideIsEmpty
  \/ FundamentalsStartAfterTheWrite
  \/ FundamentalsStartAfterTheFailure
  \/ TheMappingIsInvalid
  \/ TheMappingLoads
  \/ TheLatestFilingIsStored
  \/ TheCheckFindsNoNewerStoredFiling
  \/ TheRunHasForce
  \/ TheCheckIsRateLimited
  \/ AnEarlierTickerHitTheLimit
  \/ TheFetchIsRateLimited
  \/ TheFetchFails
  \/ TheFactsArrive
  \/ TheIndustryIsMapped
  \/ TheIndustryIsUnmapped
  \/ PricesStart
  \/ TheFactSpansAYear
  \/ TheFactSpansAQuarter
  \/ TheInstantJoinsAYearRow
  \/ TheInstantJoinsAQuarterRow
  \/ TheFactFitsNoPeriod
  \/ TheConceptWinsTheColumn
  \/ AnEarlierConceptFilledIt
  \/ TheAggregatesAreDerived
  \/ TheYearIsLabelled
  \/ TheQuarterIsCounted
  \/ TheQuarterTakesItsFilingLabel
  \/ TheQuarterHasNoLabel
  \/ TwoRowsShareALabel
  \/ TheShareCountIsRescaled
  \/ TheShareCountFitsItsPeers
  \/ TooFewOtherShareCounts
  \/ TheQuarterRowIsReady
  \/ TheFactJoinsItsRow
  \/ TheImportGoesOnWithoutIt
  \/ TheTickerAlreadyHasAPrice
  \/ TheTickerIsListed
  \/ TheNewestBarIsCurrent
  \/ TheTickerIsBehind
  \/ ThePriceFetchIsRateLimited
  \/ AnEarlierPriceFetchHitTheLimit
  \/ ThePriceFetchFails
  \/ TheBarsArrive
  \/ TheNewestBarGetsAMarketCap
  \/ TheNewestBarIsTooOld
  \/ TheSharesLookupFails
  \/ TheSharesLookupIsRateLimited
  \/ FxStarts
  \/ OnlyUsdIsListed
  \/ AnotherCurrencyIsListed
  \/ TheProviderHasNoRates
  \/ Done

Spec == Init /\ [][Next]_vars

(* Cites: damodaran.py: a core download or parse failure raises before `transaction`; import_damodaran sets status_override = "error". *)
\* A failed wacc.xls or ctryprem.xls writes nothing to the Damodaran tables.
CoreFileFailureWritesNothing ==
  dCoreFailed => (dIndustry = "kept" /\ dCountry = "kept" /\ dStatus = "error")

(* Cites: damodaran.py: upsert_industry_rows and upsert_country_rows `if not rows: return 0` before their DELETE. *)
\* An empty industry or country side never deletes the stored rows of that side.
EmptySideKeepsItsRows ==
  (dEmpty = "industry" => dIndustry = "kept") /\ (dEmpty = "country" => dCountry = "kept")

(* Cites: universe.py: _should_skip `remote_latest <= local_latest`, bypassed only by --force. *)
\* A ticker whose latest filing is already stored is skipped and writes no financials, unless the run has --force.
StoredFilingIsSkipped ==
  latestStored => (~force /\ fOutcome = "skipped" /\ ~financialsWritten)

(* Cites: universe.py: _company_row `mapping.resolve` returns None, a warning is logged, import_company still writes. *)
\* An unmapped industry label leaves the Damodaran industry empty, but the company is still imported.
UnmappedIndustryStillImported ==
  unmapped => (industryDamodaran = "empty" /\ companyWritten /\ fOutcome = "imported")

(* Cites: industry_mapping.py: load_industry_mapping raises ValueError in refresh_universe; cli.py refresh catches nothing, so `if prices:` and `if fx:` never run. *)
\* A mapping that fails validation imports no ticker, and prices and foreign exchange never run.
InvalidMappingImportsNothing ==
  mappingInvalid => (fOutcome = "none" /\ ~companyWritten /\ ~financialsWritten /\ phase \notin (PricePhases \cup FxPhases))

(* Cites: universe.py: _run_bulk_refresh `rate_limited`, refresh_run re-raises ProviderRateLimitError. *)
\* A rate-limited ticker is deferred, never counted as failed, and every later ticker is deferred too.
RateLimitDefersTheRest ==
  fRateLimit # "none" => (fOutcome \in {"none", "deferred"} /\ fLater = "deferred")

(* Cites: sec_edgar.py: _collect_period_rows keeps only year and quarter durations and instants on a period end. *)
\* A fact that is neither a year or quarter duration nor an instant on a period end is dropped.
FactOutsideAPeriodIsDropped ==
  factKind = "other" => (~factInRow /\ phase \notin {"fact_in_period", "fact_chosen", "fact_derived", "row_labelled", "fact_in_row"})

(* Cites: sec_edgar.py: _label_rows gives every year row the calendar year of its end. *)
\* A year row written to the annual financials always has a fiscal year.
AnnualRowHasAFiscalYear ==
  (rowKind = "year" /\ factInRow /\ financialsWritten) => fiscalYear = "set"

(* Cites: sec_edgar.py: _rescale_shares_diluted compares a count with the median of the other positive counts. *)
\* A share count is rescaled only when at least three other counts are positive.
RescaleNeedsThreeOtherCounts ==
  sharesRescaled => otherCounts = "three or more"

(* Cites: universe.py: refresh_prices keeps out of the request list a ticker whose newest bar `d >= cutoff`, cutoff = _last_weekday_before(today). *)
\* A ticker whose newest bar is on or after the last weekday is not requested.
CurrentTickerIsNotRequested ==
  barCurrent => ~requested

(* Cites: edgar_base.py: _stamp_market_cap, `(date.today() - newest.date).days <= _FRESH_DAYS` and a successful shares lookup. *)
\* Under a SEC EDGAR provider, a bar gets a market cap only when it is at most 7 days old and the shares lookup succeeded.
MarketCapNeedsAFreshBarAndShares ==
  marketCap => (newestAge = "7 days or less" /\ shares = "found")

(* Cites: universe.py: refresh_fx, an empty distinct_non_usd_currencies list gives total=0, _resolve_status(0.0) is "success". *)
\* A foreign exchange run with no listing currency other than USD calls no provider and succeeds.
UsdOnlyFxCallsNoProvider ==
  fxCurrencies = "only USD" => (~fxCalled /\ fxStatus = "success")

(* Cites: cli.py: refresh runs `if fmp:`, then `if prices:`, then `if fx:`. *)
\* In a --all run, prices run only after fundamentals, and foreign exchange only after prices.
StagesRunInOrder ==
  (phase \in PricePhases => "fundamentals" \in stagesDone) /\ (phase \in FxPhases => "prices" \in stagesDone)

(* Cites: universe.py: refresh_prices, _refresh_one_price re-raises ProviderRateLimitError; edgar_base.py _stamp_market_cap re-raises it. *)
\* A ticker whose prices hit the rate limit is deferred, never counted as failed, and every later ticker is deferred too.
PriceRateLimitDefersTheRest ==
  pRateLimit # "none" => (pOutcome \in {"none", "deferred"} /\ pLater = "deferred")

====
