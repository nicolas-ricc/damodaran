"""The stale-audit warning of ``docs/plano/build_estado.py`` (issue #205).

``desfasaje()`` counts the commits since ``estado.AUDITADO_EN`` that touched the
repository's top-level ``src/``. Git runs with ``cwd`` in ``docs/plano/``, so a
bare ``src`` pathspec resolved to ``docs/plano/src`` and the count was always 0.
The tests drive the real module against a throwaway repository laid out like
this one, with ``AQUI`` pointed at its ``docs/plano/``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PLANO = _ROOT / "docs" / "plano"
_BANNER = 'class="viejo"'


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "--no-verify", "-q", "-m", f"touch {path}")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "src" / "bot").mkdir(parents=True)
    (root / "src" / "bot" / "__init__.py").write_text("", encoding="utf-8")
    _commit(root, "docs/plano/README.md", "plano\n")
    return root, _git(root, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def _loaded() -> ModuleType:
    """Load build_estado once, undoing the sys.path entry and bare imports it adds."""
    path, modules = list(sys.path), set(sys.modules)
    spec = importlib.util.spec_from_file_location("plano_build_estado", _PLANO / "build_estado.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = path
        for name in set(sys.modules) - modules:
            del sys.modules[name]
    return module


@pytest.fixture
def build_estado(
    _loaded: ModuleType, monkeypatch: pytest.MonkeyPatch, repo: tuple[Path, str]
) -> ModuleType:
    root, audited = repo
    monkeypatch.setattr(_loaded, "AQUI", root / "docs" / "plano")
    monkeypatch.setattr(_loaded.estado, "AUDITADO_EN", audited)
    return _loaded


def _html(module: ModuleType) -> str:
    return (module.AQUI / "estado.html").read_text(encoding="utf-8")


def test_src_commit_after_audit_is_counted(
    build_estado: ModuleType, repo: tuple[Path, str]
) -> None:
    root, _ = repo
    _commit(root, "src/bot/x.py", "x = 1\n")
    _commit(root, "src/bot/y.py", "y = 1\n")
    assert build_estado.desfasaje() == 2


def test_banner_rendered_when_src_moved(build_estado: ModuleType, repo: tuple[Path, str]) -> None:
    root, _ = repo
    _commit(root, "src/bot/x.py", "x = 1\n")
    assert _BANNER in build_estado.aviso_desfasaje()
    build_estado.main()
    assert _BANNER in _html(build_estado)


def test_console_warning_printed_when_src_moved(
    build_estado: ModuleType, repo: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = repo
    _commit(root, "src/bot/x.py", "x = 1\n")
    build_estado.main()
    assert "AVISO" in capsys.readouterr().out


def test_docs_only_commit_after_audit_is_not_counted(
    build_estado: ModuleType, repo: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = repo
    _commit(root, "docs/plano/src/nota.md", "no es código\n")
    _commit(root, "docs/x.md", "doc\n")
    assert build_estado.desfasaje() == 0
    assert build_estado.aviso_desfasaje() == ""
    build_estado.main()
    assert _BANNER not in _html(build_estado)
    assert "AVISO" not in capsys.readouterr().out


def test_count_is_the_same_from_any_cwd(
    build_estado: ModuleType,
    repo: tuple[Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = repo
    _commit(root, "src/bot/x.py", "x = 1\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    counts = []
    for cwd in (root, root / "docs" / "plano", elsewhere):
        monkeypatch.chdir(cwd)
        counts.append(build_estado.desfasaje())
    assert counts == [1, 1, 1]


def test_git_unavailable_gives_no_banner(
    build_estado: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert build_estado.desfasaje() is None
    assert build_estado.aviso_desfasaje() == ""


def test_unknown_audit_commit_gives_no_banner(
    build_estado: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_estado.estado, "AUDITADO_EN", "0" * 40)
    assert build_estado.desfasaje() is None
    assert build_estado.aviso_desfasaje() == ""


def test_real_builder_same_output_from_any_cwd() -> None:
    outputs = []
    for cwd in (_ROOT, _PLANO):
        result = subprocess.run(
            [sys.executable, str(_PLANO / "build_estado.py")],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
