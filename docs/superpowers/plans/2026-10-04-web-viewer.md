# Web viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot site` genera un sitio htmx estático que lista las compañías analizadas y muestra por qué cada una recibió su veredicto de MoS; cada push a `master` lo construye y publica en GitHub Pages.

**Architecture:** `bot analyze` escribe un sidecar `<TICKER>.json` junto a los `.md/.html`. Los `.json` se commitean. Nuevo paquete `src/bot/web/` con tres módulos puros (`index`, `views`, `svg`) y un borde (`site`, Jinja2 → archivos). htmx vendorizado, fuentes locales. Workflow de Actions: gate de calidad → `bot site` → Pages.

**Tech Stack:** Python 3.12, Jinja2, htmx 2.x, GitHub Actions + Pages, pytest, ruff, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-10-04-web-viewer-design.md`. Dirección visual: `.impeccable/surfaces/src-bot-web-templates-base-html.md` + `docs/DESIGN.md`.

## Global Constraints

- Solo lectura: la web nunca escribe ni invoca el pipeline.
- Cero texto que no sea dato: sin párrafos, sin CTAs, sin tooltips explicativos.
- Color nunca codifica solo (pigmento + forma).
- Sin CDN, sin servidor, sin deps nuevas. CI nunca toca DuckDB ni APIs externas.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` verde en cada task.
- Conventional Commits, scope `web` (`feat(web): …`).

## Review Focus

1. Web y `.md` muestran el mismo veredicto → una sola función `margin_verdict` (Task 1).
2. Un JSON roto no tumba el listado (Task 2).
3. Análisis sin precio: `n/a`, sin value line, sin conteo de escenarios (Tasks 3–4).
4. Ticker/fecha inválidos nunca llegan a un nombre de archivo (Tasks 2, 6).
5. La lista con 500 filas no usa filtros SVG (Task 4).
6. Un push a `master` con tests rojos no deploya (Task 7).

---

### Task 1: Sidecar JSON en `bot analyze`

**Files:** `src/bot/reporting/analysis_report.py`, `src/bot/reporting/analysis_json.py` (nuevo), `src/bot/cli.py`, `tests/reporting/test_analysis_json.py`

- [ ] Renombrar `_margin_verdict` → `margin_verdict` (pública); actualizar uso.
- [ ] `render_analysis_json(analysis, *, generated_on) -> str`: `{"schema_version": 1, "generated_on", "verdict", "analysis": asdict(analysis)}`; enums/tuplas/fechas serializados con `default` explícito (no `str` genérico).
- [ ] `_analyze_one` escribe `<TICKER>.json` junto a `.md/.html` y lo imprime en `Wrote …`.
- [ ] Tests: claves presentes, `verdict == margin_verdict(mos)`, sin precio → `"n/a"` y `current_price: null`, celdas `None` del grid preservadas, JSON válido.
- [ ] `.gitignore`: reemplazar `reports/` por
  ```
  reports/*
  !reports/*/
  reports/*/*
  !reports/*/analysis/
  reports/*/analysis/*
  !reports/*/analysis/*.json
  ```
  y verificar con `git check-ignore -v` que `.md/.html` siguen ignorados y `.json` no.
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
- [ ] `filter_sort(rows, verdict, sort, dir)` puro (verdict ∈ all/…; sort ∈ ticker/mos/date).
- [ ] Tests: umbrales 1.0/1.3 exactos, sin precio, grid con `None`, orden con `None` al final en ambas direcciones.
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
- [ ] Copiar la licencia OFL de cada familia (Shantell Sans, Literata, Sometype Mono) a `static/fonts/OFL-<familia>.txt`.
- [ ] Vendorizar htmx 2.x (`htmx.min.js`, versión anotada en `static/VERSIONS`).
- [ ] `app.css`: tokens de DESIGN.md en `:root` (OKLCH), escala tipográfica ≥1.25, `tabular-nums`, layout split ≥1100px, foco visible, `prefers-reduced-motion`, crossfade 120ms en `#detail.htmx-swapping/settling`, overlay de grano 5%.
- [ ] `base.html`: defs `wobble-1..4` + grano; `list.html` (filtro de selección única con conteo, tabla con `aria-sort`), `_rows.html` (tbody), `detail.html` (orden del spec, sin `Full report`), estados vacío y `0 of N`. Todos los links con `{{ base_url }}` y `href` real además de `hx-get`.
- [ ] Copy: solo etiquetas del spec. Revisar cada string: si no es dato o etiqueta, se borra.
- [ ] Incluir `templates/` y `static/` en el wheel (`force-include`).
- [ ] Commit.

### Task 6: `web/site.py` + `bot site`

**Files:** `src/bot/web/site.py`, `src/bot/cli.py`, `tests/web/test_site.py`

- [ ] `build(reports_dir: Path, out_dir: Path, base_url: str) -> int` (devuelve nº de compañías): vacía `out_dir`, copia `static/`, escribe `index.html`, `rows/{verdict}-{sort}-{dir}.html` (30), `c/{T}.html`, `c/{T}/{date}.html`, `f/{T}.html`, `f/{T}/{date}.html`.
- [ ] `base_url` normalizado a `/…/`; ticker validado `^[A-Z0-9.\-]{1,12}$` (si no, warning y se omite).
- [ ] `bot site --out site --reports-dir reports --base-url /`: NO llama `load_settings()` ni `_open_db` (Settings exige `BOT_SEC_USER_AGENT`); imprime `Built N companies → site/`.
- [ ] Tests (`tmp_path`, fixtures JSON): conteo de archivos, fragmentos sin `<html>`, páginas completas con `<html>`, todos los `href`/`hx-get` empiezan con `base_url`, historial, dir vacío → `index.html` con `bot analyze --from-screen`, ticker inválido omitido, re-build limpia archivos viejos.
- [ ] Commit `feat(web): bot site builds the static analysis viewer`.

### Task 7: Workflow de CI → GitHub Pages

**Files:** `.github/workflows/site.yml`

- [ ] Crear:
  ```yaml
  name: site
  on:
    push:
      branches: [master]
  permissions:
    contents: read
    pages: write
    id-token: write
  concurrency:
    group: pages
    cancel-in-progress: true
  jobs:
    build:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v6
          with:
            python-version: "3.12"
        - run: uv sync --frozen
        - run: uv run ruff check .
        - run: uv run mypy src
        - run: uv run pytest -q
        - run: uv run bot site --out site --base-url "/${{ github.event.repository.name }}/"
        - uses: actions/upload-pages-artifact@v3
          with:
            path: site
    deploy:
      needs: build
      runs-on: ubuntu-latest
      environment:
        name: github-pages
        url: ${{ steps.deployment.outputs.page_url }}
      steps:
        - id: deployment
          uses: actions/deploy-pages@v4
  ```
- [ ] Verificar localmente que el comando del paso `bot site` corre con un entorno sin `.env` (`env -i PATH=$PATH HOME=$HOME uv run bot site …`): CI no tiene secrets.
- [ ] Verificar que la suite pasa sin red (tests de integración usan cassettes VCR).
- [ ] Manual (dueño del repo): Settings → Pages → Source = *GitHub Actions*.
- [ ] Commit `ci(web): build and deploy the viewer to GitHub Pages on push to master`.

### Task 8: Verificación visual (impeccable, pasada acotada)

- [ ] Generar 3 sidecars de fixture (undervalued, overvalued con flag rojo, sin precio), `bot site --out site` y `python -m http.server -d site`.
- [ ] Una ronda de screenshots Playwright desktop 1440 + mobile 390 (lista, detalle, vacío, filtro 0).
- [ ] `impeccable detect --json src/bot/web/templates src/bot/web/static/app.css`; corregir todo en un lote; una ronda de confirmación como máximo.
- [ ] Checklist: contraste AA, marks legibles en escala de grises, ningún texto filtrado por wobble, cero CTAs, navegación funciona con JS deshabilitado.
- [ ] Commit fixes.

### Task 9: Docs y planos

- [ ] ADR `docs/adr/0008-read-only-web-viewer.md` (Implemented): sitio estático público sobre `reports/*.json` commiteados; por qué sidecar JSON y no DB; por qué CI no corre `analyze`.
- [ ] Spec principal §15: nota que el viewer read-only entra; dashboard operativo sigue fuera.
- [ ] `docs/PRODUCT.md`: Product Purpose admite el viewer como superficie *Operate* de solo lectura.
- [ ] `README.md`: flujo `bot analyze` → commit `reports/*/analysis/*.json` → push a `master` → Pages; vista local con `bot site` + `http.server`.
- [ ] `CONTEXT.md`: término **Verdict** (lectura del MoS, umbrales).
- [ ] `python3 docs/plano/build.py` (agregar nodo `web/` si falla) y entrada nueva en `estado.py` INVENTARIO; `build_estado.py`.
- [ ] Surface brief: descargar FINISH (verdict del review + DESIGN.md si cambió algún token).
- [ ] Commit `docs(web): ADR 0008, product scope, planos`.
