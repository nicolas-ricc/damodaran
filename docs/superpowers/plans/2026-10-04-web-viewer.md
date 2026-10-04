# Web viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot web` sirve una interfaz htmx local, de solo lectura, que lista las compañías analizadas y muestra por qué cada una recibió su veredicto de MoS.

**Architecture:** `bot analyze` escribe un sidecar `<TICKER>.json` junto a los `.md/.html`. Nuevo paquete `src/bot/web/` con tres módulos puros (`index`, `views`, `svg`) y un borde (`app`, FastAPI + Jinja2). htmx vendorizado, fuentes locales.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Jinja2, htmx 2.x, pytest + `fastapi.testclient`, ruff, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-10-04-web-viewer-design.md`. Dirección visual: `.impeccable/surfaces/src-bot-web-templates-base-html.md` + `docs/DESIGN.md`.

## Global Constraints

- Solo lectura: la web nunca escribe ni invoca el pipeline.
- Cero texto que no sea dato: sin párrafos, sin CTAs, sin tooltips explicativos.
- Color nunca codifica solo (pigmento + forma).
- Sin CDN; bind `127.0.0.1` por defecto.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` verde en cada task.
- Conventional Commits, scope `web` (`feat(web): …`).

## Review Focus

1. Web y `.md` muestran el mismo veredicto → una sola función `margin_verdict` (Task 1).
2. Un JSON roto no tumba el listado (Task 2).
3. Análisis sin precio: `n/a`, sin value line, sin conteo de escenarios (Tasks 3–4).
4. Path traversal en `/c/{ticker}/{date}` y `/reports/...` (Task 6).
5. La lista con 500 filas no usa filtros SVG (Task 4).

---

### Task 1: Sidecar JSON en `bot analyze`

**Files:** `src/bot/reporting/analysis_report.py`, `src/bot/reporting/analysis_json.py` (nuevo), `src/bot/cli.py`, `tests/reporting/test_analysis_json.py`

- [ ] Renombrar `_margin_verdict` → `margin_verdict` (pública); actualizar uso.
- [ ] `render_analysis_json(analysis, *, generated_on) -> str`: `{"schema_version": 1, "generated_on", "verdict", "analysis": asdict(analysis)}`; enums/tuplas/fechas serializados con `default` explícito (no `str` genérico).
- [ ] `_analyze_one` escribe `<TICKER>.json` junto a `.md/.html` y lo imprime en `Wrote …`.
- [ ] Tests: claves presentes, `verdict == margin_verdict(mos)`, sin precio → `"n/a"` y `current_price: null`, celdas `None` del grid preservadas, JSON válido.
- [ ] Commit `feat(web): analyze writes a JSON sidecar per ticker`.

### Task 2: `web/index.py` — escaneo de reports

**Files:** `src/bot/web/__init__.py`, `src/bot/web/index.py`, `tests/web/test_index.py`

- [ ] `@dataclass(frozen=True) AnalysisRef(ticker, date, path)`; `CompanyEntry(ticker, latest: AnalysisRef, history: tuple[AnalysisRef, ...], data: dict)`.
- [ ] `scan(reports_dir: Path) -> list[CompanyEntry]`: glob `*/analysis/*.json`, carpeta = fecha ISO (si no parsea, se omite), último por ticker, historial desc.
- [ ] JSON malformado o `schema_version != 1` → `structlog` warning, se omite.
- [ ] `load(reports_dir, ticker, date | None) -> CompanyEntry | None`.
- [ ] Tests con `tmp_path`: dos fechas mismo ticker, archivo roto, versión 2, carpeta no-fecha, dir vacío/inexistente.
- [ ] Commit.

### Task 3: `web/views.py` — view-models

**Files:** `src/bot/web/views.py`, `tests/web/test_views.py`

- [ ] `Verdict` (StrEnum: undervalued/fair/overvalued/na) desde el string guardado.
- [ ] `RowView` (ticker, name, verdict, mos, price, intrinsic, story, flag_marks, date).
- [ ] `ValueLine` (price, intrinsic, range_low, range_high, axis_min, axis_max, t10, t13): rango = min/max de extremos no-`None` del tornado ∪ {price, intrinsic}; `None` sin precio.
- [ ] `ScenarioGrid` (axis_a, axis_b, labels, cells[verdict|None], matching: int, total: int): `matching` = celdas con el mismo veredicto que la base; `total` excluye `None`.
- [ ] `DetailView` agrupa: header, verdict, value line, grid, tornado, assumptions (label, value formateado, source), flags, sanity, dcf, history.
- [ ] Formateo reutiliza los formatters de `analysis_report` (exponer los necesarios, no duplicar).
- [ ] `filter_sort(rows, q, verdicts, sort, dir)` puro.
- [ ] Tests: umbrales 1.0/1.3 exactos, sin precio, grid con `None`, orden con `None` al final, búsqueda case-insensitive en ticker y nombre.
- [ ] Commit.

### Task 4: `web/svg.py` — gráficos a mano

**Files:** `src/bot/web/svg.py`, `tests/web/test_svg.py`

- [ ] `jitter_path(points, seed, amp) -> str`: polilínea con desplazamiento determinista (`random.Random(seed)`), `stroke-linecap/join: round`.
- [ ] `value_line(vl, *, mini: bool, seed) -> str`: eje, zona ≥1.3 oliva, banda de rango, price (trazo bistre), intrinsic (círculo índigo), segmento coloreado por veredicto. `mini=True`: 120×16, solo jitter, sin texto.
- [ ] `scenario_grid(g, seed)`, `tornado(entries, seed)`, `verdict_mark(v)`, `flag_mark(color)` — cada uno con `<title>`.
- [ ] Detalle: grupos envueltos en `<g filter="url(#wobble-N)">` (seed distinto por grupo); defs del filtro una vez en `base.html`. Texto fuera del grupo filtrado.
- [ ] Colores solo vía `var(--token)`; nada hardcodeado.
- [ ] Tests: determinismo (mismo seed → mismo string), posiciones relativas (intrinsic > price ⇒ x mayor), `mini` sin `filter=`, cada mark con `<title>`.
- [ ] Commit.

### Task 5: Templates, CSS, assets

**Files:** `src/bot/web/templates/{base,list,_rows,detail,_marks}.html`, `src/bot/web/static/{app.css,htmx.min.js,fonts/*.woff2}`, `pyproject.toml` (force-include)

- [ ] Leer `craft-floor.md` de impeccable antes de editar UI.
- [ ] Decodificar `docs/plano/fonts/*.b64` a `static/fonts/*.woff2`; `@font-face` local.
- [ ] Vendorizar htmx 2.x (`htmx.min.js`, versión anotada en `static/VERSIONS`).
- [ ] `app.css`: tokens de DESIGN.md en `:root` (OKLCH), escala tipográfica ≥1.25, `tabular-nums`, layout split ≥1100px, foco visible, `prefers-reduced-motion`, crossfade 120ms en `#detail.htmx-swapping/settling`, overlay de grano 5%.
- [ ] `base.html`: defs `wobble-1..4` + grano; `list.html` (búsqueda, toggles con conteo, tabla con `aria-sort`), `_rows.html` (tbody), `detail.html` (orden del spec), estados vacío y `0 of N`.
- [ ] Copy: solo etiquetas del spec. Revisar cada string: si no es dato o etiqueta, se borra.
- [ ] Incluir `templates/` y `static/` en el wheel (`force-include`).
- [ ] Commit.

### Task 6: `web/app.py` + `bot web`

**Files:** `src/bot/web/app.py`, `src/bot/cli.py`, `pyproject.toml`, `tests/web/test_app.py`

- [ ] `uv add fastapi uvicorn`.
- [ ] `create_app(reports_dir: Path) -> FastAPI`; rutas del spec; `HX-Request` → fragmento, si no → página completa.
- [ ] Validación `ticker` `^[A-Z0-9.\-]{1,12}$`, `date` `date.fromisoformat`; `/reports/{date}/{ticker}.html` resuelto y verificado con `is_relative_to(reports_dir)`; si no existe → 404.
- [ ] `bot web --host 127.0.0.1 --port 8000` → `uvicorn.run(create_app(settings.reports_dir))`.
- [ ] Tests `TestClient`: `/` completo; `/companies` con `HX-Request` devuelve solo `<tr>`; `verdict=`/`q=`/`sort=`; `/c/AAPL` y `/c/AAPL/2026-09-01`; ticker desconocido 404; `../` y ticker inválido → 404/422; vacío muestra `bot analyze --from-screen`.
- [ ] Commit `feat(web): bot web serves the analysis viewer`.

### Task 7: Verificación visual (impeccable, pasada acotada)

- [ ] Generar 3 sidecars de fixture (undervalued, overvalued con flag rojo, sin precio) y levantar `bot web`.
- [ ] Una ronda de screenshots Playwright desktop 1440 + mobile 390 (lista, detalle, vacío, filtro 0).
- [ ] `impeccable detect --json src/bot/web/templates src/bot/web/static/app.css`; corregir todo en un lote; una ronda de confirmación como máximo.
- [ ] Checklist: contraste AA, marks legibles en escala de grises, ningún texto filtrado por wobble, cero CTAs aparte de `Full report`.
- [ ] Commit fixes.

### Task 8: Docs y planos

- [ ] ADR `docs/adr/0008-read-only-web-viewer.md` (Implemented): web de solo lectura sobre `reports/`, por qué sidecar JSON y no DB.
- [ ] Spec principal §15: nota que el viewer read-only entra; dashboard operativo sigue fuera.
- [ ] `docs/PRODUCT.md`: Product Purpose admite el viewer como superficie *Operate* de solo lectura.
- [ ] `README.md`: paso `uv run bot web`.
- [ ] `CONTEXT.md`: término **Verdict** (lectura del MoS, umbrales).
- [ ] `python3 docs/plano/build.py` (agregar nodo `web/` si falla) y entrada nueva en `estado.py` INVENTARIO; `build_estado.py`.
- [ ] Surface brief: descargar FINISH (verdict del review + DESIGN.md si cambió algún token).
- [ ] Commit `docs(web): ADR 0008, product scope, planos`.
