"""Checks that every citation in the d2 pipeline boards still matches the repo.

    python3 docs/pipeline/check.py [dir]

Each board (`*.d2` in the folder, `classes.d2` aside) carries directives in d2
line comments, e.g. `# @symbol bot.cli.refresh`. This script resolves symbols
against the index docs/plano/codemap.py builds with ast, tables against
src/bot/storage/schema.sql, files against the repository root, `link:` targets
against the folder, and requires one SVG per board plus a fresh rendered.sha256.
Exit 1 and one `error  <msg>` line per problem; stdlib only.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import NamedTuple

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "plano"))

import codemap  # noqa: E402

KINDS: tuple[str, ...] = ("symbol", "table", "file", "rule", "param", "const", "enum")

_OPEN_RE = re.compile(r"(\|{1,3})(?:md|markdown)\b")
_DIRECTIVE_RE = re.compile(r"@(\w+)\s+(\S+)")
_WORD_RE = re.compile(r"@(\w+)")
_LINK_RE = re.compile(r"(?:^|[\s.{;])link:\s*[\"']?([^\"'\s}]+)")
_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.I)


class Directive(NamedTuple):
    kind: str
    argument: str
    text: str
    line: int


class _Line(NamedTuple):
    number: int
    code: str  # without comment and without md content
    visible: str  # without comment, md content kept
    comment: str


def _scan(text: str) -> list[_Line]:
    """One pass over the board; state is the closer of the md block we are in."""
    out: list[_Line] = []
    closer: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        code: list[str] = []
        vis: list[str] = []
        comment = ""
        i, quote = 0, ""
        while i < len(raw):
            if closer is not None:
                end = raw.find(closer, i)
                stop = len(raw) if end < 0 else end + len(closer)
                vis.append(raw[i:stop])
                i = stop
                if end >= 0:
                    closer = None
                continue
            ch = raw[i]
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch == "#" and (i == 0 or raw[i - 1].isspace()):
                comment = raw[i + 1 :]
                break
            elif ch == "|" and (m := _OPEN_RE.match(raw, i)):
                closer = m.group(1)
                code.append(raw[i : m.end()])
                vis.append(raw[i : m.end()])
                i = m.end()
                continue
            code.append(ch)
            vis.append(ch)
            i += 1
        out.append(_Line(number, "".join(code), "".join(vis), comment))
    return out


def directives(text: str) -> list[Directive]:
    found: list[Directive] = []
    pending: list[tuple[str, str]] = []
    for ln in _scan(text):
        pending += [(k, a) for k, a in _DIRECTIVE_RE.findall(ln.comment) if k in KINDS]
        shown_text = ln.visible.strip()
        if shown_text and pending:
            found += [Directive(k, a, shown_text, ln.number) for k, a in pending]
            pending = []
    return found


def unknown_directives(text: str) -> list[tuple[str, int]]:
    return [
        (f"@{w}", ln.number)
        for ln in _scan(text)
        for w in _WORD_RE.findall(ln.comment)
        if w not in KINDS
    ]


def links(text: str) -> list[tuple[str, int]]:
    return [(m[1], ln.number) for ln in _scan(text) if (m := _LINK_RE.search(ln.code))]


def visible(text: str) -> str:
    return "\n".join(ln.visible for ln in _scan(text))


def normalize(text: str) -> str:
    return " ".join(text.replace("\u2212", "-").split())


def _num(x: float) -> str:
    return str(int(x)) if x == int(x) else repr(x)


def renderings(value: object) -> set[str]:
    if isinstance(value, (tuple, list)):
        return {r for v in value for r in renderings(v)}
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {str(value)}
    out = {str(value)}
    if float(value).is_integer():
        n = int(value)
        out |= {str(n), f"{n:,}"}
        for suffix, unit in (("K", 10**3), ("M", 10**6), ("B", 10**9)):
            if n % unit == 0:
                out.add(f"{n // unit}{suffix}")
    out.add(f"{_num(round(value * 100, 9))}%")
    if abs(value) < 1:
        bps = _num(round(value * 10000, 6))
        out |= {f"{bps} bps", f"{bps}bps"}
    return out


def shown(value: object, text: str) -> bool:
    if isinstance(value, (tuple, list)):
        return all(shown(v, text) for v in value)
    haystack = normalize(text)
    return any(normalize(r) in haystack for r in renderings(value))


def indice() -> dict[str, tuple[str, int]]:
    modulos, _, simbolos = codemap.escanear()
    idx = {mod: (m["archivo"], 1) for mod, m in modulos.items()}
    for clave, s in simbolos.items():
        nombre = clave.split(":", 1)[1]
        idx[f"{s['modulo']}.{nombre}"] = (s["archivo"], s["linea"])
    return idx


def tablas(schema: str) -> set[str]:
    return set(_TABLE_RE.findall(schema))


def boards(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*.d2") if p.name != "classes.d2")


def source_hash(folder: Path) -> str:
    return hashlib.sha256(b"".join(p.read_bytes() for p in sorted(folder.glob("*.d2")))).hexdigest()


def revisar(
    folder: Path, idx: dict[str, tuple[str, int]], tables: set[str]
) -> tuple[list[str], int]:
    errors: list[str] = []
    count = 0
    for board in boards(folder):
        text = board.read_text(encoding="utf-8")
        found = directives(text)
        count += len(found)
        for d in found:
            where = f"{board.name}:{d.line}"
            if d.kind == "symbol" and d.argument not in idx:
                errors.append(f"{where} unknown @symbol {d.argument}")
            elif d.kind == "table" and d.argument not in tables:
                errors.append(f"{where} unknown @table {d.argument}")
            elif d.kind == "file" and not (codemap.REPO / d.argument).exists():
                errors.append(f"{where} missing @file {d.argument}")
        for word, line in unknown_directives(text):
            errors.append(f"{board.name}:{line} unknown directive {word}")
        for target, line in links(text):
            if not (folder / target).exists():
                errors.append(f"{board.name}:{line} missing link target {target}")
        svg = board.with_suffix(".svg")
        if not svg.exists():
            errors.append(f"{board.name} has no {svg.name}")
    stamp = folder / "rendered.sha256"
    if not stamp.exists():
        errors.append("rendered.sha256 missing")
    elif stamp.read_text().strip() != source_hash(folder):
        errors.append("rendered.sha256 is stale: run docs/pipeline/build.sh")
    return errors, count


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    folder = Path(args[0]) if args else AQUI
    schema = (codemap.REPO / "src" / "bot" / "storage" / "schema.sql").read_text()
    errors, count = revisar(folder, indice(), tablas(schema))
    for e in errors:
        print(f"error  {e}")
    print(f"check | {len(boards(folder))} boards, {count} citations, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
