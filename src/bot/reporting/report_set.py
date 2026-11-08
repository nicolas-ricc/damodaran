"""Write one ticker's report set all-or-none (#178).

The Markdown, HTML and JSON reports of an analysis belong together. A write
that fails halfway must not leave one of them on disk without its siblings,
nor mix new files with an older complete set. Contents go to temporaries
first, so a failed write leaves any previous set untouched; the renames that
follow are the only step that can change the targets.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from pathlib import Path


class ReportWriteError(Exception):
    """A report set could not be written; ``path`` names the report or directory."""

    def __init__(self, path: Path, cause: OSError) -> None:
        self.path = path
        super().__init__(f"{path}: {cause.strerror or cause}")


def write_report_set(out_dir: Path, files: Mapping[str, str]) -> list[Path]:
    """Write ``files`` (name to content) into ``out_dir``, all or none."""
    targets = {name: out_dir / name for name in files}
    temps = {name: out_dir / f".{name}.tmp" for name in files}
    renaming = False
    path = out_dir
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            path = targets[name]
            temps[name].write_text(content)
        renaming = True
        for name in files:
            path = targets[name]
            os.replace(temps[name], path)
    except BaseException as exc:
        doomed = [*temps.values(), *(targets.values() if renaming else ())]
        for victim in doomed:
            with contextlib.suppress(OSError):
                victim.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise ReportWriteError(path, exc) from exc
        raise
    return list(targets.values())
