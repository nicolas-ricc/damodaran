"""The GitHub Pages workflow gates on quality before deploying (issue #92)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "site.yml"


def _load() -> dict[Any, Any]:
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
    positions: list[int] = []
    for cmd in gate:
        assert cmd in runs, f"gate command missing from the build job of site.yml: {cmd}"
        positions.append(runs.index(cmd))
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
    assert data["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert "permissions" not in data["jobs"]["build"]


def test_concurrency_cancels_superseded_deploys() -> None:
    assert _load()["concurrency"] == {"group": "pages", "cancel-in-progress": True}
