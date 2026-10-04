"""The GitHub Pages workflow gates on quality before deploying (issue #92)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "site.yml"


def _load() -> dict[Any, Any]:
    if not _WORKFLOW.exists():
        pytest.skip("`.github/workflows/site.yml` is added by a human, see #92 (workflow scope)")
    data: dict[Any, Any] = yaml.safe_load(_WORKFLOW.read_text())
    return data


def test_triggers_only_on_push_to_master() -> None:
    data = _load()
    trigger = data.get("on", data.get(True))
    assert trigger == {"push": {"branches": ["master"]}}


def test_build_gates_then_builds_the_site() -> None:
    steps = _load()["jobs"]["build"]["steps"]
    runs = [s["run"] for s in steps if "run" in s]
    gate = ["uv run ruff check .", "uv run mypy src", "uv run pytest -q"]
    positions = [runs.index(cmd) for cmd in gate]
    assert positions == sorted(positions)
    site = [i for i, r in enumerate(runs) if r.startswith("uv run bot site")]
    assert len(site) == 1 and site[0] > positions[-1]
    assert "--out site" in runs[site[0]]
    assert '--base-url "/${{ github.event.repository.name }}/"' in runs[site[0]]
    uses = [s.get("uses", "") for s in steps]
    assert any(u.startswith("actions/upload-pages-artifact@") for u in uses)


def test_deploy_needs_build_and_uses_pages() -> None:
    data = _load()
    deploy = data["jobs"]["deploy"]
    assert deploy["needs"] == "build"
    assert deploy["environment"]["name"] == "github-pages"
    assert any(s.get("uses", "").startswith("actions/deploy-pages@") for s in deploy["steps"])
    assert data["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
