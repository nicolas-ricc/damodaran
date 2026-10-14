# Lección del pipeline de Damodaran — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-contained HTML lesson, `docs/leccion/index.html`, that explains the Damodaran pipeline (Capas A, B, C) and where each piece lives in `src/bot/`, plus `docs/leccion/check.py`, which fails when the lesson cites a symbol that no longer exists.

**Architecture:** One hand-written HTML file with inline CSS and a small inline script (no build step), nine `<section>` chapters behind a fixed chapter nav. Every claim that can drift from the code is marked up so a test can compare it with the code: `data-symbol` on cited symbols (checked by `check.py` against `docs/plano/codemap.py`'s AST index), `<data data-param>` on preset thresholds and ranking weights (checked against `config/presets/damodaran_value.yaml` and `RankingWeights`), `<data data-const>` on named module constants (checked by import), and `<data data-dcf>` / `data-dcf-out` on the DCF example (recomputed with `bot.valuator.dcf.dcf`). `tests/unit/test_leccion.py` runs all of it inside `uv run pytest -q`.

**Tech Stack:** HTML/CSS (OKLCH tokens), vanilla JS, Python 3.12 stdlib (`ast`, `html.parser`, `re`) for `check.py`; pytest + PyYAML (already a dependency) for the tests.

**Spec:** GitHub issue #120 (nicolas-ricc/damodaran), «Lección: cómo funciona el pipeline de Damodaran y dónde vive en el código». Sources of truth, in order: `src/bot/`, `docs/plano/part-data.js`, `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §3–§7, ADR 0001/0005/0006/0007, `docs/PRODUCT.md`, `docs/DESIGN.md`.

## Global Constraints

- The code in `src/bot/` beats the spec. Where they disagree, the lesson says what the code does and may add a caveat naming the difference.
- `docs/leccion/index.html` is self-contained: no `<script src>`, no `<link>` except to `fonts.googleapis.com` / `fonts.gstatic.com`, no base64 fonts, no SVG wobble filter (`feTurbulence`). Opens by double click with all content visible; no animation or script is a condition for content to show.
- Nine chapters, ids `cap-0` … `cap-8`, in the issue's order and with its working titles. Each chapter: concept → round-number example → «En el código» → caveat where it applies.
- Spanish rioplatense, voice of `docs/PRODUCT.md`. No summation signs or math notation; the DCF is one sentence plus a year-by-year table with numbers.
- Code symbols cited as `bot.modulo.Nombre` in mono, followed by `src/bot/<archivo>.py:<línea>`.
- Fonts via Google Fonts: Shantell Sans (titles), Literata (body), Sometype Mono (identifiers), each with a system fallback.
- Tokens from `docs/DESIGN.md` as OKLCH custom properties in `:root`; light by default, dark under `prefers-color-scheme: dark`. Body text ≥ 4.5:1 on `--sheet`. No horizontal scroll at 390px. Body measure between 65ch and 75ch.
- `check.py` is stdlib only and imports `docs/plano/codemap.py`; nothing else in `docs/plano/` changes. `src/` is not touched.
- `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q` stay green.

## Decisions (technical assumptions, declared)

1. **`AssumptionSource` has seven values, not five.** The issue says «los cinco valores de `AssumptionSource` … tal como están en el enum». The enum (`src/bot/valuator/assumptions.py:84`) has seven: `manual`, `sector_default_damodaran`, `sector_default_damodaran_cross_region`, `rule_based`, `historical_average`, `story_pattern`, `unresolved`. Spec §7.3 lists five including `analyst_consensus`, which the code does not have. Per the issue's own precedence rule (code first), chapter 7 lists all seven enum values verbatim and a caveat notes the spec's `analyst_consensus` does not exist in code. The test iterates the enum, so it stays true if the enum changes.
2. **Line numbers.** `check.py` hard-fails on a `data-symbol` that does not resolve and on a cited `src/bot/…py:N` whose file does not match the symbol's file. A line number that has drifted only prints a warning (`línea movida`), with exit 0, so an unrelated edit in `src/` does not break `pytest`. Authors run `check.py` and fix warnings before committing; the final task requires zero warnings.
3. **Machine-checkable claims.** Preset thresholds and ranking weights are wrapped in `<data data-param="<layer-free key>" value="<number>">` (e.g. `data-param="min_market_cap.minimum_usd" value="100000000"`); named constants in `<data data-const="bot.mod._NAME" value="…">`; the DCF example inputs in `<data data-dcf="…" value="…">` and its outputs in `<data data-dcf-out="…" value="…">`. Visible text is free-form rioplatense («USD 100 millones»); the `value` attribute carries the number the test compares.
4. **Chapter roles** (pigment in margin and title): `cap-0` selecciona, `cap-1` datos, `cap-2` datos, `cap-3` elimina, `cap-4` elimina, `cap-5` selecciona, `cap-6` valua, `cap-7` valua, `cap-8` valua. `vigila` is declared as a token (DESIGN.md has five roles) but no chapter uses it: the portfolio monitor is out of scope.
5. **Dark tokens** are the ones `docs/plano/build.py` already uses (`DARK_TOKENS`), copied, not imported.
6. **Caveats are required** in `cap-1` (benchmarks are always US: `DEFAULT_REGION = "US"`), `cap-2` (ADR 0005 not implemented; the coverage gate drops instead of guessing), `cap-4` (spec §6.7: the screener cannot judge narrative), `cap-7` (spec §16.4 garbage-in/garbage-out, plus decision 1). Other chapters add one where the code admits a limit.
7. **Mobile nav** is a `<details open>` inside `<nav>`; a tiny inline script closes it on narrow screens after load and keeps it open on wide ones. Without JS it stays open, so content and links are always reachable.
8. **Keyboard**: chapter links are plain `<a href="#cap-N">`, a skip link goes to `#contenido`, `:focus-visible` has a visible outline, and the current chapter gets `aria-current="location"` via `IntersectionObserver` (progressive, optional).
9. **The issue's `Skills: impeccable`** is not installed on the runner; the visual work follows DESIGN.md/PRODUCT.md directly.

## Review Focus

1. A rule threshold or ranking weight edited in the YAML preset or `RankingWeights` after the lesson ships: the `data-param` tests (Task 4) fail and name the key.
2. A symbol renamed or removed in `src/bot/`: `check.py` exits 1 and `test_check_py_exits_zero` (Task 1) fails in CI, listing the missing symbol.
3. The DCF example table arithmetic disagreeing with `dcf()` (hand-computed numbers, a changed formula): `test_dcf_example_matches_code` (Task 5) recomputes every row.
4. A 390px phone: wide tables or long identifiers forcing horizontal scroll. Tables sit in an `overflow-x:auto` wrapper, `code` gets `overflow-wrap:anywhere`; the agent-browser eval (`.scratch/evals-120.md`) measures `scrollWidth` at 390px; Task 2 tests pin the CSS hooks.
5. Dark mode reading as unreadable: Task 2's contrast test computes both the light and the dark `--ink`/`--ink-soft` on `--sheet` from the OKLCH values and requires ≥ 4.5:1.

---

## File map

- Create: `docs/leccion/check.py` — symbol verification (stdlib + `codemap`).
- Create: `docs/leccion/index.html` — the lesson.
- Create: `docs/leccion/README.md` — ~10 lines.
- Modify: `CONTEXT.md` — «Source of truth» gets a `docs/leccion/` bullet.
- Create: `tests/unit/test_leccion_check.py` — unit tests for `check.py`.
- Create: `tests/unit/test_leccion.py` — tests for the lesson's content and structure.

## Shared test helper (lives at the top of `tests/unit/test_leccion.py`)

Every lesson test parses the HTML once with this helper. Task 2 creates the file with it; later tasks append tests.

```python
"""The lesson in docs/leccion/ (issue #120) stays true to src/bot/."""

from __future__ import annotations

import importlib
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LECCION = _ROOT / "docs" / "leccion"
_INDEX = _LECCION / "index.html"

_CHAPTERS = [
    ("cap-0", "El mapa"),
    ("cap-1", "La vara: Damodaran (Capa A)"),
    ("cap-2", "Los números de cada empresa"),
    ("cap-3", "Quality gates"),
    ("cap-4", "Barato vs. trampa"),
    ("cap-5", "El ranking"),
    ("cap-6", "Story types (Capa C)"),
    ("cap-7", "El DCF sin matemática"),
    ("cap-8", "Dudar del resultado"),
]


@dataclass
class _Chapter:
    id: str
    title: str = ""
    text: list[str] = field(default_factory=list)
    classes: set[str] = field(default_factory=set)
    symbols: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    consts: dict[str, str] = field(default_factory=dict)
    dcf_in: dict[str, str] = field(default_factory=dict)
    dcf_out: dict[str, str] = field(default_factory=dict)
    svg_etapas: set[str] = field(default_factory=set)
    tables: int = 0


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chapters: list[_Chapter] = []
        self.nav_hrefs: list[str] = []
        self.links: list[str] = []
        self.script_srcs: list[str] = []
        self.styles: list[str] = []
        self._in_nav = 0
        self._in_h2 = False
        self._code_depth = 0
        self._code_buf: list[str] = []
        self._in_style = False
        self._section_depth = 0

    @property
    def _cur(self) -> _Chapter | None:
        return self.chapters[-1] if self._section_depth else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "section" and a.get("id", "").startswith("cap-") and not self._section_depth:
            self.chapters.append(_Chapter(a["id"]))
            self._section_depth = 1
        elif tag == "section" and self._section_depth:
            self._section_depth += 1
        if tag == "nav":
            self._in_nav += 1
        if tag == "a" and self._in_nav and a.get("href", "").startswith("#cap-"):
            self.nav_hrefs.append(a["href"])
        if tag == "link":
            self.links.append(a.get("href", ""))
        if tag == "script" and "src" in a:
            self.script_srcs.append(a["src"])
        if tag == "style":
            self._in_style = True
        cur = self._cur
        if cur is None:
            return
        cur.classes.update(a.get("class", "").split())
        if tag == "h2":
            self._in_h2 = True
        if tag == "table":
            cur.tables += 1
        if tag == "code":
            self._code_depth += 1
            self._code_buf = []
            if "data-symbol" in a:
                cur.symbols.append(a["data-symbol"])
        if "data-etapa" in a:
            cur.svg_etapas.add(a["data-etapa"])
        if tag == "data":
            for key, target in (
                ("data-param", cur.params),
                ("data-const", cur.consts),
                ("data-dcf", cur.dcf_in),
                ("data-dcf-out", cur.dcf_out),
            ):
                if key in a:
                    target[a[key]] = a.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_nav -= 1
        if tag == "style":
            self._in_style = False
        if tag == "h2":
            self._in_h2 = False
        if tag == "code" and self._code_depth:
            self._code_depth -= 1
            if self._cur is not None:
                self._cur.codes.append("".join(self._code_buf).strip())
        if tag == "section" and self._section_depth:
            self._section_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(data)
        cur = self._cur
        if cur is None:
            return
        cur.text.append(data)
        if self._in_h2:
            cur.title += data
        if self._code_depth:
            self._code_buf.append(data)


@cache
def _html() -> str:
    return _INDEX.read_text(encoding="utf-8")


@cache
def _parsed() -> _Parser:
    p = _Parser()
    p.feed(_html())
    return p


def _chapter(cid: str) -> _Chapter:
    return next(c for c in _parsed().chapters if c.id == cid)


def _css() -> str:
    return "\n".join(_parsed().styles)
```

---

### Task 1: `check.py` — symbols cited by the lesson must exist

**Files:**
- Create: `docs/leccion/check.py`
- Test: `tests/unit/test_leccion_check.py`

**Interfaces:**
- Consumes: `docs/plano/codemap.py` → `codemap.escanear() -> (modulos, aristas, simbolos)` where `modulos[mod] = {'archivo': 'src/bot/x.py', 'lineas': int}` and `simbolos['src/bot/x.py:Name'] = {'archivo', 'linea', 'modulo', 'firma'}` (methods keyed `Class.method`).
- Produces (module `check`, loaded in tests by path with `importlib.util`):
  - `indice() -> dict[str, tuple[str, int]]` — `'bot.mod'` → `(archivo, 1)`, `'bot.mod.Name'` / `'bot.mod.Class.method'` → `(archivo, linea)`.
  - `citas(html: str) -> list[tuple[str, str | None, int | None]]` — every `<code … data-symbol="S" …>…</code>`, paired with the `src/bot/…py:N` of an immediately following `<code class="at">` (whitespace or ` · ` allowed in between), else `None, None`.
  - `revisar(html: str, idx: dict[str, tuple[str, int]]) -> tuple[list[str], list[str]]` — `(errores, avisos)`. Error: symbol missing (`falta: S`), or cited file differs (`archivo: S citado en X, vive en Y`). Warning: line differs (`línea movida: S citado en X:N, ahora X:M`).
  - `main(argv: list[str] | None = None) -> int` — reads `argv[0]` or `docs/leccion/index.html`, prints errors and warnings, returns 1 if any error else 0. `if __name__ == '__main__': sys.exit(main())`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_leccion_check.py`)

```python
"""docs/leccion/check.py flags lesson citations that no longer match src/bot/ (#120)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _ROOT / "docs" / "leccion" / "check.py"


@pytest.fixture(scope="module")
def check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("leccion_check", _CHECK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def idx(check: ModuleType) -> dict[str, tuple[str, int]]:
    return check.indice()


def test_index_resolves_modules_functions_classes_and_methods(idx: dict) -> None:
    assert idx["bot.screener.rules"][0] == "src/bot/screener/rules.py"
    assert idx["bot.screener.rules.MinMarketCap"][0] == "src/bot/screener/rules.py"
    assert idx["bot.valuator.dcf.dcf"][0] == "src/bot/valuator/dcf.py"
    assert "bot.screener.rules.MinMarketCap.evaluate" in idx
    assert "bot.ingest" in idx  # package __init__


def test_citas_pairs_symbol_with_following_location(check: ModuleType) -> None:
    html = (
        '<code data-symbol="bot.valuator.dcf.dcf">bot.valuator.dcf.dcf</code> · '
        '<code class="at">src/bot/valuator/dcf.py:159</code>'
        '<code data-symbol="bot.storage.db">bot.storage.db</code>'
    )
    assert check.citas(html) == [
        ("bot.valuator.dcf.dcf", "src/bot/valuator/dcf.py", 159),
        ("bot.storage.db", None, None),
    ]


def test_missing_symbol_is_an_error(check: ModuleType, idx: dict) -> None:
    html = '<code data-symbol="bot.screener.rules.NoSuchRule">x</code>'
    errores, avisos = check.revisar(html, idx)
    assert errores == ["falta: bot.screener.rules.NoSuchRule"]
    assert avisos == []


def test_wrong_file_is_an_error(check: ModuleType, idx: dict) -> None:
    html = (
        '<code data-symbol="bot.valuator.dcf.dcf">x</code> '
        '<code class="at">src/bot/valuator/sensitivity.py:1</code>'
    )
    errores, _ = check.revisar(html, idx)
    assert len(errores) == 1 and errores[0].startswith("archivo: bot.valuator.dcf.dcf")


def test_moved_line_is_only_a_warning(check: ModuleType, idx: dict) -> None:
    _, real = idx["bot.valuator.dcf.dcf"]
    html = (
        '<code data-symbol="bot.valuator.dcf.dcf">x</code> '
        f'<code class="at">src/bot/valuator/dcf.py:{real + 7}</code>'
    )
    errores, avisos = check.revisar(html, idx)
    assert errores == []
    assert avisos == [
        f"línea movida: bot.valuator.dcf.dcf citado en src/bot/valuator/dcf.py:{real + 7}, "
        f"ahora src/bot/valuator/dcf.py:{real}"
    ]


def test_main_exit_codes(check: ModuleType, tmp_path: Path) -> None:
    good = tmp_path / "good.html"
    good.write_text('<code data-symbol="bot.storage.db">bot.storage.db</code>', encoding="utf-8")
    bad = tmp_path / "bad.html"
    bad.write_text('<code data-symbol="bot.nope.Nada">x</code>', encoding="utf-8")
    assert check.main([str(good)]) == 0
    assert check.main([str(bad)]) == 1
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_leccion_check.py -q` → errors loading `docs/leccion/check.py` (file missing).

- [ ] **Step 3: Implement `docs/leccion/check.py`**

```python
"""Verifica que cada símbolo citado por la lección exista en src/bot/.

    python3 docs/leccion/check.py [ruta/a/index.html]

Recorre cada <code data-symbol="bot.modulo.Nombre"> y lo busca en el índice que
arma docs/plano/codemap.py con ast. Si falta, o si la ubicación citada al lado
apunta a otro archivo, sale con 1 y los lista: la lección no puede quedar
citando código que ya no existe. Una línea corrida es solo un aviso.
"""
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'plano'))

import codemap  # noqa: E402

CITA_RE = re.compile(
    r'<code\b[^>]*\bdata-symbol="([^"]+)"[^>]*>.*?</code>'
    r'(?:\s*(?:·|&middot;)?\s*<code class="at">(src/bot/[^<:]+\.py):(\d+)</code>)?',
    re.S)


def indice():
    modulos, _, simbolos = codemap.escanear()
    idx = {mod: (m['archivo'], 1) for mod, m in modulos.items()}
    for clave, s in simbolos.items():
        nombre = clave.split(':', 1)[1]
        idx[f"{s['modulo']}.{nombre}"] = (s['archivo'], s['linea'])
    return idx


def citas(html):
    return [(m[1], m[2], int(m[3]) if m[3] else None) for m in CITA_RE.finditer(html)]


def revisar(html, idx):
    errores, avisos = [], []
    for simbolo, archivo, linea in citas(html):
        if simbolo not in idx:
            errores.append(f'falta: {simbolo}')
            continue
        real_archivo, real_linea = idx[simbolo]
        if archivo is None:
            continue
        if archivo != real_archivo:
            errores.append(f'archivo: {simbolo} citado en {archivo}, vive en {real_archivo}')
        elif linea != real_linea:
            avisos.append(f'línea movida: {simbolo} citado en {archivo}:{linea}, '
                          f'ahora {real_archivo}:{real_linea}')
    return errores, avisos


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    ruta = pathlib.Path(args[0]) if args else AQUI / 'index.html'
    errores, avisos = revisar(ruta.read_text(encoding='utf-8'), indice())
    for a in avisos:
        print(f'aviso  {a}')
    for e in errores:
        print(f'error  {e}')
    total = len(citas(ruta.read_text(encoding='utf-8')))
    print(f'check | {total} citas, {len(errores)} errores, {len(avisos)} avisos')
    return 1 if errores else 0


if __name__ == '__main__':
    sys.exit(main())
```

(Style matches `docs/plano/*.py`: Spanish names, single quotes, no type hints — `mypy` only covers `src`. `ruff check .` must pass.)

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/unit/test_leccion_check.py -q` and `uv run ruff check docs/leccion`.

- [ ] **Step 5: Commit** — `git add docs/leccion/check.py tests/unit/test_leccion_check.py && git commit -m "feat(#120): check.py verifies lesson symbols against src/bot"`

---

### Task 2: Page shell — head, tokens, nav, nine empty-but-titled chapters

**Files:**
- Create: `docs/leccion/index.html`
- Test: `tests/unit/test_leccion.py` (shared helper above + the tests below)

**Interfaces:**
- Consumes: nothing from Task 1 at runtime (test `test_check_py_exits_zero` runs it).
- Produces: the HTML skeleton later tasks fill. Each chapter is
  ```html
  <section id="cap-N" class="cap" data-rol="<rol>" aria-labelledby="cap-N-t">
    <header class="cap-head"><span class="cap-num">N</span><span class="cap-rol">rol</span>
      <h2 id="cap-N-t">Título</h2></header>
    <div class="concepto">…</div>
    <div class="ejemplo">…</div>
    <div class="en-codigo"><h3>En el código</h3><ul>…</ul></div>
    <aside class="caveat">…</aside>   <!-- where it applies -->
  </section>
  ```
  Symbol citation form, used by every content task:
  `<code data-symbol="bot.screener.rules.MinMarketCap">bot.screener.rules.MinMarketCap</code> · <code class="at">src/bot/screener/rules.py:121</code>`.
  Chapter roles per Decision 4.

Shell content requirements:
- `<!doctype html><html lang="es">`, `<meta charset="utf-8">`, `<meta name="viewport" content="width=device-width, initial-scale=1">`, `<title>`.
- Google Fonts: `<link rel="preconnect" href="https://fonts.googleapis.com">`, `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>`, one stylesheet link `https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,300..700;1,7..72,300..700&family=Shantell+Sans:wght@300..800&family=Sometype+Mono:wght@400..700&display=swap`.
- `:root` tokens copied from `docs/DESIGN.md`: `--desk`, `--sheet`, `--sheet-deep`, `--ink`, `--ink-soft`, and for each role `--p-<rol>` (line) and `--p-<rol>-t` (text) with roles `datos`, `elimina`, `selecciona`, `valua`, `vigila`. Font stacks: `--f-titulo: 'Shantell Sans', 'Comic Neue', system-ui, sans-serif; --f-cuerpo: 'Literata', Georgia, 'Times New Roman', serif; --f-mono: 'Sometype Mono', ui-monospace, 'Cascadia Mono', Menlo, monospace;`.
- `@media (prefers-color-scheme: dark) { :root { … } }` with the DARK_TOKENS values from `docs/plano/build.py` for the same token names.
- Layout: skip link `<a class="saltar" href="#contenido">Saltar al contenido</a>`; `<nav aria-label="Capítulos"><details class="toc" open><summary>Capítulos</summary><ol>` nine `<li><a href="#cap-N">N · Título</a></li>` `</ol></details></nav>`; `<main id="contenido">` with an intro `<header>` (h1 + two-sentence lede) and the nine sections. At `min-width: 60rem`, grid with nav fixed/sticky on the left (`position: sticky; top: 0; height: 100vh; overflow-y: auto`) and `summary` hidden; below that nav sits on top.
- Prose: `.cap > div, .cap > aside { max-width: 70ch; }` (some value in 65–75ch); `code { overflow-wrap: anywhere; font-family: var(--f-mono); }`; tables wrapped in `<div class="tabla">` with `.tabla { overflow-x: auto; }`; `img, svg { max-width: 100%; height: auto; }`; `html { overflow-x: clip }` is NOT used (it would hide the bug instead of fixing it).
- Each chapter: margin mark `border-inline-start` in `var(--p-<rol>)` with the DESIGN.md stroke mark per role (datos `solid`, elimina a `repeating-linear-gradient(45deg, …)` hatching via a `::before` strip, selecciona `double`, valua `dotted` heavy, vigila `wavy` — implement as `border-style` where CSS has it and `::before` gradient for hatching), and `h2 { color: var(--p-<rol>-t) }`, plus the visible role label `.cap-rol` so color never codes alone.
- `:focus-visible { outline: 3px solid var(--p-valua); outline-offset: 2px; }`.
- `@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto } }`, `html { scroll-behavior: smooth }` otherwise.
- Inline script at the end of `<body>` (Decision 7 and 8):
  ```html
  <script>
  (() => {
    const toc = document.querySelector('.toc');
    const ancho = matchMedia('(min-width: 60rem)');
    const ajustar = () => { toc.open = ancho.matches; };
    ajustar();
    ancho.addEventListener('change', ajustar);
    toc.addEventListener('click', e => {
      if (e.target.closest('a') && !ancho.matches) toc.open = false;
    });
    if (!('IntersectionObserver' in window)) return;
    const links = new Map([...toc.querySelectorAll('a')].map(a => [a.hash.slice(1), a]));
    const io = new IntersectionObserver(entradas => {
      for (const e of entradas) {
        if (!e.isIntersecting) continue;
        for (const a of links.values()) a.removeAttribute('aria-current');
        links.get(e.target.id)?.setAttribute('aria-current', 'location');
      }
    }, { rootMargin: '-40% 0px -55% 0px' });
    document.querySelectorAll('.cap').forEach(s => io.observe(s));
  })();
  </script>
  ```
- Chapter bodies in this task: the `cap-head` and `h2` only, plus one sentence in `.concepto`. Content tasks replace them.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_leccion.py` with the shared helper and:

```python
def test_index_is_self_contained() -> None:
    p = _parsed()
    assert p.script_srcs == []
    for href in p.links:
        assert re.match(r"https://fonts\.(googleapis|gstatic)\.com(/|$)", href), href
    html = _html()
    assert "base64," not in html
    assert "feTurbulence" not in html
    assert "@import" not in _css()
    assert re.findall(r"url\(\s*['\"]?https?://", _css()) == []


def test_document_basics() -> None:
    html = _html()
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="es">' in html
    assert re.search(r'<meta name="viewport" content="width=device-width, initial-scale=1"', html)
    for family in ("Shantell+Sans", "Literata", "Sometype+Mono"):
        assert family in html


def test_chapters_in_order_with_titles() -> None:
    chapters = _parsed().chapters
    assert [c.id for c in chapters] == [cid for cid, _ in _CHAPTERS]
    for chapter, (_, title) in zip(chapters, _CHAPTERS, strict=True):
        assert title in " ".join(chapter.title.split()), (chapter.id, chapter.title)


def test_nav_links_every_chapter_in_order() -> None:
    assert _parsed().nav_hrefs == [f"#{cid}" for cid, _ in _CHAPTERS]
    assert 'href="#contenido"' in _html()
    assert ":focus-visible" in _css()


_DESIGN_TOKENS = {
    "--desk": "oklch(0.665 0.048 66)",
    "--sheet": "oklch(0.845 0.035 82)",
    "--sheet-deep": "oklch(0.795 0.038 80)",
    "--ink": "oklch(0.315 0.045 55)",
    "--ink-soft": "oklch(0.385 0.040 56)",
    "--p-datos": "oklch(0.620 0.115 78)",
    "--p-datos-t": "oklch(0.400 0.085 72)",
    "--p-elimina": "oklch(0.505 0.145 30)",
    "--p-elimina-t": "oklch(0.385 0.120 30)",
    "--p-selecciona": "oklch(0.545 0.095 135)",
    "--p-selecciona-t": "oklch(0.395 0.075 135)",
    "--p-valua": "oklch(0.470 0.115 265)",
    "--p-valua-t": "oklch(0.375 0.105 265)",
    "--p-vigila": "oklch(0.505 0.115 350)",
    "--p-vigila-t": "oklch(0.385 0.105 350)",
}


def _block(css: str, opener: str) -> str:
    start = css.index(opener)
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return css[i : j + 1]
    raise AssertionError(f"unbalanced block after {opener!r}")


def _light_root() -> str:
    return _block(_css(), ":root")


def _dark_root() -> str:
    return _block(_css(), "prefers-color-scheme: dark")


def _token(block: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*:\s*(oklch\([^)]*\))", block)
    assert m, f"{name} missing"
    return " ".join(m[1].split())


def test_tokens_come_from_design_md() -> None:
    root = _light_root()
    for name, value in _DESIGN_TOKENS.items():
        assert _token(root, name) == value, name


def _luminance(oklch: str) -> float:
    lightness, chroma, hue = (float(x) for x in re.findall(r"[\d.]+", oklch)[:3])
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    r, g, bl = (min(max(c, 0.0), 1.0) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl


def _contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_body_text_contrast_is_aa_in_light_and_dark() -> None:
    for block in (_light_root(), _dark_root()):
        sheet = _token(block, "--sheet")
        for ink in ("--ink", "--ink-soft"):
            assert _contrast(_token(block, ink), sheet) >= 4.5, (ink, block[:40])


def test_layout_hooks_for_phone_width() -> None:
    css = _css()
    measures = [float(x) for x in re.findall(r"max-(?:width|inline-size)\s*:\s*([\d.]+)ch", css)]
    assert any(65 <= m <= 75 for m in measures), measures
    assert re.search(r"\.tabla\s*\{[^}]*overflow-x\s*:\s*auto", css)
    assert re.search(r"overflow-wrap\s*:\s*anywhere", css)
    assert "overflow-x: clip" not in css and "overflow-x:clip" not in css
    assert "prefers-reduced-motion" in css


def test_check_py_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(_LECCION / "check.py")], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_leccion.py -q` → `FileNotFoundError` on `index.html`.
- [ ] **Step 3: Write `docs/leccion/index.html`** per the shell requirements above.
- [ ] **Step 4: Run, expect PASS** for the tests above (`uv run pytest tests/unit/test_leccion.py -q -k "self_contained or basics or order or nav or tokens or contrast or layout or check_py"`). Open the file in a browser at 390px wide and at 1280px: nav on top / on the left, no horizontal scroll.
- [ ] **Step 5: Commit** — `git add docs/leccion/index.html tests/unit/test_leccion.py && git commit -m "feat(#120): lesson shell with tokens, chapter nav and nine chapters"`

---

### Task 3: Chapters 0–2 — the map, the yardstick, each company's numbers

**Files:**
- Modify: `docs/leccion/index.html` (sections `cap-0`, `cap-1`, `cap-2`)
- Test: `tests/unit/test_leccion.py` (append)

**Interfaces:**
- Consumes: the section skeleton and citation form from Task 2.
- Produces: shared tests `test_each_chapter_has_its_parts`, `test_required_symbols_are_cited`, `test_no_math_notation`, `test_named_constants_match_code` that Tasks 4–5 rely on (they only extend `_REQUIRED_SYMBOLS` / `_REQUIRED_CONSTS` entries, already listed in full here).

Content (read the anchors; the code wins over this summary):
- **cap-0 El mapa** (rol selecciona). ~500 companies in (S&P 500 trimmed universe, `src/bot/ingest/universe_default.csv`), ~20 out. Capa A gives the yardstick, Capa B discards (coverage gate → quality gates → value indicators → trap detection, then ranking), Capa C goes deeper on the shortlist without discarding. Thesis «barato ≠ buena compra». Name the three commands `bot refresh`, `bot screen`, `bot analyze` only (no operating instructions). Inline SVG funnel: `<svg role="img" aria-labelledby="embudo-t embudo-d">` with `<title id="embudo-t">` and `<desc id="embudo-d">`; four narrowing Capa B stages with `data-etapa="calidad"`, `data-etapa="valor"`, `data-etapa="trampa"`, `data-etapa="ranking"`, and a Capa C block that does not narrow, `data-etapa="capa-c"`. Stage colors from role tokens, each stage also labelled in text (color never codes alone); use `fill`/`stroke` with `var(--p-…)` so dark mode follows. Example: round numbers through the funnel (e.g. 500 → 470 measured → 260 pass gates → 60 look cheap → 35 survive traps → top 20), stated as illustrative, not measured. Anchors: `bot.cli.refresh`, `bot.cli.screen`, `bot.cli.analyze`, spec §3.
- **cap-1 La vara: Damodaran (Capa A)** (rol datos). What Damodaran publishes each January (industry medians: PE, EV/EBITDA, P/BV, ROE, WACC, beta, margins, sales-to-capital; country: ERP, tax rate, risk-free) and what it doesn't (no single company). Why calibrate against the sector instead of absolute thresholds. Same data serves cheapness (B) and default assumptions (C). Example: a PE of 14 is cheap in an industry whose median is 25 and expensive in one whose median is 9. Anchors: `bot.ingest.damodaran.import_damodaran`, `bot.ingest.damodaran.parse_industry_xls`, `bot.ingest.damodaran.parse_country_xls`, tables `damodaran_industry` / `damodaran_country` (plain `<code>`, no `data-symbol`), `bot.screener.benchmarks.load_industry_benchmarks`, `bot.screener.types.IndustryBenchmarks`. Caveat: benchmarks are US — the screener falls back to `<data data-const="bot.screener.engine.DEFAULT_REGION" value="US">US</data>` and the universe is US-only (ADR 0007).
- **cap-2 Los números de cada empresa** (rol datos). EDGAR fundamentals, Stooq prices (ADR 0007), the trimmed S&P 500 universe, DuckDB as one file (ADR 0001). The coverage gate: a company with no usable benchmark (no sector WACC) leaves the universe instead of scoring badly (ADR 0006; `run_screen` records it as `RejectedCompany(ticker, ("coverage_gate",))`). Example: a company whose industry maps to no Damodaran row. Anchors: `bot.ingest.universe.refresh_universe`, `bot.ingest.universe.refresh_prices`, `bot.ingest.sec_edgar`, `bot.storage.db`, `bot.screener.types.CompanyData`, `bot.screener.engine.build_company_data`. Caveat: ADR 0005 (valuation currency) is accepted but not implemented; safe only because the universe is US-only — say so.

- [ ] **Step 1: Append failing tests**

```python
_REQUIRED_SYMBOLS: dict[str, list[str]] = {
    "cap-0": ["bot.cli.refresh", "bot.cli.screen", "bot.cli.analyze"],
    "cap-1": [
        "bot.ingest.damodaran.import_damodaran",
        "bot.ingest.damodaran.parse_industry_xls",
        "bot.ingest.damodaran.parse_country_xls",
        "bot.screener.benchmarks.load_industry_benchmarks",
        "bot.screener.types.IndustryBenchmarks",
    ],
    "cap-2": [
        "bot.ingest.universe.refresh_universe",
        "bot.ingest.universe.refresh_prices",
        "bot.ingest.sec_edgar",
        "bot.storage.db",
        "bot.screener.types.CompanyData",
        "bot.screener.engine.build_company_data",
    ],
    "cap-3": [
        "bot.screener.rules.MinMarketCap",
        "bot.screener.rules.MinYearsHistory",
        "bot.screener.rules.ExcludeSectors",
        "bot.screener.rules.MaxNetDebtToEBITDA",
        "bot.screener.rules.MinInterestCoverage",
        "bot.screener.rules.PositiveOperatingCashflow",
        "bot.screener.rules.MaxGoodwillToAssets",
        "bot.screener.rules.register",
        "bot.screener.rules.get_rule",
    ],
    "cap-4": [
        "bot.screener.rules.PEBelowIndustryMultiple",
        "bot.screener.rules.EVEBITDABelowIndustryMultiple",
        "bot.screener.rules.PBVBelowIndustryMultipleWithROEAboveMedian",
        "bot.screener.rules.FCFYieldAbove",
        "bot.screener.rules.RevenueNotDeclining",
        "bot.screener.rules.OperatingMarginNotContracting",
        "bot.screener.rules.ROICAboveSectorWACC",
        "bot.screener.rules.SloanAccrualsBelow",
        "bot.screener.rules.ShareCountNotDiluting",
        "bot.screener.engine.evaluate_company",
        "bot.screener.engine.run_screen",
        "bot.screener.engine.ScreenResult",
        "bot.screener.engine.RejectedCompany",
    ],
    "cap-5": [
        "bot.screener.ranking.RankingWeights",
        "bot.screener.ranking.rank",
        "bot.screener.ranking.rescore_with_margins",
        "bot.screener.persist",
    ],
    "cap-6": [
        "bot.valuator.story_types.StoryType",
        "bot.valuator.story_types.classify",
        "bot.valuator.story_types.SectorContext",
        "bot.valuator.assumptions.conventional_override_path",
    ],
    "cap-7": [
        "bot.valuator.dcf.Financials",
        "bot.valuator.dcf.Assumptions",
        "bot.valuator.dcf.dcf",
        "bot.valuator.dcf.DCFResult",
        "bot.valuator.dcf.YearProjection",
        "bot.valuator.assumptions.AssumptionSource",
        "bot.valuator.assumptions.Sourced",
        "bot.valuator.assumptions.resolve_assumptions",
    ],
    "cap-8": [
        "bot.valuator.sensitivity.tornado",
        "bot.valuator.sensitivity.grid_2d",
        "bot.valuator.narrative_flags.story_margin_flag",
        "bot.valuator.narrative_flags.growth_reinvestment_flag",
        "bot.valuator.narrative_flags.beta_business_risk_flag",
        "bot.valuator.narrative_flags.terminal_value_share_flag",
        "bot.valuator.narrative_flags.country_exposure_flag",
        "bot.valuator.analysis.analyze",
        "bot.reporting.analysis_report.margin_verdict",
    ],
}

_REQUIRED_CONSTS: dict[str, list[str]] = {
    "cap-1": ["bot.screener.engine.DEFAULT_REGION"],
    "cap-5": ["bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY"],
    "cap-6": [
        "bot.valuator.story_types._DISTRESS_ALTMAN_Z",
        "bot.valuator.story_types._DISTRESS_INTEREST_COVERAGE",
        "bot.valuator.story_types._CYCLICAL_EARNINGS_CV",
        "bot.valuator.story_types._HIGH_GROWTH_CAGR",
        "bot.valuator.story_types._MATURE_AGE_YEARS",
        "bot.valuator.story_types._DECLINE_CAGR",
    ],
    "cap-7": ["bot.valuator.assumptions._HORIZON"],
    "cap-8": [
        "bot.valuator.sensitivity._TORNADO_HIGH",
        "bot.valuator.narrative_flags._TERMINAL_VALUE_SHARE_CEILING",
    ],
}

_CAVEATS = {"cap-1", "cap-2", "cap-4", "cap-7"}


def test_each_chapter_has_its_parts() -> None:
    for chapter in _parsed().chapters:
        for part in ("concepto", "ejemplo", "en-codigo"):
            assert part in chapter.classes, (chapter.id, part)
        if chapter.id in _CAVEATS:
            assert "caveat" in chapter.classes, chapter.id


def test_required_symbols_are_cited() -> None:
    for cid, symbols in _REQUIRED_SYMBOLS.items():
        missing = set(symbols) - set(_chapter(cid).symbols)
        assert not missing, (cid, sorted(missing))


def test_every_cited_symbol_is_a_bot_path() -> None:
    for chapter in _parsed().chapters:
        for symbol in chapter.symbols:
            assert symbol.startswith("bot."), symbol


def test_named_constants_match_code() -> None:
    for cid, names in _REQUIRED_CONSTS.items():
        missing = set(names) - set(_chapter(cid).consts)
        assert not missing, (cid, sorted(missing))
    for chapter in _parsed().chapters:
        for dotted, shown in chapter.consts.items():
            module, name = dotted.rsplit(".", 1)
            actual = getattr(importlib.import_module(module), name)
            if isinstance(actual, str):
                assert shown == actual, dotted
            else:
                assert math.isclose(float(shown), float(actual)), (dotted, shown, actual)


_MATH = ("∑", "Σ", "\\sum", "sum_{", "<math", "\\frac", "∫", ")^", "^t", "^N")


def test_no_math_notation() -> None:
    text = "".join(t for c in _parsed().chapters for t in c.text)
    for token in _MATH:
        assert token not in text, token


def test_funnel_svg_in_chapter_0() -> None:
    assert {"calidad", "valor", "trampa", "ranking", "capa-c"} <= _chapter("cap-0").svg_etapas
    section = _html()[_html().index('id="cap-0"') : _html().index('id="cap-1"')]
    assert re.search(r'<svg\b[^>]*role="img"', section)
    assert "<title" in section
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_leccion.py -q` → the new tests fail on `cap-0`…`cap-2` (and on later chapters until Tasks 4–5; that is expected).
- [ ] **Step 3: Write chapters 0–2** following the content list; cite each symbol in the form from Task 2 and run `python3 docs/leccion/check.py` until it reports 0 errors and 0 warnings.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_leccion.py -q -k "cap_0 or funnel or check_py or no_math"` → PASS; `test_required_symbols_are_cited` / `test_each_chapter_has_its_parts` now fail only for `cap-3`…`cap-8`.
- [ ] **Step 5: Commit** — `git commit -am "feat(#120): lesson chapters 0-2 (map, Damodaran yardstick, company data)"`

---

### Task 4: Chapters 3–5 — quality gates, cheap vs trap, ranking

**Files:**
- Modify: `docs/leccion/index.html` (sections `cap-3`, `cap-4`, `cap-5`)
- Test: `tests/unit/test_leccion.py` (append)

**Interfaces:**
- Consumes: shared tests from Task 3; preset `config/presets/damodaran_value.yaml`; `bot.screener.ranking.RankingWeights`.
- Produces: `data-param` keys `"<rule name>.<param>"` for every param of every rule in `quality_gates`, `value_indicators`, `trap_detection`, and `"ranking.<weight>"` for the four weights. List params (`exclude_sectors.excluded`) carry `value="bank,insurance"`.

Content:
- **cap-3 Quality gates** (rol elimina). The seven eliminatory filters, one by one, each with a round-number example and its financial why (debt as multiplier, cash vs accounting profit, why banks are out: their debt is raw material, EBITDA/net debt don't mean the same). Thresholds exactly from the preset, each wrapped: `<data data-param="min_market_cap.minimum_usd" value="100000000.0">USD 100 millones</data>`, `min_years_history.minimum_years` 5, `exclude_sectors.excluded` `bank,insurance` (and the `is_financial_services` flag also excludes, `src/bot/screener/rules.py` `ExcludeSectors.evaluate`), `max_net_debt_to_ebitda.maximum` 4.0, `min_interest_coverage.minimum` 2.0, `positive_operating_cashflow.min_positive` 4 and `.window` 5, `max_goodwill_to_assets.maximum` 0.5. Explain the registry: each rule class registers under a `name` with `@register`, `get_rule` resolves YAML names, so a preset is just a list of names with params. Anchors: all seven classes, `register`, `get_rule`, and the preset path in plain `<code>`.
- **cap-4 Barato vs. trampa** (rol elimina; value-indicator marks use selecciona pigment inline). Value indicators (at least one must pass; a skip neither passes nor fails) vs trap detection (every one must pass; a trap detector that cannot run eliminates, ADR 0006). Params: `pe_below_industry_multiple.multiple` 0.7, `ev_ebitda_below_industry_multiple.multiple` 0.7, `pbv_below_industry_multiple_with_roe_above_median.multiple` 0.7, `fcf_yield_above.minimum` 0.08, `revenue_not_declining.max_decline` −0.05 and `.window` 3, `operating_margin_not_contracting.max_contraction_bps` −200 and `.window` 3, `sloan_accruals_below.maximum` 0.10, `share_count_not_diluting.max_annual_growth` 0.05; `roic_above_sector_wacc` has no params. ROIC < sector WACC as the central Damodaran filter, without formula: «gana menos de lo que le cuesta el capital». Example: two companies with the same low PE, one with ROIC 6 % in a sector with WACC 8 % (trap), one with ROIC 14 % (candidate). Draw the two forces as opposed (e.g. a small inline SVG or a two-column layout with arrows pointing at each other, PRODUCT.md principle 3). Anchors: the nine classes, `evaluate_company`, `run_screen`, `ScreenResult`, `RejectedCompany`. Caveat: spec §6.7, the screener cannot judge narrative.
- **cap-5 El ranking** (rol selecciona). Percentiles within the filtered universe, not absolute thresholds. Weights wrapped: `ranking.value` 0.40, `ranking.quality` 0.30, `ranking.growth` 0.20, `ranking.margin_of_safety` 0.10. Margin of safety enters at 10 % and comes from Capa C: the first pass ranks with the placeholder `PLACEHOLDER_MARGIN_OF_SAFETY` (0.5), the second pass values the top N with the DCF and re-blends with `rescore_with_margins`; the MoS term is not a percentile and is unbounded, so the score can exceed 100. Example: a candidate at percentiles 80 % / 60 % / 50 % with MoS 1.2 scores 100 × (0.40·0.8 + 0.30·0.6 + 0.20·0.5 + 0.10·1.2) = 72 (`rank` multiplies the blend by 100 and carries MoS as the raw ratio, `src/bot/screener/ranking.py` `rank`); the same candidate with the 0.5 placeholder scores 65. Write the example as a small table, not a formula. Anchors: `RankingWeights`, `rank`, `rescore_with_margins`, `bot.screener.persist`.

- [ ] **Step 1: Append failing tests**

```python
import yaml  # noqa: E402  (move to the import block at the top when appending)

from bot.screener.ranking import RankingWeights  # noqa: E402

_PRESET = _ROOT / "config" / "presets" / "damodaran_value.yaml"
_LAYER_CHAPTER = {"quality_gates": "cap-3", "value_indicators": "cap-4", "trap_detection": "cap-4"}


def test_preset_thresholds_appear_in_chapters_3_and_4() -> None:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))
    for layer, cid in _LAYER_CHAPTER.items():
        params = _chapter(cid).params
        for rule in preset[layer]["rules"]:
            for key, value in (rule.get("params") or {}).items():
                shown = params.get(f"{rule['name']}.{key}")
                assert shown is not None, (cid, rule["name"], key)
                if isinstance(value, list):
                    assert shown.split(",") == value, (rule["name"], key)
                else:
                    assert math.isclose(float(shown), float(value)), (rule["name"], key)


def test_ranking_weights_match_code_and_preset() -> None:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))["ranking"]["weights"]
    code = RankingWeights()
    params = _chapter("cap-5").params
    for name in ("value", "quality", "growth", "margin_of_safety"):
        shown = float(params[f"ranking.{name}"])
        assert math.isclose(shown, getattr(code, name)), name
        assert math.isclose(shown, preset[name]), name
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_leccion.py -q -k "preset or ranking_weights"`.
- [ ] **Step 3: Write chapters 3–5**; `python3 docs/leccion/check.py` → 0 errors, 0 warnings.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_leccion.py -q` → only `cap-6`…`cap-8` failures remain.
- [ ] **Step 5: Commit** — `git commit -am "feat(#120): lesson chapters 3-5 (quality gates, cheap vs trap, ranking)"`

---

### Task 5: Chapters 6–8 — story types, the DCF without math, doubting the result

**Files:**
- Modify: `docs/leccion/index.html` (sections `cap-6`, `cap-7`, `cap-8`)
- Test: `tests/unit/test_leccion.py` (append)

**Interfaces:**
- Consumes: shared tests from Task 3; `bot.valuator.dcf.{Financials, Assumptions, dcf}`; `bot.valuator.assumptions.AssumptionSource`; `bot.valuator.story_types.StoryType`; `bot.reporting.analysis_report.margin_verdict`.
- Produces: `data-dcf` inputs `revenue`, `net_debt`, `shares_diluted`, `revenue_growth` (comma list of 5), `operating_margin` (single value, flat), `tax_rate`, `sales_to_capital`, `terminal_growth`, `cost_of_equity`, `pretax_cost_of_debt`, `equity_weight`, `debt_weight`; `data-dcf-out` outputs `wacc`, `fcff.1`…`fcff.5`, `pv.1`…`pv.5`, `terminal_value`, `enterprise_value`, `intrinsic_value`. `data-param` `margin_verdict.undervalued` (1.3) and `margin_verdict.fair` (1.0) in `cap-8`.

Content:
- **cap-6 Story types (Capa C)** (rol valua). The five archetypes with their exact tokens as `<code>` (`high-growth`, `mature-stable`, `mature-decline`, `cyclical`, `distressed`) and what changes in each projection (growth and margin paths, not the arithmetic). How `classify` assigns them, in priority order: distressed (Altman Z below 1.81 or interest coverage at or below 1) → cyclical (cyclical sector and earnings CV ≥ 0.5) → high-growth (revenue CAGR ≥ 15 % and age ≤ 25 years or unknown) → mature-decline (CAGR ≤ −1 %) → mature-stable (default, also when history is too short). Each threshold wrapped in `data-const` (see `_REQUIRED_CONSTS`). Manual override: `story_type` in `config/assumptions/<TICKER>.yaml`, found by `conventional_override_path`. Example: a company growing 20 % a year, 12 years old → high-growth; same growth at 40 years → mature-stable.
- **cap-7 El DCF sin matemática** (rol valua). «Cuánto vale hoy una renta futura». Free cash flow, required rate (WACC) as the price of risk, terminal value as «el resto de la vida». Two stages: explicit years (horizon `<data data-const="bot.valuator.assumptions._HORIZON" value="5">5 años</data>`) + perpetuity. One sentence for the formula. Year-by-year table (`<div class="tabla"><table>`) with the example. Example inputs (round numbers; keep them):
  revenue 1000, net_debt 200, shares_diluted 100, revenue_growth 0.10,0.08,0.06,0.05,0.04, operating_margin 0.15, tax_rate 0.25, sales_to_capital 2.0, terminal_growth 0.03, cost_of_equity 0.10, pretax_cost_of_debt 0.06, equity_weight 0.8, debt_weight 0.2.
  Compute outputs with the code, never by hand:
  ```bash
  uv run python -c "
  from bot.valuator.dcf import Financials, Assumptions, dcf
  r = dcf(Financials(revenue=1000, net_debt=200, shares_diluted=100),
          Assumptions(revenue_growth=(0.10,0.08,0.06,0.05,0.04), operating_margin=(0.15,)*5,
                      tax_rate=0.25, sales_to_capital=2.0, terminal_growth=0.03,
                      cost_of_equity=0.10, pretax_cost_of_debt=0.06, equity_weight=0.8, debt_weight=0.2))
  print(r.wacc, r.terminal_value, r.enterprise_value, r.intrinsic_value, r.terminal_value_share)
  for p in r.projections: print(p.year, p.revenue, p.ebit, p.nopat, p.reinvestment, p.fcff, p.present_value)"
  ```
  Show rounded values in the table (one decimal is enough) and put the unrounded-to-two-decimals numbers in each `value` attribute. Mention the terminal value share and that it is the number the 80 % flag watches. The six critical assumptions of spec §7.3 (growth path, operating margin, sales-to-capital, WACC, terminal growth, probability of bankruptcy) and that each carries an explicit `source` (`Sourced`): list every `AssumptionSource` value as `<code>value</code>` with a one-line meaning. Anchors: `Financials`, `Assumptions`, `dcf`, `DCFResult`, `YearProjection`, `AssumptionSource`, `Sourced`, `resolve_assumptions`. Caveats: spec §16.4 garbage-in/garbage-out; spec §7.3 lists five sources including `analyst_consensus`, the code has seven and no `analyst_consensus` (Decision 1); probability of bankruptcy and distress value are never derived automatically (`src/bot/valuator/dcf.py` docstring of `Assumptions`).
- **cap-8 Dudar del resultado** (rol valua). Tornado: each assumption moved ±20 % (`_TORNADO_HIGH` 1.2) one at a time, bars sorted by impact. 2D grid: 5×5 over two assumptions (usually the two widest bars), MoS per cell. Narrative flags: the five functions, signals not ranking, colors green/yellow/red/unknown and unknown ≠ green; terminal-value share above `_TERMINAL_VALUE_SHARE_CEILING` (0.80) is yellow. Margin of safety = intrinsic value / price, verdict thresholds wrapped `<data data-param="margin_verdict.undervalued" value="1.3">` and `<data data-param="margin_verdict.fair" value="1.0">` with the verdict strings in `<code>`. «El headline es un punto en una nube.» Where it ends: the analysis report and the read-only viewer (ADR 0008). Example: intrinsic 30 vs price 20 → MoS 1.5 → `potentially undervalued`; a tornado where terminal growth swings value ±25 %. Anchors: `tornado`, `grid_2d`, five flag functions, `analyze`, `margin_verdict`.

- [ ] **Step 1: Append failing tests**

```python
from bot.reporting.analysis_report import margin_verdict  # noqa: E402
from bot.valuator.assumptions import AssumptionSource  # noqa: E402
from bot.valuator.dcf import Assumptions, Financials, dcf  # noqa: E402
from bot.valuator.story_types import StoryType  # noqa: E402


def test_story_types_listed_in_chapter_6() -> None:
    codes = set(_chapter("cap-6").codes)
    assert {s.value for s in StoryType} <= codes


def test_every_assumption_source_listed_in_chapter_7() -> None:
    codes = set(_chapter("cap-7").codes)
    missing = {s.value for s in AssumptionSource} - codes
    assert not missing, sorted(missing)


def _close(shown: str, actual: float) -> bool:
    return math.isclose(float(shown), actual, rel_tol=0.01, abs_tol=0.051)


def test_dcf_example_matches_code() -> None:
    chapter = _chapter("cap-7")
    i = {k: v for k, v in chapter.dcf_in.items()}
    growth = tuple(float(x) for x in i["revenue_growth"].split(","))
    result = dcf(
        Financials(
            revenue=float(i["revenue"]),
            net_debt=float(i["net_debt"]),
            shares_diluted=float(i["shares_diluted"]),
        ),
        Assumptions(
            revenue_growth=growth,
            operating_margin=(float(i["operating_margin"]),) * len(growth),
            tax_rate=float(i["tax_rate"]),
            sales_to_capital=float(i["sales_to_capital"]),
            terminal_growth=float(i["terminal_growth"]),
            cost_of_equity=float(i["cost_of_equity"]),
            pretax_cost_of_debt=float(i["pretax_cost_of_debt"]),
            equity_weight=float(i["equity_weight"]),
            debt_weight=float(i["debt_weight"]),
        ),
    )
    out = chapter.dcf_out
    assert len(growth) >= 2
    assert chapter.tables >= 1
    assert _close(out["wacc"], result.wacc)
    for p in result.projections:
        assert _close(out[f"fcff.{p.year}"], p.fcff), p.year
        assert _close(out[f"pv.{p.year}"], p.present_value), p.year
    for name in ("terminal_value", "enterprise_value", "intrinsic_value"):
        assert _close(out[name], getattr(result, name)), name


def test_margin_verdict_thresholds_match_code() -> None:
    params = _chapter("cap-8").params
    under = float(params["margin_verdict.undervalued"])
    fair = float(params["margin_verdict.fair"])
    assert margin_verdict(under) == "potentially undervalued"
    assert margin_verdict(under - 1e-9) == "around fair value"
    assert margin_verdict(fair) == "around fair value"
    assert margin_verdict(fair - 1e-9) == "potentially overvalued"
    codes = set(_chapter("cap-8").codes)
    assert {"potentially undervalued", "around fair value", "potentially overvalued"} <= codes
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_leccion.py -q -k "story_types or assumption_source or dcf_example or margin_verdict"`.
- [ ] **Step 3: Write chapters 6–8**; `python3 docs/leccion/check.py` → 0 errors, 0 warnings.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_leccion.py tests/unit/test_leccion_check.py -q` → all PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(#120): lesson chapters 6-8 (story types, DCF, sensitivity and verdict)"`

---

### Task 6: README, CONTEXT link, final verification

**Files:**
- Create: `docs/leccion/README.md`
- Modify: `CONTEXT.md` («Source of truth» list)
- Test: `tests/unit/test_leccion.py` (append)

- [ ] **Step 1: Append failing tests**

```python
def test_readme_is_short_and_says_how_to_use_it() -> None:
    readme = (_LECCION / "README.md").read_text(encoding="utf-8")
    assert len(readme.strip().splitlines()) <= 12
    for needle in ("index.html", "python3 docs/leccion/check.py", "Artifact"):
        assert needle in readme, needle


def test_context_source_of_truth_links_the_lesson() -> None:
    context = (_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    section = context[context.index("## Source of truth") : context.index("## Working with the plans")]
    assert "docs/leccion/" in section
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Write** `docs/leccion/README.md` (≈10 lines, Spanish, same voice as `docs/plano/README.md`): what it is (a lesson for someone who knows investing but not advanced financial maths, explaining the pipeline and where it lives in the code); how to open it (double click `index.html`, no server); how to verify it (`python3 docs/leccion/check.py`, exits 1 listing missing symbols, warns on moved lines; `uv run pytest tests/unit/test_leccion.py` also checks thresholds, weights and the DCF example); to publish as a claude.ai Artifact, upload the file as is. Add to `CONTEXT.md` «Source of truth»: `- **The lesson**: \`docs/leccion/\` — \`index.html\` teaches the Damodaran pipeline chapter by chapter and points at the code; \`check.py\` fails when it cites a symbol that no longer exists. See \`docs/leccion/README.md\`.`
- [ ] **Step 4: Full verification** — `python3 docs/leccion/check.py` (0 errors, 0 warnings), `uv run ruff check . && uv run mypy src`, `uv run pytest -q`; open `index.html` at 390px and 1280px, light and dark.
- [ ] **Step 5: Commit** — `git add docs/leccion/README.md CONTEXT.md tests/unit/test_leccion.py && git commit -m "docs(#120): lesson README and CONTEXT source-of-truth link"`
