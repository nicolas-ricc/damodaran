---- MODULE portfolio ----
(* One holding, from the bot portfolio command through the notifier check, the Trader Workstation
   (TWS) snapshot, the corporate actions import, the trades, today's mark, the twelve events and
   alerts.md, to the exit code, in one run of `bot portfolio`. The model follows one ticker; the
   other holdings of the account repeat the same steps. *)
VARIABLES phase, channel, stored, flexFailed, held, valuation,
          gates, prevMark, above, prev, filing,
          event, anyFired, alerts

vars == << phase, channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, event, anyFired, alerts >>

EndPhases == {"channel_misconfigured", "tws_unreachable", "tws_lost", "not_sent", "sent", "send_failed"}

(* Some steps reset what no later step reads, to keep the model under the chart's 500 states.
   Leaving flags_checked resets valuation to "unread". Leaving recal_checked resets gates to "unread".
   Leaving concentration_checked resets above to FALSE and prevMark to "unread". Leaving
   currency_checked resets prev to "unread". Leaving filings_checked resets filing to "unread".
   Leaving alerts_written resets anyFired to FALSE. *)
(* stored holds what the run wrote that this holding sees: events_log only when this holding fired an
   event (persist_events writes nothing for no events), alerts_md always (it lists every holding's events). *)
Init ==
  /\ phase = "started"
  /\ channel = "unchecked"
  /\ stored = {}
  /\ flexFailed = FALSE
  /\ held = FALSE
  /\ valuation = "unread"
  /\ gates = "unread"
  /\ prevMark = "unread"
  /\ above = FALSE
  /\ prev = "unread"
  /\ filing = "unread"
  /\ event = "none"
  /\ anyFired = FALSE
  /\ alerts = "unwritten"

(* src/bot/cli.py: portfolio, `build_notifier` raises `NotifierConfigError` and the command exits with `typer.Exit(code=2)`, before `_open_db` and `run_portfolio` *)
TheChannelIsMisconfigured ==
  /\ phase = "started"
  /\ phase' = "channel_misconfigured"
  /\ channel' = "misconfigured"
  /\ event' = "none"
  /\ UNCHANGED << stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/notifier/__init__.py: build_notifier returns a notifier or `None` *)
TheChannelIsValid ==
  /\ phase = "started"
  /\ phase' = "channel_checked"
  /\ channel' = "valid"
  /\ event' = "none"
  /\ UNCHANGED << stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/sync.py: sync_portfolio, `client.connect()` raises before `_replace_account_day`; src/bot/cli.py catches `ConnectionError` and `TimeoutError` and exits with code 1 *)
TwsIsUnreachable ==
  /\ phase = "channel_checked"
  /\ phase' = "tws_unreachable"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/sync.py: sync_portfolio, `client.connect()`, `client.accounts()` *)
TwsAnswers ==
  /\ phase = "channel_checked"
  /\ phase' = "tws_reached"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/sync.py: sync_portfolio, `value_positions`, `_replace_account_day`, `_insert_positions`, `_insert_cash` *)
ItIsStoredWithAMarketValue ==
  /\ phase = "tws_reached"
  /\ phase' = "snapshot_stored"
  /\ held' = TRUE
  /\ stored' = stored \cup {"portfolio_snapshots", "cash_balances"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/sync.py: value_positions gives `market_value` `None` for no close, a close of 0 or less, or a missing rate *)
ItIsStoredUnpriced ==
  /\ phase = "tws_reached"
  /\ phase' = "snapshot_stored"
  /\ held' = TRUE
  /\ stored' = stored \cup {"portfolio_snapshots", "cash_balances"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/sync.py: sync_portfolio writes only the positions the accounts return *)
TheSnapshotIsStoredWithoutIt ==
  /\ phase = "tws_reached"
  /\ phase' = "snapshot_stored"
  /\ held' = FALSE
  /\ stored' = stored \cup {"portfolio_snapshots", "cash_balances"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/ingest/ibkr_flex.py: import_corporate_actions returns `None` without a token or query id *)
FlexIsNotConfigured ==
  /\ phase = "snapshot_stored"
  /\ phase' = "actions_synced"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/ingest/ibkr_flex.py: import_corporate_actions, `fetch_statement`, `upsert_corporate_actions` *)
FlexImportsTheActions ==
  /\ phase = "snapshot_stored"
  /\ phase' = "actions_synced"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/command.py: run_portfolio, `except Exception` then `log.warning("corporate_actions_import_failed")` *)
FlexFails ==
  /\ phase = "snapshot_stored"
  /\ phase' = "actions_synced"
  /\ flexFailed' = TRUE
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/trades.py: sync_trades calls `client.connect()` again; src/bot/cli.py exits with code 1 *)
TwsDropsBeforeTheTrades ==
  /\ phase = "actions_synced"
  /\ phase' = "tws_lost"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/trades.py: sync_trades, `_watermark`, `_insert_dedup` *)
TheNewFillsAreStored ==
  /\ phase = "actions_synced"
  /\ phase' = "trades_synced"
  /\ stored' = stored \cup {"trades"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: _held_tickers, `HAVING SUM(qty) <> 0` *)
ItIsAHolding ==
  /\ phase = "trades_synced"
  /\ held
  /\ phase' = "holding"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: _held_tickers; src/bot/portfolio/events.py: compute_events `held_tickers`; detect_concentration weighs positions with a market value above 0 *)
ItIsNoLongerAHolding ==
  /\ phase = "trades_synced"
  /\ ~held
  /\ phase' = "concentration_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: mark_holdings, `analyze_fn` gives `intrinsic_value`, `current_price`, and flags with `FlagColor.RED` *)
TheValuatorValuesItWithARedFlag ==
  /\ phase = "holding"
  /\ phase' = "valuation_done"
  /\ valuation' = "red"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: mark_holdings, `analyze_fn` gives `intrinsic_value`, `current_price`, and no flag with `FlagColor.RED` *)
TheValuatorValuesItWithNoRedFlag ==
  /\ phase = "holding"
  /\ phase' = "valuation_done"
  /\ valuation' = "clear"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: mark_holdings, `except (LookupError, ValueError)` leaves all three `None` *)
TheValuatorCannotValueIt ==
  /\ phase = "holding"
  /\ phase' = "valuation_done"
  /\ valuation' = "unknown"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/screener/engine.py: load_holding_inputs; src/bot/portfolio/marks.py: mark_holdings `failed_gates`, `benchmarks.wacc` *)
TheGatesAreJudged ==
  /\ phase = "valuation_done"
  /\ phase' = "gates_done"
  /\ gates' = "with_wacc"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: mark_holdings, `sector_wacc = benchmarks.wacc if benchmarks else None` *)
TheGatesAreJudgedWithoutWacc ==
  /\ phase = "valuation_done"
  /\ phase' = "gates_done"
  /\ gates' = "without_wacc"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: mark_holdings, `if ticker in inputs` is false; src/bot/valuator/analysis.py raises `LookupError` for a ticker not in `companies`, so it was not valued either *)
TheGatesCannotBeJudged ==
  /\ phase = "valuation_done"
  /\ valuation = "unknown"
  /\ phase' = "gates_done"
  /\ gates' = "unknown"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/marks.py: persist_marks *)
TheMarkIsStored ==
  /\ phase = "gates_done"
  /\ phase' = "marked"
  /\ stored' = stored \cup {"holding_marks"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: compute_events, `load_marks(conn, prev_snapshot_date)` *)
ThePreviousMarkIsRead ==
  /\ phase = "marked"
  /\ phase' = "marks_read"
  /\ prevMark' = "present"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: compute_events, `prev_marks` is `{}` or lacks the ticker *)
ThereIsNoPreviousMark ==
  /\ phase = "marked"
  /\ phase' = "marks_read"
  /\ prevMark' = "absent"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_intrinsic_value_cross *)
IntrinsicValueCrossFires ==
  /\ phase = "marks_read"
  /\ prevMark = "present" /\ valuation # "unknown"
  /\ phase' = "cross_checked"
  /\ event' = "intrinsic_value_crossed_price"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_intrinsic_value_cross returns `None` *)
NoCross ==
  /\ phase = "marks_read"
  /\ phase' = "cross_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_new_red_flags *)
NewRedFlagFires ==
  /\ phase = "cross_checked"
  /\ valuation = "red"
  /\ phase' = "flags_checked"
  /\ event' = "new_red_flag"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_new_red_flags returns `[]` *)
NoNewRedFlag ==
  /\ phase = "cross_checked"
  /\ valuation # "red" \/ prevMark = "present"
  /\ phase' = "flags_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_below_quality_gate *)
BelowQualityGateFires ==
  /\ phase = "flags_checked"
  /\ prevMark = "present" /\ gates # "unknown"
  /\ phase' = "gates_checked"
  /\ event' = "below_quality_gate"
  /\ anyFired' = TRUE
  /\ valuation' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_below_quality_gate returns `[]` *)
NoNewFailedGate ==
  /\ phase = "flags_checked"
  /\ phase' = "gates_checked"
  /\ event' = "none"
  /\ valuation' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_sector_recalibration, `DEFAULT_WACC_RECALIBRATION_BPS` *)
SectorRecalibratedFires ==
  /\ phase = "gates_checked"
  /\ prevMark = "present" /\ gates = "with_wacc"
  /\ phase' = "recal_checked"
  /\ event' = "sector_recalibrated"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_sector_recalibration returns `None` *)
NoRecalibration ==
  /\ phase = "gates_checked"
  /\ phase' = "recal_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_concentration, weight is market value divided by the total of positive market values; `DEFAULT_CONCENTRATION_THRESHOLD` *)
ItsWeightIsAbove15 ==
  /\ phase = "recal_checked"
  /\ phase' = "weighed"
  /\ above' = TRUE
  /\ event' = "none"
  /\ gates' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, prevMark, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_concentration, weight is market value divided by the total of positive market values; `DEFAULT_CONCENTRATION_THRESHOLD` *)
ItsWeightIsNotAbove15 ==
  /\ phase = "recal_checked"
  /\ phase' = "weighed"
  /\ above' = FALSE
  /\ event' = "none"
  /\ gates' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, prevMark, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_concentration, `weight > threshold` *)
ConcentrationFires ==
  /\ phase = "weighed"
  /\ above
  /\ phase' = "concentration_checked"
  /\ event' = "concentration"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_concentration, `weight > threshold` is false *)
NotConcentrated ==
  /\ phase = "weighed"
  /\ ~above
  /\ phase' = "concentration_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/command.py: run_portfolio, `_previous_snapshot_date` gives `None`; src/bot/portfolio/events.py: compute_events, `prev_positions = []` *)
ThisIsTheFirstRun ==
  /\ phase = "concentration_checked"
  /\ held /\ prevMark # "present"
  /\ phase' = "window"
  /\ prev' = "none"
  /\ event' = "none"
  /\ above' = FALSE
  /\ prevMark' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: compute_events, `_load_positions(conn, prev_snapshot_date)` *)
ThePreviousSnapshotHeldIt ==
  /\ phase = "concentration_checked"
  /\ phase' = "window"
  /\ prev' = "with_it"
  /\ event' = "none"
  /\ above' = FALSE
  /\ prevMark' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: compute_events, `_load_positions(conn, prev_snapshot_date)` *)
ThePreviousSnapshotLacksIt ==
  /\ phase = "concentration_checked"
  /\ held /\ prevMark # "present"
  /\ phase' = "window"
  /\ prev' = "without_it"
  /\ event' = "none"
  /\ above' = FALSE
  /\ prevMark' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_position_changes *)
PositionOpenedFires ==
  /\ phase = "window"
  /\ held /\ prev # "with_it"
  /\ phase' = "positions_diffed"
  /\ event' = "position_opened"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_position_changes *)
PositionClosedFires ==
  /\ phase = "window"
  /\ ~held
  /\ phase' = "positions_diffed"
  /\ event' = "position_closed"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_position_changes, `DEFAULT_SIZE_CHANGE_THRESHOLD` *)
PositionSizeChangedFires ==
  /\ phase = "window"
  /\ held /\ prev = "with_it"
  /\ phase' = "positions_diffed"
  /\ event' = "position_size_changed"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_position_changes, `DEFAULT_SIZE_CHANGE_THRESHOLD` *)
PositionSizeHolds ==
  /\ phase = "window"
  /\ held /\ prev = "with_it"
  /\ phase' = "positions_diffed"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: compute_events, `if prev_snapshot_date is not None`; detect_currency_changes *)
CurrencyChangedFires ==
  /\ phase = "positions_diffed"
  /\ held /\ prev = "with_it"
  /\ phase' = "currency_checked"
  /\ event' = "currency_changed"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: compute_events, `if prev_snapshot_date is not None`; detect_currency_changes *)
CurrencyIsTheSame ==
  /\ phase = "positions_diffed"
  /\ phase' = "currency_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: _load_corporate_actions (held tickers, the window), detect_corporate_action_events *)
DividendFires ==
  /\ phase = "currency_checked"
  /\ held
  /\ phase' = "dividend_checked"
  /\ event' = "dividend"
  /\ anyFired' = TRUE
  /\ prev' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, filing, alerts >>

(* src/bot/portfolio/events.py: _load_corporate_actions (held tickers, the window), detect_corporate_action_events *)
NoDividend ==
  /\ phase = "currency_checked"
  /\ phase' = "dividend_checked"
  /\ event' = "none"
  /\ prev' = "unread"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: _load_corporate_actions (held tickers, the window), detect_corporate_action_events *)
SplitFires ==
  /\ phase = "dividend_checked"
  /\ held
  /\ phase' = "split_checked"
  /\ event' = "split"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: _load_corporate_actions (held tickers, the window), detect_corporate_action_events *)
NoSplit ==
  /\ phase = "dividend_checked"
  /\ phase' = "split_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: _load_filings, _load_reported_filings *)
ItsFilingIsNotInTheLog ==
  /\ phase = "split_checked"
  /\ held
  /\ phase' = "filing_found"
  /\ filing' = "unreported"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, anyFired, alerts >>

(* src/bot/portfolio/events.py: _load_filings, _load_reported_filings *)
ItsFilingIsInTheLog ==
  /\ phase = "split_checked"
  /\ held
  /\ phase' = "filing_found"
  /\ filing' = "reported"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_new_filings, the window bounds and `held_tickers` *)
NoFilingInTheWindow ==
  /\ phase = "split_checked"
  /\ phase' = "filings_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: detect_new_filings *)
NewFilingFires ==
  /\ phase = "filing_found"
  /\ filing = "unreported"
  /\ phase' = "filings_checked"
  /\ event' = "new_filing"
  /\ anyFired' = TRUE
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/portfolio/events.py: detect_new_filings, `in reported: continue` *)
NewFilingIsSkipped ==
  /\ phase = "filing_found"
  /\ filing = "reported"
  /\ phase' = "filings_checked"
  /\ event' = "none"
  /\ UNCHANGED << channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/events.py: persist_events writes nothing for no events *)
TheEventsAreAppended ==
  /\ phase = "filings_checked"
  /\ phase' = "logged"
  /\ stored' = IF anyFired THEN stored \cup {"events_log"} ELSE stored
  /\ event' = "none"
  /\ filing' = "unread"
  /\ UNCHANGED << channel, flexFailed, held, valuation, gates, prevMark, above, prev, anyFired, alerts >>

(* src/bot/portfolio/command.py: run_portfolio, `build_report`, `render_portfolio`, `portfolio_path.write_text` *)
PortfolioMdIsWritten ==
  /\ phase = "logged"
  /\ phase' = "portfolio_written"
  /\ stored' = stored \cup {"portfolio_md"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired, alerts >>

(* src/bot/portfolio/report.py: render_alerts; src/bot/portfolio/command.py: `alerts_path.write_text` *)
AlertsMdListsTheEvents ==
  /\ phase = "portfolio_written"
  /\ phase' = "alerts_written"
  /\ alerts' = "text"
  /\ stored' = stored \cup {"alerts_md"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired >>

(* src/bot/portfolio/report.py: render_alerts returns `""` without events *)
AlertsMdIsBlank ==
  /\ phase = "portfolio_written"
  /\ ~anyFired
  /\ phase' = "alerts_written"
  /\ alerts' = "blank"
  /\ stored' = stored \cup {"alerts_md"}
  /\ event' = "none"
  /\ UNCHANGED << channel, flexFailed, held, valuation, gates, prevMark, above, prev, filing, anyFired >>

(* src/bot/notifier/__init__.py: build_notifier returns `None`; notify_alerts returns `False` *)
NoChannelIsSet ==
  /\ phase = "alerts_written"
  /\ phase' = "not_sent"
  /\ channel' = "none"
  /\ event' = "none"
  /\ anyFired' = FALSE
  /\ UNCHANGED << stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/notifier/__init__.py: notify_alerts, `if not text.strip()` *)
TheBlankFileIsNotSent ==
  /\ phase = "alerts_written"
  /\ alerts = "blank"
  /\ phase' = "not_sent"
  /\ channel' = "configured"
  /\ event' = "none"
  /\ anyFired' = FALSE
  /\ UNCHANGED << stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/notifier/__init__.py: notify_alerts, `notifier.send(text)` *)
TheAlertsAreSent ==
  /\ phase = "alerts_written"
  /\ alerts = "text"
  /\ phase' = "sent"
  /\ channel' = "configured"
  /\ event' = "none"
  /\ anyFired' = FALSE
  /\ UNCHANGED << stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

(* src/bot/cli.py: portfolio, `NotificationError` exits with code 1 *)
TheSendFails ==
  /\ phase = "alerts_written"
  /\ alerts = "text"
  /\ phase' = "send_failed"
  /\ channel' = "configured"
  /\ event' = "none"
  /\ anyFired' = FALSE
  /\ UNCHANGED << stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, alerts >>

Done ==
  /\ phase \in EndPhases
  /\ UNCHANGED vars

Next ==
  TheChannelIsMisconfigured
  \/ TheChannelIsValid
  \/ TwsIsUnreachable
  \/ TwsAnswers
  \/ ItIsStoredWithAMarketValue
  \/ ItIsStoredUnpriced
  \/ TheSnapshotIsStoredWithoutIt
  \/ FlexIsNotConfigured
  \/ FlexImportsTheActions
  \/ FlexFails
  \/ TwsDropsBeforeTheTrades
  \/ TheNewFillsAreStored
  \/ ItIsAHolding
  \/ ItIsNoLongerAHolding
  \/ TheValuatorValuesItWithARedFlag
  \/ TheValuatorValuesItWithNoRedFlag
  \/ TheValuatorCannotValueIt
  \/ TheGatesAreJudged
  \/ TheGatesAreJudgedWithoutWacc
  \/ TheGatesCannotBeJudged
  \/ TheMarkIsStored
  \/ ThePreviousMarkIsRead
  \/ ThereIsNoPreviousMark
  \/ IntrinsicValueCrossFires
  \/ NoCross
  \/ NewRedFlagFires
  \/ NoNewRedFlag
  \/ BelowQualityGateFires
  \/ NoNewFailedGate
  \/ SectorRecalibratedFires
  \/ NoRecalibration
  \/ ItsWeightIsAbove15
  \/ ItsWeightIsNotAbove15
  \/ ConcentrationFires
  \/ NotConcentrated
  \/ ThisIsTheFirstRun
  \/ ThePreviousSnapshotHeldIt
  \/ ThePreviousSnapshotLacksIt
  \/ PositionOpenedFires
  \/ PositionClosedFires
  \/ PositionSizeChangedFires
  \/ PositionSizeHolds
  \/ CurrencyChangedFires
  \/ CurrencyIsTheSame
  \/ DividendFires
  \/ NoDividend
  \/ SplitFires
  \/ NoSplit
  \/ ItsFilingIsNotInTheLog
  \/ ItsFilingIsInTheLog
  \/ NoFilingInTheWindow
  \/ NewFilingFires
  \/ NewFilingIsSkipped
  \/ TheEventsAreAppended
  \/ PortfolioMdIsWritten
  \/ AlertsMdListsTheEvents
  \/ AlertsMdIsBlank
  \/ NoChannelIsSet
  \/ TheBlankFileIsNotSent
  \/ TheAlertsAreSent
  \/ TheSendFails
  \/ Done

Spec == Init /\ [][Next]_vars

(* Cites: cli.py portfolio: `build_notifier` raises `NotifierConfigError` and the command exits with code 2 before `_open_db` and `run_portfolio`, so no sync runs. *)
\* A misconfigured notifier channel ends the run before any sync, so nothing is stored.
MisconfiguredChannelStoresNothing ==
  channel = "misconfigured" => (phase = "channel_misconfigured" /\ stored = {})

(* Cites: sync_portfolio: `client.connect()` raises before `_replace_account_day`; sync_trades connects again; mark_holdings and compute_events run only after both syncs; cli.py exits with code 1. *)
\* When Trader Workstation (TWS) cannot be reached, the run ends: before the snapshot on the first call, and never with a mark or an event written.
UnreachableTwsWritesNoMarkOrEvent ==
  (phase = "tws_unreachable" => stored = {})
    /\ (phase \in {"tws_unreachable", "tws_lost"} => ("holding_marks" \notin stored /\ "events_log" \notin stored /\ ~anyFired))

(* Cites: mark_holdings: persist_marks runs after sync_portfolio stored the snapshot, over `_held_tickers` only. *)
\* A holding is marked only after the day's snapshot is stored, and only while it is held.
MarkedAfterTheSnapshot ==
  "holding_marks" \in stored => ("portfolio_snapshots" \in stored /\ held)

(* Cites: detect_intrinsic_value_cross, detect_new_red_flags, detect_below_quality_gate and detect_sector_recalibration return nothing when the current value, flags, gates or WACC are `None`. *)
\* An unknown current value never fires a mark event: no intrinsic value cross, new red flag, failed gate or recalibration.
UnknownValueFiresNoMarkEvent ==
  (valuation = "unknown" => event \notin {"intrinsic_value_crossed_price", "new_red_flag"})
    /\ (gates = "unknown" => event \notin {"below_quality_gate", "sector_recalibrated"})
    /\ (gates = "without_wacc" => event # "sector_recalibrated")

(* Cites: compute_events: with no previous snapshot `prev_positions = []`, so detect_position_changes sees every position as new and skips the currency comparison. *)
\* On the first run every position fires position opened, and none fires position closed, size changed or currency changed.
FirstRunOpensEveryPosition ==
  prev = "none" => (event \notin {"position_closed", "currency_changed", "position_size_changed"}
      /\ (phase = "positions_diffed" => event = "position_opened"))

(* Cites: compute_events: without a previous mark detect_intrinsic_value_cross, detect_below_quality_gate and detect_sector_recalibration return nothing; detect_new_red_flags compares only with the previous red flags. *)
\* With no previous mark, intrinsic value cross, below quality gate and sector recalibration never fire, while a red flag now does fire.
NoPreviousMarkOnlyRedFlags ==
  prevMark = "absent" => (event \notin {"intrinsic_value_crossed_price", "below_quality_gate", "sector_recalibrated"}
      /\ ((phase = "flags_checked" /\ valuation = "red") => event = "new_red_flag"))

(* Cites: detect_new_filings: `in reported: continue`, with `_load_reported_filings` reading the events log. *)
\* A filing already in the events log never fires new filing again.
ReportedFilingNeverFiresAgain ==
  event = "new_filing" => filing = "unreported"

(* Cites: detect_concentration reads only `curr_positions`, never the previous snapshot or mark. *)
\* A holding above 15% of the portfolio fires concentration on every run while it stays above, whatever the previous snapshot held.
ConcentrationOnEveryRun ==
  phase = "concentration_checked" => (above = (event = "concentration"))

(* Cites: run_portfolio: persist_events runs before render_alerts and `alerts_path.write_text`. *)
\* Every event fired is appended to the events log before alerts.md is written.
EventsLoggedBeforeAlerts ==
  ("alerts_md" \in stored /\ anyFired) => "events_log" \in stored

(* Cites: run_portfolio writes alerts.md before notify_alerts; notify_alerts: `if not text.strip()` returns before `notifier.send(text)`; build_notifier returns `None` for no channel. *)
\* alerts.md is always written, and it is sent only when a channel is configured and the file is not blank.
AlertsWrittenSentOnlyWithText ==
  (phase \in {"not_sent", "sent", "send_failed"} => "alerts_md" \in stored)
    /\ (phase \in {"sent", "send_failed"} => (channel = "configured" /\ alerts = "text"))

(* Cites: run_portfolio: the `except Exception` around `corporate_actions_fn` only logs a warning; the run goes on to sync_trades. *)
\* A corporate actions failure never stops the run: both reports are still written unless TWS drops afterwards.
CorporateActionsFailureNeverStops ==
  (flexFailed /\ phase \in EndPhases) => (phase = "tws_lost" \/ {"portfolio_md", "alerts_md"} \subseteq stored)

====
