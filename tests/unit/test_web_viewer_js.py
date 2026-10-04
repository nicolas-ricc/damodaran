"""The viewer's local script and the htmx wiring it relies on (issue #92)."""

from __future__ import annotations

import re
from pathlib import Path

_WEB = Path(__file__).resolve().parents[2] / "src" / "bot" / "web"


def test_viewer_script_is_local_and_loaded() -> None:
    script = (_WEB / "static" / "viewer.js").read_text()
    assert not re.search(r"https?://", script)
    assert "static/viewer.js" in (_WEB / "templates" / "base.html").read_text()


def test_rows_do_not_gate_the_click_in_the_template() -> None:
    assert "matchMedia" not in (_WEB / "templates" / "_rows.html").read_text()


def test_detail_links_use_the_crossfade_delay() -> None:
    for name in ("_rows.html", "detail.html"):
        assert 'hx-swap="innerHTML swap:120ms"' in (_WEB / "templates" / name).read_text()
