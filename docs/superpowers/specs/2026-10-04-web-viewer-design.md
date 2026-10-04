# Web viewer de análisis — design

**Goal.** Un sitio estático, de solo lectura, publicado en GitHub Pages en cada
push a `main`, para recorrer las compañías analizadas por `bot analyze` y ver de
un vistazo por qué cada una recibió su veredicto.

**Status.** Decisiones del usuario (2026-10-04): stack htmx; fuente = archivos en
`reports/`; sin servidor ni DB en el deploy (export estático a GitHub Pages, solo
en push a `main`); veredicto = solo margin of safety; mundo visual = `docs/DESIGN.md`
completo, trazo a mano incluido; UI en inglés. Diseño vía impeccable (modo
*Operate*). Contrato de dirección en
`.impeccable/surfaces/src-bot-web-templates-base-html.md`.

**Cambio de alcance.** Spec §15 dejaba el dashboard web fuera de Fase 1 y
`PRODUCT.md` dice "el bot es CLI y así se queda". Esto no lo contradice del todo:
el viewer no opera nada (no corre screen/analyze, no escribe). El sitio es
público (repo público + Pages): los análisis commiteados quedan visibles. Igual se registra
en ADR 0008 y se enmienda `PRODUCT.md`.

## Principio rector

Cada píxel transmite un dato. Sin párrafos explicativos, sin CTAs, sin tarjetas de
métrica, sin onboarding. Etiquetas cortas; los números y las formas cargan el
mensaje. Único texto largo admitido: los `reason` que ya produce el bot (story
type, narrative flags), porque son datos.

## Datos

### Fuente: sidecar JSON en `reports/`

Hoy `bot analyze` escribe `<reports_dir>/YYYY-MM-DD/analysis/<TICKER>.{md,html}`.
Parsear el `.md` es frágil, así que `analyze` pasa a escribir además
`<TICKER>.json` en el mismo directorio. La web solo lee esos JSON.

```json
{
  "schema_version": 1,
  "generated_on": "2026-10-01",
  "verdict": "potentially undervalued",
  "analysis": { ...dataclasses.asdict(Analysis), enums como str... }
}
```

- `verdict` sale de la función que ya usa el reporte (`_margin_verdict`, que pasa
  a pública como `margin_verdict`), así web y `.md` nunca discrepan.
- Reportes previos sin `.json` no aparecen; se regeneran con `bot analyze`.
- Los `.json` se commitean (`.gitignore` deja pasar solo
  `reports/*/analysis/*.json`). Son la única entrada del build: CI no necesita
  DuckDB, EDGAR ni Tiingo. `.md`/`.html` siguen ignorados.
- JSON malformado o `schema_version` desconocido → se omite y se loguea warning;
  no rompe el listado.
- Índice: un escaneo de `reports_dir/*/analysis/*.json` por build. Por ticker vale el más reciente; los anteriores forman su
  historial.

### Veredicto

Solo MoS, umbrales actuales: `≥1.3` undervalued · `≥1.0` fair · `<1.0`
overvalued · sin precio `n/a`. Flags, story type y sanity se muestran como
contexto: no deciden.

### "Por qué" = cuatro hechos derivados, sin prosa

| Hecho | Origen | Forma |
|---|---|---|
| Precio vs intrinsic | `current_price`, `dcf_result.intrinsic_value` | Value line |
| Robustez | celdas de `grid` con el mismo veredicto que la base | `n/25` + grilla 5×5 |
| Qué lo mueve | `tornado` (ordenado por impacto) | barras |
| De dónde salen los supuestos | `assumptions.*.{value,source}` | tabla |

Contexto: story type + reasons, 5 narrative flags, sanity check (P/E, EV/Sales vs
sector), proyección DCF (colapsada).

## Superficies

Todo se pre-renderiza a HTML. htmx carga fragmentos estáticos; sin JS, cada link
apunta a una página completa equivalente (progressive enhancement).

| Archivo | Contenido |
|---|---|
| `index.html` | Lista (todos, MoS desc) + detalle del primero. |
| `rows/{verdict}-{sort}-{dir}.html` | `<tbody>` pre-generado: verdict ∈ all/undervalued/fair/overvalued/na × sort ∈ ticker/mos/date × asc/desc (30 fragmentos). |
| `c/{TICKER}.html` | Detalle, página completa (último análisis). |
| `c/{TICKER}/{date}.html` | Detalle de un análisis anterior. |
| `f/{TICKER}.html`, `f/{TICKER}/{date}.html` | Mismo detalle como fragmento para `#detail`. |
| `static/*` | CSS, htmx, fuentes. |

URLs relativas a `--base-url` (Pages de proyecto sirve bajo `/damodaran/`).

### Lista

Columnas: `Ticker` · `Name` · verdict mark · `MoS` (número + mini value line) ·
`Price` · `Intrinsic` · `Story` · flags (una marca por flag rojo/amarillo) ·
`Date`.

Controles (únicos de la app):
- Filtro de veredicto: selección única (`all` `undervalued` `fair` `overvalued`
  `n/a`) con conteo; `hx-get rows/…` sobre el `<tbody>`.
- Orden: headers `Ticker` `MoS` `Date` clicables (`MoS` desc por defecto); `aria-sort`.
- Sin búsqueda: requiere servidor y la shortlist es corta (~20).
- Fila = link a `c/{ticker}.html`; en desktop `hx-get f/{ticker}.html`,
  `hx-target="#detail"`, `hx-push-url` a la página completa.

Vacío: `No analyses` y la línea `bot analyze --from-screen`.
Filtro sin resultados: `0 of N`.

### Detalle (primer viewport, de arriba abajo)

1. `AAPL  Apple Inc.` · `2026-10-01` · `mature-stable` · historial como links de fecha si hay más de uno.
2. Verdict mark + `potentially undervalued` + `MoS 1.42×`.
3. **Value line** (movimiento firma, ver abajo).
4. `Scenarios 19/25` + grilla 5×5 (ejes = las dos assumptions de `grid`).
5. `Drivers`: tornado, todas las axes, la más ancha arriba.
6. Dos columnas: `Assumptions` (value · source) | `Flags` (marca · name · reason).
7. `Sanity`: `P/E 18.2 / 24.1` · `EV/Sales 4.1 / 3.8` (implied / sector).
8. `<details>` `DCF` (tabla de proyección + EV/equity/net debt).

Sin link a `Full report`: el `.html` con Plotly inline pesa MB y no se commitea.

## Dirección visual

Mundo = `docs/DESIGN.md` entero: hoja `--sheet` sobre `--desk`, tintas bistre,
Shantell Sans / Literata / Sometype Mono, OKLCH, trazo a mano. Modo *Operate*: el
mundo aporta tipo, paleta, densidad y un movimiento firma; layout, navegación y
controles son estándar (tabla, inputs, toggles, links).

### Notación del veredicto (color nunca solo)

| Veredicto | Pigmento (rol) | Forma |
|---|---|---|
| undervalued | oliva (*selecciona*) | check doble trazo |
| fair | ocre (*datos*) | círculo abierto |
| overvalued | terracota (*elimina*) | compuerta con hatching |
| n/a | `--ink-soft` | guion |

Flags: `red` terracota hatching · `yellow` ocre círculo · `green` oliva check ·
`unknown` contorno punteado vacío (nunca se lee como pass, spec §7.5).

### Movimiento firma: la value line

Un eje horizontal a mano en unidades de precio por acción:
- marcador de **price** (trazo vertical bistre) e **intrinsic** (círculo índigo, *valúa*);
- banda de rango = min/max de los extremos del tornado (la "nube" de §7.4);
- ticks de umbral en `price×1.0` y `price×1.3`, la zona ≥1.3 sombreada oliva;
- el segmento price→intrinsic coloreado por veredicto.

Se lee sin texto: dónde cae el intrinsic respecto del precio y si la nube cruza
el umbral. En la lista aparece en miniatura.

### Trazo a mano: dos técnicas según costo

- **Detalle** (pocos grupos grandes: value line, grilla, tornado, marks): SVG
  limpio + filtro `wobble` de DESIGN.md (`feTurbulence`+`feDisplacementMap`,
  `scale` 1.5–3, seed por grupo, rotación ±0.6°). Texto nunca filtrado.
- **Lista** (N filas): sin filtros. Paths con jitter determinista generado en el
  servidor (`seed = hash(ticker)`), mismo look, costo cero en el cliente.
- Grano de papel: una sola capa overlay al 5%.

### Tipografía y números

- Shantell Sans: títulos, ticker grande del detalle, etiquetas de gráficos.
- Literata: cuerpo, reasons, tablas; `font-variant-numeric: tabular-nums lining-nums`.
- Sometype Mono: tickers en la lista, nombres de assumption/flag, `source`.
- Fuentes servidas locales (woff2 decodificados de `docs/plano/fonts/*.b64`).

### Layout

- `≥1100px`: lista a la izquierda (≈40%, scroll propio, sticky) + detalle a la
  derecha. Selección marcada en la fila.
- `<1100px`: solo lista; la fila navega a `/c/{ticker}` como página.
- Sin cards. Agrupación por espaciado y filetes dibujados.

### Motion

- Swap de htmx: crossfade 120ms ease-out en `#detail`. Nada más.
- `prefers-reduced-motion`: swap instantáneo.

### Anti-goals

KPI cards, gradientes, azul marino/dorado, líneas verdes de fintech, fondo crema,
editorial italic + mono labels, iconografía decorativa, tooltips con texto
explicativo, banners, botones "View details", modales.

## Arquitectura

```
src/bot/web/
  __init__.py
  index.py      # escaneo de reports_dir → CompanyEntry (puro sobre Path)
  views.py      # dict JSON → view-models tipados (VerdictView, ValueLine, ScenarioGrid…)
  svg.py        # value line, grilla, tornado, marks; jitter determinista; puro
  site.py       # build(reports_dir, out_dir, base_url): render Jinja → archivos
  templates/    # base.html, list.html, _rows.html, detail.html, _marks.html
  static/       # app.css, htmx.min.js (2.x, vendorizado), fonts/*.woff2
```

- CLI: `bot site --out site/ [--base-url /]`. No abre la DB ni lee `.env`
  obligatorios. Vista local: `python -m http.server -d site`.
- Sin deps nuevas: Jinja2 ya está. Sin servidor, sin CDN.
- `index`, `views`, `svg` son puros; `site.build` es el único borde (escribe a
  `out_dir`, que se vacía antes).
- Tickers validados `^[A-Z0-9.\-]{1,12}$` antes de usarse en nombres de archivo;
  autoescape Jinja activo.

## CI / deploy

`.github/workflows/site.yml`, solo `on: push: branches: [main]`.

1. `checkout` → `astral-sh/setup-uv` → `uv sync --frozen`.
2. Gate: `ruff check`, `mypy src`, `pytest -q`. Si falla, no se deploya.
3. `uv run bot site --out site --base-url /${{ github.event.repository.name }}/`.
4. `actions/upload-pages-artifact` → `actions/deploy-pages` (environment
   `github-pages`; permisos `pages: write`, `id-token: write`).
5. `concurrency: pages`, `cancel-in-progress: true`.

CI no corre `bot analyze`: sin DB ni APIs no hay qué analizar. Flujo:
`bot analyze` local → commit de los `.json` → push a `main` → CI construye y
publica. Requisito único: Settings → Pages → Source = *GitHub Actions*.

## Accesibilidad

WCAG 2.2 AA (contrastes de DESIGN.md ya verificados). Marks con `<title>` y texto
del veredicto visible al lado. Filas focusables (link real). `aria-live="polite"`
en `#detail` y en el conteo del filtro. Foco visible dibujado.

## Testing

- `index`: último por ticker, historial, JSON roto omitido, versión desconocida omitida.
- `views`/`svg`: posiciones de la value line, conteo de escenarios (incluye celdas
  `None`), sin precio → `n/a` sin value line, jitter determinista.
- `site.build` sobre `tmp_path`: genera los 30 `rows/*`, `c/` y `f/` por ticker e
  historial; `base-url` aplicado a todos los links; dir vacío → `index.html` con
  estado vacío; ticker inválido omitido.
- Sidecar: round-trip `Analysis → JSON → view-model`.
- `ruff`, `mypy --strict`, `pytest`; `impeccable detect` sobre templates/CSS al final.

## Fuera de alcance

Ejecutar comandos del bot desde la web o en CI, servidor/búsqueda, edición de
overrides, auth, multi-usuario, gráficos interactivos (Plotly), portfolio/alerts,
dark mode (DESIGN.md fuerza claro), deploy programado.
