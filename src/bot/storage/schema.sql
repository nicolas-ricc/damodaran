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
