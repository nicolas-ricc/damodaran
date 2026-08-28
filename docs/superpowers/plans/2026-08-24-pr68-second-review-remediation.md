# PR 68 Second-Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every finding of the 2026-08-24 two-axis review of PR 68 (8 Standards judgement calls, 2 Spec findings) without changing pipeline behaviour.

**Architecture:** Small, behaviour-preserving refactors on the PR 68 branch: extract three duplicated shapes into single helpers, move the canonical `ParsedCompanyData` record into the provider port so the port stops depending on an adapter, tighten `TickerOutcome.status` to a `Literal`, drop the `"fmp"` defaults from provider-neutral writers, name one magic number, unify the mixed-language user strings, harden `schema_table_count`, and reconcile the port design doc with the shipped `FxRate`. The last task is the still-unattested real-network run from the previous remediation plan.

**Tech Stack:** Python 3.12, DuckDB, Typer, pytest, ruff, mypy --strict, uv.

**Spec:** The 2026-08-24 review report (Standards findings 1–8, Spec findings a.1 and c.1) plus `docs/superpowers/plans/2026-08-22-pr68-review-remediation.md` (Task 3, the real run) and `docs/superpowers/specs/2026-08-24-market-data-provider-port-design.md` (`FxRate` shape).

## Global Constraints

- Every task ends with `uv run pytest -q && uv run ruff check . && uv run mypy src` green/clean (721 tests baseline).
- Seam rule (port design, "enforcement"): "nothing outside `fmp.py` imports `FmpClient`"; `cli.py` is the only file naming `FmpProvider`. `tests/unit/test_seam_enforcement.py` must keep passing.
- Conventional Commits; one commit per task.
- No behaviour change in Tasks 1–9: existing tests are the safety net; new tests pin the extracted helpers only.
- Language decision (Finding 7): **user-facing CLI text and docstrings in English** — that is what the overwhelming majority of `src/` already uses. Plan/ADR docs stay in Spanish as they are.

---

### Task 1: One `conventional_override_path` helper (Finding 1 — Duplicated Code)

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (add public helper next to `_load_override`, ~line 455)
- Modify: `src/bot/cli.py:406-409` (`_analyze_one`)
- Modify: `src/bot/screener/engine.py:112-116` (`_batch_dcf_margins`)
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Produces: `conventional_override_path(assumptions_dir: Path | None, ticker: str) -> Path | None` — returns `<assumptions_dir>/<TICKER>.yaml` if that file exists, else `None`. Uppercases the ticker.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_valuator_assumptions.py`:

```python
from pathlib import Path

from bot.valuator.assumptions import conventional_override_path


def test_conventional_override_path_finds_the_ticker_yaml(tmp_path: Path) -> None:
    (tmp_path / "AAPL.yaml").write_text("story_type: mature\n")
    assert conventional_override_path(tmp_path, "aapl") == tmp_path / "AAPL.yaml"


def test_conventional_override_path_is_none_when_missing_or_no_dir(tmp_path: Path) -> None:
    assert conventional_override_path(tmp_path, "MSFT") is None
    assert conventional_override_path(None, "MSFT") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -k conventional_override_path -v`
Expected: FAIL — `ImportError: cannot import name 'conventional_override_path'`.

- [ ] **Step 3: Implement the helper**

In `src/bot/valuator/assumptions.py`, directly above `def _load_override`:

```python
def conventional_override_path(assumptions_dir: Path | None, ticker: str) -> Path | None:
    """Return ``<assumptions_dir>/<TICKER>.yaml`` when it exists (spec §7.6), else None.

    The single place that knows the convention: ``bot analyze`` and the
    screener's second-pass DCF both resolve overrides through here.
    """
    if assumptions_dir is None:
        return None
    candidate = assumptions_dir / f"{ticker.upper()}.yaml"
    return candidate if candidate.exists() else None
```

- [ ] **Step 4: Replace both call sites**

`src/bot/cli.py` `_analyze_one` — replace

```python
    if override is None:
        conventional = settings.assumptions_dir / f"{ticker}.yaml"
        if conventional.exists():
            override = conventional
```

with

```python
    if override is None:
        override = conventional_override_path(settings.assumptions_dir, ticker)
```

and add `conventional_override_path` to the existing `from bot.valuator.assumptions import ...` line (or add the import if `cli.py` does not import that module yet).

`src/bot/screener/engine.py` `_batch_dcf_margins` — replace

```python
        override_path = None
        if assumptions_dir is not None:
            candidate_path = assumptions_dir / f"{ticker}.yaml"
            if candidate_path.exists():
                override_path = candidate_path
```

with

```python
        override_path = conventional_override_path(assumptions_dir, ticker)
```

and add `from bot.valuator.assumptions import conventional_override_path` to the engine's imports (grouped with its other `bot.valuator` imports).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: all green; `tests/unit/test_cli_analyze.py` and `tests/unit/test_screener_engine.py` still pass unchanged (they exercise the convention end-to-end).

- [ ] **Step 6: Commit**

```bash
git add src/bot/valuator/assumptions.py src/bot/cli.py src/bot/screener/engine.py tests/unit/test_valuator_assumptions.py
git commit -m "refactor(assumptions): one conventional_override_path shared by analyze and the screener"
```

---

### Task 2: One universe-loading preamble in the CLI (Finding 2 — Duplicated Code)

**Files:**
- Modify: `src/bot/cli.py:173-227` (`_refresh_fmp_universe`, `_refresh_prices`)
- Test: `tests/unit/test_cli_refresh_fmp.py`

**Interfaces:**
- Produces: `_universe_tickers(universe: Path | None, limit: int | None) -> tuple[Path, list[str]]` — resolves the universe path (default when `None`), loads it, applies `limit`. An empty list is returned, not handled; callers keep their `exit 2` message.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_cli_refresh_fmp.py` (copy the CSV header shape `load_universe` expects from `tests/unit/test_universe_csv.py`):

```python
from pathlib import Path

from bot.cli import _universe_tickers


def test_universe_tickers_applies_limit_and_returns_the_path(tmp_path: Path) -> None:
    csv_path = tmp_path / "u.csv"
    csv_path.write_text("ticker\nAAPL\nMSFT\nNVDA\n")
    path, tickers = _universe_tickers(csv_path, limit=2)
    assert path == csv_path
    assert tickers == ["AAPL", "MSFT"]
    assert _universe_tickers(csv_path, limit=None)[1] == ["AAPL", "MSFT", "NVDA"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_cli_refresh_fmp.py -k universe_tickers -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement and use the helper**

Add above `_refresh_fmp_universe` in `src/bot/cli.py`:

```python
def _universe_tickers(universe: Path | None, limit: int | None) -> tuple[Path, list[str]]:
    """Resolve the universe file, load its tickers and apply ``--limit``."""
    path = universe or default_universe_path()
    tickers = load_universe(path)
    if limit is not None:
        tickers = tickers[:limit]
    return path, tickers
```

In both `_refresh_fmp_universe` and `_refresh_prices`, replace the four lines

```python
    path = universe or default_universe_path()
    tickers = load_universe(path)
    if limit is not None:
        tickers = tickers[:limit]
```

with

```python
    path, tickers = _universe_tickers(universe, limit)
```

The `if not tickers: ... return 2` block stays in each (it is the caller's exit-code policy).

- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/bot/cli.py tests/unit/test_cli_refresh_fmp.py
git commit -m "refactor(cli): share the universe-loading preamble between the refresh subcommands"
```

---

### Task 3: One date coercion (Finding 3 — Duplicated Code)

**Files:**
- Modify: `src/bot/ingest/base.py` (add `coerce_date`)
- Modify: `src/bot/ingest/fmp.py:317-318, 335, 351-357` (`_as_date`, `_latest_filing_from_rows`, `_date_or_none`)
- Modify: `src/bot/ingest/universe.py:165-172, 495-502` (`latest_local_filing_date`, `_max_price_date`)
- Test: `tests/unit/test_ingest_base.py`

**Interfaces:**
- Produces: `coerce_date(value: object) -> date | None` in `bot.ingest.base` — `None`/empty → `None`; `datetime` → `.date()`; `date` → itself; anything else → `date.fromisoformat(str(value)[:10])`, `None` on `ValueError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_ingest_base.py`:

```python
from datetime import date, datetime

from bot.ingest.base import coerce_date


def test_coerce_date_accepts_every_shape_the_pipeline_sees() -> None:
    assert coerce_date(None) is None
    assert coerce_date("") is None
    assert coerce_date(date(2024, 1, 2)) == date(2024, 1, 2)
    assert coerce_date(datetime(2024, 1, 2, 13, 45)) == date(2024, 1, 2)
    assert coerce_date("2024-01-02") == date(2024, 1, 2)
    assert coerce_date("2024-01-02 00:00:00") == date(2024, 1, 2)
    assert coerce_date("not-a-date") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_ingest_base.py -k coerce_date -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

In `src/bot/ingest/base.py` (add `from datetime import date, datetime` to the imports if absent):

```python
def coerce_date(value: object) -> date | None:
    """Coerce a DB cell or provider date-ish string to a ``date``.

    ``None``/empty → None; ``datetime`` → its date; ``date`` → itself; any other
    value is parsed as the first 10 chars of its ISO text, None if unparsable.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
```

- [ ] **Step 4: Replace the four variants**

`src/bot/ingest/fmp.py` — add `coerce_date` to the `from bot.ingest.base import ...` line, then:

- Replace the body of `_as_date` with:

  ```python
  def _as_date(value: Any) -> date:
      parsed = coerce_date(value)
      if parsed is None:
          raise ValueError(f"FMP row has no usable date: {value!r}")
      return parsed
  ```

- Delete `_date_or_none` and replace its single caller (line 105) with `ipo_date=coerce_date(profile.get("ipoDate"))`.
- In `_latest_filing_from_rows`, replace the `try: filed = date.fromisoformat(...) except ValueError: continue` block with:

  ```python
        filed = coerce_date(filed_raw)
        if filed is None:
            continue
  ```

`src/bot/ingest/universe.py` — add `coerce_date` to the `from bot.ingest.base import ...` line and, in both `latest_local_filing_date` and `_max_price_date`, replace

```python
    if row is None or row[0] is None:
        return None
    value = row[0]
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
```

with

```python
    return coerce_date(row[0]) if row is not None else None
```

`datetime` stays imported in `universe.py` (`datetime.now()` in `_run_bulk_refresh` uses it); ruff will flag anything that became unused.

- [ ] **Step 5: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green — `test_fmp_parser.py`, `test_fmp_provider.py`, `test_prices_refresh.py`, `test_universe_refresh.py` cover all four sites.

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/base.py src/bot/ingest/fmp.py src/bot/ingest/universe.py tests/unit/test_ingest_base.py
git commit -m "refactor(ingest): one coerce_date for DB cells and provider date strings"
```

---

### Task 4: The port owns `ParsedCompanyData`; the seam test polices it (Finding 4)

**Files:**
- Modify: `src/bot/ingest/provider.py:16` (define the record here, drop the `sec_edgar` import)
- Modify: `src/bot/ingest/sec_edgar.py:81-87` (import from the port instead of defining)
- Modify: `src/bot/ingest/fmp.py:27`, `tests/fake_provider.py:14` (import path)
- Test: `tests/unit/test_seam_enforcement.py`

**Interfaces:**
- Produces: `bot.ingest.provider.ParsedCompanyData` (same fields: `company: dict[str, Any]`, `annual`, `quarterly`, `filings: list[dict[str, Any]]`, lists default-empty). `bot.ingest.sec_edgar.ParsedCompanyData` remains importable as a re-export so no other caller breaks.

- [ ] **Step 1: Write the failing seam test**

Append to `tests/unit/test_seam_enforcement.py`:

```python
def test_the_port_imports_no_concrete_adapter() -> None:
    port = (SRC / "ingest" / "provider.py").read_text(encoding="utf-8")
    assert re.search(r"from bot\.ingest\.(sec_edgar|fmp)\b", port) is None
    assert re.search(r"import bot\.ingest\.(sec_edgar|fmp)\b", port) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_seam_enforcement.py -v`
Expected: the new test FAILS (provider.py line 16 imports from `sec_edgar`).

- [ ] **Step 3: Move the dataclass**

In `src/bot/ingest/provider.py`, delete `from bot.ingest.sec_edgar import ParsedCompanyData`, add `field` to the `dataclasses` import, and insert above `class CompanyInfo`:

```python
@dataclass
class ParsedCompanyData:
    """Fundamentals in DB-row shape: one company dict plus annual/quarterly/filings rows.

    The canonical record every adapter (SEC EDGAR, FMP, fakes) produces, so the
    importer never sees a source's wire format.
    """

    company: dict[str, Any]
    annual: list[dict[str, Any]] = field(default_factory=list)
    quarterly: list[dict[str, Any]] = field(default_factory=list)
    filings: list[dict[str, Any]] = field(default_factory=list)
```

In `src/bot/ingest/sec_edgar.py`, delete the class at lines 81–87 and add `from bot.ingest.provider import ParsedCompanyData` to the imports (keep `field` in the `dataclasses` import only if still used; ruff will tell you). If the module has an `__all__`, add `"ParsedCompanyData"` to it; otherwise the plain import already re-exports it.

Change `src/bot/ingest/fmp.py:27` and `tests/fake_provider.py:14` to `from bot.ingest.provider import ParsedCompanyData`.

- [ ] **Step 4: Check for an import cycle**

Run: `uv run python -c "import bot.ingest.provider, bot.ingest.sec_edgar, bot.ingest.fmp, bot.ingest.universe; print('ok')"`
Expected: `ok`. (`provider.py` now imports nothing from `bot.ingest`; `sec_edgar` → `provider` is one-directional.)

- [ ] **Step 5: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/provider.py src/bot/ingest/sec_edgar.py src/bot/ingest/fmp.py tests/fake_provider.py tests/unit/test_seam_enforcement.py
git commit -m "refactor(ingest): the provider port owns ParsedCompanyData; seam test forbids adapter imports"
```

---

### Task 5: `TickerStatus` literal and no `"fmp"` defaults in neutral writers (Finding 5)

**Files:**
- Modify: `src/bot/ingest/universe.py:70-79, 157-158, 384-394, 458-463, 660`
- Modify: `src/bot/utils/fx.py:43-48`
- Modify tests that relied on the defaults: `tests/unit/test_fx.py:24,92,95,104,116`, `tests/unit/test_portfolio_sync.py:325`, `tests/unit/test_universe_refresh.py:136-137`
- Test: `tests/unit/test_universe_refresh.py`

**Interfaces:**
- Produces: `TickerStatus = Literal["imported", "skipped", "failed", "deferred"]` exported from `bot.ingest.universe`; `TickerOutcome.status: TickerStatus`.
- Changes: `upsert_prices_daily(..., source: str)`, `upsert_fx_rates(..., source: str)`, `latest_local_filing_date(conn, ticker, source: str)` — `source` becomes required (keyword-only for the two upserts, positional-or-keyword for `latest_local_filing_date`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_universe_refresh.py`:

```python
import inspect
from typing import get_args

from bot.ingest.universe import TickerStatus, latest_local_filing_date, upsert_prices_daily
from bot.utils.fx import upsert_fx_rates


def test_ticker_status_names_the_four_outcomes() -> None:
    assert set(get_args(TickerStatus)) == {"imported", "skipped", "failed", "deferred"}


def test_provider_neutral_writers_require_an_explicit_source() -> None:
    for fn in (upsert_prices_daily, upsert_fx_rates, latest_local_filing_date):
        assert inspect.signature(fn).parameters["source"].default is inspect.Parameter.empty
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_universe_refresh.py -k "ticker_status or explicit_source" -v`
Expected: FAIL — `ImportError: TickerStatus`, then the default assertion.

- [ ] **Step 3: Implement**

`src/bot/ingest/universe.py`:

- Add `from typing import Literal` and `from collections import Counter` to the imports and, above `class TickerOutcome`:

  ```python
  TickerStatus = Literal["imported", "skipped", "failed", "deferred"]
  ```

- Change `status: str` to `status: TickerStatus` in `TickerOutcome` (keep the comments describing each value).
- Replace the counting cascade in `_run_bulk_refresh` — delete `imported = skipped = failed = deferred = 0`, the `deferred += 1` lines and the whole `if outcome.status == "imported": ... else: failed += 1` block — with a `Counter`:

  ```python
    counts: Counter[TickerStatus] = Counter()
    ...
        if rate_limited:
            outcomes.append(TickerOutcome(ticker=item.upper(), status="deferred"))
            counts["deferred"] += 1
            continue
        try:
            outcome = process(item)
        except ProviderRateLimitError as exc:
            log.warning(f"{label}.refresh.rate_limited", item=item, error=str(exc))
            rate_limited = True
            outcomes.append(TickerOutcome(ticker=item.upper(), status="deferred"))
            counts["deferred"] += 1
            continue
        outcomes.append(outcome)
        counts[outcome.status] += 1
  ```

  Wherever the function later reads `imported`, `skipped`, `failed`, `deferred` (the progress log and the `UniverseRefreshResult(...)` constructor — read the rest of the function to find them), use `counts["imported"]`, `counts["skipped"]`, `counts["failed"]`, `counts["deferred"]`.
- `latest_local_filing_date(conn, ticker, source: str)` — drop the default; update its caller at line ~660 to `latest_local_filing_date(conn, sym, provider.name)`.
- `upsert_prices_daily(..., source: str)` — drop the default (its only caller already passes `source=provider.name`).

`src/bot/utils/fx.py`: `upsert_fx_rates(..., source: str)` — drop the default (its caller in `import_fx_rates` already passes `source=provider.name`).

Tests: add `source="fmp"` to the `upsert_fx_rates(` calls at `tests/unit/test_fx.py` lines 24, 92, 95, 104, 116 and `tests/unit/test_portfolio_sync.py:325`; change `tests/unit/test_universe_refresh.py:136-137` to `latest_local_filing_date(conn, "aapl", "fmp")` / `latest_local_filing_date(conn, "MSFT", "fmp")`. Then run `grep -rn "upsert_prices_daily(\|upsert_fx_rates(\|latest_local_filing_date(" tests src | grep -v source=` — it must list only `def` lines and the two positional test calls.

- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green; mypy now rejects any `status="typo"`.

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/universe.py src/bot/utils/fx.py tests/unit/test_fx.py tests/unit/test_portfolio_sync.py tests/unit/test_universe_refresh.py
git commit -m "refactor(ingest): TickerStatus literal; provider-neutral writers take an explicit source"
```

---

### Task 6: Name the cycle length; one mean (Finding 6)

**Files:**
- Modify: `src/bot/valuator/assumptions.py:424, 687-688`
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Produces: module constant `_MIN_CYCLE_YEARS = 4` (private; the test reads it by name).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_valuator_assumptions.py`:

```python
from bot.valuator import assumptions as assumptions_mod


def test_cyclical_margin_needs_a_full_cycle_of_history() -> None:
    assert assumptions_mod._MIN_CYCLE_YEARS == 4
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -k full_cycle -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement**

Next to `_HORIZON` in `src/bot/valuator/assumptions.py`:

```python
# A cyclical company's "cycle average" margin is only meaningful once we hold at
# least one full business cycle of annual margins; fewer years fall back to the
# sector median rather than averaging a half-cycle.
_MIN_CYCLE_YEARS = 4
```

In `_resolve_operating_margin` replace

```python
    if story_type is StoryType.CYCLICAL and len(margin_history) >= 4:
        cycle_avg = sum(margin_history) / len(margin_history)
```

with

```python
    if story_type is StoryType.CYCLICAL and len(margin_history) >= _MIN_CYCLE_YEARS:
        cycle_avg = fmean(margin_history)
```

and at line 424 replace `average = sum(growths) / len(growths)` with `average = fmean(growths)` (`fmean` is already imported). Update the `_resolve_operating_margin` docstring's "cyclical" sentence to say "given at least `_MIN_CYCLE_YEARS` years of margin history".

- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green (`test_valuator_story_types.py` pins the cyclical branch numerically).

- [ ] **Step 5: Commit**

```bash
git add src/bot/valuator/assumptions.py tests/unit/test_valuator_assumptions.py
git commit -m "refactor(valuator): name the minimum cycle length and use fmean throughout"
```

---

### Task 7: English user-facing strings and docstrings in the PR's code (Finding 7)

**Files:**
- Modify: `src/bot/cli.py:253-256` (deferred NOTE)
- Modify: `src/bot/storage/db.py:31` (docstring)
- Modify: any other Spanish docstring/`typer.echo` introduced by this branch — find them with `git diff origin/master...HEAD -- src | grep '^+' | grep -P '[áéíóñ¿¡]|\bpara\b|\bque\b'`
- Test: `tests/unit/test_cli_refresh_fmp.py` (existing deferred-NOTE assertion, if any)

- [ ] **Step 1: Find any test that asserts the Spanish text**

Run: `grep -rn "volvé\|mañana" tests`
Expected: zero or a few hits — update those assertions in Step 3 to the new English text.

- [ ] **Step 2: Rewrite the strings**

`src/bot/cli.py` `_report_universe_refresh`:

```python
    if result.deferred:
        typer.echo(
            f"NOTE — {result.deferred} tickers deferred (FMP daily quota); "
            "re-run the same command tomorrow to continue.",
        )
```

`src/bot/storage/db.py` `schema_table_count` docstring → `"""Number of tables ``schema.sql`` defines (used by ``bot doctor``)."""`.

For every other hit from the grep in **Files**, translate the docstring/message to English preserving meaning. Do not touch `docs/`, ADRs, or `README.md`.

- [ ] **Step 3: Full gate (after updating any assertions found in Step 1)**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add -A src tests
git commit -m "style: English for the user-facing strings and docstrings added by the US-only branch"
```

---

### Task 8: Robust `schema_table_count`; drop the duplicated `run.details` (Finding 8)

**Files:**
- Modify: `src/bot/storage/db.py:30-33`
- Modify: `src/bot/ingest/universe.py:574` (delete the second `run.details = {"ticker": sym}` in `_refresh_one_price`; keep the first at ~552)
- Test: `tests/unit/test_storage_db.py`

**Interfaces:**
- Produces: `_count_create_tables(sql: str) -> int` and `schema_table_count() -> int` (signature unchanged) in `bot.storage.db`; the count now comes from the regex `^\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+` (multiline, case-insensitive) over comment-stripped SQL instead of a substring count.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_storage_db.py`:

```python
import re
from importlib import resources

from bot.storage.db import _count_create_tables, schema_table_count


def test_count_create_tables_ignores_case_spacing_and_comments() -> None:
    sql = """
    -- CREATE TABLE IF NOT EXISTS commented_out (x INT);
    create table   if   not   exists  a (x INT);
    CREATE TABLE b (x INT);
    CREATE INDEX ix ON b (x);
    """
    assert _count_create_tables(sql) == 2


def test_schema_table_count_matches_the_shipped_schema() -> None:
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    expected = len(re.findall(r"(?im)^\s*create\s+table\b", sql))
    assert schema_table_count() == expected == 15
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_storage_db.py -k "create_tables or schema_table_count" -v`
Expected: FAIL — `ImportError: _count_create_tables`.

- [ ] **Step 3: Implement**

`src/bot/storage/db.py` (add `import re` if absent):

```python
_CREATE_TABLE = re.compile(
    r"^\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+", re.IGNORECASE | re.MULTILINE
)


def _count_create_tables(sql: str) -> int:
    """Count CREATE TABLE statements, ignoring SQL line comments."""
    uncommented = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return len(_CREATE_TABLE.findall(uncommented))


def schema_table_count() -> int:
    """Number of tables ``schema.sql`` defines (used by ``bot doctor``)."""
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    return _count_create_tables(sql)
```

`src/bot/ingest/universe.py` `_refresh_one_price`: delete the line `run.details = {"ticker": sym}` that follows `run.rows_affected = affected` (line ~574). The identical assignment at the top of the `with refresh_run(...)` block stays.

- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green (`test_cli_doctor.py` still passes).

- [ ] **Step 5: Commit**

```bash
git add src/bot/storage/db.py src/bot/ingest/universe.py tests/unit/test_storage_db.py
git commit -m "fix(storage): count CREATE TABLE statements robustly; drop a duplicated run.details write"
```

---

### Task 9: Reconcile the port design doc with the shipped `FxRate` (Spec finding c.1)

**Files:**
- Modify: `docs/superpowers/specs/2026-08-24-market-data-provider-port-design.md:48` (the `FxRate` field list)
- Modify: `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md` (append item 5 under `## Desviaciones aceptadas (post-review, 2026-08-22)`)

Decision: keep the code (`FxRate(date, rate_to_usd)`, currency carried by `upsert_fx_rates(currency=...)`) — the port plan's Task 1 tests and every caller already use it, and a per-row currency would only duplicate the keyword every call passes. Amend the design doc so the spec stops disagreeing with itself.

- [ ] **Step 1: Amend the design spec**

In the design doc, change the `FxRate` description to read: ``and `FxRate` (`date: date`, `rate_to_usd: float`) — the currency is the `fx_rates(currency, since)` argument and the `upsert_fx_rates(currency=...)` keyword, not a per-row field.`` Keep the rest of the sentence.

- [ ] **Step 2: Record the deviation**

Append to the `## Desviaciones aceptadas` list in the connect-phases plan:

```markdown
5. **`FxRate` no lleva `currency`** (el diseño del port lo listaba): la moneda
   viaja como argumento de `fx_rates(currency, since)` y como keyword de
   `upsert_fx_rates(currency=...)`, igual que en los tests de la Tarea 1 del
   plan del port. El diseño quedó corregido el 2026-08-24.
```

- [ ] **Step 3: Verify and commit**

Run: `grep -n "rate_to_usd" docs/superpowers/specs/2026-08-24-market-data-provider-port-design.md`
Expected: the amended line, with no `currency: str` inside the `FxRate` tuple.

```bash
git add docs/superpowers/specs/2026-08-24-market-data-provider-port-design.md docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md
git commit -m "docs(spec): FxRate carries no currency field — design doc matches the port"
```

---

### Task 10: The real-network run, attested (Spec finding a.1 — remediation plan Task 3)

**Files:**
- Modify: `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md` (append the attestation under `## Desviaciones aceptadas`)
- Possibly modify: `src/bot/ingest/damodaran/*`, `src/bot/ingest/fmp.py` plus regression tests, if the run breaks

**Blocked on:** a populated `.env` (FMP key; see `.env.example` and the README quickstart). This is user-provided; if `bot doctor` exits 1, stop and report — never fake the attestation.

- [ ] **Step 1: Preflight**

Run: `test -f .env && uv run bot doctor`
Expected: exit 0. On exit 1 → blocked; ask the user for credentials and stop this task.

- [ ] **Step 2: Sector benchmarks**

Run: `uv run bot refresh --damodaran`
Expected: US sector rows ingested with non-NULL WACC. On failure: use superpowers:systematic-debugging, fix the adapter, add a regression test for the failure shape, commit as `fix(damodaran): <what broke>`.

- [ ] **Step 3: Universe + prices, quota-bounded**

Run: `uv run bot refresh --fmp --limit 25 && uv run bot refresh --prices --limit 25`
Expected: ≥ 1 ticker imported; a 429 produces `deferred` outcomes and the English NOTE from Task 7; exit 0 unless > 5% of *attempted* tickers failed. Same fix protocol on failure. If quota allows, re-run without `--limit`.

- [ ] **Step 4: Screen and analyze**

Run: `uv run bot screen --preset damodaran_value --top 10 && uv run bot analyze --from-screen`
Expected: the screen report prints `Excluded (no sector benchmark, ADR 0006): N`; analyze writes one report per shortlisted ticker. Same fix protocol on failure.

- [ ] **Step 5: Attest with the real numbers**

Append to `## Desviaciones aceptadas` in `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md`, replacing every `<...>` with the figures observed in Steps 1–4 (never commit the template):

```markdown
### Corrida real (Tarea 13) — ejecutada 2026-08-<DD>

`doctor` OK · `refresh --damodaran` OK (<n> sectores) · `refresh --fmp/--prices
--limit 25`: <ok/deferred/failed> · `screen`: <candidatos, excluidos ADR 0006>
· `analyze --from-screen`: <n> reportes. Roturas encontradas y arregladas:
<lista de commits fix(...), o "ninguna">.
```

- [ ] **Step 6: Full gate and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: green/clean.

```bash
git add docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md
git commit -m "docs(plan): attest the real-network run of Task 13"
```

---

## Self-Review

- **Finding coverage:** Standards 1→T1, 2→T2, 3→T3, 4→T4, 5→T5, 6→T6, 7→T7, 8→T8 (both halves). Spec a.1→T10, c.1→T9. Spec (b) had no findings.
- **Placeholders:** the only `<...>` tokens are inside T10's attestation template, which the step explicitly says to fill from observed output.
- **Type consistency:** `conventional_override_path(Path | None, str) -> Path | None` is used identically at T1's two call sites; `coerce_date(object) -> date | None` returns `None`, so T3's `_as_date` wrapper raises rather than leaking `None`; `TickerStatus` in T5 is a `Literal`, so `Counter[TickerStatus]` keys are exactly the four strings; T5's required `source` params are updated at every caller listed by the grep in its Step 3; T8's `_count_create_tables` name matches its test import.
- **Order:** T1–T8 are independent of each other except that T7's grep should run after T1–T6 so it sees their final strings; T9 is docs-only; T10 last, and it is the only task that may be blocked (credentials).
