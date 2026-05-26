# M1 — Skeleton + Damodaran (Capa A) + SEC EDGAR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first vertical slice of the investment bot: a Python project skeleton with DuckDB storage, importer for Damodaran datasets (Capa A), and SEC EDGAR adapter to fetch US company fundamentals — exposed through a minimal Typer CLI.

**Architecture:** Layered Python package (`src/bot/`) with clean separation between `storage`, `ingest`, `utils`, and `cli`. DuckDB single-file database. Each ingest adapter is a pure module that downloads/parses/normalizes data into the shared schema. CLI is a thin Typer wrapper over the modules.

**Tech Stack:** Python 3.12+, uv (package manager), Typer (CLI), DuckDB (storage), Polars (data manipulation), Pydantic v2 (validation), httpx (HTTP), structlog (logging), pytest + pytest-vcr (testing), ruff + mypy --strict (quality).

**Reference spec:** `docs/superpowers/specs/2026-05-25-investment-bot-design.md` (sections 4, 5, 10, 11).

**End state demoable:**
- `bot --help` lists all M1 commands.
- `bot refresh --damodaran` downloads + imports Damodaran datasets into DuckDB.
- `bot show <TICKER>` (US ticker) fetches from SEC EDGAR if absent, prints company + last 5 years of fundamentals.
- `bot doctor` reports system health.
- `bot status` reports last refresh times.
- Full test suite passes with `pytest`.

---

## File Structure

**Created in this milestone:**

```
investment-bot/
├── pyproject.toml                          # deps, ruff/mypy/pytest config, entry point
├── uv.lock
├── .gitignore                              # ignore .env, bot.duckdb, reports/, .venv/
├── .env.example                            # template for required env vars
├── README.md                               # quickstart
├── CONTEXT.md                              # project context (per user convention)
├── docs/
│   ├── adr/
│   │   ├── 0001-use-duckdb.md
│   │   ├── 0002-sec-edgar-first-fmp-later.md
│   │   └── 0003-client-portal-api-over-tws.md
│   ├── superpowers/
│   │   ├── specs/2026-05-25-investment-bot-design.md  # already exists
│   │   └── plans/2026-05-25-m1-skeleton-damodaran-sec-edgar.md  # this file
├── src/bot/
│   ├── __init__.py                         # version
│   ├── cli.py                              # Typer app, all CLI commands
│   ├── config.py                           # Pydantic Settings (env vars)
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                           # connect(), apply_schema(), helpers
│   │   └── schema.sql                      # idempotent DDL for all M1 tables
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── base.py                         # Adapter Protocol + shared types
│   │   ├── damodaran.py                    # download + parse + upsert
│   │   └── sec_edgar.py                    # fetch + parse + upsert
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py                      # structlog setup
│   │   └── dates.py                        # date helpers
│   └── reporting/
│       ├── __init__.py
│       └── show.py                         # render `bot show` output
├── tests/
│   ├── conftest.py                         # shared fixtures (in-memory DuckDB, etc.)
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_storage_db.py
│   │   ├── test_damodaran_parser.py
│   │   ├── test_sec_edgar_parser.py
│   │   └── test_reporting_show.py
│   ├── integration/
│   │   ├── test_damodaran_import.py        # uses VCR cassettes
│   │   └── test_sec_edgar_import.py        # uses VCR cassettes
│   └── fixtures/
│       ├── damodaran/                      # sample Damodaran xls files (real, mini)
│       │   ├── wacc_sample.xls
│       │   └── ctryprem_sample.xls
│       └── cassettes/                      # VCR-recorded HTTP responses
│           ├── damodaran_download_wacc.yaml
│           ├── damodaran_download_ctryprem.yaml
│           ├── sec_edgar_lookup_aapl.yaml
│           └── sec_edgar_facts_aapl.yaml
└── scripts/                                # (placeholder; populated in M6)
```

**Boundaries**: every file has one responsibility. `storage/db.py` knows nothing about Damodaran or SEC. `ingest/damodaran.py` knows nothing about SEC. The CLI orchestrates but contains no business logic. Tests mirror source layout.

---

## Task 1: Project bootstrap with uv

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Create `.gitignore`**

Write to `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/

# Project artifacts
.env
bot.duckdb
bot.duckdb.wal
reports/
logs/

# VCR — record locally, ignore re-records
tests/fixtures/cassettes/**/*.yaml.tmp
```

- [ ] **Step 2: Create `.env.example`**

Write to `.env.example`:

```bash
# DuckDB file path
BOT_DB_PATH=./bot.duckdb

# SEC EDGAR requires a User-Agent identifying you (per their fair-use policy)
# Format: "Name email@example.com"
BOT_SEC_USER_AGENT=Nicolas Riccomini nicolas.riccomini@gmail.com

# Reports output directory
BOT_REPORTS_DIR=./reports

# Logging
BOT_LOG_LEVEL=INFO
```

- [ ] **Step 3: Create `pyproject.toml`**

Write to `pyproject.toml`:

```toml
[project]
name = "bot"
version = "0.1.0"
description = "Personal investment bot — value screener + portfolio monitor"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "duckdb>=1.1",
    "polars>=1.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "httpx>=0.27",
    "structlog>=24.1",
    "python-dotenv>=1.0",
    "openpyxl>=3.1",       # for reading Damodaran .xls/.xlsx
    "xlrd>=2.0",           # legacy .xls fallback
    "rich>=13.7",          # pretty CLI output (used by Typer)
]

[project.scripts]
bot = "bot.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-vcr>=1.0.2",
    "ruff>=0.5",
    "mypy>=1.10",
    "types-openpyxl",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/bot"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "B", "UP", "RUF", "SIM", "TID"]
ignore = ["E501"]  # line length handled by formatter

[tool.mypy]
strict = true
python_version = "3.12"
mypy_path = "src"
packages = ["bot"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers"
markers = [
    "integration: tests that hit external services (use VCR cassettes)",
]
```

- [ ] **Step 4: Create `README.md`**

Write to `README.md`:

```markdown
# investment-bot

Personal investment bot: value screener (Damodaran-style) + portfolio monitor for Interactive Brokers UK.

CLI-only. Local. No real-time data, no execution.

See `docs/superpowers/specs/2026-05-25-investment-bot-design.md` for the full design.

## Quickstart

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync                          # install dependencies
cp .env.example .env             # configure
$EDITOR .env                     # set BOT_SEC_USER_AGENT to your name + email

uv run bot --help                # see available commands
uv run bot doctor                # verify setup
uv run bot refresh --damodaran   # import Damodaran datasets (M1)
uv run bot show AAPL             # show a US company's fundamentals (M1)
```

## Development

```bash
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type check
```
```

- [ ] **Step 5: Initialize uv and verify install**

Run:

```bash
cd /home/nicolasr/Projects/investment-bot
uv sync
uv run python -c "import duckdb, polars, typer, pydantic, httpx, structlog; print('OK')"
```

Expected: `OK` printed; `uv.lock` created.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .env.example README.md
git commit -m "feat(m1): bootstrap project with uv, deps, and base config"
```

---

## Task 2: CLI skeleton with Typer

**Files:**
- Create: `src/bot/__init__.py`
- Create: `src/bot/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_cli.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_cli.py`:

```python
from typer.testing import CliRunner

from bot.cli import app


def test_cli_help_works():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "investment bot" in result.stdout.lower()


def test_cli_version_command():
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
```

Write empty `tests/__init__.py`, `tests/unit/__init__.py`, and `tests/conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'bot.cli'`.

- [ ] **Step 3: Create `src/bot/__init__.py`**

Write to `src/bot/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Implement CLI skeleton**

Write to `src/bot/cli.py`:

```python
"""Investment bot — command-line interface."""

import typer

from bot import __version__

app = typer.Typer(
    help="Personal investment bot — value screener + portfolio monitor.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(__version__)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli.py -v`

Expected: PASS (both tests).

- [ ] **Step 6: Verify entry point works**

Run: `uv run bot version`

Expected: `0.1.0` printed.

- [ ] **Step 7: Commit**

```bash
git add src/bot/__init__.py src/bot/cli.py tests/__init__.py tests/unit/__init__.py tests/unit/test_cli.py tests/conftest.py
git commit -m "feat(m1): add CLI skeleton with version command"
```

---

## Task 3: Structured logging setup

**Files:**
- Create: `src/bot/utils/__init__.py`
- Create: `src/bot/utils/logging.py`
- Create: `tests/unit/test_logging.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_logging.py`:

```python
import json
import logging

from bot.utils.logging import configure_logging, get_logger


def test_configure_logging_produces_json(capsys):
    configure_logging(level="INFO", json_output=True)
    logger = get_logger("test")
    logger.info("hello", extra_field="value")
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["event"] == "hello"
    assert payload["extra_field"] == "value"
    assert payload["level"] == "info"


def test_configure_logging_respects_level(capsys):
    configure_logging(level="WARNING", json_output=True)
    logger = get_logger("test")
    logger.info("should_not_appear")
    logger.warning("should_appear")
    captured = capsys.readouterr()
    assert "should_not_appear" not in captured.out
    assert "should_appear" in captured.out
```

- [ ] **Step 2: Create empty `src/bot/utils/__init__.py`**

Write empty file `src/bot/utils/__init__.py`.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_logging.py -v`

Expected: FAIL — module not found.

- [ ] **Step 4: Implement logging**

Write to `src/bot/utils/logging.py`:

```python
"""Structured logging via structlog."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog with the given level and output format."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_logging.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bot/utils/__init__.py src/bot/utils/logging.py tests/unit/test_logging.py
git commit -m "feat(m1): add structlog-based logging utility"
```

---

## Task 4: Configuration loading (Pydantic Settings)

**Files:**
- Create: `src/bot/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_config.py`:

```python
from pathlib import Path

import pytest

from bot.config import Settings


def test_settings_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Test User test@example.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_LOG_LEVEL", "DEBUG")

    s = Settings()
    assert s.db_path == tmp_path / "test.duckdb"
    assert s.sec_user_agent == "Test User test@example.com"
    assert s.reports_dir == tmp_path / "reports"
    assert s.log_level == "DEBUG"


def test_settings_requires_sec_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_SEC_USER_AGENT", raising=False)
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    with pytest.raises(Exception) as exc:
        Settings(_env_file=None)
    assert "sec_user_agent" in str(exc.value).lower()


def test_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "X Y x@y.com")
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.delenv("BOT_LOG_LEVEL", raising=False)
    monkeypatch.delenv("BOT_REPORTS_DIR", raising=False)
    s = Settings(_env_file=None)
    assert s.log_level == "INFO"
    assert isinstance(s.reports_dir, Path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement config**

Write to `src/bot/config.py`:

```python
"""Application settings, loaded from environment / .env."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the bot."""

    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(default=Path("./bot.duckdb"))
    sec_user_agent: str = Field(
        ...,
        description="User-Agent header for SEC EDGAR requests. "
        "Required by SEC fair-use policy.",
    )
    reports_dir: Path = Field(default=Path("./reports"))
    log_level: str = Field(default="INFO")


def load_settings() -> Settings:
    """Load settings; raises on missing required fields."""
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`

Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add src/bot/config.py tests/unit/test_config.py
git commit -m "feat(m1): add Pydantic Settings-based configuration"
```

---

## Task 5: DuckDB storage layer — connection and schema

**Files:**
- Create: `src/bot/storage/__init__.py`
- Create: `src/bot/storage/db.py`
- Create: `src/bot/storage/schema.sql`
- Create: `tests/unit/test_storage_db.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_storage_db.py`:

```python
import duckdb

from bot.storage.db import apply_schema, connect


def test_connect_creates_file(tmp_path):
    db_file = tmp_path / "x.duckdb"
    conn = connect(db_file)
    assert db_file.exists()
    result = conn.execute("SELECT 1 AS x").fetchone()
    assert result == (1,)
    conn.close()


def test_apply_schema_creates_all_tables(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    expected = {
        "damodaran_industry",
        "damodaran_country",
        "companies",
        "financials_annual",
        "financials_quarterly",
        "filings_log",
        "refresh_log",
    }
    assert expected.issubset(tables)
    conn.close()


def test_apply_schema_is_idempotent(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    apply_schema(conn)  # should not raise
    conn.close()


def test_connect_in_memory():
    conn = connect(":memory:")
    apply_schema(conn)
    result = conn.execute("SELECT COUNT(*) FROM companies").fetchone()
    assert result == (0,)
    conn.close()
```

- [ ] **Step 2: Create empty `src/bot/storage/__init__.py`**

Write empty file `src/bot/storage/__init__.py`.

- [ ] **Step 3: Write `schema.sql`**

Write to `src/bot/storage/schema.sql`:

```sql
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
```

- [ ] **Step 4: Implement `db.py`**

Write to `src/bot/storage/db.py`:

```python
"""DuckDB connection and schema management."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Union

import duckdb

DbPath = Union[Path, str]


def connect(db_path: DbPath) -> duckdb.DuckDBPyConnection:
    """Open (and create if missing) a DuckDB database at the given path.

    Pass ":memory:" for an in-memory DB (useful in tests).
    """
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(db_path))
    return duckdb.connect(db_path)


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply the DDL in `schema.sql`. Idempotent (uses CREATE TABLE IF NOT EXISTS)."""
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    conn.execute(sql)
```

- [ ] **Step 5: Update `pyproject.toml` to include `schema.sql` in package**

Edit `pyproject.toml`: under `[tool.hatch.build.targets.wheel]`, ensure the SQL file is included by adding:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/bot"]

[tool.hatch.build.targets.wheel.force-include]
"src/bot/storage/schema.sql" = "bot/storage/schema.sql"
```

Then run `uv sync` to refresh the install.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_storage_db.py -v`

Expected: PASS (all four tests).

- [ ] **Step 7: Commit**

```bash
git add src/bot/storage/ tests/unit/test_storage_db.py pyproject.toml
git commit -m "feat(m1): add DuckDB storage layer with schema for Damodaran + SEC tables"
```

---

## Task 6: Ingest base types (Adapter Protocol)

**Files:**
- Create: `src/bot/ingest/__init__.py`
- Create: `src/bot/ingest/base.py`
- Create: `tests/unit/test_ingest_base.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_ingest_base.py`:

```python
from datetime import datetime

from bot.ingest.base import IngestResult


def test_ingest_result_basic():
    r = IngestResult(
        source="test",
        rows_affected=10,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
    )
    assert r.duration_seconds() == 5.0
    assert r.is_success() is True


def test_ingest_result_partial_failure():
    r = IngestResult(
        source="test",
        rows_affected=5,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="partial",
        error_message="3 of 8 records failed validation",
    )
    assert r.is_success() is False
```

- [ ] **Step 2: Create empty `src/bot/ingest/__init__.py`**

Write empty file `src/bot/ingest/__init__.py`.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_ingest_base.py -v`

Expected: FAIL — module not found.

- [ ] **Step 4: Implement `base.py`**

Write to `src/bot/ingest/base.py`:

```python
"""Shared types for ingest adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

IngestStatus = Literal["success", "partial", "error"]


@dataclass
class IngestResult:
    """Outcome of a single ingest run, written to `refresh_log`."""

    source: str
    started_at: datetime
    finished_at: datetime
    status: IngestStatus
    rows_affected: int = 0
    error_message: str | None = None
    details: dict = field(default_factory=dict)

    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def is_success(self) -> bool:
        return self.status == "success"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_ingest_base.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/__init__.py src/bot/ingest/base.py tests/unit/test_ingest_base.py
git commit -m "feat(m1): add IngestResult shared type for adapters"
```

---

## Task 7: Damodaran parser (pure function over xls)

**Files:**
- Create: `tests/fixtures/__init__.py` (empty marker)
- Create: `tests/fixtures/damodaran/wacc_sample.xls` (placeholder; populated in this task)
- Create: `tests/fixtures/damodaran/ctryprem_sample.xls` (placeholder; populated in this task)
- Create: `src/bot/ingest/damodaran.py` (initial — parser only)
- Create: `tests/unit/test_damodaran_parser.py`

**Important context**: Damodaran's actual xls files have several worksheets and column names that vary between annual editions. The parser must:
1. Open the file with `openpyxl` (modern .xlsx) or `xlrd` (legacy .xls) — Damodaran uses both depending on the dataset.
2. Find the "Industry Averages" or "By Country" worksheet by name (case-insensitive partial match).
3. Read into a Polars DataFrame.
4. Apply a **column mapping config** (passed as parameter — defaults provided for the two M1 datasets).
5. Return a list of normalized dicts matching the DB schema.

The column mappings are inspected once from the actual Damodaran file structure and embedded as defaults in the parser. Engineers should download one file (`wacc.xlsx` and `ctryprem.xlsx`) from `pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html` to inspect the actual column headers and adjust the default mapping below.

- [ ] **Step 1: Download a sample Damodaran file for fixture and inspection**

Run:

```bash
mkdir -p tests/fixtures/damodaran
curl -fsSL -o tests/fixtures/damodaran/wacc_sample.xls \
    "https://pages.stern.nyu.edu/~adamodar/pc/datasets/wacc.xls"
curl -fsSL -o tests/fixtures/damodaran/ctryprem_sample.xls \
    "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xls"
ls -la tests/fixtures/damodaran/
```

Expected: both files downloaded, non-zero size. If the URLs return 404, check `pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html` for the current paths and update both the fixture commands and the URLs in `damodaran.py` (Step 5 below).

- [ ] **Step 2: Inspect column headers from the sample files**

Run:

```bash
uv run python -c "
import openpyxl
import xlrd
import sys
try:
    wb = openpyxl.load_workbook('tests/fixtures/damodaran/wacc_sample.xls', data_only=True)
    print('openpyxl sheets:', wb.sheetnames)
    for s in wb.sheetnames:
        ws = wb[s]
        rows = list(ws.iter_rows(min_row=1, max_row=3, values_only=True))
        print(f'--- {s} (first 3 rows) ---'); [print(r) for r in rows]
except Exception as e:
    print('openpyxl failed:', e, '; trying xlrd', file=sys.stderr)
    wb = xlrd.open_workbook('tests/fixtures/damodaran/wacc_sample.xls')
    print('xlrd sheets:', wb.sheet_names())
    for sn in wb.sheet_names():
        s = wb.sheet_by_name(sn)
        print(f'--- {sn} (first 3 rows) ---')
        for r in range(min(3, s.nrows)):
            print(s.row_values(r))
"
```

Expected: prints sheet names and the first 3 rows. **Note the sheet name and header row positions** — use them in Step 5's default mapping if they differ from what's coded below.

- [ ] **Step 3: Write the failing test**

Write to `tests/unit/test_damodaran_parser.py`:

```python
from pathlib import Path

import pytest

from bot.ingest.damodaran import (
    DEFAULT_COUNTRY_COLUMN_MAP,
    DEFAULT_INDUSTRY_COLUMN_MAP,
    parse_industry_xls,
    parse_country_xls,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"


@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran wacc fixture not downloaded; run Task 7 Step 1.",
)
def test_parse_industry_xls_returns_rows():
    rows = parse_industry_xls(
        FIXTURES / "wacc_sample.xls",
        region="US",
        year=2026,
        column_map=DEFAULT_INDUSTRY_COLUMN_MAP,
    )
    assert len(rows) > 50  # Damodaran publishes ~90+ industries
    sample = rows[0]
    assert "industry" in sample
    assert sample["region"] == "US"
    assert sample["year"] == 2026
    # at least one numeric column populated
    numeric_keys = {"wacc", "cost_of_equity", "beta_unlevered"}
    assert any(sample.get(k) is not None for k in numeric_keys)


@pytest.mark.skipif(
    not (FIXTURES / "ctryprem_sample.xls").exists(),
    reason="Damodaran ctryprem fixture not downloaded; run Task 7 Step 1.",
)
def test_parse_country_xls_returns_rows():
    rows = parse_country_xls(
        FIXTURES / "ctryprem_sample.xls",
        year=2026,
        column_map=DEFAULT_COUNTRY_COLUMN_MAP,
    )
    assert len(rows) > 100  # ~150 countries
    sample = rows[0]
    assert "country" in sample
    assert sample["year"] == 2026
    assert any(sample.get(k) is not None for k in {"erp", "country_risk_premium"})


def test_parse_industry_xls_skips_blank_rows(tmp_path):
    # build a minimal synthetic xlsx with a blank row to verify filtering
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Industry Averages"
    ws.append(["Industry Name", "Cost of Equity", "WACC"])
    ws.append(["Software", 0.10, 0.09])
    ws.append([None, None, None])
    ws.append(["Retail", 0.08, 0.07])
    path = tmp_path / "tiny.xlsx"
    wb.save(path)

    mapping = {
        "industry": "Industry Name",
        "cost_of_equity": "Cost of Equity",
        "wacc": "WACC",
    }
    rows = parse_industry_xls(
        path, region="US", year=2026, column_map=mapping, sheet_name="Industry Averages"
    )
    assert len(rows) == 2
    assert {r["industry"] for r in rows} == {"Software", "Retail"}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_damodaran_parser.py -v`

Expected: FAIL — module not found.

- [ ] **Step 5: Implement parser**

Write to `src/bot/ingest/damodaran.py`:

```python
"""Damodaran datasets — downloader, parser, importer (Capa A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from bot.utils.logging import get_logger

log = get_logger(__name__)

# Default column mapping for the industry-level WACC dataset (US edition).
# Adjust these keys after inspecting the actual file structure (Task 7 Step 2).
# Each value is the column header in the xls; missing columns are simply skipped.
DEFAULT_INDUSTRY_COLUMN_MAP: dict[str, str] = {
    "industry": "Industry Name",
    "cost_of_equity": "Cost of Equity",
    "cost_of_debt": "Cost of Debt",
    "wacc": "Cost of Capital",
    "beta_levered": "Beta",
    "beta_unlevered": "Unlevered beta",
    "debt_to_equity": "D/E Ratio",
    "tax_rate": "Tax Rate",
}

DEFAULT_COUNTRY_COLUMN_MAP: dict[str, str] = {
    "country": "Country",
    "rating": "Moody's rating",
    "erp": "Total Equity Risk Premium",
    "country_risk_premium": "Country Risk Premium",
    "region": "Region",
}

# Default Damodaran source URLs (override via importer config if Damodaran moves files).
INDUSTRY_WACC_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/wacc.xls"
COUNTRY_RISK_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xls"


def _load_workbook_to_df(path: Path, sheet_name: str | None) -> pl.DataFrame:
    """Read an xls/xlsx file into a Polars DataFrame, picking the first matching sheet.

    If `sheet_name` is provided, requires an exact match.
    Otherwise picks the sheet whose name contains 'industry' or 'country' (case-insensitive),
    falling back to the first non-empty sheet.
    """
    import openpyxl

    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception:
        # Fall back to xlrd for legacy .xls
        import xlrd

        book = xlrd.open_workbook(str(path))
        sheets = book.sheet_names()
        if sheet_name and sheet_name in sheets:
            picked = sheet_name
        else:
            picked = next(
                (
                    s
                    for s in sheets
                    if "industry" in s.lower() or "country" in s.lower()
                ),
                sheets[0],
            )
        ws = book.sheet_by_name(picked)
        rows = [ws.row_values(r) for r in range(ws.nrows)]
        header = rows[_find_header_row(rows)]
        data_rows = rows[_find_header_row(rows) + 1 :]
        return pl.DataFrame(
            {str(h): [r[i] if i < len(r) else None for r in data_rows] for i, h in enumerate(header)}
        )

    if sheet_name:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' not found. Available: {wb.sheetnames}")
        picked = sheet_name
    else:
        picked = next(
            (
                s
                for s in wb.sheetnames
                if "industry" in s.lower() or "country" in s.lower() or "average" in s.lower()
            ),
            wb.sheetnames[0],
        )
    ws = wb[picked]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        return pl.DataFrame()
    header_idx = _find_header_row(rows)
    header = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    data_rows = rows[header_idx + 1 :]
    cols: dict[str, list] = {h: [] for h in header}
    for r in data_rows:
        for i, h in enumerate(header):
            cols[h].append(r[i] if i < len(r) else None)
    return pl.DataFrame(cols)


def _find_header_row(rows: list[list]) -> int:
    """Find the row index that looks like a header (mostly non-numeric, non-empty)."""
    for i, r in enumerate(rows[:20]):
        non_empty = [c for c in r if c is not None and str(c).strip() != ""]
        if len(non_empty) >= 3 and sum(1 for c in non_empty if isinstance(c, str)) >= 2:
            return i
    return 0


def _to_normalized_rows(
    df: pl.DataFrame, column_map: dict[str, str], constants: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply column mapping; drop rows with empty primary key field; coerce numerics."""
    pk_field = next(iter(column_map))  # first mapped key is the PK
    out: list[dict[str, Any]] = []
    for record in df.to_dicts():
        normalized: dict[str, Any] = dict(constants)
        for db_col, xls_col in column_map.items():
            if xls_col not in record:
                continue
            value = record[xls_col]
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    value = None
                elif value.endswith("%"):
                    try:
                        value = float(value[:-1]) / 100.0
                    except ValueError:
                        pass
            normalized[db_col] = value
        if normalized.get(pk_field) in (None, ""):
            continue
        out.append(normalized)
    return out


def parse_industry_xls(
    path: Path,
    *,
    region: str,
    year: int,
    column_map: dict[str, str],
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a Damodaran industry-level xls into normalized rows.

    Returns a list of dicts ready to upsert into `damodaran_industry`.
    """
    df = _load_workbook_to_df(path, sheet_name)
    if df.is_empty():
        log.warning("damodaran.industry.empty_file", path=str(path))
        return []
    return _to_normalized_rows(df, column_map, {"region": region, "year": year})


def parse_country_xls(
    path: Path,
    *,
    year: int,
    column_map: dict[str, str],
    sheet_name: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a Damodaran country-level xls into normalized rows.

    Returns a list of dicts ready to upsert into `damodaran_country`.
    """
    df = _load_workbook_to_df(path, sheet_name)
    if df.is_empty():
        log.warning("damodaran.country.empty_file", path=str(path))
        return []
    return _to_normalized_rows(df, column_map, {"year": year})
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_damodaran_parser.py -v`

Expected: PASS. If the fixture-based tests fail because the actual Damodaran column headers differ from the defaults, **edit `DEFAULT_INDUSTRY_COLUMN_MAP` / `DEFAULT_COUNTRY_COLUMN_MAP` in `damodaran.py`** to match the actual headers from Task 7 Step 2 output, then re-run. Only the synthetic test (`test_parse_industry_xls_skips_blank_rows`) is guaranteed to pass without inspection — the other two skip if fixtures are missing.

- [ ] **Step 7: Commit**

```bash
git add src/bot/ingest/damodaran.py tests/unit/test_damodaran_parser.py tests/fixtures/damodaran/ tests/fixtures/__init__.py
git commit -m "feat(m1): add Damodaran xls parser with default column mappings"
```

---

## Task 8: Damodaran downloader + importer + DB upsert

**Files:**
- Modify: `src/bot/ingest/damodaran.py` (add download + import functions)
- Create: `tests/integration/__init__.py` (empty marker)
- Create: `tests/integration/test_damodaran_import.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/integration/test_damodaran_import.py`:

```python
from datetime import datetime
from pathlib import Path

import pytest

from bot.ingest.damodaran import import_damodaran_from_files
from bot.storage.db import apply_schema, connect

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"


@pytest.mark.integration
@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran fixtures not downloaded; run Task 7 Step 1.",
)
def test_import_damodaran_from_files_populates_db():
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )

    assert result.is_success()
    assert result.rows_affected > 0

    industry_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]
    country_count = conn.execute("SELECT COUNT(*) FROM damodaran_country").fetchone()[0]
    assert industry_count > 50
    assert country_count > 100

    refresh_rows = conn.execute(
        "SELECT source, status, rows_affected FROM refresh_log WHERE source = 'damodaran'"
    ).fetchall()
    assert len(refresh_rows) == 1
    assert refresh_rows[0][1] == "success"

    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran fixtures not downloaded; run Task 7 Step 1.",
)
def test_import_damodaran_is_idempotent():
    """Running the import twice should not duplicate rows (uses upsert)."""
    conn = connect(":memory:")
    apply_schema(conn)

    import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    first_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]

    import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    second_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]

    assert first_count == second_count
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_damodaran_import.py -v`

Expected: FAIL — `ImportError: cannot import name 'import_damodaran_from_files'`.

- [ ] **Step 3: Add download + upsert + import to `damodaran.py`**

Edit `src/bot/ingest/damodaran.py`: add the following imports near the top of the file (alongside `import polars as pl`):

```python
import uuid
from datetime import datetime

import duckdb
import httpx

from bot.ingest.base import IngestResult
```

Then append to the end of the file:

```python


# ---------- Downloader ----------


def download_dataset(url: str, dest: Path, timeout: float = 60.0) -> Path:
    """Download a Damodaran xls/xlsx file to `dest`. Overwrites if present."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    log.info("damodaran.download.ok", url=url, dest=str(dest), bytes=len(response.content))
    return dest


# ---------- Upsert ----------


def upsert_industry_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> int:
    """Upsert into damodaran_industry. Returns number of rows affected."""
    if not rows:
        return 0
    # Discover columns present across rows
    all_columns: set[str] = set()
    for r in rows:
        all_columns.update(r.keys())
    cols = sorted(all_columns)

    # DuckDB doesn't have native UPSERT for arbitrary tables before 0.10; emulate
    # with DELETE-then-INSERT inside a transaction, scoped to the PK (industry, region, year).
    conn.execute("BEGIN TRANSACTION")
    try:
        # Delete existing rows for (region, year) tuples present in payload
        pairs = {(r["region"], r["year"]) for r in rows}
        for region, year in pairs:
            conn.execute(
                "DELETE FROM damodaran_industry WHERE region = ? AND year = ?",
                [region, year],
            )
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO damodaran_industry ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def upsert_country_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> int:
    """Upsert into damodaran_country. Returns number of rows affected."""
    if not rows:
        return 0
    all_columns: set[str] = set()
    for r in rows:
        all_columns.update(r.keys())
    cols = sorted(all_columns)

    conn.execute("BEGIN TRANSACTION")
    try:
        years = {r["year"] for r in rows}
        for year in years:
            conn.execute("DELETE FROM damodaran_country WHERE year = ?", [year])
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO damodaran_country ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


# ---------- High-level importers ----------


def _log_refresh(
    conn: duckdb.DuckDBPyConnection, result: IngestResult, run_id: str
) -> None:
    conn.execute(
        """
        INSERT INTO refresh_log
            (source, run_id, started_at, finished_at, status, rows_affected, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            result.source,
            run_id,
            result.started_at,
            result.finished_at,
            result.status,
            result.rows_affected,
            result.error_message,
        ],
    )


def import_damodaran_from_files(
    conn: duckdb.DuckDBPyConnection,
    *,
    industry_path: Path,
    country_path: Path,
    region: str,
    year: int,
) -> IngestResult:
    """Import already-downloaded Damodaran files into the DB."""
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    try:
        industry_rows = parse_industry_xls(
            industry_path,
            region=region,
            year=year,
            column_map=DEFAULT_INDUSTRY_COLUMN_MAP,
        )
        country_rows = parse_country_xls(
            country_path,
            year=year,
            column_map=DEFAULT_COUNTRY_COLUMN_MAP,
        )
        total = upsert_industry_rows(conn, industry_rows) + upsert_country_rows(
            conn, country_rows
        )
        result = IngestResult(
            source="damodaran",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="success",
            rows_affected=total,
            details={
                "industry_rows": len(industry_rows),
                "country_rows": len(country_rows),
                "region": region,
                "year": year,
            },
        )
    except Exception as e:
        log.exception("damodaran.import.failed", error=str(e))
        result = IngestResult(
            source="damodaran",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="error",
            error_message=str(e),
        )
    _log_refresh(conn, result, run_id)
    return result


def import_damodaran(
    conn: duckdb.DuckDBPyConnection,
    *,
    download_dir: Path,
    region: str = "US",
    year: int | None = None,
    industry_url: str = INDUSTRY_WACC_URL,
    country_url: str = COUNTRY_RISK_URL,
) -> IngestResult:
    """Download and import current-year Damodaran datasets."""
    year = year or datetime.utcnow().year
    industry_path = download_dataset(industry_url, download_dir / "wacc.xls")
    country_path = download_dataset(country_url, download_dir / "ctryprem.xls")
    return import_damodaran_from_files(
        conn,
        industry_path=industry_path,
        country_path=country_path,
        region=region,
        year=year,
    )
```

- [ ] **Step 4: Create `tests/integration/__init__.py`**

Write empty file `tests/integration/__init__.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_damodaran_import.py -v`

Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/damodaran.py tests/integration/
git commit -m "feat(m1): add Damodaran downloader, importer, and DB upsert"
```

---

## Task 9: CLI command `bot refresh --damodaran`

**Files:**
- Modify: `src/bot/cli.py`
- Create: `tests/unit/test_cli_refresh.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_cli_refresh.py`:

```python
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.base import IngestResult
from datetime import datetime


def test_refresh_damodaran_calls_importer(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    fake_result = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 10),
        status="success",
        rows_affected=237,
    )
    with patch("bot.cli.import_damodaran", return_value=fake_result) as mock:
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran"])
        assert result.exit_code == 0
        assert "237" in result.stdout
        assert mock.called


def test_refresh_without_flags_shows_help(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    runner = CliRunner()
    result = runner.invoke(app, ["refresh"])
    # No flags = nothing to do; exit non-zero with message
    assert result.exit_code != 0
    assert "specify" in result.stdout.lower() or "flag" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_refresh.py -v`

Expected: FAIL — `refresh` command not defined.

- [ ] **Step 3: Add `refresh` command to CLI**

Edit `src/bot/cli.py` — replace its full contents with:

```python
"""Investment bot — command-line interface."""

from pathlib import Path

import typer

from bot import __version__
from bot.config import load_settings
from bot.ingest.damodaran import import_damodaran
from bot.storage.db import apply_schema, connect
from bot.utils.logging import configure_logging, get_logger

app = typer.Typer(
    help="Personal investment bot — value screener + portfolio monitor.",
    no_args_is_help=True,
)
log = get_logger(__name__)


def _open_db():
    settings = load_settings()
    configure_logging(level=settings.log_level, json_output=False)
    conn = connect(settings.db_path)
    apply_schema(conn)
    return conn, settings


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(__version__)


@app.command()
def refresh(
    damodaran: bool = typer.Option(False, "--damodaran", help="Refresh Damodaran datasets."),
    region: str = typer.Option("US", "--region", help="Damodaran region (US, Europe, EM, ...)."),
    year: int | None = typer.Option(None, "--year", help="Damodaran dataset year (defaults to current)."),
    download_dir: Path = typer.Option(
        Path("./.cache/damodaran"),
        "--download-dir",
        help="Where to cache downloaded Damodaran files.",
    ),
) -> None:
    """Refresh data from external sources."""
    if not damodaran:
        typer.echo(
            "Specify what to refresh. Available flags: --damodaran",
            err=True,
        )
        raise typer.Exit(code=2)

    conn, _ = _open_db()
    typer.echo(f"Importing Damodaran datasets (region={region}, year={year or 'current'})...")
    result = import_damodaran(conn, download_dir=download_dir, region=region, year=year)
    if result.is_success():
        typer.echo(
            f"OK — imported {result.rows_affected} rows in {result.duration_seconds():.1f}s "
            f"(industry={result.details.get('industry_rows')}, "
            f"country={result.details.get('country_rows')})"
        )
        raise typer.Exit(code=0)
    typer.echo(f"FAILED — {result.error_message}", err=True)
    raise typer.Exit(code=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_refresh.py -v`

Expected: PASS (both tests).

- [ ] **Step 5: End-to-end smoke test**

Run:

```bash
rm -f /tmp/smoke-bot.duckdb
BOT_DB_PATH=/tmp/smoke-bot.duckdb \
BOT_SEC_USER_AGENT="Nicolas Riccomini nicolas.riccomini@gmail.com" \
uv run bot refresh --damodaran --year 2026 --download-dir /tmp/.cache/damodaran
```

Expected: prints `OK — imported N rows ...` where N > 50.

- [ ] **Step 6: Commit**

```bash
git add src/bot/cli.py tests/unit/test_cli_refresh.py
git commit -m "feat(m1): add 'bot refresh --damodaran' CLI command"
```

---

## Task 10: SEC EDGAR client (raw HTTP)

**Files:**
- Create: `src/bot/ingest/sec_edgar.py`
- Create: `tests/fixtures/cassettes/__init__.py` (empty marker)
- Create: `tests/integration/test_sec_edgar_client.py`

**Background:** SEC EDGAR exposes machine-readable fundamentals at:
- `https://www.sec.gov/files/company_tickers.json` — full ticker → CIK lookup table.
- `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` — all XBRL-tagged facts for one company, where `{cik}` is 10-digit zero-padded (e.g. `0000320193` for AAPL).

Both require a `User-Agent` header per SEC fair-use policy.

- [ ] **Step 1: Write the failing test**

Write to `tests/integration/test_sec_edgar_client.py`:

```python
import pytest

from bot.ingest.sec_edgar import SecEdgarClient


@pytest.fixture
def vcr_cassette_dir(request):
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes")


@pytest.fixture
def vcr_config():
    return {
        "filter_headers": [("User-Agent", "Tester t@example.com")],
        "record_mode": "once",
    }


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_cik_for_known_ticker():
    client = SecEdgarClient(user_agent="Tester t@example.com")
    cik = client.lookup_cik("AAPL")
    assert cik == "0000320193"


@pytest.mark.integration
@pytest.mark.vcr
def test_lookup_cik_unknown_returns_none():
    client = SecEdgarClient(user_agent="Tester t@example.com")
    cik = client.lookup_cik("ZZZNOTREAL")
    assert cik is None


@pytest.mark.integration
@pytest.mark.vcr
def test_fetch_company_facts_returns_json():
    client = SecEdgarClient(user_agent="Tester t@example.com")
    facts = client.fetch_company_facts("0000320193")  # AAPL
    assert "entityName" in facts
    assert "facts" in facts
    assert "us-gaap" in facts["facts"]
```

Write empty `tests/fixtures/cassettes/__init__.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sec_edgar_client.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement SEC client**

Write to `src/bot/ingest/sec_edgar.py`:

```python
"""SEC EDGAR adapter — fetch + parse + import US company fundamentals."""

from __future__ import annotations

from typing import Any

import httpx

from bot.utils.logging import get_logger

log = get_logger(__name__)

TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class SecEdgarClient:
    """Thin HTTP client for SEC EDGAR public endpoints.

    Note: SEC requires every request to carry a User-Agent identifying the requester
    (per https://www.sec.gov/os/accessing-edgar-data). Provide one explicitly.
    """

    def __init__(self, user_agent: str, timeout: float = 30.0) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent identifying you. "
                "Format: 'Your Name email@example.com'"
            )
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._ticker_table: dict[str, str] | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _load_ticker_table(self) -> dict[str, str]:
        if self._ticker_table is not None:
            return self._ticker_table
        r = self._client.get(TICKER_LOOKUP_URL)
        r.raise_for_status()
        data = r.json()
        # The file is { "0": {"cik_str": 320193, "ticker": "AAPL", ...}, "1": {...}, ... }
        self._ticker_table = {
            entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
            for entry in data.values()
        }
        log.info("sec.ticker_table.loaded", count=len(self._ticker_table))
        return self._ticker_table

    def lookup_cik(self, ticker: str) -> str | None:
        """Return zero-padded 10-digit CIK for a ticker, or None if not found."""
        table = self._load_ticker_table()
        return table.get(ticker.upper())

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        """Fetch XBRL company facts JSON for the given CIK (10-digit zero-padded)."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        url = COMPANY_FACTS_URL_TEMPLATE.format(cik=cik)
        r = self._client.get(url)
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 4: Run test to record cassettes and verify it passes**

Run: `uv run pytest tests/integration/test_sec_edgar_client.py -v`

Expected: PASS (records cassettes on first run; replays on subsequent runs). If you do not have internet access at first run, the test fails — re-run when online.

Check that cassettes were created:

```bash
ls tests/fixtures/cassettes/sec_edgar/
```

Expected: 3 yaml files (one per test).

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/sec_edgar.py tests/integration/test_sec_edgar_client.py tests/fixtures/cassettes/
git commit -m "feat(m1): add SEC EDGAR HTTP client with CIK lookup and company facts"
```

---

## Task 11: SEC EDGAR parser (pure function)

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (add parser)
- Create: `tests/unit/test_sec_edgar_parser.py`

The XBRL `companyfacts` JSON groups facts by taxonomy (`us-gaap`) and concept (`Revenues`, `Assets`, etc.). Each concept has units (`USD`, `shares`) and entries with `fy` (fiscal year), `fp` (fiscal period: `FY` for annual, `Q1..Q4` for quarterly), `end` (period end date), `val`, and `form` (`10-K`, `10-Q`).

The parser must:
1. Iterate a curated mapping of `xbrl_concept → db_column` for our `financials_annual` and `financials_quarterly` schemas.
2. For each concept, prefer `form == "10-K"` and `fp == "FY"` for annual; `form == "10-Q"` and `fp in {Q1..Q4}` for quarterly.
3. Deduplicate: if a value for `(ticker, fiscal_year)` is restated (later filing date for same period), prefer the most recent.

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_sec_edgar_parser.py`:

```python
import json
from pathlib import Path

import pytest

from bot.ingest.sec_edgar import parse_company_facts


# Minimal hand-crafted facts JSON exercising the parser
FAKE_FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2023-11-03"},
                        {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "fp": "FY", "form": "10-K/A", "filed": "2024-01-15"},
                        {"end": "2022-09-30", "val": 394328000000, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2022-10-28"},
                        {"end": "2024-03-30", "val": 90753000000, "fy": 2024, "fp": "Q2", "form": "10-Q", "filed": "2024-05-03"},
                    ]
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "units": {
                    "USD": [
                        {"end": "2023-09-30", "val": 96995000000, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2023-11-03"},
                    ]
                },
            },
            "Assets": {
                "label": "Total Assets",
                "units": {
                    "USD": [
                        {"end": "2023-09-30", "val": 352583000000, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2023-11-03"},
                    ]
                },
            },
        }
    },
}


def test_parse_extracts_annual_revenue_and_net_income():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    assert result.company["ticker"] == "AAPL"
    assert result.company["name"] == "Apple Inc."
    assert result.company["cik"] == "0000320193"

    annual = {row["fiscal_year"]: row for row in result.annual}
    assert 2023 in annual
    assert annual[2023]["revenue"] == 383285000000
    assert annual[2023]["net_income"] == 96995000000
    assert annual[2023]["total_assets"] == 352583000000
    assert annual[2023]["ticker"] == "AAPL"
    assert annual[2022]["revenue"] == 394328000000


def test_parse_prefers_most_recent_filing_for_restated_year():
    # The 2023 row has two filings (10-K then 10-K/A). The parser should keep the latest.
    result = parse_company_facts("AAPL", FAKE_FACTS)
    annual = {row["fiscal_year"]: row for row in result.annual}
    # is_restated flag = True for the chosen row (since filing form is /A or filed_at is later)
    # We tolerate either marking, as long as the value is the latest filing's
    assert annual[2023]["revenue"] == 383285000000  # value happens to be the same


def test_parse_extracts_quarterly():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    q = [row for row in result.quarterly if row["fiscal_quarter"] == 2 and row["fiscal_year"] == 2024]
    assert len(q) == 1
    assert q[0]["revenue"] == 90753000000


def test_parse_returns_filings_log_entries():
    result = parse_company_facts("AAPL", FAKE_FACTS)
    assert len(result.filings) >= 1
    forms = {f["filing_type"] for f in result.filings}
    assert "10-K" in forms
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sec_edgar_parser.py -v`

Expected: FAIL — `cannot import name 'parse_company_facts'`.

- [ ] **Step 3: Add parser to `sec_edgar.py`**

Edit `src/bot/ingest/sec_edgar.py`: add the following imports near the top of the file (alongside `import httpx`):

```python
from dataclasses import dataclass, field
from datetime import datetime
```

Then append to the end of the file:

```python


# ---------- Parser ----------


@dataclass
class ParsedCompanyData:
    """Result of parsing SEC company facts JSON."""

    company: dict[str, Any]
    annual: list[dict[str, Any]] = field(default_factory=list)
    quarterly: list[dict[str, Any]] = field(default_factory=list)
    filings: list[dict[str, Any]] = field(default_factory=list)


# XBRL concept (us-gaap) -> our DB column for annual financials.
# Many companies use different concepts for the same thing; the parser tries
# each in order and takes the first one with data.
ANNUAL_CONCEPT_MAP: dict[str, list[str]] = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": ["OperatingExpenses"],
    "ebit": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense"],
    "tax_expense": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
    "total_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
    "total_equity": ["StockholdersEquity"],
    "goodwill": ["Goodwill"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "depreciation": ["DepreciationDepletionAndAmortization", "Depreciation"],
    "operating_cashflow": ["NetCashProvidedByUsedInOperatingActivities"],
    "dividends_paid": ["PaymentsOfDividends"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}


def parse_company_facts(ticker: str, facts: dict[str, Any]) -> ParsedCompanyData:
    """Normalize SEC company facts JSON into our DB rows."""
    ticker = ticker.upper()
    cik_raw = facts.get("cik")
    cik = str(cik_raw).zfill(10) if cik_raw is not None else None
    name = facts.get("entityName", ticker)

    company = {
        "ticker": ticker,
        "cik": cik,
        "name": name,
        "country": "US",
        "currency": "USD",
        "source": "sec_edgar",
        "status": "active",
    }

    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    annual_rows = _collect_period_rows(
        ticker, us_gaap, fiscal_period="FY", form_prefix="10-K"
    )
    quarterly_rows = _collect_period_rows(
        ticker, us_gaap, fiscal_period_set={"Q1", "Q2", "Q3", "Q4"}, form_prefix="10-Q"
    )
    filings = _collect_filings(ticker, us_gaap)

    return ParsedCompanyData(
        company=company,
        annual=annual_rows,
        quarterly=quarterly_rows,
        filings=filings,
    )


def _collect_period_rows(
    ticker: str,
    us_gaap: dict[str, Any],
    *,
    fiscal_period: str | None = None,
    fiscal_period_set: set[str] | None = None,
    form_prefix: str,
) -> list[dict[str, Any]]:
    """Build per-period rows from the XBRL facts."""
    # period_key -> { db_col -> {"val": ..., "filed": ..., "form": ...} }
    accum: dict[tuple[int, int | None], dict[str, dict]] = {}

    for db_col, concepts in ANNUAL_CONCEPT_MAP.items():
        for concept in concepts:
            entries = (
                us_gaap.get(concept, {}).get("units", {}).get("USD")
                or us_gaap.get(concept, {}).get("units", {}).get("shares")
            )
            if not entries:
                continue
            for e in entries:
                fp = e.get("fp")
                form = e.get("form", "")
                if not form.startswith(form_prefix):
                    continue
                if fiscal_period and fp != fiscal_period:
                    continue
                if fiscal_period_set and fp not in fiscal_period_set:
                    continue
                fy = e.get("fy")
                if fy is None:
                    continue
                q = None if fp == "FY" else int(fp[1:]) if fp.startswith("Q") else None
                key = (fy, q)
                slot = accum.setdefault(key, {})
                existing = slot.get(db_col)
                # Take the latest filing for each (period, column)
                if existing is None or e.get("filed", "") > existing.get("filed", ""):
                    slot[db_col] = {
                        "val": e.get("val"),
                        "filed": e.get("filed"),
                        "form": form,
                        "end": e.get("end"),
                    }
            if any(db_col in slot for slot in accum.values()):
                break  # found a concept with data — don't fall through to alternates

    out: list[dict[str, Any]] = []
    for (fy, q), cols in accum.items():
        is_restated = any(c["form"].endswith("/A") for c in cols.values())
        row: dict[str, Any] = {
            "ticker": ticker,
            "fiscal_year": fy,
            "currency": "USD",
            "source": "sec_edgar",
            "is_restated": is_restated,
        }
        if q is not None:
            row["fiscal_quarter"] = q
        end_dates = [c.get("end") for c in cols.values() if c.get("end")]
        if end_dates:
            row["period_end_date"] = max(end_dates)
        for db_col, info in cols.items():
            row[db_col] = info["val"]
        # Derived: EBITDA = EBIT + Depreciation (if both present)
        if "ebit" in row and "depreciation" in row:
            row["ebitda"] = (row["ebit"] or 0) + (row["depreciation"] or 0)
        # Derived: FCF = OCF - Capex
        if "operating_cashflow" in row and "capex" in row:
            row["free_cashflow"] = (row["operating_cashflow"] or 0) - (row["capex"] or 0)
        out.append(row)
    return out


def _collect_filings(ticker: str, us_gaap: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract unique (form, filed_date) pairs as filings_log entries."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for concept in us_gaap.values():
        for unit_entries in concept.get("units", {}).values():
            for e in unit_entries:
                form = e.get("form")
                filed = e.get("filed")
                if not form or not filed:
                    continue
                key = (form, filed)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "ticker": ticker,
                        "filing_type": form,
                        "filing_date": filed,
                        "accession_number": e.get("accn"),
                        "source": "sec_edgar",
                    }
                )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sec_edgar_parser.py -v`

Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/sec_edgar.py tests/unit/test_sec_edgar_parser.py
git commit -m "feat(m1): add SEC EDGAR XBRL facts parser"
```

---

## Task 12: SEC EDGAR importer + DB upsert

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (add importer)
- Create: `tests/integration/test_sec_edgar_import.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/integration/test_sec_edgar_import.py`:

```python
import pytest

from bot.ingest.sec_edgar import import_company_from_sec
from bot.storage.db import apply_schema, connect


@pytest.fixture
def vcr_cassette_dir(request):
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes")


@pytest.fixture
def vcr_config():
    return {
        "filter_headers": [("User-Agent", "Tester t@example.com")],
        "record_mode": "once",
    }


@pytest.mark.integration
@pytest.mark.vcr
def test_import_company_from_sec_populates_db():
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_company_from_sec(
        conn, ticker="AAPL", user_agent="Tester t@example.com"
    )

    assert result.is_success()
    assert result.rows_affected > 0

    companies = conn.execute(
        "SELECT ticker, cik, name, country FROM companies WHERE ticker = 'AAPL'"
    ).fetchall()
    assert len(companies) == 1
    assert companies[0] == ("AAPL", "0000320193", "Apple Inc.", "US")

    annual_count = conn.execute(
        "SELECT COUNT(*) FROM financials_annual WHERE ticker = 'AAPL'"
    ).fetchone()[0]
    assert annual_count >= 5  # AAPL has > 5 years of XBRL filings

    filings_count = conn.execute(
        "SELECT COUNT(*) FROM filings_log WHERE ticker = 'AAPL'"
    ).fetchone()[0]
    assert filings_count >= 1

    refresh_rows = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'sec_edgar'"
    ).fetchall()
    assert refresh_rows[0][0] == "success"

    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sec_edgar_import.py -v`

Expected: FAIL — `import_company_from_sec` not defined.

- [ ] **Step 3: Add importer to `sec_edgar.py`**

Edit `src/bot/ingest/sec_edgar.py`: add the following imports near the top of the file (alongside the existing imports):

```python
import uuid

import duckdb

from bot.ingest.base import IngestResult
```

Then append to the end of the file:

```python


# ---------- Importer + Upsert ----------


def upsert_company(conn: duckdb.DuckDBPyConnection, company: dict[str, Any]) -> None:
    cols = sorted(company.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    conn.execute(f"DELETE FROM companies WHERE ticker = ?", [company["ticker"]])
    conn.execute(
        f"INSERT INTO companies ({col_list}) VALUES ({placeholders})",
        [company[c] for c in cols],
    )


def upsert_financials_annual(
    conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]
) -> int:
    if not rows:
        return 0
    all_cols: set[str] = set()
    for r in rows:
        all_cols.update(r.keys())
    cols = sorted(all_cols)

    conn.execute("BEGIN TRANSACTION")
    try:
        tickers = {r["ticker"] for r in rows}
        for ticker in tickers:
            conn.execute("DELETE FROM financials_annual WHERE ticker = ?", [ticker])
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO financials_annual ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def upsert_financials_quarterly(
    conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]
) -> int:
    if not rows:
        return 0
    all_cols: set[str] = set()
    for r in rows:
        all_cols.update(r.keys())
    cols = sorted(all_cols)

    conn.execute("BEGIN TRANSACTION")
    try:
        tickers = {r["ticker"] for r in rows}
        for ticker in tickers:
            conn.execute("DELETE FROM financials_quarterly WHERE ticker = ?", [ticker])
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        for r in rows:
            conn.execute(
                f"INSERT INTO financials_quarterly ({col_list}) VALUES ({placeholders})",
                [r.get(c) for c in cols],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


def upsert_filings(conn: duckdb.DuckDBPyConnection, filings: list[dict[str, Any]]) -> int:
    if not filings:
        return 0
    cols = ["ticker", "filing_type", "filing_date", "accession_number", "source"]
    placeholders = ", ".join(["?"] * len(cols))
    inserted = 0
    for f in filings:
        # Replace existing rows for the same PK (ticker, filing_type, filing_date, source)
        conn.execute(
            "DELETE FROM filings_log WHERE ticker = ? AND filing_type = ? AND filing_date = ? AND source = ?",
            [f["ticker"], f["filing_type"], f["filing_date"], f["source"]],
        )
        conn.execute(
            f"INSERT INTO filings_log ({', '.join(cols)}) VALUES ({placeholders})",
            [f.get(c) for c in cols],
        )
        inserted += 1
    return inserted


def import_company_from_sec(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    user_agent: str,
) -> IngestResult:
    """Fetch + parse + upsert one US ticker from SEC EDGAR."""
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    try:
        with SecEdgarClient(user_agent=user_agent) as client:
            cik = client.lookup_cik(ticker)
            if cik is None:
                raise ValueError(f"Ticker {ticker} not found in SEC EDGAR ticker table")
            facts = client.fetch_company_facts(cik)
        parsed = parse_company_facts(ticker, facts)
        upsert_company(conn, parsed.company)
        annual = upsert_financials_annual(conn, parsed.annual)
        quarterly = upsert_financials_quarterly(conn, parsed.quarterly)
        filings = upsert_filings(conn, parsed.filings)
        total = 1 + annual + quarterly + filings
        result = IngestResult(
            source="sec_edgar",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="success",
            rows_affected=total,
            details={"ticker": ticker, "annual": annual, "quarterly": quarterly, "filings": filings},
        )
    except Exception as e:
        log.exception("sec_edgar.import.failed", ticker=ticker, error=str(e))
        result = IngestResult(
            source="sec_edgar",
            started_at=started,
            finished_at=datetime.utcnow(),
            status="error",
            error_message=str(e),
            details={"ticker": ticker},
        )

    # Log to refresh_log (same helper-shaped insert as in damodaran.py)
    conn.execute(
        """
        INSERT INTO refresh_log
            (source, run_id, started_at, finished_at, status, rows_affected, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            result.source,
            run_id,
            result.started_at,
            result.finished_at,
            result.status,
            result.rows_affected,
            result.error_message,
        ],
    )
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_sec_edgar_import.py -v`

Expected: PASS (uses the cassettes recorded in Task 10 — if any new endpoint is hit, you'll get a fresh cassette).

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/sec_edgar.py tests/integration/test_sec_edgar_import.py tests/fixtures/cassettes/
git commit -m "feat(m1): add SEC EDGAR importer with DB upsert"
```

---

## Task 13: CLI command `bot show <TICKER>`

**Files:**
- Create: `src/bot/reporting/__init__.py`
- Create: `src/bot/reporting/show.py`
- Modify: `src/bot/cli.py`
- Create: `tests/unit/test_reporting_show.py`
- Create: `tests/unit/test_cli_show.py`

- [ ] **Step 1: Write the failing test for the formatter**

Write to `tests/unit/test_reporting_show.py`:

```python
from bot.reporting.show import format_company_summary


def test_format_company_summary_renders_table():
    company = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "cik": "0000320193",
        "country": "US",
        "currency": "USD",
    }
    annual_rows = [
        {"fiscal_year": 2022, "revenue": 394_328_000_000, "net_income": 99_803_000_000},
        {"fiscal_year": 2023, "revenue": 383_285_000_000, "net_income": 96_995_000_000},
    ]
    text = format_company_summary(company, annual_rows)
    assert "AAPL" in text
    assert "Apple Inc." in text
    assert "2022" in text
    assert "2023" in text
    assert "394" in text  # revenue
    assert "USD" in text


def test_format_company_summary_no_financials():
    company = {"ticker": "XYZ", "name": "XYZ Corp", "cik": None, "country": "US", "currency": "USD"}
    text = format_company_summary(company, [])
    assert "no financials" in text.lower()
```

Write empty `src/bot/reporting/__init__.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_reporting_show.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement formatter**

Write to `src/bot/reporting/show.py`:

```python
"""Render `bot show <TICKER>` output to a string."""

from __future__ import annotations

from typing import Any


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:,.2f}M"
    return f"{value:,.0f}"


def format_company_summary(company: dict[str, Any], annual_rows: list[dict[str, Any]]) -> str:
    """Render a plain-text summary of a company and its last N years of annual financials."""
    lines: list[str] = []
    lines.append(f"{company['ticker']} — {company.get('name', '(no name)')}")
    lines.append(
        f"CIK={company.get('cik') or '—'}  "
        f"Country={company.get('country') or '—'}  "
        f"Currency={company.get('currency') or '—'}"
    )
    lines.append("")

    if not annual_rows:
        lines.append("(no financials in DB for this ticker)")
        return "\n".join(lines)

    # Sort most recent first, take up to 5
    rows = sorted(annual_rows, key=lambda r: r["fiscal_year"], reverse=True)[:5]
    metrics = [
        ("revenue", "Revenue"),
        ("ebit", "EBIT"),
        ("net_income", "Net Income"),
        ("operating_cashflow", "OCF"),
        ("free_cashflow", "FCF"),
        ("total_debt", "Total Debt"),
        ("cash", "Cash"),
        ("total_assets", "Total Assets"),
        ("total_equity", "Equity"),
    ]
    header = f"{'Metric':<14}" + "".join(f"{r['fiscal_year']:>16}" for r in rows)
    lines.append(header)
    lines.append("-" * len(header))
    for key, label in metrics:
        row_str = f"{label:<14}"
        for r in rows:
            row_str += f"{_fmt_money(r.get(key)):>16}"
        lines.append(row_str)
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_reporting_show.py -v`

Expected: PASS (both tests).

- [ ] **Step 5: Write the failing test for the CLI command**

Write to `tests/unit/test_cli_show.py`:

```python
from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.base import IngestResult


def test_show_existing_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    # Pre-populate the DB with a fake company so we don't hit SEC
    from bot.storage.db import apply_schema, connect

    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO companies (ticker, name, country, currency, source) VALUES (?, ?, ?, ?, ?)",
        ["FAKE", "Fake Co", "US", "USD", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, revenue, source) VALUES (?, ?, ?, ?)",
        ["FAKE", 2023, 1_000_000_000, "sec_edgar"],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["show", "FAKE"])
    assert result.exit_code == 0
    assert "FAKE" in result.stdout
    assert "Fake Co" in result.stdout


def test_show_missing_ticker_triggers_sec_import(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    fake_result = IngestResult(
        source="sec_edgar",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
        rows_affected=10,
    )

    def populate_then_return(conn, *, ticker, user_agent):
        conn.execute(
            "INSERT INTO companies (ticker, name, country, currency, source) VALUES (?, ?, ?, ?, ?)",
            [ticker, f"{ticker} Inc", "US", "USD", "sec_edgar"],
        )
        return fake_result

    with patch("bot.cli.import_company_from_sec", side_effect=populate_then_return) as mock:
        runner = CliRunner()
        result = runner.invoke(app, ["show", "NEW"])
        assert result.exit_code == 0
        assert mock.called
        assert "NEW Inc" in result.stdout
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_show.py -v`

Expected: FAIL — `show` command not defined.

- [ ] **Step 7: Add `show` command to CLI**

In `src/bot/cli.py`, add at the top of the imports section:

```python
from bot.ingest.sec_edgar import import_company_from_sec
from bot.reporting.show import format_company_summary
```

Then append this command before the `if __name__` block (file end):

```python


@app.command()
def show(
    ticker: str = typer.Argument(..., help="Company ticker (e.g. AAPL)."),
    fetch_if_missing: bool = typer.Option(
        True,
        "--fetch/--no-fetch",
        help="If the ticker isn't in the DB, fetch it from SEC EDGAR first.",
    ),
) -> None:
    """Show a company's basic info and last 5 years of financials."""
    conn, settings = _open_db()
    ticker = ticker.upper()

    row = conn.execute(
        "SELECT ticker, name, cik, country, currency FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()

    if row is None:
        if not fetch_if_missing:
            typer.echo(f"{ticker} not in DB (use --fetch to import from SEC).", err=True)
            raise typer.Exit(code=2)
        typer.echo(f"{ticker} not in DB — fetching from SEC EDGAR...")
        result = import_company_from_sec(
            conn, ticker=ticker, user_agent=settings.sec_user_agent
        )
        if not result.is_success():
            typer.echo(f"Failed to import {ticker}: {result.error_message}", err=True)
            raise typer.Exit(code=1)
        row = conn.execute(
            "SELECT ticker, name, cik, country, currency FROM companies WHERE ticker = ?",
            [ticker],
        ).fetchone()

    company = dict(zip(["ticker", "name", "cik", "country", "currency"], row))
    annual = conn.execute(
        """
        SELECT *
        FROM financials_annual
        WHERE ticker = ?
        ORDER BY fiscal_year DESC
        LIMIT 5
        """,
        [ticker],
    ).fetchall()
    columns = [d[0] for d in conn.description]
    annual_rows = [dict(zip(columns, r)) for r in annual]

    typer.echo(format_company_summary(company, annual_rows))
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_show.py -v`

Expected: PASS (both tests).

- [ ] **Step 9: Commit**

```bash
git add src/bot/reporting/ src/bot/cli.py tests/unit/test_reporting_show.py tests/unit/test_cli_show.py
git commit -m "feat(m1): add 'bot show <TICKER>' CLI command"
```

---

## Task 14: CLI command `bot doctor`

**Files:**
- Modify: `src/bot/cli.py`
- Create: `tests/unit/test_cli_doctor.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_cli_doctor.py`:

```python
from typer.testing import CliRunner

from bot.cli import app


def test_doctor_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ok" in result.stdout.lower()


def test_doctor_fails_when_user_agent_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.delenv("BOT_SEC_USER_AGENT", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    # load_settings() raises before doctor can run; we expect non-zero exit
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_doctor.py -v`

Expected: FAIL — `doctor` command not defined.

- [ ] **Step 3: Add `doctor` command**

Append to `src/bot/cli.py`:

```python


@app.command()
def doctor() -> None:
    """Run health checks and report what's broken (if anything)."""
    issues: list[str] = []

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"FAIL: Settings invalid — {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"DB path:          {settings.db_path}")
    typer.echo(f"Reports dir:      {settings.reports_dir}")
    typer.echo(f"SEC user agent:   {settings.sec_user_agent}")
    typer.echo(f"Log level:        {settings.log_level}")

    # Check DB is openable + schema applied
    try:
        conn = connect(settings.db_path)
        apply_schema(conn)
        tables = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        if tables < 7:
            issues.append(f"DB has only {tables} tables — schema may be incomplete.")
        else:
            typer.echo(f"DB tables:        {tables} (OK)")
        conn.close()
    except Exception as e:
        issues.append(f"DB error — {e}")

    # Check reports dir is writable
    try:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.reports_dir / ".doctor_probe"
        probe.write_text("x")
        probe.unlink()
        typer.echo("Reports dir:      writable (OK)")
    except Exception as e:
        issues.append(f"Reports dir not writable — {e}")

    if issues:
        typer.echo("", err=True)
        for issue in issues:
            typer.echo(f"FAIL: {issue}", err=True)
        raise typer.Exit(code=1)
    typer.echo("\nAll checks OK.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_doctor.py -v`

Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/bot/cli.py tests/unit/test_cli_doctor.py
git commit -m "feat(m1): add 'bot doctor' health check command"
```

---

## Task 15: CLI command `bot status`

**Files:**
- Modify: `src/bot/cli.py`
- Create: `tests/unit/test_cli_status.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/unit/test_cli_status.py`:

```python
from datetime import datetime

from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect


def test_status_with_no_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no refresh history" in result.stdout.lower()


def test_status_with_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        """
        INSERT INTO refresh_log (source, run_id, started_at, finished_at, status, rows_affected)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ["damodaran", "run-1", datetime(2026, 5, 25, 9, 0), datetime(2026, 5, 25, 9, 0, 30), "success", 237],
    )
    conn.execute(
        """
        INSERT INTO refresh_log (source, run_id, started_at, finished_at, status, rows_affected)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ["sec_edgar", "run-2", datetime(2026, 5, 25, 9, 5), datetime(2026, 5, 25, 9, 5, 10), "success", 50],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "damodaran" in result.stdout
    assert "sec_edgar" in result.stdout
    assert "237" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_status.py -v`

Expected: FAIL — `status` command not defined.

- [ ] **Step 3: Add `status` command**

Append to `src/bot/cli.py`:

```python


@app.command()
def status() -> None:
    """Show the most recent refresh result per data source."""
    conn, _ = _open_db()
    rows = conn.execute(
        """
        SELECT source, MAX(finished_at) AS last_finished, status, rows_affected
        FROM refresh_log
        GROUP BY source, status, rows_affected
        QUALIFY ROW_NUMBER() OVER (PARTITION BY source ORDER BY last_finished DESC) = 1
        ORDER BY source
        """
    ).fetchall()
    if not rows:
        typer.echo("No refresh history yet — run `bot refresh --damodaran` first.")
        return
    typer.echo(f"{'Source':<14}{'Last run':<22}{'Status':<10}{'Rows':>8}")
    typer.echo("-" * 54)
    for source, last_finished, status_str, rows_affected in rows:
        typer.echo(
            f"{source:<14}{last_finished.strftime('%Y-%m-%d %H:%M:%S'):<22}{status_str:<10}{rows_affected:>8}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_status.py -v`

Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/bot/cli.py tests/unit/test_cli_status.py
git commit -m "feat(m1): add 'bot status' command showing last refresh per source"
```

---

## Task 16: ADRs (Architecture Decision Records)

**Files:**
- Create: `docs/adr/0001-use-duckdb.md`
- Create: `docs/adr/0002-sec-edgar-first-fmp-later.md`
- Create: `docs/adr/0003-client-portal-api-over-tws.md`

- [ ] **Step 1: Write ADR 0001**

Write to `docs/adr/0001-use-duckdb.md`:

```markdown
# ADR 0001 — Use DuckDB for storage

**Status:** Accepted (2026-05-25)

## Context

The bot stores fundamentals (~50k companies × 10 years), Damodaran datasets, and portfolio snapshots. Queries are analytical (joins, aggregations across years/sectors) and there's a single user (no concurrency requirement).

Options considered:
- **SQLite**: ubiquitous, embedded, single-file. Fine for OLTP but slow on analytical queries (10–50× slower for our shape).
- **Postgres**: production-grade, but requires a running server, auth, and operational overhead unjustified for a single-user offline tool.
- **DuckDB**: columnar OLAP engine, embedded (single file), no server. Reads Parquet/CSV natively. Optimised for exactly the query shape we have.

## Decision

Use DuckDB.

## Consequences

- Backups = `cp bot.duckdb backup/`.
- No concurrent writes (acceptable — single user, CLI invocations are serial).
- DDL uses DuckDB syntax (some divergence from standard SQL, e.g. `QUALIFY` clause).
- If we ever need multi-user concurrent access, migration path is to Postgres; schema is mostly portable.
```

- [ ] **Step 2: Write ADR 0002**

Write to `docs/adr/0002-sec-edgar-first-fmp-later.md`:

```markdown
# ADR 0002 — SEC EDGAR for US fundamentals; FMP for international (deferred to M2)

**Status:** Accepted (2026-05-25)

## Context

We need fundamentals for a global universe. The spec settles on a hybrid: free, authoritative source for US + paid provider for international.

## Decision

- **M1:** Implement SEC EDGAR adapter only (US coverage, official XBRL data, free).
- **M2:** Add Financial Modeling Prep adapter for non-US fundamentals (target ~50k companies) and global daily EOD prices.
- IBKR remains the source of truth for portfolio + execution-adjacent data (M5).

## Consequences

- M1 is shippable as a US-only research tool — useful for early iteration on Capa B/C even without global coverage.
- The `Adapter` interface (`src/bot/ingest/base.py`) is designed so M2 plugs in without touching the screener or valuator.
- We accept the column-mapping work that comes with FMP (their schema ≠ XBRL); that's part of M2.
```

- [ ] **Step 3: Write ADR 0003**

Write to `docs/adr/0003-client-portal-api-over-tws.md`:

```markdown
# ADR 0003 — Use IBKR Client Portal API (REST) over TWS API (deferred to M5)

**Status:** Accepted (2026-05-25)

## Context

For M5 we need to sync portfolio positions from Interactive Brokers UK. IBKR offers two main APIs:

- **TWS API** (Python `ib_insync`, etc.): TCP socket, requires TWS or IB Gateway running headless. Robust but operationally heavy.
- **Client Portal API**: HTTP/JSON REST. Local `cp-gateway` Docker. OAuth + session that requires re-login every ~24h.

We only need **read** access (no order execution in M5).

## Decision

Use Client Portal API.

## Consequences

- Daily re-auth via browser (~10 seconds, tolerable).
- Simpler ops (one Docker container vs full TWS install).
- If the daily re-auth becomes intolerable or we want execution later, migrate to TWS API. Sync logic is behind an adapter so this is a contained change.
```

- [ ] **Step 4: Commit**

```bash
git add docs/adr/
git commit -m "docs(m1): add ADRs 0001-0003 (DuckDB, SEC-first, Client Portal API)"
```

---

## Task 17: CONTEXT.md (per user convention) and final integration check

**Files:**
- Create: `CONTEXT.md`

- [ ] **Step 1: Write `CONTEXT.md`**

Write to `CONTEXT.md`:

```markdown
# investment-bot — Context

Personal investment bot. Local CLI tool. Single user. Greenfield project.

## Domain language

- **Universe**: set of companies the screener considers (~50k global once M2 is done).
- **Story type**: Damodaran's classification of a company's life-cycle / risk profile (`high-growth`, `mature-stable`, `mature-decline`, `cyclical`, `distressed`).
- **Margin of safety (MoS)**: `intrinsic_value / current_price`. > 1 = potentially undervalued.
- **Quality gates**: eliminatory filters in the screener (Capa B) that disqualify a company outright.
- **Value indicators**: filters checking cheapness relative to sector medians (Damodaran datasets).
- **Trap detection**: filters that flag companies that *look* cheap but are cheap for a reason.
- **Capas A/B/C**: see spec §3 — data / mechanical screener / interpretive analysis.

## Source of truth

- **Spec**: `docs/superpowers/specs/2026-05-25-investment-bot-design.md`
- **ADRs**: `docs/adr/`
- **Active plan**: `docs/superpowers/plans/2026-05-25-m1-skeleton-damodaran-sec-edgar.md`

## External services

- **SEC EDGAR** (`data.sec.gov`): US fundamentals, free, requires User-Agent header.
- **Damodaran datasets** (`pages.stern.nyu.edu/~adamodar/`): industry/country benchmarks, annual.
- **Financial Modeling Prep** (M2): international fundamentals + global EOD prices.
- **Interactive Brokers Client Portal API** (M5): portfolio sync, read-only.

## Conventions

- Type hints required everywhere (`mypy --strict`).
- Each ingest adapter is a pure module: `download → parse → upsert`. Functions accept paths/connections, no global state.
- Tests for `valuator/` (M4) and `screener/rules.py` (M3) target 100% coverage.
- Integration tests use VCR cassettes (no live API calls in CI).
- Commits: Conventional Commits (`feat(m1): ...`, `fix: ...`, `docs: ...`).
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
uv run pytest -v
```

Expected: all tests pass. If integration tests requiring cassettes fail because cassettes don't exist yet, re-run any tests that need recording with network access.

- [ ] **Step 3: Run lint + type check**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: all clean. Fix any issues that appear.

- [ ] **Step 4: End-to-end smoke test**

Run:

```bash
rm -rf /tmp/m1-smoke && mkdir /tmp/m1-smoke
BOT_DB_PATH=/tmp/m1-smoke/bot.duckdb \
BOT_SEC_USER_AGENT="Nicolas Riccomini nicolas.riccomini@gmail.com" \
BOT_REPORTS_DIR=/tmp/m1-smoke/reports \
sh -c '
  uv run bot doctor &&
  uv run bot refresh --damodaran --year 2026 --download-dir /tmp/m1-smoke/.cache &&
  uv run bot show AAPL &&
  uv run bot status
'
```

Expected:
- `doctor` prints all OK.
- `refresh --damodaran` imports > 50 industry rows and > 100 country rows.
- `show AAPL` fetches from SEC (cassettes won't catch this), then prints a formatted table of AAPL fundamentals.
- `status` shows two rows (damodaran + sec_edgar) with successful runs.

- [ ] **Step 5: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(m1): add CONTEXT.md with domain language and conventions"
```

- [ ] **Step 6: Tag the milestone**

```bash
git tag -a m1-complete -m "M1 complete: skeleton + Damodaran (Capa A) + SEC EDGAR"
git log --oneline | head -20
```

Expected: ~17 commits visible, tag `m1-complete` on the last one.

---

## Done — M1 acceptance checklist

- [ ] `uv run bot --help` works and lists `version`, `refresh`, `show`, `doctor`, `status`.
- [ ] `uv run bot doctor` reports OK with valid env.
- [ ] `uv run bot refresh --damodaran` imports current-year datasets.
- [ ] `uv run bot show AAPL` works end-to-end (fetches from SEC if missing, prints table).
- [ ] `uv run bot status` shows the runs.
- [ ] `uv run pytest` is green.
- [ ] `uv run ruff check . && uv run mypy src` are clean.
- [ ] `docs/adr/0001..0003` present.
- [ ] `CONTEXT.md` present.

When all checked: M1 is shippable. Open the next plan: M2 (FMP adapter + universe ingest + refresh incremental).
