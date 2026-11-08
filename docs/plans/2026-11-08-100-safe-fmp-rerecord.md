# Safe FMP Re-record Implementation Plan (#100)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uv run pytest -m integration --vcr-record=all` records the FMP cassettes with the real `BOT_FMP_API_KEY`. It refuses to run without that key, and it never writes a non-2xx response to disk. Replay stays exactly as it is.

**Architecture:** `tests/vcr_settings.py` gains three things: the dummy key constant, a pure resolver `fmp_test_key(record, environ)`, and a `before_record_response` hook in `VCR_CONFIG` that drops non-2xx responses. `tests/integration/conftest.py` exposes the resolver as a session-scoped `fmp_api_key` fixture. The five FMP integration modules use that fixture in place of their hard-coded `API_KEY`. Offline proofs: a subprocess pytest run over a copy of the FMP tests and cassettes, and a loopback `http.server` that answers 401.

**Tech Stack:** Python 3.12, pytest 8, pytest-vcr 1.0.2, vcrpy 8.1.1, httpx, uv.

**Spec:** GitHub issue nicolas-ricc/damodaran#100, the "Agent Brief" comment.

## Global Constraints

- In replay mode (the default), nothing changes: the dummy key is used and cassettes are replayed. `uv run pytest -q` passes with no real key.
- Record mode active, no real key: FMP tests "skip or fail with a clear message before any request", and no cassette file is modified (proven offline).
- "A non-2xx response is never written to a cassette." Proven offline with a loopback server, like `tests/unit/test_vcr_record_switch.py`.
- "The key is still scrubbed from recordings." `filter_query_parameters` keeps `("apikey", "SCRUBBED")`.
- The README re-record paragraph (`README.md:106-111`) matches the new behaviour.
- Out of scope: actually re-recording (#52), and the SEC EDGAR and IBKR Flex cassettes. No cassette content changes.
- Do not write the token `record_mode` in new comments or docstrings (#99 grep criterion, `docs/plans/2026-10-06-99-vcr-hardening.md`).
- Suite: `uv run pytest -q`. Lint: `uv run ruff check . && uv run mypy src`. Conventional commits referencing #100.

## Declared technical assumptions

- **A1 — fail, not skip.** With a record mode set and no real key, each FMP test errors at fixture setup through `pytest.fail(..., pytrace=False)`. The run exits non-zero. Rejected alternative: skip. A skipped re-record looks green, and the human would believe the cassettes were refreshed. To re-record SEC EDGAR alone, pass its test paths.
- **A2 — "record mode active"** means pytest-vcr's effective option is something other than `"none"`. That option is `--vcr-record` or, failing that, the deprecated `--vcr-record-mode` (`pytest_vcr._update_kwargs`). `None` and `"none"` mean replay. `--disable-vcr` records nothing and is not covered.
- **A3 — "no real key"** means `BOT_FMP_API_KEY` in `os.environ` is unset, blank after `strip()`, or equal to the dummy `"test-fmp-key"`. A key held only in `.env` does not count. The README says to export the key.
- **A4 — reading the real key.** The root autouse fixture `_default_fmp_api_key` is function-scoped and overwrites the variable for every test. `fmp_api_key` is session-scoped, and pytest sets up wider scopes first, so it reads `os.environ` before that override applies. Each earlier test's monkeypatch is undone at its own teardown.
- **A5 — the hook is shared.** The non-2xx hook goes into `VCR_CONFIG`, so SEC EDGAR and IBKR Flex recordings get it too. Every cassette on disk holds only `code: 200` responses, so replay is unaffected. vcrpy also runs the hook on load (`Cassette._load` → `append`).
- **A6 — drop, not raise.** The hook returns `None` for status codes outside 200-299, which is vcrpy's documented way to skip one interaction. The client still receives the real response, so `raise_for_status` fails the test loudly. When every response is dropped, the cassette is never marked dirty and its file is not rewritten.

## Review Focus

1. A real key equal to the dummy (`BOT_FMP_API_KEY=test-fmp-key` exported) must count as missing. Pinned in Task 1 (`test_dummy_key_counts_as_missing`).
2. A whitespace-only key must count as missing. Pinned in Task 1 (`test_blank_key_counts_as_missing`).
3. The deprecated `--vcr-record-mode=all` must trigger the guard just like `--vcr-record=all`. Pinned in Task 1 (`test_record_option_reads_deprecated_flag`).
4. A 401 during re-record of an existing cassette must leave that file byte-identical, not just keep 401 bodies out of new files. Pinned in Task 2 (`test_error_response_leaves_existing_cassette_untouched`).
5. The guard must fire before any request leaves the machine. Pinned in Task 1: the subprocess runs with `HTTPS_PROXY`/`HTTP_PROXY` pointing at a dead loopback port, and the test asserts the message plus unchanged bytes.

---

### Task 1: Real key when recording, refusal without one

**Files:**
- Modify: `tests/vcr_settings.py`
- Modify: `tests/integration/conftest.py`
- Modify: `tests/conftest.py` (use `DUMMY_FMP_KEY`; docstring sentence on recording)
- Modify: `tests/integration/test_fmp_client.py`, `test_fmp_import.py`, `test_fx_import.py`, `test_prices_import.py`, `test_universe_refresh.py`: delete `API_KEY = "test-fmp-key"`, take the `fmp_api_key: str` fixture, and pass it wherever `API_KEY` was used
- Test: `tests/unit/test_vcr_settings.py` (extend), `tests/unit/test_fmp_record_guard.py` (new)

**Interfaces:**
- Produces, in `tests/vcr_settings.py`:
  - `DUMMY_FMP_KEY: str = "test-fmp-key"`
  - `class MissingFmpKeyError(RuntimeError)`
  - `record_option(config: pytest.Config) -> str | None`: `config.getoption("--vcr-record") or config.getoption("--vcr-record-mode")`
  - `fmp_test_key(record: str | None, environ: Mapping[str, str]) -> str`: `DUMMY_FMP_KEY` when `record in (None, "none")`. Otherwise the stripped `environ["BOT_FMP_API_KEY"]`. Raises `MissingFmpKeyError` when that is blank or equals the dummy. The message names `BOT_FMP_API_KEY` and the record mode, and says that nothing was recorded.
- Produces, in `tests/integration/conftest.py`: the session-scoped fixture `fmp_api_key(pytestconfig: pytest.Config) -> str`. It calls `fmp_test_key(record_option(pytestconfig), os.environ)` and turns `MissingFmpKeyError` into `pytest.fail(str(err), pytrace=False)`.

- [ ] **Step 1: Write the failing unit tests** (in `tests/unit/test_vcr_settings.py`)

```python
@pytest.mark.parametrize("record", [None, "none"])
def test_replay_uses_dummy_key_even_with_real_one(record: str | None) -> None:
    assert fmp_test_key(record, {"BOT_FMP_API_KEY": "real"}) == DUMMY_FMP_KEY

@pytest.mark.parametrize("record", ["once", "new_episodes", "all"])
def test_recording_uses_real_key(record: str) -> None:
    assert fmp_test_key(record, {"BOT_FMP_API_KEY": " real-key "}) == "real-key"

def test_recording_without_key_raises() -> None:
    with pytest.raises(MissingFmpKeyError, match="BOT_FMP_API_KEY"):
        fmp_test_key("all", {})

def test_dummy_key_counts_as_missing() -> None:
    with pytest.raises(MissingFmpKeyError):
        fmp_test_key("all", {"BOT_FMP_API_KEY": DUMMY_FMP_KEY})

def test_blank_key_counts_as_missing() -> None:
    with pytest.raises(MissingFmpKeyError):
        fmp_test_key("all", {"BOT_FMP_API_KEY": "   "})

def test_record_option_reads_deprecated_flag(pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch) -> None:
    # Fake getoption: --vcr-record unset, --vcr-record-mode="all" -> "all"
    ...
```

The last test monkeypatches `pytestconfig.getoption` with a dict lookup: `{"--vcr-record": None, "--vcr-record-mode": "all"}` gives `"all"`, and `{"--vcr-record": "once", "--vcr-record-mode": "all"}` gives `"once"`.

- [ ] **Step 2: Write the failing offline end-to-end proof** in `tests/unit/test_fmp_record_guard.py`, test `test_record_without_key_aborts_and_keeps_cassettes`:
  - Copy into `tmp_path`: `pyproject.toml`, `tests/__init__.py`, `tests/conftest.py`, `tests/vcr_settings.py`, `tests/integration/__init__.py`, `tests/integration/conftest.py`, `tests/integration/test_fmp_client.py`, and the whole `tests/fixtures/cassettes/fmp/` directory. Snapshot `{name: bytes}` of the copied cassettes.
  - Build the env from `os.environ` minus `BOT_FMP_API_KEY`, plus `HTTPS_PROXY` and `HTTP_PROXY` set to `http://127.0.0.1:9` (a leak fails fast instead of reaching FMP).
  - Run `[sys.executable, "-m", "pytest", "tests/integration/test_fmp_client.py", "--vcr-record=all", "-p", "no:cacheprovider", "-q"]` with `cwd=tmp_path`, `capture_output=True`, `text=True`, `timeout=120`.
  - Assert `returncode != 0`, `"BOT_FMP_API_KEY" in stdout`, and the cassette snapshot after equals the one before (same names, same bytes).
  - A second parametrised case passes `BOT_FMP_API_KEY=test-fmp-key` and expects the same result.

- [ ] **Step 3: Run to verify they fail.** `uv run pytest tests/unit/test_vcr_settings.py tests/unit/test_fmp_record_guard.py -q`. Expected: ImportError on `fmp_test_key`. The subprocess test fails because there is no message.

- [ ] **Step 4: Implement** the Interfaces above. Replace `API_KEY` in the five modules. In `test_universe_refresh.py`, `_CassetteFmpProvider(cassette_dir, fmp_api_key, ...)`. The root conftest sets `DUMMY_FMP_KEY`.

- [ ] **Step 5: Verify.** `uv run pytest -q tests/unit/test_vcr_settings.py tests/unit/test_fmp_record_guard.py tests/integration && git status --porcelain tests/fixtures`. Expected: all pass, and no cassette is modified. Then `grep -rn '"test-fmp-key"' tests/` must show only `tests/vcr_settings.py` and test files that assert on it.

- [ ] **Step 6: Commit** `fix(#100): FMP tests record with the real key and refuse without one`

---

### Task 2: Never persist a non-2xx response; README

**Files:**
- Modify: `tests/vcr_settings.py` (`VCR_CONFIG["before_record_response"]`)
- Test: `tests/unit/test_vcr_record_switch.py` (extend), `tests/unit/test_vcr_settings.py` (extend)
- Modify: `README.md:106-111`; the "Re-record ..." docstring sentence in the five FMP integration modules

**Interfaces:**
- Consumes: `fmp_test_key`, `DUMMY_FMP_KEY` (Task 1).
- Produces: `drop_error_response(response: dict[str, Any]) -> dict[str, Any] | None` in `tests/vcr_settings.py`. It returns `response` when `200 <= response["status"]["code"] < 300` and `None` otherwise. `VCR_CONFIG["before_record_response"] = drop_error_response`.

- [ ] **Step 1: Write the failing tests**
  - `test_vcr_settings.py`: `test_drop_error_response` is parametrised over codes `200, 204` (kept, the same object is returned) and `301, 401, 403, 404, 429, 500` (gives `None`). Also add `test_error_hook_is_shared`: `VCR_CONFIG["before_record_response"] is drop_error_response`.
  - `test_vcr_record_switch.py`: add a second loopback handler that answers `401` with the JSON body `{"Error Message": "Invalid API KEY."}`, plus its fixture `unauthorized_url`.
    - `test_error_response_is_not_recorded(unauthorized_url, tmp_path)`: record into a missing `tmp_path / "new.yaml"` with `VCR_CONFIG | {"record_mode": "all"}`. `FmpClient(...).lookup_company("AAPL")` raises `httpx.HTTPStatusError`. Assert `not (tmp_path / "new.yaml").exists()`.
    - `test_error_response_leaves_existing_cassette_untouched(unauthorized_url, tmp_path)`: copy `tests/fixtures/cassettes/fmp/test_lookup_company_us.yaml` into `tmp_path`, record over it with `"all"` (`HTTPStatusError`), and assert the bytes are unchanged.
    - Extend `test_record_all_writes_scrubbed_cassette` so the key comes from `fmp_test_key("all", {"BOT_FMP_API_KEY": FAKE_KEY})`, and assert `FAKE_KEY not in text`. This keeps the "no API key in recordings" criterion tied to the recording path.

- [ ] **Step 2: Run to verify they fail.** `uv run pytest tests/unit/test_vcr_settings.py tests/unit/test_vcr_record_switch.py -q`. Expected: ImportError on `drop_error_response`.

- [ ] **Step 3: Implement** `drop_error_response` and wire it into `VCR_CONFIG`, with a one-line comment: a 401/403 must never replace a cassette.

- [ ] **Step 4: README and docstrings.** Replace the last sentence of the FMP paragraph (`README.md:109-111`) with:

```markdown
`tests/fixtures/cassettes/SYNTHETIC.txt`); the suite only replays them, with a dummy key. To
re-record, export a real key and run `BOT_FMP_API_KEY=<key> uv run pytest -m integration --vcr-record=all`:
with a record mode set the FMP tests use that key and fail before any request if it is missing, and a
non-2xx response is never written to a cassette (the key is scrubbed as `apikey=SCRUBBED`). Recording
rewrites each file, dropping its `# SYNTHETIC` header; then remove its entry from `SYNTHETIC.txt`.
```

  In the five module docstrings, "with a real BOT_FMP_API_KEY via ..." becomes "by exporting a real BOT_FMP_API_KEY and running ...". The `tests/vcr_settings.py` module docstring gains a sentence: recording uses the exported key, and error responses are dropped.

- [ ] **Step 5: Verify.** Full `uv run pytest -q`, then `uv run ruff check . && uv run mypy src`. `git status --porcelain tests/fixtures` must be empty.

- [ ] **Step 6: Commit** `fix(#100): never record a non-2xx response; README re-record steps`

---

### Close-out

- [ ] `grep -rn 'record_mode' tests/`: the only new hits are the `"all"` literals in test code, with none in comments or docstrings.
- [ ] No `estado.html` or ADR change: FMP stays dormant (ADR 0007), and test infrastructure is not a component in the plans.
