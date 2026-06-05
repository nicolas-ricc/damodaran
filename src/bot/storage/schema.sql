-- Damodaran datasets — industry-level benchmarks (Capa A)
CREATE TABLE IF NOT EXISTS damodaran_industry (
    industry        VARCHAR NOT NULL,
    region          VARCHAR NOT NULL,
    year            INTEGER NOT NULL,
    wacc            DOUBLE,
    cost_of_equity  DOUBLE,
    cost_of_debt    DOUBLE,
    beta_unlevered  DOUBLE,
    beta_levered    DOUBLE,
    debt_to_equity  DOUBLE,
    op_margin       DOUBLE,
    net_margin      DOUBLE,
    roe             DOUBLE,
    roic            DOUBLE,
    pe              DOUBLE,
    pbv             DOUBLE,
    ev_ebitda       DOUBLE,
    ev_sales        DOUBLE,
    sales_to_capital DOUBLE,
    reinvestment_rate DOUBLE,
    tax_rate        DOUBLE,
    payout_ratio    DOUBLE,
    PRIMARY KEY (industry, region, year)
);

CREATE TABLE IF NOT EXISTS damodaran_country (
    country         VARCHAR NOT NULL,
    year            INTEGER NOT NULL,
    erp             DOUBLE,
    country_risk_premium DOUBLE,
    risk_free_rate  DOUBLE,
    tax_rate        DOUBLE,
    rating          VARCHAR,
    region          VARCHAR,
    PRIMARY KEY (country, year)
);

-- Daily FX rates against USD (M2.5). One row per (currency, date).
-- `rate_to_usd` is the multiplier that converts 1 unit of `currency` into USD:
--   usd_amount = amount_in_currency * rate_to_usd.
-- Sourced from FMP historical forex prices (pair {CURRENCY}USD, daily close).
-- USD itself is stored with rate_to_usd = 1.0. Lookups use nearest-prior date
-- (see bot.utils.fx.get_fx_rate) so a period-end on a weekend/holiday resolves
-- to the last available trading day.
CREATE TABLE IF NOT EXISTS currencies (
    currency        VARCHAR NOT NULL,
    date            DATE NOT NULL,
    rate_to_usd     DOUBLE NOT NULL,
    source          VARCHAR NOT NULL DEFAULT 'fmp',
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (currency, date)
);

-- Daily end-of-day prices (M2.4). One row per (ticker, date).
-- `close` is the unadjusted closing price in the company's listing currency
-- (`currency`). `market_cap` is FMP's reported market capitalization for that
-- day when available. Sourced from FMP's historical EOD price endpoint. The
-- importer (`import_prices_from_fmp`) is incremental: it only fetches dates
-- after max(date) already stored for the ticker, so a second run with current
-- data performs zero new INSERTs.
CREATE TABLE IF NOT EXISTS prices_daily (
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    close           DOUBLE,
    volume          DOUBLE,
    market_cap      DOUBLE,
    currency        VARCHAR,
    source          VARCHAR NOT NULL DEFAULT 'fmp',
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS companies (
    ticker          VARCHAR PRIMARY KEY,
    cik             VARCHAR,
    name            VARCHAR NOT NULL,
    country         VARCHAR,
    exchange        VARCHAR,
    industry        VARCHAR,
    industry_damodaran VARCHAR,
    isin            VARCHAR,
    currency        VARCHAR,
    status          VARCHAR DEFAULT 'active',
    source          VARCHAR NOT NULL,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS financials_annual (
    ticker          VARCHAR NOT NULL,
    fiscal_year     INTEGER NOT NULL,
    period_end_date DATE,
    currency        VARCHAR,
    revenue         DOUBLE,
    cogs            DOUBLE,
    gross_profit    DOUBLE,
    operating_expenses DOUBLE,
    ebit            DOUBLE,
    ebitda          DOUBLE,
    interest_expense DOUBLE,
    tax_expense     DOUBLE,
    net_income      DOUBLE,
    total_assets    DOUBLE,
    total_debt      DOUBLE,
    cash            DOUBLE,
    total_equity    DOUBLE,
    goodwill        DOUBLE,
    working_capital DOUBLE,
    capex           DOUBLE,
    depreciation    DOUBLE,
    operating_cashflow DOUBLE,
    free_cashflow   DOUBLE,
    dividends_paid  DOUBLE,
    shares_diluted  DOUBLE,
    is_restated     BOOLEAN DEFAULT FALSE,
    source          VARCHAR NOT NULL,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_year, is_restated)
);

CREATE TABLE IF NOT EXISTS financials_quarterly (
    ticker          VARCHAR NOT NULL,
    fiscal_year     INTEGER NOT NULL,
    fiscal_quarter  INTEGER NOT NULL,
    period_end_date DATE,
    currency        VARCHAR,
    revenue         DOUBLE,
    ebit            DOUBLE,
    ebitda          DOUBLE,
    net_income      DOUBLE,
    operating_cashflow DOUBLE,
    free_cashflow   DOUBLE,
    total_debt      DOUBLE,
    cash            DOUBLE,
    is_restated     BOOLEAN DEFAULT FALSE,
    source          VARCHAR NOT NULL,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_year, fiscal_quarter, is_restated)
);

CREATE TABLE IF NOT EXISTS filings_log (
    ticker          VARCHAR NOT NULL,
    filing_type     VARCHAR NOT NULL,
    filing_date     DATE NOT NULL,
    accession_number VARCHAR,
    source          VARCHAR NOT NULL,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, filing_type, filing_date, source)
);

CREATE TABLE IF NOT EXISTS refresh_log (
    source          VARCHAR NOT NULL,
    run_id          VARCHAR NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    status          VARCHAR NOT NULL,
    rows_affected   INTEGER,
    error_message   VARCHAR,
    PRIMARY KEY (source, run_id)
);

-- Screener shortlist (Capa B) — latest ranked candidates per preset run.
-- One row per (run_id, ticker). `ticker` references companies.ticker
-- (logical FK; not enforced because a screen run may rank tickers that have
-- not yet been individually imported into `companies`).
-- Sub-scores follow spec §6.5: score = 0.40*value + 0.30*quality
-- + 0.20*growth + 0.10*margin_of_safety. passed_gates / failed_gates hold the
-- serialized rule names (§6.2/§6.4) that the candidate cleared or tripped.
-- Daily portfolio snapshot from the read-only IBKR client (M5, #26).
-- Append-only across days; one batch of rows per (account, snapshot_date).
-- `sync_portfolio` is idempotent per day: re-running on the same calendar day
-- deletes that day's rows for the account and re-inserts, so a same-day refresh
-- never duplicates while a new day appends a fresh snapshot.
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_date   DATE NOT NULL,
    account         VARCHAR NOT NULL,
    ticker          VARCHAR NOT NULL,
    con_id          INTEGER,
    sec_type        VARCHAR,
    exchange        VARCHAR,
    qty             DOUBLE,
    avg_cost        DOUBLE,
    market_value    DOUBLE,
    currency        VARCHAR,
    source          VARCHAR NOT NULL DEFAULT 'ibkr',
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_date, account, ticker, con_id)
);

-- Per-currency cash balances captured alongside each portfolio snapshot
-- (M5, #26). One row per (snapshot_date, account, currency); same per-day
-- delete-then-insert idempotency as portfolio_snapshots.
CREATE TABLE IF NOT EXISTS cash_balances (
    snapshot_date   DATE NOT NULL,
    account         VARCHAR NOT NULL,
    currency        VARCHAR NOT NULL,
    amount          DOUBLE,
    source          VARCHAR NOT NULL DEFAULT 'ibkr',
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_date, account, currency)
);

-- Trade executions (fills) sourced from the IBKR TWS socket (M5, #27).
-- Append-only: one row per broker execution. `sync_trades` is incremental —
-- it derives a watermark from max(executed_at) already stored and only fetches
-- fills newer than that, de-duping on the broker `exec_id` so an overlapping
-- look-back window cannot double-insert. `exec_id` is IBKR's globally-unique
-- execution id and is the primary key. `executed_at` is the fill timestamp
-- normalised to naive UTC (ib_async returns it timezone-aware; the sync layer
-- converts to UTC and drops the tzinfo so DuckDB needs no pytz at read time).
-- NOTE: the live TWS socket only
-- returns the current session's fills (today + a short look-back), so this
-- table accumulates history across daily runs; a one-shot historical backfill
-- needs IBKR Flex (out of scope, see #27 addendum).
CREATE TABLE IF NOT EXISTS trades (
    exec_id         VARCHAR PRIMARY KEY,
    account         VARCHAR NOT NULL,
    con_id          INTEGER,
    ticker          VARCHAR NOT NULL,
    sec_type        VARCHAR,
    side            VARCHAR,
    qty             DOUBLE,
    price           DOUBLE,
    currency        VARCHAR,
    executed_at     TIMESTAMP NOT NULL,
    perm_id         INTEGER,
    source          VARCHAR NOT NULL DEFAULT 'ibkr',
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Corporate actions — dividends received, splits, mergers (M5, #27).
-- DEFERRED / STUBBED: the live TWS socket does NOT expose corporate actions in
-- any reliable form (see #27 addendum). They come from IBKR's Flex Web Service
-- (a Flex Query + token fetched over HTTP) or downloaded account statements —
-- a separate integration with its own auth that is out of scope here. This
-- table is created so the schema is ready, but nothing populates it yet; a
-- follow-up issue will add a Flex importer. `details` is a JSON blob holding
-- the fields that vary by action type (split ratio, merger terms, etc.).
CREATE TABLE IF NOT EXISTS corporate_actions (
    action_id       VARCHAR PRIMARY KEY,
    account         VARCHAR,
    action_type     VARCHAR NOT NULL,
    ticker          VARCHAR NOT NULL,
    effective_date  DATE NOT NULL,
    details         JSON,
    source          VARCHAR NOT NULL DEFAULT 'ibkr-flex',
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio monitor event log (spec §8.3, M5, #28). One row per detected event
-- between two consecutive portfolio snapshots. `event_type` is a member of
-- bot.portfolio.events.EventType (e.g. 'position_opened', 'new_filing',
-- 'intrinsic_value_crossed_price'). `ticker` is the affected position.
-- `prev_snapshot_date` is NULL for the very first snapshot (no prior baseline);
-- `curr_snapshot_date` is the snapshot the event was detected on. `details` is a
-- JSON blob carrying the event-specific payload (the % size change, the crossed
-- price/intrinsic value, the red flag name, the filing accession, etc.). This is
-- an append-only audit trail; rendering / alerting lives in #29 / #32.
CREATE TABLE IF NOT EXISTS events_log (
    event_type          VARCHAR NOT NULL,
    ticker              VARCHAR NOT NULL,
    prev_snapshot_date  DATE,
    curr_snapshot_date  DATE NOT NULL,
    details             JSON,
    source              VARCHAR NOT NULL DEFAULT 'portfolio-monitor',
    detected_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS screener_candidates (
    run_id          VARCHAR NOT NULL,
    preset          VARCHAR NOT NULL,
    ticker          VARCHAR NOT NULL,
    rank            INTEGER NOT NULL,
    score           DOUBLE,
    value_score     DOUBLE,
    quality_score   DOUBLE,
    growth_score    DOUBLE,
    mos_score       DOUBLE,
    passed_gates    VARCHAR[],
    failed_gates    VARCHAR[],
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, ticker)
);
