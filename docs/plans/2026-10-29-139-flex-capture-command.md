# bot flex-capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hidden `bot flex-capture` command that pulls one Flex statement through the existing client and writes a scrubbed, redacted VCR cassette, the redacted XML and a JSON summary under fixed paths.

**Architecture:** `ibkr_flex.py` gains a `fetch_flex_statement` seam so the client class stays private to its module. `ibkr_flex_capture.py` (which already holds `redact_statement` / `summarize_statement` from #138) gains an `httpx.BaseTransport` wrapper that records each exchange, a renderer that turns the recording into vcrpy v1 YAML (token scrubbed, statement redacted, headers reduced to `Content-Type`, token-leak check), and `capture()` that renders all three artefacts in memory before writing any. `cli.py` exposes it as a hidden Typer command with exit codes 2 (missing settings) and 1 (Flex failure or token leak).

**Tech Stack:** Python 3, httpx 0.28, PyYAML, Typer, pytest, vcrpy 8.1 (tests only), mypy --strict, ruff.

**Spec:** GitHub issue #139 (nicolas-ricc/damodaran), "[M5.7b-2] bot flex-capture: record a scrubbed cassette, redacted XML and JSON summary from the live Flex endpoint"; story context and design decisions in the plan comment of parent #110.

## Global Constraints

- The string `FlexClient` appears only in `src/bot/ingest/ibkr_flex.py` — not in the capture module, `cli.py` or any test added here, not even in a comment (`tests/unit/test_seam_enforcement.py::test_flex_client_is_internal_to_its_module`).
- Do not import `vcr` anywhere under `src/`; it is dev-only.
- Fixed paths, relative to the repo root: `CASSETTE_PATH = Path("tests/fixtures/cassettes/ibkr_flex/statement_real.yaml")`, `REDACTED_XML_PATH = Path("tests/fixtures/ibkr_flex/statement_real_redacted.xml")`, `SUMMARY_PATH = Path("tests/fixtures/ibkr_flex/statement_real_summary.json")`.
- Missing-settings message, verbatim: `BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID must both be set (put them in .env); nothing was written`.
- Token-leak message, verbatim: `token found in the rendered cassette; nothing written`.
- CLI Flex failure line: `Flex capture failed: {exc}` on stderr.
- Token forms checked: `token`, `urllib.parse.quote(token, safe="")`, `urllib.parse.quote_plus(token, safe="")`.
- The raw statement is never written to disk; the token is never logged or echoed. All three artefacts are computed before the first write.
- Cassette shape: `{"interactions": [{"request": {"body": "", "headers": {}, "method", "uri"}, "response": {"status": {"code", "message"}, "headers", "body": {"string"}}}], "version": 1}`, prefixed by one `#` comment line.
- `import_corporate_actions` tests in `tests/unit/test_ibkr_flex_import.py` pass unchanged.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green. Commits: Conventional Commits scoped `(#139)`.

## Review Focus

1. A token with `/`, `+`, `=` is percent-encoded by httpx in the URL; the cassette must carry `t=SCRUBBED` and none of the three forms. Pinned by the stage-3 capture test with `TOKEN = "1234567890/abc+def=4567"`.
2. The cassette must replay through vcrpy (same request sequence, `GetStatement` twice with the same query) with no network. Pinned by the stage-3 replay test.
3. A failure after the fetch (token leak) must leave the target directory empty, not half-written. Pinned by the stage-3 token-leak test (`tmp_path` empty).
4. A `FlexError` echoed by the CLI must not reveal the token in any form. Pinned by the stage-3 CLI failure test.
5. Real response headers (`Set-Cookie`, `Authorization`-like) must never reach the cassette: only `Content-Type`. Pinned by a test in Task 2 (`test_render_cassette_keeps_only_content_type`).

## Assumptions

- The cassette's multi-line body strings are emitted in YAML literal block style (`|`), like the FMP reference cassette, and without line folding. `yaml.safe_dump` takes no `Dumper` argument, so this uses `yaml.dump(..., Dumper=<SafeDumper subclass with a str representer choosing style "|" for strings containing a newline>, sort_keys=False, allow_unicode=True, width=float("inf"))`. A SafeDumper subclass only emits safe YAML and loads with `yaml.safe_load`. Rejected: plain `safe_dump`, which would fold the statement into an escaped double-quoted scalar that a human cannot review before committing it (#141).
- `Interaction.body` is `response.text` (decoded); `Interaction.reason` is `response.reason_phrase`; `content_type` is `response.headers.get("content-type")`.
- `capture` does not close the recorder explicitly a second time if the client's context manager already closed it; `RecordingTransport.close()` delegating to the inner transport is idempotent for `HTTPTransport` and `MockTransport`.
- Tests for this issue go in the existing `tests/unit/test_ibkr_flex_capture.py` (the file the issue's "How to test" lists), appended after the #138 tests.
- The CLI tests inject a transport by monkeypatching `bot.cli.capture` with `functools.partial(capture, transport=<MockTransport>)`; the command itself always passes no transport.
- `RecordingTransport` stores interactions in a plain `list[Interaction]` attribute `interactions`.
- Sequential playback of the two identical `GetStatement` requests relies on vcrpy's defaults (`allow_playback_repeats=False`: each recorded interaction is served once, in order) and on vcrpy patching the httpx client when no transport is injected. Not a repo rule; the replay test pins both.
- A failure on the second or third write (disk full, permissions) leaves a partial set on disk; a re-run overwrites all three. Rejected: temp files plus atomic rename, which nothing asks for in a one-shot maintainer tool.
- Paths are resolved under the current directory (the issue's `capture(settings, root=Path.cwd())`); the maintainer runs it from the repo root. The CLI prints `Path.cwd() / constant`, which is exactly what `capture` wrote.
- `response.text` uses httpx's charset handling (UTF-8 when `Content-Type` has no charset); the cassette is written UTF-8 and vcrpy re-encodes `body.string` as UTF-8 on replay. Pinned by the replay test.
- Exact cassette header line is chosen here (the issue fixes only its meaning): `# Recorded by bot flex-capture (#110): the Flex token is scrubbed and the statement is redacted.` A test asserts the cassette text starts with it.
- A token with non-printable characters, which YAML would escape into a form none of the three checks match, is not considered: IBKR tokens are printable ASCII digits.

## Stage-3 tests (written before any task, commit `test(#139): evals`)

All appended to `tests/unit/test_ibkr_flex_capture.py`, sharing `TOKEN = "1234567890/abc+def=4567"`, `QUERY = "987654"`, an autouse fixture patching `ibkr_flex.POLL_DELAY_SECONDS` to `0`, and a MockTransport answering SendRequest success, GetStatement `1019`, then the sample:

- `test_fetch_flex_statement_returns_the_statement`
- `test_capture_writes_exactly_the_three_paths`
- `test_capture_cassette_is_scrubbed_and_redacted` (`t=SCRUBBED`, no token form, no `U1234567`/`U7654321`, 3 interactions, header line)
- `test_capture_writes_redacted_xml_and_summary`, `test_capture_returns_the_summary`
- `test_capture_cassette_replays_through_vcr` (cassette in `tmp_path`, `vcr.VCR(record_mode="none", filter_query_parameters=[("t", "SCRUBBED")])` used directly; no pytest-vcr fixture)
- `test_capture_refuses_a_cassette_carrying_the_token` (`tmp_path` empty)
- `test_capture_propagates_flex_error_and_writes_nothing` (SendRequest `Fail`/`1012`)
- `test_capture_missing_settings_writes_nothing`
- `test_render_cassette_keeps_only_content_type`, `test_render_cassette_leaves_non_statement_bodies_unchanged`
- `test_cli_missing_settings_exits_2`
- `test_cli_flex_error_exits_1_without_the_token`, parametrized over SendRequest `Fail`/`1012` and an HTTP 500 (whose httpx error text embeds the URL with the token, scrubbed by the client)
- `test_cli_success_prints_paths_and_summary`, `test_flex_capture_is_hidden`

Task steps below that say "stage-3 test ... failing" refer to these.

---

### Task 1: `fetch_flex_statement` seam

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py` (add function after the client class; rewire `import_corporate_actions`)
- Test: `tests/unit/test_ibkr_flex_capture.py` (stage-3 tests), `tests/unit/test_ibkr_flex_import.py` (unchanged)

**Interfaces:**
- Produces: `fetch_flex_statement(token: str, query_id: str, *, transport: httpx.BaseTransport | None = None) -> str` in `bot.ingest.ibkr_flex`. Raises `FlexError` exactly as the client does.

- [ ] **Step 1:** Stage-3 test `test_fetch_flex_statement_returns_the_statement` (MockTransport: SendRequest success, then sample) is already failing with ImportError. Run: `uv run pytest -q tests/unit/test_ibkr_flex_capture.py -k fetch_flex_statement` → FAIL.
- [ ] **Step 2:** Implement `fetch_flex_statement`: open the client as a context manager, return `fetch_statement()`. Make `import_corporate_actions` call it with its `transport`.
- [ ] **Step 3:** Run `uv run pytest -q tests/unit/test_ibkr_flex_import.py tests/unit/test_ibkr_flex_client.py tests/unit/test_seam_enforcement.py tests/unit/test_ibkr_flex_capture.py -k "fetch_flex_statement or import or client or seam"` → PASS.
- [ ] **Step 4:** Commit `feat(#139): fetch_flex_statement seam`.

### Task 2: recording, cassette rendering and `capture()`, plus the shared VCR config

**Files:**
- Modify: `src/bot/ingest/ibkr_flex_capture.py`
- Modify: `tests/vcr_settings.py`
- Test: `tests/unit/test_ibkr_flex_capture.py`

**Interfaces:**
- Consumes: `fetch_flex_statement` (Task 1); `redact_statement`, `summarize_statement`, `FlexSummary` (existing, #138); `FlexError` from `bot.ingest.ibkr_flex`; `Settings` from `bot.config` (`ibkr_flex_token`, `ibkr_flex_query_id`).
- Produces, in `bot.ingest.ibkr_flex_capture`:
  - `@dataclass(frozen=True) class Interaction(method: str, url: str, status: int, reason: str, content_type: str | None, body: str)`
  - `class RecordingTransport(httpx.BaseTransport)`: `__init__(self, inner: httpx.BaseTransport)`, `interactions: list[Interaction]`, `handle_request(request) -> httpx.Response` (forward, `response.read()`, append, return), `close()` (closes inner). No logging.
  - `class FlexCaptureError(RuntimeError)` with `exit_code: int` (constructor `FlexCaptureError(message: str, *, exit_code: int = 1)`); missing settings raise with `exit_code=2`.
  - `render_cassette(interactions: Sequence[Interaction], *, token: str) -> str`
  - `CASSETTE_PATH`, `REDACTED_XML_PATH`, `SUMMARY_PATH` (Global Constraints)
  - `capture(settings: Settings, *, root: Path, transport: httpx.BaseTransport | None = None) -> FlexSummary`

- [ ] **Step 1:** Stage-3 tests for capture (three files, cassette content, redacted/summary equality, return value), replay, token leak, `FlexError` propagation, missing settings are failing. Add `test_render_cassette_keeps_only_content_type`: render one `Interaction` whose recording came from a MockTransport response carrying `Set-Cookie: s=1` and `Content-Type: text/xml`; `yaml.safe_load` the result; assert response `headers == {"Content-Type": ["text/xml"]}`, request `headers == {}`, and `"Set-Cookie" not in text`. Add `test_render_cassette_leaves_non_statement_bodies_unchanged` (a `FlexStatementResponse` body is kept byte-for-byte as `body.string`). Run `uv run pytest -q tests/unit/test_ibkr_flex_capture.py` → those FAIL.
- [ ] **Step 2:** Implement the recorder, error class and path constants.
- [ ] **Step 3:** Implement `render_cassette`: `uri = str(httpx.URL(url).copy_set_param("t", "SCRUBBED"))` only when `t` is among the URL's params, else the URL unchanged; body redacted only when it parses (`xml.etree.ElementTree.fromstring`, `ParseError` → unchanged) with root tag `FlexQueryResponse`; header comment line exactly `# Recorded by bot flex-capture (#110): the Flex token is scrubbed and the statement is redacted.`; YAML emitted per the Assumptions; token-form check last, raising `FlexCaptureError("token found in the rendered cassette; nothing written")`.
- [ ] **Step 4:** Implement `capture` in the five steps of the issue (strip settings → missing-settings error with `exit_code=2`; record through `RecordingTransport(transport or httpx.HTTPTransport())`; compute redacted, summary, cassette in memory; `mkdir(parents=True, exist_ok=True)` and write the three files UTF-8; return the summary).
- [ ] **Step 5:** In `tests/vcr_settings.py` add `("t", "SCRUBBED")` to `filter_query_parameters` with the comment that the Flex token travels as `t`, and `"test_ibkr_flex_": "ibkr_flex"` to `_CASSETTE_SUBDIRS`.
- [ ] **Step 6:** Run `uv run pytest -q tests/unit/test_ibkr_flex_capture.py tests/unit/test_seam_enforcement.py tests/integration/test_fmp_client.py && uv run mypy src` → PASS (CLI tests may still fail until Task 3).
- [ ] **Step 7:** Commit `feat(#139): record and render the Flex capture`.

### Task 3: hidden `bot flex-capture` command

**Files:**
- Modify: `src/bot/cli.py` (import `capture`, `FlexCaptureError`, `FlexError`; command placed after `portfolio`)
- Test: `tests/unit/test_ibkr_flex_capture.py`

**Interfaces:**
- Consumes: `capture`, `FlexCaptureError` (Task 2), `FlexError`, `load_settings`, `configure_logging`.
- Produces: `@app.command(name="flex-capture", hidden=True) def flex_capture() -> None`.

- [ ] **Step 1:** Stage-3 CLI tests (missing settings → exit 2, both var names in output, `tmp_path` empty; FlexError → exit 1, `Flex capture failed:` on stderr, no token form) fail. Add `test_cli_success_prints_paths_and_summary`: with a patched `bot.cli.capture` writing via the MockTransport flow, exit 0, output contains `Wrote ` followed by `tmp_path / CASSETTE_PATH` (and likewise the two other paths) and the summary JSON. Add `test_flex_capture_is_hidden`: `bot --help` output does not contain `flex-capture`. Run → FAIL.
- [ ] **Step 2:** Implement the command: docstring saying it is the maintainer's validation step for the Flex importer (#110); `load_settings()`, `configure_logging(level=settings.log_level, json_output=False)`, `capture(settings, root=Path.cwd())`; `FlexCaptureError` → stderr message, `typer.Exit(code=exc.exit_code)`; `FlexError` → stderr `Flex capture failed: {exc}`, exit 1; success → `Wrote {Path.cwd() / constant}` for the three constants, in the order cassette, redacted XML, summary, then `summary.to_json()` (use `nl=False`, it already ends in a newline).
- [ ] **Step 3:** Run `uv run pytest -q tests/unit/test_ibkr_flex_capture.py tests/unit/test_seam_enforcement.py && uv run ruff check . && uv run mypy src` → PASS.
- [ ] **Step 4:** Full suite `uv run pytest -q` → PASS. Commit `feat(#139): bot flex-capture command`.

## Grilling

One round, 18 questions; griller model `fable`. Revisions were clarifications (test names listed, assumptions added, header line and HTTP-500 cases pinned); no step added or removed and no seam changed, so no second round.

- ISSUE (4): #5 replay uses a `tmp_path` cassette through `vcr.VCR` directly; #12 only `FlexQueryResponse` bodies are redacted ("else the body unchanged"); #15 fixed path constants (issue §2 and #110 decision 7: "fixed constants so #111 can rely on them"); #17 "Nothing else in the suite depends on a `t` parameter" (also no `t=` in `tests/fixtures/cassettes/`).
- CODE (7): #2 `src/bot/utils/logging.py:30` sets the `httpx` logger to WARNING; #3 `src/bot/config.py:67-74` both settings are plain `str`; #6 and #7 `ibkr_flex.py` `FlexClient._get` passes `params=` and scrubs the three token forms from httpx error text; #13 `fetch_statement` returns only a `FlexQueryResponse` root, and redaction/summary walk elements generically; #14 `import_corporate_actions` uses only `fetch_statement()` inside the context manager; #18 `tests/unit/test_ibkr_flex_capture.py:174` asserts `to_json()` ends in `\n`.
- NO SOURCE → technical assumptions (7): #1 stage-3 tests listed; #4 vcrpy sequential playback; #8 any body with a `\r` or a space before a newline (a real statement's element tails can carry them through `ET.tostring`) falls back to a double-quoted scalar: replay and the leak check are unaffected, only readability (stage-5 review; the body is not normalised so the cassette replays the redacted statement byte for byte); #9 partial writes on disk failure; #10 cwd as root; #11 httpx charset and re-read; #16 exact header line.
- Spec ambiguities: none. Out of scope: none; no issue opened.
