# Notifier module (email / Telegram) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After `bot portfolio` writes `alerts.md`, optionally forward its contents to email or Telegram, chosen by `BOT_NOTIFIER=email|telegram|none` (default `none`).

**Architecture:** New package `src/bot/notifier/` with two backends (`email.py` over stdlib `smtplib`, `telegram.py` over `httpx`) that share one structural interface, `send(text: str) -> None`. `base.py` owns the interface and the error types; the package `__init__.py` re-exports them and owns `build_notifier(settings)` (env → backend) and `notify_alerts(path, notifier)` (read file, skip when empty, send). The CLI command `bot portfolio` is the composition root: it builds the notifier before touching TWS (fail fast on misconfiguration) and calls `notify_alerts` after both reports are written. `run_portfolio` stays unchanged — the library keeps writing files; sending is a CLI concern.

**Tech Stack:** Python 3.12, pydantic-settings, stdlib `smtplib`/`email.message`, `httpx` (already a dependency; `httpx.MockTransport` in tests), Typer, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #32; `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §15 ("Si se quiere push, módulo `notifier` aparte que lea `alerts.md`").

## Global Constraints

- "Optional module that reads `alerts.md` after `bot portfolio` and forwards it to a notification channel."
- "Channel choice via env: `BOT_NOTIFIER=email|telegram|none` (default none)."
- "For email: SMTP config via env. For Telegram: bot token + chat ID via env."
- "No fancy UX — just send the file contents. Skip silently if `alerts.md` is empty."
- AC: "`src/bot/notifier/` module with backends `email.py` and `telegram.py`".
- AC: "Hook in `bot portfolio` that sends the alerts file when notifier is configured".
- AC: "Unit tests with mocked transports" — no real SMTP server or network in tests.
- AC: "mypy --strict + ruff clean": `uv run ruff check . && uv run mypy src`.
- Test suite: `uv run pytest -q`.
- CONTEXT.md: type hints everywhere; functions accept their dependencies, no global state; Conventional Commits.

## Decisions (technical assumptions, declared)

- **Env var names.** All settings use the existing `BOT_` prefix (`src/bot/config.py`): `BOT_NOTIFIER`, `BOT_SMTP_HOST`, `BOT_SMTP_PORT` (default 587), `BOT_SMTP_SECURITY` (`starttls` default | `ssl` | `none`), `BOT_SMTP_USERNAME`, `BOT_SMTP_PASSWORD`, `BOT_SMTP_FROM`, `BOT_SMTP_TO` (comma-separated), `BOT_TELEGRAM_BOT_TOKEN`, `BOT_TELEGRAM_CHAT_ID`. Secrets are plain `str` fields, like `fmp_api_key` and `tiingo_api_key`.
- **One-method interface `send(text)`.** "Just send the file contents": Telegram sends the text as-is; email derives its subject from the first non-empty line of the text with leading `#` and spaces stripped (`alerts.md` starts with `# Alerts — YYYY-MM-DD`), falling back to `"bot alerts"`.
- **"Empty" means blank.** `notify_alerts` skips when `text.strip() == ""` (the file is zero bytes on quiet days per #29; whitespace-only counts as empty too). The skip is silent for the user (no CLI line); a debug-level log records it.
- **Telegram plain text.** No `parse_mode`: Markdown tables contain `|`, `_` and `*`, which Telegram's Markdown parser rejects. Messages over Telegram's 4096-character limit are split on line boundaries (length measured in UTF-16 code units, which is how Telegram counts); a single line longer than the limit is hard-split.
- **Errors never leak secrets.** Backends wrap transport failures in `NotificationError` with a message that never contains the bot token (Telegram puts it in the URL path, and `httpx` errors print the URL) or the SMTP password.
- **CLI failure modes.** Misconfiguration (`BOT_NOTIFIER=email` without host/from/to, or `telegram` without token/chat id) → `NotifierConfigError`, caught in `bot portfolio` before connecting to TWS: stderr `Notifier misconfigured: …`, exit 2, no report written. A send failure after reports are written → stderr `Alerts not sent: …`, exit 1 (reports stay on disk; a cron run must not look green when the push failed). Success → stdout `Sent alerts via <channel>`.
- **`BOT_NOTIFIER=` (blank) means `none`**, mirroring the `industry_mapping_path` blank-is-unset validator.
- **`AUDITADO_EN`/`AUDITADO_EL` are not bumped**: this change adds one inventory entry, not a full re-audit (same rule as `2026-10-01-portfolio-cli-close-gaps.md`).

## Assumptions

Recorded by plan grilling (round 1). Each names the rejected alternative.

- **Errors/protocol in `notifier/base.py`** (rejected: define them in `__init__.py` and import backends lazily inside `build_notifier`). Backends importing from the package `__init__` while it imports them is a cycle; a leaf module removes it with top-level imports only.
- **Exit codes** follow spec §9 ("Exit codes: 0 OK, 1 error operativo, 2 data error") and the existing CLI precedent for a missing config (`cli.py:558`, preset not found → 2): misconfigured notifier → 2; failed delivery (an operational error) → 1 (rejected: warn and exit 0 — spec §12 "degrade gracefully, alert loudly").
- **Hook in the CLI, not in `run_portfolio`** (rejected: a `notifier` parameter on `run_portfolio`). The AC says "Hook in `bot portfolio`"; the CLI already is the composition root that builds the IBKR client and gates (`cli.py:532-591`), and `run_portfolio`'s contract is "write both report files" (`portfolio/command.py:69-161`).
- **No retry, no 429 `retry_after` handling** (rejected: retry loop). One user, at most a handful of messages per day; the issue asks for "no fancy UX". A failed send exits 1; re-running `bot portfolio` the same day re-renders the same `alerts.md` (same previous snapshot, `command.py:111`) and re-sends it, possibly duplicating chunks already delivered — documented in the README.
- **`BOT_SMTP_SECURITY=none` exists for local relays** (rejected: only `starttls`/`ssl`), but combined with a username it is rejected by `build_notifier` so a password never travels in cleartext.
- **Text encoding:** `notify_alerts` reads with the same default encoding `run_portfolio` writes with (`command.py:142-143`, `write_text` without encoding) (rejected: force UTF-8 on one side only, which would make them disagree on a non-UTF-8 locale).
- **No new ADR.** CONTEXT.md asks ADRs to record architecture decisions and to be closed when implemented; this module is the one spec §15 already prescribes ("módulo `notifier` aparte que lea `alerts.md`").
- **Secrets as plain `str`** like `fmp_api_key`/`tiingo_api_key` (rejected: `SecretStr`). No code path serialises `Settings` (`grep model_dump|repr(settings)` over `src/` is empty); `bot doctor` prints keys as `set`/`MISSING` only (`cli.py:611`).

## Review Focus

1. Quiet day: `alerts.md` is zero bytes → nothing is sent and the CLI prints no notifier line — pinned in Task 1 (`notify_alerts`) and Task 4 (CLI).
2. Telegram rejects a real `alerts.md` (Markdown table with `|`/`_`) or a long one (>4096 chars) — pinned in Task 2 (no `parse_mode`; chunking test).
3. A Telegram/SMTP failure prints the bot token or password to the terminal — pinned in Task 2 (error message does not contain the token) and Task 3 (password absent).
4. `BOT_NOTIFIER=email` with missing SMTP settings: the run must fail before syncing, naming the missing env vars — pinned in Task 1 (`build_notifier`) and Task 4 (exit 2, no reports).
5. `BOT_SMTP_TO="a@x.com, b@y.com"` (spaces, trailing comma) delivers to both — pinned in Task 1.

---

### Task 1: Settings + notifier core (`build_notifier`, `notify_alerts`)

**Files:**
- Modify: `src/bot/config.py` (new fields + blank-notifier validator)
- Create: `src/bot/notifier/base.py` (`Notifier`, `NotifierConfigError`, `NotificationError`)
- Create: `src/bot/notifier/__init__.py`
- Create: `src/bot/notifier/email.py`, `src/bot/notifier/telegram.py` (constructors only in this task; `send` raises `NotImplementedError` until Tasks 2/3)
- Test: `tests/unit/test_notifier.py`, `tests/unit/test_config.py`

**Interfaces:**
- Produces (`bot.config.Settings`): `notifier: Literal["email", "telegram", "none"] = "none"`, `smtp_host: str = ""`, `smtp_port: int = 587`, `smtp_security: Literal["starttls", "ssl", "none"] = "starttls"`, `smtp_username: str = ""`, `smtp_password: str = ""`, `smtp_from: str = ""`, `smtp_to: str = ""`, `telegram_bot_token: str = ""`, `telegram_chat_id: str = ""`.
- Produces (`bot.notifier`):
  - `class Notifier(Protocol): def send(self, text: str) -> None: ...`
  - `class NotifierConfigError(ValueError)`
  - `class NotificationError(RuntimeError)`
  - `def build_notifier(settings: Settings) -> Notifier | None`
  - `def notify_alerts(alerts_path: Path, notifier: Notifier | None) -> bool` — `True` iff something was sent.
- Produces (backend constructors, keyword-only):
  - `EmailNotifier(*, host: str, port: int, sender: str, recipients: Sequence[str], username: str = "", password: str = "", security: Literal["starttls", "ssl", "none"] = "starttls", timeout: float = 30.0, smtp_factory: SmtpFactory | None = None)` with public read-only attributes `host`, `port`, `sender`, `recipients` (tuple), `username`, `security`.
  - `TelegramNotifier(*, bot_token: str, chat_id: str, transport: httpx.BaseTransport | None = None, timeout: float = 30.0)` with public attribute `chat_id`.
  - `Notifier`, `NotificationError`, `NotifierConfigError` live in `bot/notifier/base.py`; backends import them from `bot.notifier.base`; `bot/notifier/__init__.py` imports the backends at module top and re-exports the three names (`__all__`), so callers and tests use `from bot.notifier import ...`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_config.py` — append:

```python
def test_notifier_defaults_to_none(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "X Y x@y.com")
    monkeypatch.delenv("BOT_NOTIFIER", raising=False)
    s = Settings(_env_file=None)
    assert s.notifier == "none"
    assert s.smtp_port == 587
    assert s.smtp_security == "starttls"


def test_blank_notifier_is_none(monkeypatch):
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "X Y x@y.com")
    monkeypatch.setenv("BOT_NOTIFIER", "  ")
    assert Settings(_env_file=None).notifier == "none"


def test_unknown_notifier_is_rejected(monkeypatch):
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "X Y x@y.com")
    monkeypatch.setenv("BOT_NOTIFIER", "slack")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

`tests/unit/test_notifier.py`:

```python
from pathlib import Path

import pytest

from bot.config import Settings
from bot.notifier import NotifierConfigError, build_notifier, notify_alerts
from bot.notifier.email import EmailNotifier
from bot.notifier.telegram import TelegramNotifier


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, sec_user_agent="X Y x@y.com", **overrides)  # type: ignore[call-arg]


def test_notify_alerts_sends_file_contents(tmp_path: Path) -> None:
    path = tmp_path / "alerts.md"
    path.write_text("# Alerts — 2026-06-01\n\n| a | b |\n")
    rec = _Recorder()
    assert notify_alerts(path, rec) is True
    assert rec.sent == ["# Alerts — 2026-06-01\n\n| a | b |\n"]


@pytest.mark.parametrize("content", ["", "\n", "  \n\t"])
def test_notify_alerts_skips_blank_file(tmp_path: Path, content: str) -> None:
    path = tmp_path / "alerts.md"
    path.write_text(content)
    rec = _Recorder()
    assert notify_alerts(path, rec) is False
    assert rec.sent == []


def test_notify_alerts_without_notifier_does_not_read(tmp_path: Path) -> None:
    assert notify_alerts(tmp_path / "missing.md", None) is False


def test_build_notifier_none() -> None:
    assert build_notifier(_settings()) is None


def test_build_notifier_email_parses_recipients() -> None:
    n = build_notifier(
        _settings(
            notifier="email",
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_security="ssl",
            smtp_username="u",
            smtp_password="p",
            smtp_from="bot@example.com",
            smtp_to=" a@x.com, b@y.com ,",
        )
    )
    assert isinstance(n, EmailNotifier)
    assert n.recipients == ("a@x.com", "b@y.com")
    assert (n.host, n.port, n.security, n.sender) == ("smtp.example.com", 465, "ssl", "bot@example.com")


def test_build_notifier_email_missing_fields_names_env_vars() -> None:
    with pytest.raises(NotifierConfigError) as exc:
        build_notifier(_settings(notifier="email", smtp_to=" , "))
    msg = str(exc.value)
    assert "BOT_SMTP_HOST" in msg and "BOT_SMTP_FROM" in msg and "BOT_SMTP_TO" in msg


def test_build_notifier_rejects_cleartext_login() -> None:
    with pytest.raises(NotifierConfigError) as exc:
        build_notifier(
            _settings(
                notifier="email",
                smtp_host="h",
                smtp_from="f@x.com",
                smtp_to="t@x.com",
                smtp_security="none",
                smtp_username="u",
            )
        )
    assert "BOT_SMTP_SECURITY" in str(exc.value)


def test_build_notifier_telegram() -> None:
    n = build_notifier(_settings(notifier="telegram", telegram_bot_token="123:abc", telegram_chat_id="-100"))
    assert isinstance(n, TelegramNotifier)
    assert n.chat_id == "-100"


def test_build_notifier_telegram_missing_fields() -> None:
    with pytest.raises(NotifierConfigError) as exc:
        build_notifier(_settings(notifier="telegram"))
    assert "BOT_TELEGRAM_BOT_TOKEN" in str(exc.value)
    assert "BOT_TELEGRAM_CHAT_ID" in str(exc.value)
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_notifier.py tests/unit/test_config.py -q` — expected: FAIL (`ModuleNotFoundError: bot.notifier`, missing settings fields).

- [ ] **Step 3: Implement.** Settings fields as listed under Interfaces, each with a `description=` naming when it is required (follow `fmp_api_key`'s style), plus:

```python
    @field_validator("notifier", mode="before")
    @classmethod
    def _blank_notifier_is_none(cls, value: object) -> object:
        """Treat ``BOT_NOTIFIER=`` as the default ``none``."""
        if isinstance(value, str) and not value.strip():
            return "none"
        return value
```

`src/bot/notifier/base.py`:

```python
"""The interface every notifier backend implements, and its two errors."""

from typing import Protocol


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class NotifierConfigError(ValueError):
    """``BOT_NOTIFIER`` names a channel whose required settings are missing or unsafe."""


class NotificationError(RuntimeError):
    """A backend could not deliver; the message never contains credentials."""
```

`src/bot/notifier/__init__.py`:

```python
"""Optional push of ``alerts.md`` to email or Telegram (spec §15, #32)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bot.notifier.base import NotificationError, Notifier, NotifierConfigError
from bot.notifier.email import EmailNotifier
from bot.notifier.telegram import TelegramNotifier
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    from bot.config import Settings

__all__ = ["NotificationError", "Notifier", "NotifierConfigError", "build_notifier", "notify_alerts"]

log = get_logger(__name__)


def _require(pairs: list[tuple[str, str]]) -> None:
    missing = [env for env, value in pairs if not value.strip()]
    if missing:
        raise NotifierConfigError(f"missing {', '.join(missing)}")


def build_notifier(settings: Settings) -> Notifier | None:
    if settings.notifier == "none":
        return None
    if settings.notifier == "email":
        recipients = [r.strip() for r in settings.smtp_to.split(",") if r.strip()]
        _require([
            ("BOT_SMTP_HOST", settings.smtp_host),
            ("BOT_SMTP_FROM", settings.smtp_from),
            ("BOT_SMTP_TO", ",".join(recipients)),
        ])
        if settings.smtp_security == "none" and settings.smtp_username.strip():
            raise NotifierConfigError(
                "BOT_SMTP_SECURITY=none would send BOT_SMTP_PASSWORD in cleartext; "
                "use starttls or ssl, or drop BOT_SMTP_USERNAME"
            )
        return EmailNotifier(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.smtp_from,
            recipients=recipients,
            username=settings.smtp_username,
            password=settings.smtp_password,
            security=settings.smtp_security,
        )
    _require([
        ("BOT_TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
        ("BOT_TELEGRAM_CHAT_ID", settings.telegram_chat_id),
    ])
    return TelegramNotifier(bot_token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)


def notify_alerts(alerts_path: Path, notifier: Notifier | None) -> bool:
    if notifier is None:
        return False
    text = alerts_path.read_text()
    if not text.strip():
        log.debug("alerts_empty_not_sent", alerts=str(alerts_path))
        return False
    notifier.send(text)
    log.info("alerts_sent", alerts=str(alerts_path), notifier=type(notifier).__name__)
    return True
```

Backend skeletons: constructors storing the arguments as attributes (`recipients` as `tuple(recipients)`); `send` raises `NotImplementedError` (replaced in Tasks 2/3). Note: inside `bot/notifier/email.py`, `from email.message import EmailMessage` resolves to the stdlib (absolute imports), so the module name is safe.

- [ ] **Step 4:** `uv run pytest tests/unit/test_notifier.py tests/unit/test_config.py -q && uv run ruff check . && uv run mypy src` — expected: PASS / clean.
- [ ] **Step 5:** Commit `feat(#32): notifier settings, build_notifier and notify_alerts`.

### Task 2: Telegram backend

**Files:**
- Modify: `src/bot/notifier/telegram.py`
- Test: `tests/unit/test_notifier_telegram.py`

**Interfaces:**
- Consumes: `NotificationError` from `bot.notifier.base`; constructor from Task 1.
- Produces: `TelegramNotifier.send(text: str) -> None`; module constants `API_BASE = "https://api.telegram.org"`, `MAX_MESSAGE_LEN = 4096`; `split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (`httpx.MockTransport`, no network):

```python
import json

import httpx
import pytest

from bot.notifier import NotificationError
from bot.notifier.telegram import MAX_MESSAGE_LEN, TelegramNotifier, split_message

TOKEN = "123456:SECRET-token"


def _notifier(handler) -> TelegramNotifier:
    return TelegramNotifier(bot_token=TOKEN, chat_id="-100", transport=httpx.MockTransport(handler))


def test_send_posts_plain_text_to_send_message() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    text = "# Alerts — 2026-06-01\n\n| Type | Ticker |\n| position_opened | AAPL |\n"
    _notifier(handler).send(text)

    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = json.loads(req.content)
    assert body["chat_id"] == "-100"
    assert body["text"] == text
    assert "parse_mode" not in body


def test_long_text_is_split_into_ordered_messages() -> None:
    texts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    lines = [f"| position_opened | T{i:04d} | {'x' * 60} |" for i in range(200)]
    text = "\n".join(lines) + "\n"
    _notifier(handler).send(text)

    assert len(texts) > 1
    assert all(len(t.encode("utf-16-le")) // 2 <= MAX_MESSAGE_LEN for t in texts)
    assert "".join(texts) == text


def test_split_message_hard_splits_an_overlong_line() -> None:
    chunks = split_message("a" * 10 + "\n", limit=4)
    assert chunks == ["aaaa", "aaaa", "aa\n"]


def test_split_message_counts_utf16_units() -> None:
    # "😀" is two UTF-16 code units: three of them do not fit in a 4-unit chunk.
    assert split_message("😀😀😀", limit=4) == ["😀😀", "😀"]


def test_api_error_raises_without_leaking_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(NotificationError) as exc:
        _notifier(handler).send("hello")
    assert "chat not found" in str(exc.value)
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None or TOKEN not in str(exc.value.__cause__)


def test_transport_error_raises_without_leaking_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(NotificationError) as exc:
        _notifier(handler).send("hello")
    assert TOKEN not in str(exc.value)
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_notifier_telegram.py -q` — expected: FAIL.

- [ ] **Step 3: Implement.**
  - `split_message`: walk `text.splitlines(keepends=True)`; append a line to the current chunk if the chunk's UTF-16 length plus the line's stays ≤ `limit`, else flush; a line longer than `limit` on its own is cut into `limit`-unit pieces (never splitting a surrogate pair: cut by characters, counting each char as 2 units if `ord(c) > 0xFFFF` else 1). Concatenating the chunks reproduces `text` exactly.
  - `send`: one `httpx.Client(base_url=API_BASE, transport=self._transport, timeout=self._timeout)`; for each chunk `client.post(f"/bot{token}/sendMessage", json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True})`.
  - Error handling: catch `httpx.HTTPError` → `raise NotificationError(f"Telegram request failed: {type(exc).__name__}") from None` (`from None` so the traceback does not chain the URL-bearing exception). Non-2xx → read `description` from the JSON body when present → `raise NotificationError(f"Telegram sendMessage HTTP {status}: {description}")`.

- [ ] **Step 4:** `uv run pytest tests/unit/test_notifier_telegram.py tests/unit/test_notifier.py -q && uv run ruff check . && uv run mypy src` — PASS / clean.
- [ ] **Step 5:** Commit `feat(#32): Telegram notifier backend`.

### Task 3: Email backend

**Files:**
- Modify: `src/bot/notifier/email.py`
- Test: `tests/unit/test_notifier_email.py`

**Interfaces:**
- Consumes: `NotificationError` from `bot.notifier.base`; constructor from Task 1.
- Produces: `SmtpFactory = Callable[[str, int, float], smtplib.SMTP]` (host, port, timeout → connected client); `EmailNotifier.send(text: str) -> None`.

- [ ] **Step 1: Write the failing tests** with a fake `smtplib.SMTP` subclass (constructing `smtplib.SMTP()` without a host does not connect; on leaving the `with` block, `smtplib.SMTP.__exit__` sends `QUIT` via `docmd`, which raises `SMTPServerDisconnected` on the unconnected fake and is swallowed, then `close()` — so no `quit` call is recorded):

```python
import smtplib
from email.message import EmailMessage

import pytest

from bot.notifier import NotificationError
from bot.notifier.email import EmailNotifier


class FakeSMTP(smtplib.SMTP):
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        super().__init__()
        self.args = (host, port, timeout)
        self.calls: list[str] = []
        self.messages: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def starttls(self, *args, **kwargs):  # type: ignore[override]
        self.calls.append("starttls")
        return (220, b"ok")

    def login(self, user, password, **kwargs):  # type: ignore[override]
        self.calls.append(f"login:{user}")
        return (235, b"ok")

    def send_message(self, msg, *args, **kwargs):  # type: ignore[override]
        self.calls.append("send_message")
        self.messages.append(msg)
        return {}


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSMTP.instances.clear()


def _notifier(**kw) -> EmailNotifier:
    base = dict(host="smtp.example.com", port=587, sender="bot@example.com",
                recipients=["a@x.com", "b@y.com"], username="u", password="s3cret",
                smtp_factory=FakeSMTP)
    base.update(kw)
    return EmailNotifier(**base)


def test_send_starttls_login_and_message() -> None:
    text = "# Alerts — 2026-06-01\n\n| position_opened | AAPL |\n"
    _notifier().send(text)
    smtp = FakeSMTP.instances[0]
    assert smtp.args[:2] == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", "login:u", "send_message"]
    msg = smtp.messages[0]
    assert msg["Subject"] == "Alerts — 2026-06-01"
    assert msg["From"] == "bot@example.com"
    assert msg["To"] == "a@x.com, b@y.com"
    assert msg.get_content() == text


def test_no_login_without_username_and_no_starttls_when_security_none() -> None:
    _notifier(username="", password="", security="none").send("hi")
    assert FakeSMTP.instances[0].calls == ["send_message"]


def test_subject_falls_back_when_text_has_no_heading_text() -> None:
    _notifier().send("\n#\n")
    assert FakeSMTP.instances[0].messages[0]["Subject"] == "bot alerts"


def test_smtp_failure_raises_notification_error_without_password() -> None:
    class Refusing(FakeSMTP):
        def login(self, user, password, **kwargs):  # type: ignore[override]
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    with pytest.raises(NotificationError) as exc:
        _notifier(smtp_factory=Refusing).send("hi")
    assert "s3cret" not in str(exc.value)


def test_connection_failure_raises_notification_error() -> None:
    def refuse(host: str, port: int, timeout: float) -> smtplib.SMTP:
        raise ConnectionRefusedError(111, "Connection refused")

    with pytest.raises(NotificationError):
        _notifier(smtp_factory=refuse).send("hi")
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_notifier_email.py -q` — expected: FAIL.

- [ ] **Step 3: Implement.**
  - Default factory: `smtplib.SMTP_SSL(host, port, timeout=timeout)` when `security == "ssl"`, else `smtplib.SMTP(host, port, timeout=timeout)`; for `starttls` use `ssl.create_default_context()`.
  - `send`: build `EmailMessage` (`Subject` from first non-empty line, `lstrip("#").strip()`, fallback `"bot alerts"`; `From` = sender; `To` = `", ".join(recipients)`; `set_content(text)`); `with factory(host, port, timeout) as smtp:` → `starttls` if security is `starttls` → `login` if `username` → `send_message(msg)`.
  - Wrap `(smtplib.SMTPException, OSError)` → `raise NotificationError(f"SMTP send to {host}:{port} failed: {exc}") from None`. `smtplib` exceptions carry the server reply (`SMTPAuthenticationError(code, resp)`), never the client's credentials; `from None` keeps both backends uniform.

- [ ] **Step 4:** `uv run pytest tests/unit/test_notifier_email.py tests/unit/test_notifier.py -q && uv run ruff check . && uv run mypy src` — PASS / clean.
- [ ] **Step 5:** Commit `feat(#32): email notifier backend`.

### Task 4: Hook into `bot portfolio`

**Files:**
- Modify: `src/bot/cli.py` (`portfolio` command; imports)
- Test: `tests/unit/test_cli_portfolio.py`

**Interfaces:**
- Consumes: `build_notifier`, `notify_alerts`, `NotifierConfigError`, `NotificationError` from `bot.notifier` (imported into `bot.cli` by name so tests can monkeypatch `bot.cli.build_notifier`). The test file already has `import bot.cli` and `from typing import Any`; add `from bot.notifier import NotificationError`.

- [ ] **Step 1: Write the failing tests** (append; reuse the file's `_env` fixture helper and `_FakeIbkrClient`, whose first run emits `position_opened` events so `alerts.md` is non-empty):

```python
class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def test_portfolio_sends_alerts_when_notifier_configured(tmp_path, monkeypatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch)
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.output
    alerts = next(reports_dir.glob("*/alerts.md")).read_text()
    assert rec.sent == [alerts]
    assert "Sent alerts via" in result.stdout


def test_portfolio_default_notifier_sends_nothing(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "none")  # process env beats a developer's .env

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.output
    assert "Sent alerts" not in result.stdout


def test_portfolio_skips_empty_alerts(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)
    real_run_portfolio = bot.cli.run_portfolio

    def _quiet_day(*args: Any, **kwargs: Any) -> Any:
        result = real_run_portfolio(*args, **kwargs)
        result.alerts_path.write_text("")  # what run_portfolio writes on a day with no events
        return result

    monkeypatch.setattr(bot.cli, "run_portfolio", _quiet_day)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.output
    assert rec.sent == []
    assert "Sent alerts" not in result.stdout


def test_portfolio_misconfigured_notifier_fails_before_sync(tmp_path, monkeypatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "telegram")
    monkeypatch.setenv("BOT_TELEGRAM_BOT_TOKEN", "")  # empty env beats a developer's .env
    monkeypatch.setenv("BOT_TELEGRAM_CHAT_ID", "")

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 2
    assert "Notifier misconfigured" in result.output
    assert "BOT_TELEGRAM_BOT_TOKEN" in result.output
    assert not list(reports_dir.glob("*/*.md"))


def test_portfolio_send_failure_exits_1_and_keeps_reports(tmp_path, monkeypatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch)

    class _Failing:
        def send(self, text: str) -> None:
            raise NotificationError("Telegram sendMessage HTTP 400: chat not found")

    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: _Failing())

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 1
    assert "Alerts not sent: Telegram sendMessage HTTP 400: chat not found" in result.output
    assert len(list(reports_dir.glob("*/alerts.md"))) == 1
```

`test_portfolio_skips_empty_alerts` forces a quiet day by blanking `alerts.md` after the real `run_portfolio`: with this fake every first snapshot opens positions, and a same-day rerun diffs against no earlier snapshot, so it never produces a natural empty day. The zero-byte-on-no-events contract itself is already pinned by `tests/integration/test_portfolio_command.py::test_alerts_present_but_empty_when_no_events`.

- [ ] **Step 2:** `uv run pytest tests/unit/test_cli_portfolio.py -q` — expected: new tests FAIL.

- [ ] **Step 3: Implement** in `portfolio()`:
  - After `settings = load_settings()` and before the preset check / `_open_db()`:

```python
    try:
        notifier = build_notifier(settings)
    except NotifierConfigError as exc:
        typer.echo(f"Notifier misconfigured (BOT_NOTIFIER={settings.notifier}): {exc}", err=True)
        raise typer.Exit(code=2) from exc
```

  - After the existing `typer.echo(f"Wrote {result.alerts_path}")`:

```python
    try:
        sent = notify_alerts(result.alerts_path, notifier)
    except NotificationError as exc:
        typer.echo(f"Alerts not sent: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if sent:
        typer.echo(f"Sent alerts via {settings.notifier}")
```

  - Replace the docstring's "Sending notifications is out of scope (the notifier owns email/Telegram)." with one sentence: "When ``BOT_NOTIFIER`` is ``email`` or ``telegram``, a non-empty ``alerts.md`` is then sent through that channel."

- [ ] **Step 4:** `uv run pytest tests/unit/test_cli_portfolio.py -q && uv run ruff check . && uv run mypy src` — PASS / clean.
- [ ] **Step 5:** Commit `feat(#32): send alerts.md from bot portfolio when a notifier is configured`.

### Task 5: Docs

**Files:**
- Modify: `.env.example`, `README.md` (new "Notifications" subsection after the IBKR configuration block), `src/bot/portfolio/command.py` (module docstring: replace "Sending notifications is out of scope (#32 owns email/Telegram)." with "Sending ``alerts.md`` is the CLI's job (``bot.notifier``, #32)."), `docs/plano/part-data.js` (`reports.idea[0]`: the "sin mail, sin Telegram" sentence now says that the output is a file on disk, and that an optional notifier forwards `alerts.md` by email or Telegram), `docs/plano/estado.py` (add inventory entry `("notifier", "Notificador opcional", "hecho", "notifier/__init__.py; notifier/email.py; notifier/telegram.py; cli.py", "<one-sentence note in Spanish: BOT_NOTIFIER elige email o Telegram; bot portfolio manda alerts.md si no está vacío; tests con transportes simulados>")` in the output section after `rep-portfolio`; update the `rep-portfolio` note if it still says notifications are out of scope).

- [ ] **Step 1:** `.env.example` — append commented block:

```bash
# BOT_NOTIFIER=none               # or: email, telegram — bot portfolio forwards a non-empty alerts.md
# BOT_SMTP_HOST=smtp.example.com  # email: required
# BOT_SMTP_PORT=587               # default; 465 with BOT_SMTP_SECURITY=ssl
# BOT_SMTP_SECURITY=starttls      # default; or: ssl, none
# BOT_SMTP_USERNAME=""
# BOT_SMTP_PASSWORD=""
# BOT_SMTP_FROM=bot@example.com   # email: required
# BOT_SMTP_TO=me@example.com      # email: required; comma-separated
# BOT_TELEGRAM_BOT_TOKEN=""       # telegram: required (from @BotFather)
# BOT_TELEGRAM_CHAT_ID=""         # telegram: required
```

- [ ] **Step 2:** README subsection: what is sent (contents of `alerts.md`, plain text, nothing on quiet days), the env vars, the two failure exit codes (2 misconfigured before sync, 1 send failure after reports are written), and that there is no automatic retry — re-running `bot portfolio` the same day re-renders and re-sends the day's alerts.
- [ ] **Step 3:** `python3 docs/plano/build.py && python3 docs/plano/build_estado.py` — expected: both build (the estado "old snapshot" warning is acceptable). If `build.py` reports a new dependency tension or unknown symbol, fix the plano sources, not the code.
- [ ] **Step 4:** `uv run pytest -q && uv run ruff check . && uv run mypy src` — all green.
- [ ] **Step 5:** Commit `docs(#32): document the notifier`.

## Grilling

One round (griller: `fable`); 16 questions. Revisions were local (a leaf `base.py`, test fixes, one guard), not a different seam, so no second round.

| # | Answer source |
|---|---|
| 1 | CODE: `/usr/lib/python3.12/smtplib.py` `SMTP.__exit__` — `docmd("QUIT")`, swallows `SMTPServerDisconnected`, `close()`; never `quit()`. Test fixed: no `quit` in the expected calls. |
| 2 | CODE: `src/bot/config.py:13-18` (`env_file=".env"`), `:98-100` (`load_settings` → `Settings()`); `tests/unit/test_cli_portfolio.py:85-98` (`_env` sets env only). Process env beats `.env` in pydantic-settings, so the CLI tests now `setenv` (`BOT_NOTIFIER=none`, empty token/chat id) instead of `delenv`. |
| 3 | CODE: `src/bot/cli.py:553` `load_settings()`, `:554-558` preset check (exit 2), `:560` `_open_db()`, `:564-583` `run_portfolio` (TWS connect inside), `:590` `Wrote {alerts_path}`; `src/bot/portfolio/command.py:60` `PortfolioRunResult.alerts_path`. |
| 4 | NO SOURCE → technical assumption (no retry; same-day rerun re-sends, `command.py:111`). |
| 5 | DOC: spec §9 "Exit codes: 0 OK, 1 error operativo, 2 data error"; CODE: `cli.py:558` missing preset → 2. |
| 6 | CODE: `command.py:141-143` always writes `alerts.md` before returning; if `run_portfolio` raises, the CLI exits before `notify_alerts`. Test id confirmed: `tests/integration/test_portfolio_command.py:174`. |
| 7 | CODE: `tests/unit/test_cli_portfolio.py:12,17` (`Any`, `import bot.cli`), `:85-98` (`_env` does not create `reports_dir`); `tests/integration/test_portfolio_command.py:145-171` (first snapshot → `position_opened`). |
| 8 | CODE: `pyproject.toml:58` ruff `select` has `TID`, no `PLC`. Cycle removed via `base.py` → assumption. |
| 9 | CODE: `src/bot/utils/logging.py:50-52` returns `structlog.stdlib.BoundLogger`; same style at `command.py:144`. |
| 10 | CODE: `smtplib.SMTP.login` raises `SMTPAuthenticationError(code, resp)` with the server reply. Email now uses `from None` as well. |
| 11 | CODE: no `model_dump`/`repr(settings)` in `src/`; `cli.py:611` prints keys as `set`/`MISSING`. |
| 12 | NO SOURCE → technical assumption (`none` kept for local relays; `none` + username rejected). |
| 13 | CODE: `command.py:142-143` `write_text` default encoding → assumption (read with the same default). |
| 14 | CODE: `config.py:21-24` only `sec_user_agent` is required (`...`); `test_blank_notifier_is_none` feeds the value through the env, so it exercises the `mode="before"` validator on the env path. |
| 15 | DOC: `docs/plano/README.md` "Por qué falla el build a propósito" (build checks symbols cited in fichas and dependency tensions; the estado inventory is free text) and step 3 (`AUDITADO_EN` = commit of a real re-audit). |
| 16 | ISSUE: "Hook in `bot portfolio` that sends the alerts file when notifier is configured"; exit codes and hook location → assumptions; DOC: spec §12 "degrade gracefully, alert loudly". |

Per source type: CODE 12, DOC 3 (with CODE overlap), ISSUE 1, NO SOURCE 3 (all technical assumptions; none spec ambiguity, none out of scope).

Assumptions: see `## Assumptions`. Issues opened: none.
