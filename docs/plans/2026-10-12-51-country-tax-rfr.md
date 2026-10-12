# Lock in Damodaran country tax_rate and risk_free_rate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove with tests that a Damodaran import leaves `damodaran_country.tax_rate` and `risk_free_rate` populated and that the valuator and screener consume the imported values; add an opt-in live check; fix the text that still says the column is NULL.

**Architecture:** Tests and docs only; no importer, column-map or precedence change. Offline tests import the committed Jan-2026 fixtures (`tests/fixtures/damodaran/wacc_sample.xls`, `ctryprem_sample.xls`) with `import_damodaran_from_files` and assert on `damodaran_country` and on the two consumers. A new `live` pytest marker, skipped at collection unless `BOT_LIVE_TESTS=1`, guards one test that downloads the current files and checks shape only.

**Tech Stack:** Python 3.12, pytest (`--strict-markers`), DuckDB, structlog, `uv`.

**Spec:** GitHub issue #51 (nicolas-ricc/damodaran). Context: ADR 0005 §4 (per-currency risk-free rate, #109), ADR 0007.

## Global Constraints

- No change to importer behaviour, column maps, or tax-rate precedence (valuator: manual → sector → country → 0.25; screener: country → 0.21).
- Do not test or change the broadcast of the US Treasury rate into every country row; assert `risk_free_rate` only on the `United States` row.
- Offline: `uv run pytest -q` passes with the live test reported as skipped; `uv run ruff check . && uv run mypy src` clean.
- The live test never pins exact live numbers.
- Exact fixture values (probed on the committed fixtures): US `tax_rate == 0.25`, US `risk_free_rate == 0.0395`, Australia `0.30`, Bahamas `0.0`; 157 of 158 country rows carry a tax rate, the NULL one is `Frontier Markets (no sovereign ratings)`.

## Review Focus

1. A tax rate stored as a percentage (`25` instead of `0.25`) after a release change: the `[0, 1]` range assertion over every non-NULL row (Task 1) catches it.
2. The country tax sheet silently disappearing (every `tax_rate` NULL): the >= 95% coverage assertion (Task 1) catches it offline and in the live test (Task 3).
3. The valuator country fallback is only reachable when the industry row has no tax rate; every fixture industry row has one, so Task 2 blanks the Software row with `UPDATE` and checks the value is the country's `0.25`, not the sector's ~0.055.
4. The live test running in CI or a plain local run: Task 3 skips at collection unless `BOT_LIVE_TESTS=1`, and a test asserts the skip is applied.
5. `terminal_growth` passing because it equals GDP by accident: Task 2 uses `gdp_nominal=0.04 > 0.0395`, so the bare-GDP value would fail the equality.

---

### Task 1: Fixture import populates the country tax and risk-free columns

**Files:**
- Modify: `tests/integration/test_damodaran_import.py`

**Interfaces:**
- Consumes: `import_damodaran_from_files(conn, *, industry_path, country_path, region, year) -> IngestResult`.
- Produces: module helper `_imported_conn() -> duckdb.DuckDBPyConnection` (fixtures imported into an in-memory DB with the schema applied, `region="US"`, `year=2026`, result asserted `success`), and the module constant `_FIXTURES_PRESENT: bool`. Task 2 reuses both.

- [ ] **Step 1: Add the helper and the test**

```python
_FIXTURES_PRESENT = (FIXTURES / "wacc_sample.xls").exists() and (
    FIXTURES / "ctryprem_sample.xls"
).exists()


def _imported_conn() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    result = import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    assert result.is_success(), result.error_message
    return conn


def _country_value(conn: duckdb.DuckDBPyConnection, column: str, country: str) -> Any:
    row = conn.execute(
        f"SELECT {column} FROM damodaran_country WHERE country = ?", [country]
    ).fetchone()
    assert row is not None, country
    return row[0]


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_import_fills_country_tax_and_risk_free_rates() -> None:
    conn = _imported_conn()

    assert _country_value(conn, "tax_rate", "United States") == pytest.approx(0.25)
    assert _country_value(conn, "risk_free_rate", "United States") == pytest.approx(0.0395)
    assert _country_value(conn, "tax_rate", "Australia") == pytest.approx(0.30)
    assert _country_value(conn, "tax_rate", "Bahamas") == pytest.approx(0.0)

    total, with_tax = conn.execute(
        "SELECT COUNT(*), COUNT(tax_rate) FROM damodaran_country"
    ).fetchone()
    # Aggregate rows such as "Frontier Markets (no sovereign ratings)" have no rate.
    assert with_tax / total >= 0.95
    out_of_range = conn.execute(
        "SELECT country, tax_rate FROM damodaran_country "
        "WHERE tax_rate IS NOT NULL AND (tax_rate < 0 OR tax_rate > 1)"
    ).fetchall()
    assert out_of_range == []
    conn.close()
```

Add `from typing import Any` and `import duckdb` to the imports. Leave the two existing tests as they are.

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/integration/test_damodaran_import.py -q`
Expected: PASS (the importer already fills both columns since d5b322a; this pins it).

- [ ] **Step 3: Negative control (do not commit)**

Only with a clean `src/bot/ingest/damodaran.py` (Task 4 has not started): temporarily replace `tax_rates = parse_country_tax_rates(country_path)` with `tax_rates = {}`, rerun; expect FAIL on the US tax assertion. Revert with `git checkout -- src/bot/ingest/damodaran.py` and confirm `git status` is clean for that file.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_damodaran_import.py
git commit -m "test(#51): pin imported country tax and risk-free rates"
```

---

### Task 2: Valuator and screener consume the imported rates

**Files:**
- Modify: `tests/integration/test_damodaran_import.py`

**Interfaces:**
- Consumes: `_imported_conn()` and `_FIXTURES_PRESENT` from Task 1; `bot.valuator.assumptions.resolve_assumptions(ticker, conn, *, gdp_nominal=...) -> Assumptions` (fields `terminal_growth`, `tax_rate` are `Sourced` with `.value`, `.source`); `bot.valuator.assumptions.AssumptionSource`; `bot.screener.engine._resolve_tax_rate(conn, country) -> float`.
- Produces: nothing other tasks use.

The industry `Software (System & Application)` exists in `wacc_sample.xls`; its `tax_rate` is about 0.055, so it differs from the US country rate 0.25.

- [ ] **Step 1: Add the seeding helper and three tests**

```python
_SOFTWARE = "Software (System & Application)"


def _seed_us_software_company(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry_damodaran, source) "
        "VALUES ('ACME', 'ACME Inc', 'United States', ?, 'test')",
        [_SOFTWARE],
    )


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_terminal_growth_is_capped_by_the_imported_risk_free_rate() -> None:
    conn = _imported_conn()
    _seed_us_software_company(conn)
    gdp_nominal = 0.04  # above the imported 0.0395, so min() must pick the rate

    growth = resolve_assumptions("ACME", conn, gdp_nominal=gdp_nominal).terminal_growth

    assert growth.value == pytest.approx(min(0.0395, gdp_nominal))
    assert growth.value != pytest.approx(gdp_nominal)
    assert growth.source is AssumptionSource.RULE_BASED
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_screener_reads_the_imported_us_tax_rate() -> None:
    conn = _imported_conn()
    assert screener_tax_rate(conn, "United States") == pytest.approx(0.25)
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_valuator_falls_back_to_the_imported_country_tax_rate() -> None:
    conn = _imported_conn()
    _seed_us_software_company(conn)
    # Every fixture industry row carries a tax rate; blank one to reach the
    # country step of manual -> sector -> country -> default.
    conn.execute(
        "UPDATE damodaran_industry SET tax_rate = NULL WHERE industry = ?", [_SOFTWARE]
    )

    tax = resolve_assumptions("ACME", conn).tax_rate

    assert tax.value == pytest.approx(0.25)
    assert tax.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    conn.close()
```

Imports to add:

```python
from bot.screener.engine import _resolve_tax_rate as screener_tax_rate
from bot.valuator.assumptions import AssumptionSource, resolve_assumptions
```

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/integration/test_damodaran_import.py -q`
Expected: PASS.

- [ ] **Step 3: Negative control (do not commit)**

Only with a clean `src/bot/ingest/damodaran.py` (Task 4 has not started): temporarily delete the line `row["risk_free_rate"] = risk_free_rate` (and its `if`) in `_import_files_into_run`; the terminal-growth test must FAIL (value falls to 0.04). Revert with `git checkout -- src/bot/ingest/damodaran.py` and confirm `git status` is clean for that file.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_damodaran_import.py
git commit -m "test(#51): consumers read imported country tax and risk-free rates"
```

---

### Task 3: Opt-in live check of the published files

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options].markers`)
- Modify: `tests/conftest.py` (collection hook)
- Create: `tests/integration/test_damodaran_live.py`
- Test: `tests/unit/test_live_marker.py`

**Interfaces:**
- Consumes: `bot.ingest.damodaran.download_dataset(url, dest) -> Path`, `INDUSTRY_WACC_URL`, `COUNTRY_RISK_URL`, `import_damodaran_from_files`.
- Produces: marker `live`; env switch `BOT_LIVE_TESTS=1`.

- [ ] **Step 1: Write the failing marker test**

`tests/unit/test_live_marker.py` uses pytest's `pytester` to prove the collection skip without touching the network:

```python
"""The ``live`` marker: skipped at collection unless BOT_LIVE_TESTS=1."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_ROOT_CONFTEST = Path(__file__).parent.parent / "conftest.py"

_LIVE_TEST = """
import pytest

@pytest.mark.live
def test_hits_the_network():
    assert True
"""


def _run(pytester: pytest.Pytester) -> pytest.RunResult:
    pytester.makeconftest(_ROOT_CONFTEST.read_text())
    pytester.makeini("[pytest]\naddopts = --strict-markers\nmarkers =\n    live: x\n")
    pytester.makepyfile(_LIVE_TEST)
    return pytester.runpytest("-q")


def test_live_tests_are_skipped_by_default(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_LIVE_TESTS", raising=False)
    _run(pytester).assert_outcomes(skipped=1)


def test_live_tests_run_when_opted_in(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_LIVE_TESTS", "1")
    _run(pytester).assert_outcomes(passed=1)


def test_live_marker_is_registered(pytestconfig: pytest.Config) -> None:
    markers = pytestconfig.getini("markers")
    assert any(m.startswith("live:") for m in markers)
```

Run: `uv run pytest tests/unit/test_live_marker.py -q`
Expected: FAIL (`test_live_tests_are_skipped_by_default` passes 1 instead of skipping; marker not registered).

- [ ] **Step 2: Register the marker** in `pyproject.toml`:

```toml
markers = [
    "integration: tests that hit external services (use VCR cassettes)",
    "live: downloads current published data; skipped unless BOT_LIVE_TESTS=1",
]
```

- [ ] **Step 3: Add the collection hook** to `tests/conftest.py` (add `import os` to the imports):

```python
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``live`` tests unless ``BOT_LIVE_TESTS=1``: the default run stays offline."""
    if os.environ.get("BOT_LIVE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="live test; set BOT_LIVE_TESTS=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
```

Mention the hook in the module docstring of `tests/conftest.py` in one sentence.

- [ ] **Step 4: Run the marker tests**

Run: `uv run pytest tests/unit/test_live_marker.py -q`
Expected: PASS.

- [ ] **Step 5: Write the live test** `tests/integration/test_damodaran_live.py`:

```python
"""Live shape check of the published Damodaran files (opt-in, ``BOT_LIVE_TESTS=1``).

Run after a new Damodaran release: ``BOT_LIVE_TESTS=1 uv run pytest -m live``.
Asserts shape only, never exact numbers, so a routine release does not break it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.ingest.damodaran import (
    COUNTRY_RISK_URL,
    INDUSTRY_WACC_URL,
    download_dataset,
    import_damodaran_from_files,
)
from bot.storage.db import apply_schema, connect

_UNAVAILABLE_EVENTS = {
    "damodaran.country_tax_sheet.unavailable",
    "damodaran.risk_free_rate.unavailable",
}


@pytest.mark.live
def test_published_files_still_carry_country_tax_and_risk_free_rates(tmp_path: Path) -> None:
    industry_path = download_dataset(INDUSTRY_WACC_URL, tmp_path / "wacc.xls")
    country_path = download_dataset(COUNTRY_RISK_URL, tmp_path / "ctryprem.xls")
    conn = connect(":memory:")
    apply_schema(conn)

    with capture_logs() as logs:
        result = import_damodaran_from_files(
            conn,
            industry_path=industry_path,
            country_path=country_path,
            region="US",
            year=date.today().year,
        )

    assert result.is_success(), result.error_message
    assert not _UNAVAILABLE_EVENTS & {entry["event"] for entry in logs}
    us = conn.execute(
        "SELECT tax_rate, risk_free_rate FROM damodaran_country WHERE country = 'United States'"
    ).fetchone()
    assert us is not None
    tax_rate, risk_free_rate = us
    assert tax_rate is not None and 0 < tax_rate < 1
    assert risk_free_rate is not None and 0 < risk_free_rate < 0.15
    total, with_tax = conn.execute(
        "SELECT COUNT(*), COUNT(tax_rate) FROM damodaran_country"
    ).fetchone()
    assert with_tax / total >= 0.95
    conn.close()
```

- [ ] **Step 6: Confirm it is skipped offline**

Run: `uv run pytest tests/integration/test_damodaran_live.py -q -rs`
Expected: 1 skipped, reason `live test; set BOT_LIVE_TESTS=1 to run`. Do NOT run with `BOT_LIVE_TESTS=1` (the agent stays offline; the PR says a human runs it).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/unit/test_live_marker.py tests/integration/test_damodaran_live.py
git commit -m "test(#51): opt-in live check of published Damodaran country rates"
```

---

### Task 4: Fix the stale text

**Files:**
- Modify: `src/bot/screener/engine.py` (docstring of `_resolve_tax_rate`)
- Modify: `tests/unit/test_screener_engine.py` (comment in `test_resolve_tax_rate_reads_country`)
- Modify: `src/bot/ingest/damodaran.py` (module docstring only)

**Interfaces:** none; text only.

- [ ] **Step 1: Screener docstring.** Replace the "Note: the current Damodaran country ingest ... waits on the data." paragraph with:

```
    ``damodaran_country.tax_rate`` comes from the ``Country Tax Rates`` sheet of
    ``ctryprem.xls``, joined onto the country rows by the Damodaran importer; a
    country absent from that sheet (aggregate rows such as "Frontier Markets") is
    NULL and falls back to the default. A rate outside ``[0, 1)`` (e.g. a
    percentage stored as ``30`` instead of ``0.30``) is rejected back to the
    default rather than producing a negative NOPAT.
```

- [ ] **Step 2: Test comment.** Replace the two `# NB:` lines with:

```python
    # Hand-seeded so the resolver is tested on its own; the imported rows are
    # covered by tests/integration/test_damodaran_import.py.
```

- [ ] **Step 3: Importer module docstring.** Append a paragraph:

```
Two country columns are not columns of the ``ERPs by country`` sheet: ``tax_rate``
comes from the ``Country Tax Rates`` sheet of ``ctryprem.xls`` and
``risk_free_rate`` from the pre-header cell ``Long Term Treasury bond rate =`` of
``wacc.xls``. To verify a new release still carries both, run
``BOT_LIVE_TESTS=1 uv run pytest -m live``.
```

- [ ] **Step 4: Verify**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: all pass; the live test reported skipped.

- [ ] **Step 5: Commit**

```bash
git add src/bot/screener/engine.py tests/unit/test_screener_engine.py src/bot/ingest/damodaran.py
git commit -m "docs(#51): describe the current source of country tax and risk-free rates"
```

## Assumptions

- The valuator's country fallback is tagged `SECTOR_DEFAULT_DAMODARAN` by the code (`src/bot/valuator/assumptions.py:912-913`; the enum at `:84-96` has no country member). Task 2 therefore distinguishes sector from country by value (0.25 vs the Software row's ~0.055), not by source. Rejected: adding a country enum member (would change behaviour, which the issue forbids).
- Reaching the country step needs an industry row with `tax_rate IS NULL`; no fixture row has one, so Task 2 blanks the Software row with `UPDATE`. `_load_sector` reads `WHERE industry = ? ORDER BY year DESC, region LIMIT 1` (`assumptions.py:473-474`) and the table key is `(industry, region, year)` (`src/bot/storage/schema.sql`), so with one imported region/year the `UPDATE` hits exactly the row the resolver reads. Rejected: seeding a company in an industry absent from the fixture (would test "no sector row", not "industry row with NULL tax").
- The live-skip uses a `pytest_collection_modifyitems` hook in `tests/conftest.py` (18 lines today, one autouse fixture, no existing hook, no `bot` import), so the pytester copy in `test_live_marker.py` is self-contained. Rejected: a `skipif` on the test itself (the issue asks for a skip at collection, applied to the marker).
- Live download failures surface as `httpx.HTTPStatusError`/timeout from `download_dataset` (`damodaran.py:608-617`, `raise_for_status`), a different traceback from a shape assertion; no retry is added (not asked for).
- Negative controls run before Task 4 touches `damodaran.py`, so the `git checkout --` revert cannot discard docstring work.

## Grilling

- Rounds: 1 (revisions were clarifications, not new steps or seams).
- Questions: 18. Sources: CODE 12, ISSUE 5, DOC 1. NO SOURCE: 0 (two technical points recorded above as assumptions after code checks).
- Issues opened: none. Per-currency risk-free rates are already #109 (issue's Out of scope).
