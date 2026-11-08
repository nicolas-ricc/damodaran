"""The README states the real lint and format policy (issue #78)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WHOLE_TREE = re.compile(r"ruff format(\s+-\S+)*\s+\.(?=[\s`]|$)", re.MULTILINE)
_CI_COMMAND = re.compile(r"^\s*- run: (uv run (?:ruff|mypy|pytest)\b.*)$", re.MULTILINE)


def _readme() -> str:
    return (_ROOT / "README.md").read_text(encoding="utf-8")


def _development_section() -> str:
    readme = _readme()
    heading = "\n## Development\n"
    assert heading in readme
    start = readme.index(heading)
    end = readme.find("\n## ", start + len(heading))
    return readme[start:] if end == -1 else readme[start:end]


def test_readme_has_no_whole_tree_format() -> None:
    readme = _readme()
    assert "ruff format ." not in readme
    assert _WHOLE_TREE.search(readme) is None
    for args in re.findall(r"uv run ruff format([^`\n#]*)", readme):
        paths = [a for a in args.split() if not a.startswith("-")]
        assert paths and "." not in paths, args


def test_readme_lists_ci_commands() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "site.yml").read_text(encoding="utf-8")
    commands = [c.strip() for c in _CI_COMMAND.findall(workflow)]
    assert len(commands) >= 3
    section = _development_section()
    for command in commands:
        assert command in section, command


def test_readme_lists_lint_gate() -> None:
    with (_ROOT / ".factory" / "config.toml").open("rb") as f:
        lint = tomllib.load(f)["lint"]
    assert lint in _development_section()


def test_readme_says_format_not_enforced() -> None:
    section = _development_section()
    assert "not enforced" in section
    assert "--fix" in section
    assert "whole tree" in section
