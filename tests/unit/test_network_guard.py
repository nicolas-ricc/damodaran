"""The suite refuses non-loopback connections: pytest-socket, from ``addopts``.

``203.0.113.1`` is TEST-NET-3 (RFC 5737) and ``example.invalid`` never
resolves, so no proof here reaches the internet: the guard raises before any
packet, and the unguarded proofs send one SYN to an unrouted address and give
up after half a second.
"""

from __future__ import annotations

import re
import shlex
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

pytest_plugins = ["pytester"]

GUARD_ADDOPTS = "--allow-hosts=127.0.0.1,::1,localhost --allow-unix-socket"
BLOCKED_IP = "203.0.113.1"

# Copied into the pytester sandbox, as in test_live_marker.py.
_ROOT_CONFTEST = Path(__file__).parent.parent / "conftest.py"


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def loopback_port() -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_socket_to_public_ip_is_blocked() -> None:
    with pytest.warns(UserWarning), pytest.raises(RuntimeError, match=re.escape(BLOCKED_IP)):
        socket.create_connection((BLOCKED_IP, 80), timeout=0.5)


def test_socket_to_hostname_is_blocked() -> None:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        with (
            pytest.warns(UserWarning),
            pytest.raises(RuntimeError, match=re.escape("example.invalid")),
        ):
            sock.connect(("example.invalid", 80))
    finally:
        sock.close()


def test_httpx_to_public_ip_is_blocked() -> None:
    with pytest.warns(UserWarning), pytest.raises(RuntimeError, match=re.escape(BLOCKED_IP)):
        httpx.get(f"http://{BLOCKED_IP}/", timeout=0.5)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_server_reachable(loopback_port: int, host: str) -> None:
    response = httpx.get(f"http://{host}:{loopback_port}/", timeout=5)
    assert response.status_code == 200
    assert response.text == "ok"


_BLOCKED = f"""
import socket
import pytest

{{marker}}
def test_connect():
    with pytest.warns(UserWarning), pytest.raises(RuntimeError):
        socket.create_connection(("{BLOCKED_IP}", 80), timeout=0.5)
"""

# Past the guard: an OSError (timeout, unreachable) or a connect a proxy accepted.
_UNGUARDED = f"""
import socket
import pytest

{{marker}}
def test_connect():
    try:
        socket.create_connection(("{BLOCKED_IP}", 80), timeout=0.5).close()
    except RuntimeError as exc:
        pytest.fail(f"guard still on: {{{{exc}}}}")
    except OSError:
        pass
"""


def _run(pytester: pytest.Pytester, source: str, *args: str) -> pytest.RunResult:
    """Run ``source`` in a subprocess: in-process, it would inherit this test's guard.

    pytest-socket's ``enable_socket`` restores ``socket.socket`` but not the
    patched ``connect``, so a nested in-process run could never lift the guard.
    """
    pytester.makeconftest(_ROOT_CONFTEST.read_text())
    pytester.makeini(
        f"[pytest]\naddopts = {GUARD_ADDOPTS}\nstrict_markers = true\n"
        f"pythonpath = {shlex.quote(str(_ROOT_CONFTEST.parent.parent))}\nmarkers =\n    live: x\n"
    )
    pytester.makepyfile(source)
    return pytester.runpytest_subprocess("-q", *args)


def _plain(template: str) -> str:
    return template.format(marker="")


def _live(template: str) -> str:
    return template.format(marker="@pytest.mark.live")


def test_plain_test_is_blocked_by_default(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_LIVE_TESTS", raising=False)
    _run(pytester, _plain(_BLOCKED)).assert_outcomes(passed=1)


def test_live_skipped_by_default(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_LIVE_TESTS", raising=False)
    _run(pytester, _live(_UNGUARDED)).assert_outcomes(skipped=1)


def test_live_unguarded_when_opted_in(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_LIVE_TESTS", "1")
    _run(pytester, _live(_UNGUARDED)).assert_outcomes(passed=1)


def test_live_opt_in_keeps_guard_on_plain_tests(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_LIVE_TESTS", "1")
    _run(pytester, _plain(_BLOCKED)).assert_outcomes(passed=1)


def test_vcr_record_all_unguarded(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_LIVE_TESTS", raising=False)
    _run(pytester, _plain(_UNGUARDED), "--vcr-record=all").assert_outcomes(passed=1)


def test_vcr_record_none_keeps_guard(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_LIVE_TESTS", raising=False)
    _run(pytester, _plain(_BLOCKED), "--vcr-record=none").assert_outcomes(passed=1)
