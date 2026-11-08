"""``write_report_set`` writes a report set all-or-none (#178)."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

import bot.reporting.report_set as report_set
from bot.reporting.report_set import ReportWriteError, write_report_set

_FILES = {"A.md": "m", "A.html": "h", "A.json": "j"}


def _fail_write_text(monkeypatch: pytest.MonkeyPatch, name: str, exc: BaseException) -> None:
    real = Path.write_text

    def write_text(self: Path, *args: object, **kwargs: object) -> int:
        if self.name == name:
            raise exc
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", write_text)


def _enospc() -> OSError:
    return OSError(errno.ENOSPC, "No space left on device")


def _write_old_set(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in _FILES:
        (out_dir / name).write_text("old")


def test_writes_every_file_and_no_temporary(tmp_path: Path) -> None:
    out_dir = tmp_path / "analysis"
    paths = write_report_set(out_dir, _FILES)
    assert paths == [out_dir / "A.md", out_dir / "A.html", out_dir / "A.json"]
    for name, content in _FILES.items():
        assert (out_dir / name).read_text() == content
    assert sorted(p.name for p in out_dir.iterdir()) == ["A.html", "A.json", "A.md"]


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    out_dir = tmp_path / "x" / "y"
    write_report_set(out_dir, _FILES)
    assert (out_dir / "A.md").read_text() == "m"


def test_a_failed_write_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir = tmp_path / "analysis"
    _fail_write_text(monkeypatch, ".A.html.tmp", _enospc())
    with pytest.raises(ReportWriteError) as info:
        write_report_set(out_dir, _FILES)
    assert info.value.path == out_dir / "A.html"
    assert "No space left on device" in str(info.value)
    assert str(out_dir / "A.html") in str(info.value)
    assert list(out_dir.iterdir()) == []


def test_a_failed_write_keeps_the_previous_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "analysis"
    _write_old_set(out_dir)
    _fail_write_text(monkeypatch, ".A.json.tmp", _enospc())
    with pytest.raises(ReportWriteError):
        write_report_set(out_dir, _FILES)
    for name in _FILES:
        assert (out_dir / name).read_text() == "old"
    assert sorted(p.name for p in out_dir.iterdir()) == ["A.html", "A.json", "A.md"]


def test_a_failed_rename_removes_the_whole_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "analysis"
    _write_old_set(out_dir)
    real = report_set.os.replace

    def replace(src: object, dst: object) -> None:
        if Path(str(dst)).name == "A.html":
            raise _enospc()
        real(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(report_set.os, "replace", replace)
    with pytest.raises(ReportWriteError) as info:
        write_report_set(out_dir, _FILES)
    assert info.value.path == out_dir / "A.html"
    assert list(out_dir.iterdir()) == []


def test_a_failed_mkdir_is_a_report_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "analysis"

    def mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(ReportWriteError) as info:
        write_report_set(out_dir, _FILES)
    assert info.value.path == out_dir
    assert "Permission denied" in str(info.value)


def test_written_files_have_the_default_mode(tmp_path: Path) -> None:
    out_dir = tmp_path / "analysis"
    write_report_set(out_dir, _FILES)
    sibling = tmp_path / "plain.txt"
    sibling.write_text("x")
    for name in _FILES:
        assert (out_dir / name).stat().st_mode == sibling.stat().st_mode


def test_a_stale_temporary_is_overwritten(tmp_path: Path) -> None:
    out_dir = tmp_path / "analysis"
    out_dir.mkdir()
    (out_dir / ".A.md.tmp").write_text("stale")
    write_report_set(out_dir, _FILES)
    assert (out_dir / "A.md").read_text() == "m"
    assert not list(out_dir.glob("*.tmp"))


def test_other_exceptions_clean_up_and_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "analysis"
    _fail_write_text(monkeypatch, ".A.html.tmp", KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        write_report_set(out_dir, _FILES)
    assert list(out_dir.iterdir()) == []
