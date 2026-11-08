"""Write one ticker's report set all-or-none (#178).

The Markdown, HTML and JSON reports of an analysis belong together. A write
that fails halfway must not leave one of them on disk without its siblings,
nor mix new files with an older complete set.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


class ReportWriteError(Exception):
    """A report set could not be written; ``path`` names the report or directory."""

    def __init__(self, path: Path, cause: OSError) -> None:
        self.path = path
        super().__init__(f"{path}: {cause.strerror or cause}")


def write_report_set(out_dir: Path, files: Mapping[str, str]) -> list[Path]:
    """Write ``files`` (name to content) into ``out_dir``, all or none."""
    raise NotImplementedError
