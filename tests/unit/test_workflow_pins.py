"""Every GitHub Action is pinned to a commit SHA and Dependabot bumps the pins (issue #96)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_USES = re.compile(r"^\s*(?:- )?uses:")
_PINNED = re.compile(r"^\s*(?:- )?uses:\s*[\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+\s*$")


def test_every_action_is_pinned_to_a_sha_with_a_version_comment() -> None:
    # Raw text, not YAML: PyYAML drops the version comment.
    lines = [
        (wf.name, line)
        for wf in sorted((_ROOT / ".github" / "workflows").glob("*.yml"))
        for line in wf.read_text().splitlines()
        if _USES.match(line)
    ]
    for name, line in lines:
        assert _PINNED.match(line), f"{name}: not pinned to a SHA with a version comment: {line}"
    assert len(lines) >= 10, f"expected at least 10 uses: lines, found {len(lines)}"


def test_dependabot_updates_github_actions_weekly() -> None:
    data: dict[Any, Any] = yaml.safe_load((_ROOT / ".github" / "dependabot.yml").read_text())
    assert data["version"] == 2
    assert len(data["updates"]) == 1
    update = data["updates"][0]
    assert update["package-ecosystem"] == "github-actions"
    assert update["directory"] == "/"
    assert update["schedule"] == {"interval": "weekly"}
    assert update["groups"] == {"github-actions": {"patterns": ["*"]}}
