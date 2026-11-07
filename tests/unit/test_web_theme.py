"""DaisyUI vendoring, the synthwave theme and the palette swap (issue #258)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from bot.web.site import build
from tests.web_sidecars import make_sidecar, write_sidecar

_ROOT = Path(__file__).resolve().parents[2]
_WEB = _ROOT / "src" / "bot" / "web"
_STATIC = _WEB / "static"
_SCRIPT = _ROOT / "scripts" / "vendor_daisyui.sh"

# Spec section 3, verbatim: a dropped or edited variable fails.
_THEME_VARS = (
    ("--color-base-100", "oklch(15% 0.09 281.288)"),
    ("--color-base-200", "oklch(20% 0.09 281.288)"),
    ("--color-base-300", "oklch(25% 0.09 281.288)"),
    ("--color-base-content", "oklch(78% 0.115 274.713)"),
    ("--color-primary", "oklch(71% 0.202 349.761)"),
    ("--color-primary-content", "oklch(28% 0.109 3.907)"),
    ("--color-secondary", "oklch(82% 0.111 230.318)"),
    ("--color-secondary-content", "oklch(29% 0.066 243.157)"),
    ("--color-accent", "oklch(75% 0.183 55.934)"),
    ("--color-accent-content", "oklch(26% 0.079 36.259)"),
    ("--color-neutral", "oklch(45% 0.24 277.023)"),
    ("--color-neutral-content", "oklch(87% 0.065 274.039)"),
    ("--color-info", "oklch(74% 0.16 232.661)"),
    ("--color-info-content", "oklch(29% 0.066 243.157)"),
    ("--color-success", "oklch(77% 0.152 181.912)"),
    ("--color-success-content", "oklch(27% 0.046 192.524)"),
    ("--color-warning", "oklch(90% 0.182 98.111)"),
    ("--color-warning-content", "oklch(42% 0.095 57.708)"),
    ("--color-error", "oklch(73.7% 0.121 32.639)"),
    ("--color-error-content", "oklch(23.501% 0.096 290.329)"),
    ("--radius-selector", "0rem"),
    ("--radius-field", "0rem"),
    ("--radius-box", "0rem"),
    ("--size-selector", "0.25rem"),
    ("--size-field", "0.25rem"),
    ("--border", "1px"),
    ("--depth", "1"),
    ("--noise", "1"),
)

_RIM_TOKENS = (
    "--color-paper",
    "--color-ink",
    "--color-muted",
    "--color-rule",
    "--color-accent",
    "--color-focus",
    "--color-under",
    "--color-fair",
    "--color-over",
)


def _pins() -> dict[str, str]:
    pins = re.findall(r'^DAISYUI_(VERSION|SHA256)="([^"]+)"', _SCRIPT.read_text(), re.MULTILINE)
    return dict(pins)


def test_vendored_daisyui_matches_the_script_pin() -> None:
    pins = _pins()
    data = (_STATIC / "daisyui.css").read_bytes()
    assert hashlib.sha256(data).hexdigest() == pins["SHA256"]
    assert f"daisyUI {pins['VERSION']}" in data.decode().splitlines()[0]
    line = f"daisyui {pins['VERSION']} (MIT License) https://daisyui.com"
    assert line in (_STATIC / "VERSIONS").read_text().splitlines()


def test_daisyui_css_fetches_nothing_remote() -> None:
    css = (_STATIC / "daisyui.css").read_text()
    assert "@import" not in css
    assert re.search(r"url\(\s*['\"]?https?:", css) is None


def test_theme_css_defines_every_synthwave_variable() -> None:
    css = (_STATIC / "theme.css").read_text()
    assert '[data-theme="synthwave"]' in css
    assert "color-scheme: dark" in css
    for name, value in _THEME_VARS:
        assert f"{name}: {value};" in css, name
    assert "@layer" not in css


def test_built_index_uses_the_theme_and_links_in_order(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    write_sidecar(reports, "2026-10-01", make_sidecar("AAA", mos=1.5))
    out = tmp_path / "site"
    build(reports, out, "/")
    index = (out / "index.html").read_text()
    assert '<html lang="en" data-theme="synthwave">' in index
    hrefs = [f'href="/static/{name}"' for name in ("daisyui.css", "theme.css", "app.css")]
    positions = [index.find(h) for h in hrefs]
    assert -1 not in positions, positions
    assert positions == sorted(positions)
    assert all(index.count(h) == 1 for h in hrefs)
    assert (out / "static" / "daisyui.css").is_file()
    assert (out / "static" / "theme.css").is_file()


def test_no_rim_token_survives() -> None:
    paths = [_STATIC / "app.css", _WEB / "svg.py", *(_WEB / "templates").glob("*.html")]
    for path in paths:
        text = path.read_text()
        for token in _RIM_TOKENS:
            assert token not in text, f"{token} in {path.name}"


def test_list_table_overrides_daisyui_list_component() -> None:
    css = (_STATIC / "app.css").read_text()
    rule = re.search(r"^\.list \{[^}]*\}", css, re.M)
    assert rule is not None
    assert "display: table" in rule.group(0)
