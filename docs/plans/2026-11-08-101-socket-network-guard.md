# Socket-level network guard for the test suite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the default test run, a connection to any non-loopback address fails the test with a clear error. Loopback stays allowed. `live` tests (with `BOT_LIVE_TESTS=1`) and re-recording (`--vcr-record`) are exempt.

**Architecture:** pytest-socket, enabled from `addopts` with a loopback allow-list (`--allow-hosts`). It patches `socket.socket.connect` for each test. The root `tests/conftest.py` exempts items by adding pytest-socket's `enable_socket` marker in its existing `pytest_collection_modifyitems` hook. The conftest never imports `pytest_socket`, so the copied conftest keeps working in the pytester and subprocess sandboxes.

**Tech Stack:** Python 3.12, pytest 9, pytest-socket >= 0.8.1, uv, ruff, mypy --strict (src only).

**Spec:** GitHub issue #101 (`gh issue view 101 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec. The planner comment ("Plan (planner, 2026-11-08)") fixes the design decisions this plan follows.

## Global Constraints

- Loopback allow-list, exactly: `127.0.0.1`, `::1`, `localhost`. Unix sockets allowed (`--allow-unix-socket`).
- `addopts = "-v --allow-hosts=127.0.0.1,::1,localhost --allow-unix-socket"`. No `--disable-socket`.
- `pytest-socket>=0.8.1` goes in the `[dependency-groups] dev` list. `uv.lock` is updated (CI runs `uv sync --frozen`).
- `tests/conftest.py` must not import `pytest_socket`. It may import from `tests.vcr_settings`, as it already does.
- Out of scope, unchanged: VCR record modes, cassettes, `tests/integration/conftest.py`, live tests in CI.
- `tests/unit/test_vcr_record_switch.py`, `tests/unit/test_fmp_record_guard.py` and `tests/unit/test_live_marker.py` pass unchanged.
- No test touches the real network. Blocked-address proofs use `203.0.113.1` (TEST-NET-3, RFC 5737) and the literal hostname `example.invalid`. Unguarded proofs use a 0.5 s socket timeout.
- `uv run pytest -q` passes offline, and `uv run ruff check . && uv run mypy src` stay green.

## Assumptions (declared)

- The hostname proof calls `socket.socket().connect(("example.invalid", 80))` directly. pytest-socket compares the literal host given to `connect` and raises before any DNS lookup. `socket.create_connection` would resolve the name first and fail with `gaierror`, which proves nothing.
- The guard's error is pytest-socket's `SocketConnectBlockedError`, a `RuntimeError` subclass. Its message names the blocked host. Tests match `RuntimeError` with `match="203.0.113.1"` (or `match="example.invalid"`), and wrap the call in `pytest.warns(UserWarning)` because the plugin warns each time it blocks.
- "Got past the guard" means the connect did not raise `RuntimeError`. It either raised `OSError` (timeout, unreachable, refused) or succeeded. A transparent proxy or captive portal may accept any port-80 connect, so success is accepted too. The `_UNGUARDED` body is written as `try: connect; except RuntimeError: pytest.fail(...); except OSError: pass`. Rejected: requiring `OSError`, which is network-dependent.
- The guard covers `socket.socket.connect` (TCP and connected UDP), as the Agent Brief's "any attempt to connect" says. DNS resolution (libc `getaddrinfo`) and `sendto` on an unconnected UDP socket are not intercepted. A real hostname is still blocked at the `connect` that follows resolution. Rejected: `--disable-socket`, which blocks socket creation and would break the loopback `HTTPServer` and the `--vcr-record` exemption design.
- Floor `pytest-socket>=0.8.1`: this is the release the planner's dry run validated (3510 passed). Its `guarded_connect` closes the fd before it raises. Rejected: `>=0.7.0`, which was not validated.
- `tests/conftest.py` does not import `pytest_socket`. Nothing breaks if it does; it simply has no need to, because markers are plain `pytest.mark.enable_socket`. Rejected: importing it for typing alone.
- The intermediate Task 1 commit blocks `--vcr-record` and `live` runs until Task 2 lands. That is acceptable on the feature branch, because the PR is squash-merged. `test_fmp_record_guard` still passes at that commit: its only connect target is the loopback dead proxy (`127.0.0.1:9`), which is allowed.

## Review Focus

1. A test that connects through `httpx` (the client the code base uses) and not only through raw sockets: the guard must hold. Pinned by `test_httpx_to_public_ip_is_blocked` (Task 1).
2. `localhost` by name, not only `127.0.0.1`: it must stay reachable. Pinned by `test_loopback_server_reachable[localhost]` (Task 1).
3. `--vcr-record=none` is the replay mode: it must keep the guard on. Pinned by `test_vcr_record_none_keeps_guard` (Task 2).
4. `BOT_LIVE_TESTS=1` must exempt only `live` items, not every test. Pinned by `test_live_opt_in_keeps_guard_on_plain_tests` (Task 2).
5. The `test_fmp_record_guard` subprocess runs with `--vcr-record=all` and the copied `pyproject.toml`, and its dead proxy is loopback. It must still fail the way it does today. Covered by that existing test, which stays unchanged.

---

### Task 1: pytest-socket blocks non-loopback connects in the default run

**Files:**
- Modify: `pyproject.toml` (dev group, `[tool.pytest.ini_options].addopts`), `uv.lock`
- Create: `tests/unit/test_network_guard.py`
- Modify: `README.md` `## Development` section

**Interfaces:**
- Produces: the module constant `GUARD_ADDOPTS = "--allow-hosts=127.0.0.1,::1,localhost --allow-unix-socket"` in `tests/unit/test_network_guard.py`. Task 2's pytester ini reuses it.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_network_guard.py`:
  - `test_socket_to_public_ip_is_blocked`: inside `pytest.warns(UserWarning)` and `pytest.raises(RuntimeError, match="203.0.113.1")`, run `socket.create_connection(("203.0.113.1", 80), timeout=0.5)`.
  - `test_socket_to_hostname_is_blocked`: the same check, but with a raw `socket.socket()` and `.connect(("example.invalid", 80))`, matching `"example.invalid"`. Close the socket.
  - `test_httpx_to_public_ip_is_blocked`: `httpx.get("http://203.0.113.1/", timeout=0.5)` raises `RuntimeError` matching `"203.0.113.1"`, inside `pytest.warns(UserWarning)`.
  - `test_loopback_server_reachable[127.0.0.1|localhost]`: start an `HTTPServer(("127.0.0.1", 0))` on a daemon thread, with a handler that returns 200 and the body `ok`. `httpx.get(f"http://{host}:{port}/")` returns status 200 and the text `"ok"`. Reuse the `_serve` pattern of `tests/unit/test_vcr_record_switch.py:69-75` (daemon thread, `shutdown()` then `server_close()`).
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_network_guard.py -q`. Expected: the three blocked tests FAIL (no `RuntimeError` is raised), and loopback passes.
- [ ] **Step 3: Implement.** Run `uv add --dev "pytest-socket>=0.8.1"`, then set `addopts` per the Global Constraints. Add two sentences to the README `## Development` section: the suite refuses non-loopback connections through pytest-socket, and `BOT_LIVE_TESTS=1` (for `live` tests) and `--vcr-record` lift the guard.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_network_guard.py tests/unit/test_vcr_record_switch.py tests/unit/test_fmp_record_guard.py tests/unit/test_readme_dev_docs.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#101): pytest-socket blocks non-loopback connects`.

### Task 2: conftest exempts `live` (opted in) and re-recording runs

**Files:**
- Modify: `tests/conftest.py` (module docstring, `pytest_collection_modifyitems`)
- Test: `tests/unit/test_network_guard.py` (pytester section)

**Interfaces:**
- Consumes: `GUARD_ADDOPTS` (Task 1), `tests.vcr_settings.record_option(config: pytest.Config) -> str | None`.
- Produces: `pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None`.

- [ ] **Step 1: Write the failing pytester tests.** Add `pytest_plugins = ["pytester"]`. A helper `_run(pytester, source, *args) -> pytest.RunResult` does the following:
  - copy `tests/conftest.py` with `pytester.makeconftest`;
  - write an ini with `addopts = <GUARD_ADDOPTS>`, `strict_markers = true` and the marker `live: x`;
  - write `source` as the test file and run `pytester.runpytest("-q", *args)`.

  The test bodies connect to `203.0.113.1:80` with `timeout=0.5`. `_BLOCKED` asserts `pytest.raises(RuntimeError)`. `_UNGUARDED` asserts that `OSError` is raised and that it is not a `RuntimeError`. Write these tests:
  - `test_plain_test_is_blocked_by_default`: a plain `_BLOCKED` body passes (outcome `passed=1`).
  - `test_live_skipped_by_default`: with `BOT_LIVE_TESTS` unset, a `live` `_UNGUARDED` body is `skipped=1`.
  - `test_live_unguarded_when_opted_in`: with `BOT_LIVE_TESTS=1`, the same body is `passed=1`.
  - `test_live_opt_in_keeps_guard_on_plain_tests`: with `BOT_LIVE_TESTS=1`, a plain `_BLOCKED` body is `passed=1`.
  - `test_vcr_record_all_unguarded`: a plain `_UNGUARDED` body with `--vcr-record=all` is `passed=1`.
  - `test_vcr_record_none_keeps_guard`: a plain `_BLOCKED` body with `--vcr-record=none` is `passed=1`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_network_guard.py -q`. Expected: `test_live_unguarded_when_opted_in` and `test_vcr_record_all_unguarded` FAIL.
- [ ] **Step 3: Implement.** In `pytest_collection_modifyitems(config, items)`:
  - when `record_option(config) not in (None, "none")`, add `pytest.mark.enable_socket` to every item;
  - for `live` items, add `enable_socket` if `BOT_LIVE_TESTS == "1"` and the existing skip marker otherwise.

  Update the module docstring: one paragraph on the guard and its two exemptions.
- [ ] **Step 4: Run** `uv run pytest -q`, then `uv run ruff check . && uv run mypy src`. Expected: all green. `test_live_marker.py` passes unchanged.
- [ ] **Step 5: Commit** `feat(#101): live and re-record runs lift the network guard`.

## Grilling

- Rounds: 1. The plan's steps and seam were unchanged; only the assumptions were revised.
- Questions: 19. By source: CODE 14 (pytest-socket 0.8.1 wheel source, `pytest_vcr.py`, httpcore `_backends/sync.py`, `tests/`, `pyproject.toml`, `.github/workflows/site.yml`), ISSUE 3 (the Agent Brief and the planner comment), DOC 0, NO SOURCE 2 (both technical assumptions).
- Assumptions added: `_UNGUARDED` accepts a successful connect; the guard scope is `connect` only (DNS and unconnected UDP excluded); the `>=0.8.1` floor; no import of `pytest_socket`; the intermediate commit is acceptable.
- Issues opened: none.
