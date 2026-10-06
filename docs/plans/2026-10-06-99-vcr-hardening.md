# VCR Layer Hardening Implementation Plan (#99)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The test suite can never reach the network through VCR. Synthetic cassettes are pinned by an allowlist. The parsed FMP output gets a shape test. A network-free test proves that the re-record switch works and scrubs the API key.

**Architecture:** One shared module, `tests/vcr_settings.py`, owns the scrub lists, the default record mode and the cassette-directory rule. `tests/integration/conftest.py` exposes it through pytest-vcr's `vcr_config` / `vcr_cassette_dir` fixtures. Tests that build their own `vcr.VCR` import it directly. `FmpClient` and `FmpProvider` gain a `base_url` keyword so a local `http.server` can stand in for FMP.

**Tech Stack:** Python 3.12, pytest 8, pytest-vcr 1.0.2, vcrpy 8.1, httpx, uv.

**Spec:** GitHub issue nicolas-ricc/damodaran#99 ("Harden the VCR layer: record mode none, synthetic-cassette allowlist, FMP parser shape test").

## Global Constraints

- No outbound network, no API key. Every cassette on disk is replayed and none is written.
- Do not touch the SEC EDGAR cassettes (`tests/fixtures/cassettes/sec_edgar/*.yaml`), and do not touch any other cassette content either.
- Do not change which provider is the default. Edit the FMP parser only to add the `base_url` parameter.
- `grep -rn 'record_mode' tests/` shows exactly one `"none"` default plus the `"all"` in the stub test. No `"once"` remains. Do not write the token `record_mode` in comments or docstrings.
- The exact-value assertions in the existing integration tests stay.
- Re-record command: `uv run pytest -m integration --vcr-record=all`.
- Suite: `uv run pytest -q`. Lint: `uv run ruff check . && uv run mypy src`.
- Conventional commits referencing #99.

## Declared technical assumptions (from reading the code)

- **A1 — statement dates.** `parse_fmp_fundamentals` emits `period_end_date` as an ISO `YYYY-MM-DD` string (`src/bot/ingest/fmp.py:520`), and `filings[*].filing_date` likewise. Asserting `isinstance(..., date)` would require editing the parser, which the issue puts out of scope. The shape test therefore asserts that each statement date is a `str` for which `date.fromisoformat` returns a `date`.
- **A2 — market cap.** Neither `FundamentalsBundle` nor `CompanyInfo` has a market-cap field, and none of the 7 shape cassettes contains `marketCap`. The test asserts "when present": any `market_cap` key with a non-`None` value, in any parsed row or in the company dict, must be a positive `float`. Today that check is vacuous. It bites once the cassettes are re-recorded.
- **A3 — one cassette, one replay.** vcrpy plays each recorded response once per cassette context. `fundamentals` and `lookup_company` are therefore replayed in two separate `use_cassette` contexts over the same file.
- **A4 — cassette dir rule.** The module name decides: a module whose basename contains `sec_edgar` maps to `sec_edgar`, every other module maps to `fmp`. This covers `test_fmp_client`, `test_fmp_import`, `test_fx_import`, `test_prices_import` → `fmp`, and `test_sec_edgar_client`, `test_sec_edgar_import` → `sec_edgar`. The universe test keeps its own `universe/` dir.
- **A5 — SEC header scrub.** The SEC files filtered `User-Agent` on record. The shared config carries that filter for every module. Header filters do not take part in request matching, so replay of the FMP cassettes is unchanged.
- **A6 — grep criterion.** Besides the `"none"` default and the stub's `"all"`, the grep also shows one plumbing line that contains no literal: `vcr_kwargs` applying the `--vcr-record` override. That line is what lets the hand-built universe VCR honour the re-record command.

## Review Focus

1. A test module that adds `@pytest.mark.vcr` with no matching cassette must raise rather than hit the network. Pinned in Task 1 (`test_missing_cassette_is_refused`).
2. Running `--vcr-record=all` must also re-record the universe cassettes, not only the pytest-vcr fixture tests. Pinned in Task 1 (`test_vcr_kwargs_applies_override`).
3. Removing the `SYNTHETIC` header from any single listed cassette must fail the allowlist test. Pinned in Task 2, parametrised over all 17.
4. A synthetic header that appears on line 2 or later must not count. Only the first line counts. Pinned in Task 2 (`test_header_below_first_line_is_not_synthetic`).
5. The scrubbed recording must not leak the key anywhere in the YAML (body, URI). Pinned in Task 3 (asserts the fake key is absent from the whole file).

---

### Task 1: Shared VCR settings and a single integration conftest

**Files:**
- Create: `tests/vcr_settings.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/unit/test_vcr_settings.py`
- Modify: `tests/integration/test_fmp_client.py`, `test_fmp_import.py`, `test_fx_import.py`, `test_prices_import.py`, `test_sec_edgar_client.py`, `test_sec_edgar_import.py` (delete their `vcr_config` / `vcr_cassette_dir` fixtures; rewrite the "MUST be re-recorded" docstring sentences)
- Modify: `tests/integration/test_universe_refresh.py` (`_cassette_vcr` uses `vcr_kwargs`; docstring)
- Modify: `README.md` (FMP paragraph, around line 111)

**Interfaces:**
- Produces, in `tests/vcr_settings.py`:
  - `VCR_CONFIG: dict[str, object]`, holding the apikey scrub, the User-Agent scrub and the `"none"` default
  - `vcr_kwargs(record: str | None = None) -> dict[str, object]`
  - `cassette_subdir(module_name: str) -> str`

- [ ] **Step 1: Write the failing tests** (already committed in stage 3 as `tests/unit/test_vcr_settings.py`)

```python
"""The shared VCR settings: replay-only by default, apikey scrubbed everywhere."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import vcr
from vcr.errors import CannotOverwriteExistingCassetteException

from tests.vcr_settings import VCR_CONFIG, cassette_subdir, vcr_kwargs


def test_missing_cassette_is_refused(tmp_path: Path) -> None:
    with (
        vcr.VCR(**VCR_CONFIG).use_cassette(str(tmp_path / "absent.yaml")),
        pytest.raises(CannotOverwriteExistingCassetteException),
    ):
        httpx.get("http://127.0.0.1:9/never")
    assert not (tmp_path / "absent.yaml").exists()


def test_apikey_is_scrubbed_by_default() -> None:
    assert ("apikey", "SCRUBBED") in VCR_CONFIG["filter_query_parameters"]


def test_vcr_kwargs_defaults_to_shared_config() -> None:
    assert vcr_kwargs() == VCR_CONFIG
    assert vcr_kwargs(None) == VCR_CONFIG


def test_vcr_kwargs_applies_override() -> None:
    kwargs = vcr_kwargs("all")
    assert kwargs != VCR_CONFIG
    assert kwargs["filter_query_parameters"] == VCR_CONFIG["filter_query_parameters"]
    assert VCR_CONFIG == vcr_kwargs()  # the shared dict is not mutated


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("tests.integration.test_fmp_client", "fmp"),
        ("tests.integration.test_fmp_import", "fmp"),
        ("tests.integration.test_fx_import", "fmp"),
        ("tests.integration.test_prices_import", "fmp"),
        ("tests.integration.test_sec_edgar_client", "sec_edgar"),
        ("tests.integration.test_sec_edgar_import", "sec_edgar"),
    ],
)
def test_cassette_subdir_follows_module_name(module: str, expected: str) -> None:
    assert cassette_subdir(module) == expected
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_vcr_settings.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'tests.vcr_settings'`.

- [ ] **Step 3: Create `tests/vcr_settings.py`**

```python
"""The one VCR configuration every cassette-backed test uses.

Replay only: a missing cassette raises instead of reaching the network. To
re-record against the live APIs, run
``uv run pytest -m integration --vcr-record=all``.
"""

from __future__ import annotations

VCR_CONFIG: dict[str, object] = {
    # FMP authenticates with an ``apikey`` query param; SEC EDGAR wants a
    # contact User-Agent. Neither may land in a cassette.
    "filter_query_parameters": [("apikey", "SCRUBBED")],
    "filter_headers": [("User-Agent", "Tester t@example.com")],
    "record_mode": "none",
}


def vcr_kwargs(record: str | None = None) -> dict[str, object]:
    """``VCR_CONFIG`` with pytest-vcr's ``--vcr-record`` value applied, if any."""
    return VCR_CONFIG | {"record_mode": record} if record else dict(VCR_CONFIG)


def cassette_subdir(module_name: str) -> str:
    """The cassette folder under ``tests/fixtures/cassettes`` for a test module."""
    return "sec_edgar" if "sec_edgar" in module_name.rsplit(".", 1)[-1] else "fmp"
```

`vcr_kwargs` carries the one plumbing line A6 describes.

- [ ] **Step 4: Create `tests/integration/conftest.py`**

```python
"""pytest-vcr fixtures shared by every cassette-backed integration test."""

from __future__ import annotations

import pytest

from tests.vcr_settings import VCR_CONFIG, cassette_subdir


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return dict(VCR_CONFIG)


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    subdir = cassette_subdir(request.module.__name__)
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / subdir)
```

- [ ] **Step 5: Delete the per-file fixtures.** In each of the six integration files, remove both `@pytest.fixture(scope="module") def vcr_cassette_dir...` and `def vcr_config...`. Drop the `import pytest` only if it becomes unused (it stays wherever `@pytest.mark.vcr` is used, which is every file).

- [ ] **Step 6: Universe test.** In `tests/integration/test_universe_refresh.py`:
  - `_cassette_vcr()` becomes `_cassette_vcr(record: str | None) -> vcr.VCR: return vcr.VCR(**vcr_kwargs(record))`.
  - `_CassetteFmpProvider.__init__` gains a keyword `record: str | None = None` and stores it.
  - `_use_cassette` calls `_cassette_vcr(self._record)`.
  - The tests take the `pytestconfig: pytest.Config` fixture and pass `record=pytestconfig.getoption("--vcr-record")` to every `_CassetteFmpProvider(...)`.
  - Import `from tests.vcr_settings import vcr_kwargs`.

- [ ] **Step 7: Docstrings and README.** Replace each "MUST be re-recorded against the live FMP API with a real BOT_FMP_API_KEY before production use" sentence (test_fmp_client, test_fmp_import, test_fx_import, test_prices_import, test_universe_refresh) with: "Re-record them against the live API with a real BOT_FMP_API_KEY via ``uv run pytest -m integration --vcr-record=all``." In `README.md`, append to the FMP paragraph:

```markdown
Its test cassettes under `tests/fixtures/cassettes/{fmp,universe}/` are synthetic (listed in
`tests/fixtures/cassettes/SYNTHETIC.txt`); the suite only replays them. Re-record against the live
API with a real key via `uv run pytest -m integration --vcr-record=all`, then remove the
`# SYNTHETIC` header and the entry in `SYNTHETIC.txt`.
```

- [ ] **Step 8: Verify**

Run: `uv run pytest -q tests/unit/test_vcr_settings.py tests/integration && grep -rn 'record_mode' tests/ && git status --porcelain tests/fixtures`
Expected: all pass. The grep shows no `"once"`, and `git status` shows no cassette modified.

- [ ] **Step 9: Commit** `refactor(#99): one shared VCR config, replay-only by default`

---

### Task 2: Synthetic-cassette allowlist

**Files:**
- Create: `tests/fixtures/cassettes/SYNTHETIC.txt`
- Create: `tests/unit/test_cassette_headers.py`

**Interfaces:** none consumed. `SYNTHETIC.txt` holds one path per line, relative to `tests/fixtures/cassettes/`, sorted.

- [ ] **Step 1: Write the failing test** (committed in stage 3)

```python
"""Pins which cassettes are synthetic (hand-authored) to SYNTHETIC.txt."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes"


def _listed(root: Path) -> set[str]:
    return {
        line.strip()
        for line in (root / "SYNTHETIC.txt").read_text().splitlines()
        if line.strip()
    }


def _headed(root: Path) -> set[str]:
    out = set()
    for path in root.rglob("*.yaml"):
        with path.open() as fh:
            if "SYNTHETIC" in fh.readline():
                out.add(path.relative_to(root).as_posix())
    return out


def test_synthetic_headers_match_allowlist() -> None:
    assert _headed(CASSETTES) == _listed(CASSETTES)


def test_allowlist_has_the_17_fmp_cassettes() -> None:
    listed = _listed(CASSETTES)
    assert len(listed) == 17
    assert all(p.startswith(("fmp/", "universe/")) for p in listed)


@pytest.mark.parametrize("entry", sorted(_listed(CASSETTES)))
def test_dropping_a_header_breaks_the_match(tmp_path: Path, entry: str) -> None:
    root = tmp_path / "cassettes"
    shutil.copytree(CASSETTES, root)
    target = root / entry
    target.write_text(target.read_text().split("\n", 1)[1])
    assert _headed(root) != _listed(root)


def test_unlisted_synthetic_cassette_breaks_the_match(tmp_path: Path) -> None:
    root = tmp_path / "cassettes"
    shutil.copytree(CASSETTES, root)
    (root / "fmp" / "extra.yaml").write_text("# SYNTHETIC cassette\ninteractions: []\n")
    assert _headed(root) != _listed(root)


def test_header_below_first_line_is_not_synthetic(tmp_path: Path) -> None:
    (tmp_path / "SYNTHETIC.txt").write_text("")
    (tmp_path / "a.yaml").write_text("interactions: []\n# SYNTHETIC\n")
    assert _headed(tmp_path) == set()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_cassette_headers.py -q`
Expected: collection error / `FileNotFoundError` on `SYNTHETIC.txt`.

- [ ] **Step 3: Create `SYNTHETIC.txt`**

```bash
cd tests/fixtures/cassettes && for f in $(find . -name '*.yaml' | sort); do head -1 "$f" | grep -q SYNTHETIC && echo "${f#./}"; done > SYNTHETIC.txt
```

Expected content: the 12 `fmp/*.yaml` and the 5 `universe/*.yaml`, 17 lines.

- [ ] **Step 4: Run it to verify it passes.** Same command. Expected: PASS.

- [ ] **Step 5: Commit** `test(#99): pin synthetic cassettes to SYNTHETIC.txt`

---

### Task 3: `base_url` pass-through and the record-switch proof

**Files:**
- Modify: `src/bot/ingest/fmp.py` (`FmpClient.__init__` line ~64; `FmpProvider.__init__` line ~255 and `_fmp`)
- Create: `tests/unit/test_vcr_record_switch.py`

**Interfaces:**
- Consumes: `VCR_CONFIG` from Task 1.
- Produces: `FmpClient(api_key: str, timeout: float = 30.0, base_url: str = BASE_URL)` and `FmpProvider(api_key: str, timeout: float = 30.0, base_url: str = BASE_URL)`.

- [ ] **Step 1: Write the failing test** (committed in stage 3)

```python
"""Proves the re-record switch writes a scrubbed cassette, with no network."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import vcr

from bot.ingest.fmp import FmpClient, FmpProvider
from tests.vcr_settings import VCR_CONFIG

FAKE_KEY = "fake-key-do-not-record"

PROFILE = [
    {
        "symbol": "AAPL",
        "companyName": "Apple Inc.",
        "exchange": "NASDAQ",
        "exchangeShortName": "NASDAQ",
        "country": "US",
        "currency": "USD",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "isActivelyTrading": True,
        "ipoDate": "1980-12-12",
    }
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(PROFILE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def stub_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/stable"
    server.shutdown()
    server.server_close()


def test_record_all_writes_scrubbed_cassette(stub_url: str, tmp_path: Path) -> None:
    cassette = tmp_path / "recorded.yaml"
    recorder = vcr.VCR(**(VCR_CONFIG | {"record_mode": "all"}))
    with recorder.use_cassette(str(cassette)), FmpClient(api_key=FAKE_KEY, base_url=stub_url) as client:
        info = client.lookup_company("AAPL")
    assert info is not None and info.ticker == "AAPL"
    text = cassette.read_text()
    assert "apikey=SCRUBBED" in text
    assert FAKE_KEY not in text


def test_provider_passes_base_url_through(stub_url: str) -> None:
    with FmpProvider(api_key=FAKE_KEY, base_url=stub_url) as provider:
        info = provider.lookup_company("AAPL")
    assert info is not None and info.name == "Apple Inc."
```

Check `FmpClient.lookup_company` (`src/bot/ingest/fmp.py:96`) for the exact profile keys it reads, and align `PROFILE` with them if they differ.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_vcr_record_switch.py -q`
Expected: `TypeError: ... unexpected keyword argument 'base_url'`.

- [ ] **Step 3: Implement**

```python
    def __init__(self, api_key: str, timeout: float = 30.0, base_url: str = BASE_URL) -> None:
        ...
        self._client = httpx.Client(
            base_url=base_url,
```

```python
    def __init__(self, api_key: str, timeout: float = 30.0, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._base_url = base_url
        self._client: FmpClient | None = None
    ...
            self._client = FmpClient(
                api_key=self._api_key, timeout=self._timeout, base_url=self._base_url
            )
```

- [ ] **Step 4: Run it to verify it passes,** then `uv run mypy src && uv run ruff check .`.

- [ ] **Step 5: Commit** `feat(#99): FmpClient base_url, proof that --vcr-record scrubs the key`

---

### Task 4: FMP parser shape test

**Files:**
- Create: `tests/unit/test_fmp_shapes.py`

**Interfaces:** Consumes `VCR_CONFIG` (Task 1) and `FmpProvider` (unchanged API).

- [ ] **Step 1: Write the test** (committed in stage 3. It fails only until Task 1's `tests/vcr_settings.py` exists)

```python
"""Shape of the parsed FMP output, independent of the (synthetic) values.

Each cassette is replayed through ``FmpProvider`` in replay-only mode. The
exact-value checks stay in the integration tests; this file asserts only types
and nullness, so it keeps holding once the cassettes are re-recorded live.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import vcr

from bot.ingest.fmp import FmpProvider
from bot.ingest.provider import CompanyInfo, FundamentalsBundle
from tests.vcr_settings import VCR_CONFIG

CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes"

CASES = [
    ("universe/AAPL.yaml", "AAPL"),
    ("universe/MSFT.yaml", "MSFT"),
    ("universe/NVDA.yaml", "NVDA"),
    ("universe/NESN.SW.yaml", "NESN.SW"),
    ("universe/SAP.DE.yaml", "SAP.DE"),
    ("fmp/test_import_company_from_fmp_us_populates_db.yaml", "AAPL"),
    ("fmp/test_import_company_from_fmp_non_us_has_local_currency.yaml", "NESN.SW"),
]


def _replay(cassette: str) -> Any:
    return vcr.VCR(**VCR_CONFIG).use_cassette(str(CASSETTES / cassette))


def _assert_info_shape(info: CompanyInfo | None) -> None:
    assert info is not None
    assert isinstance(info.currency, str)
    assert len(info.currency) == 3 and info.currency.isalpha() and info.currency.isupper()
    assert isinstance(info.country, str)
    assert len(info.country) == 2 and info.country.isalpha() and info.country.isupper()
    assert info.ipo_date is None or isinstance(info.ipo_date, date)


def _assert_iso_date(value: object) -> None:
    # The parser emits DB-row dates as ISO strings (see plan assumption A1).
    assert isinstance(value, str)
    assert isinstance(date.fromisoformat(value), date)


def _assert_market_cap(row: dict[str, Any]) -> None:
    cap = row.get("market_cap")
    if cap is not None:
        assert isinstance(cap, float) and cap > 0


def _assert_bundle_shape(bundle: FundamentalsBundle) -> None:
    _assert_info_shape(bundle.info)
    _assert_market_cap(bundle.annual.company)
    assert len(bundle.annual.annual) >= 1
    for row in [*bundle.annual.annual, *bundle.quarterly.quarterly]:
        assert type(row["fiscal_year"]) is int
        assert 1990 <= row["fiscal_year"] <= 2100
        _assert_iso_date(row["period_end_date"])
        _assert_market_cap(row)
    for filing in bundle.filings:
        _assert_iso_date(filing["filing_date"])


@pytest.mark.parametrize(("cassette", "ticker"), CASES, ids=[c for c, _ in CASES])
def test_fundamentals_shape(cassette: str, ticker: str) -> None:
    with _replay(cassette), FmpProvider(api_key="shape-test") as provider:
        bundle = provider.fundamentals(ticker)
    _assert_bundle_shape(bundle)


@pytest.mark.parametrize(("cassette", "ticker"), CASES, ids=[c for c, _ in CASES])
def test_lookup_company_shape(cassette: str, ticker: str) -> None:
    # A separate cassette context: each recorded response replays only once.
    with _replay(cassette), FmpProvider(api_key="shape-test") as provider:
        info = provider.lookup_company(ticker)
    _assert_info_shape(info)
```

Confirm the ticker of the non-US import cassette from its request URIs (`grep 'symbol=' <file>`) before relying on `NESN.SW`.

- [ ] **Step 2: Run it.** `uv run pytest tests/unit/test_fmp_shapes.py -q`. Expected: 14 pass once Task 1 is in. If a case fails, read the cassette. A genuine shape violation in a synthetic cassette is a finding to report, not a reason to loosen the assertion.

- [ ] **Step 3: Commit** `test(#99): shape test for parsed FMP output`

---

### Task 5: Close-out

- [ ] Full suite `uv run pytest -q`, lint `uv run ruff check . && uv run mypy src`.
- [ ] `git status --porcelain tests/fixtures/cassettes` is empty apart from the new `SYNTHETIC.txt`.
- [ ] `grep -rn 'record_mode' tests/` matches the A6 expectation.
- [ ] `python3 docs/plano/build.py` still builds. No `estado.html` change: FMP stays dormant, and test infrastructure is not one of its components.
