-- Damodaran datasets — industry-level benchmarks (Capa A)
CREATE TABLE IF NOT EXISTS damodaran_industry (
    industry        VARCHAR NOT NULL,
    region          VARCHAR NOT NULL,        -- 'US', 'Europe', 'EM', 'Japan', 'China', 'India', 'AusNZCan', 'Global'
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

-- Damodaran datasets — country-level risk (Capa A)
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

-- Universe of companies (populated by SEC EDGAR in M1; expanded by FMP in M2)
CREATE TABLE IF NOT EXISTS companies (
    ticker          VARCHAR PRIMARY KEY,
    cik             VARCHAR,                 -- SEC CIK (10 chars, zero-padded)
    name            VARCHAR NOT NULL,
    country         VARCHAR,                 -- ISO 3166-1 alpha-2
    exchange        VARCHAR,
    industry        VARCHAR,                 -- raw, as reported by source
    industry_damodaran VARCHAR,              -- mapped to Damodaran taxonomy
    isin            VARCHAR,
    currency        VARCHAR,                 -- ISO 4217
    status          VARCHAR DEFAULT 'active', -- 'active' | 'delisted' | 'acquired'
    source          VARCHAR NOT NULL,        -- 'sec_edgar' | 'fmp' | ...
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Annual financials (one row per ticker × fiscal_year)
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

-- Quarterly financials (same shape, different grain)
CREATE TABLE IF NOT EXISTS financials_quarterly (
    ticker          VARCHAR NOT NULL,
    fiscal_year     INTEGER NOT NULL,
    fiscal_quarter  INTEGER NOT NULL,        -- 1..4
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

-- Track filings we've ingested (for incremental refresh)
CREATE TABLE IF NOT EXISTS filings_log (
    ticker          VARCHAR NOT NULL,
    filing_type     VARCHAR NOT NULL,        -- '10-K', '10-Q', '8-K', 'annual-fmp', ...
    filing_date     DATE NOT NULL,
    accession_number VARCHAR,                -- SEC accession or provider id
    source          VARCHAR NOT NULL,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, filing_type, filing_date, source)
);

-- Daily price history populated by FMP (M2.4)
CREATE TABLE IF NOT EXISTS prices_daily (
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    close           DOUBLE NOT NULL,
    adjusted_close  DOUBLE,
    volume          BIGINT,
    market_cap      DOUBLE,
    currency        VARCHAR,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

-- Track refresh runs by source (for `bot status`)
CREATE TABLE IF NOT EXISTS refresh_log (
    source          VARCHAR NOT NULL,        -- 'damodaran', 'sec_edgar', 'fmp', 'ibkr'
    run_id          VARCHAR NOT NULL,        -- uuid
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    status          VARCHAR NOT NULL,        -- 'running' | 'success' | 'partial' | 'error'
    rows_affected   INTEGER,
    error_message   VARCHAR,
    PRIMARY KEY (source, run_id)
);
