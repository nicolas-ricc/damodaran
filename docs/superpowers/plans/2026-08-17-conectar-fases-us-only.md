# Conectar las fases — versión funcionando, solo bolsa de USA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `bot refresh → bot screen → bot analyze` funcione de punta a punta contra datos reales de empresas de bolsa de USA (universo S&P 500, FMP tier gratis), con los cables muertos que rompen esa cadena conectados y el screener honesto según la ADR 0006.

**Architecture:** Cinco fases secuenciales. Fase 1 hace la Capa A apta para datos reales (universo real, resiliencia al rate limit de FMP, fixes de ingesta). Fase 2 implementa la compuerta de cobertura (ADR 0006) en el screener. Fase 3 conecta el story type a la valuación (versión mínima) y los overrides por convención. Fase 4 conecta screen → analyze (`--from-screen`). Fase 5 verifica: doctor honesto, test E2E con fixtures, y la corrida real contra la red. TDD en cada tarea.

**Tech Stack:** Python 3.14, DuckDB, Pydantic v2 / pydantic-settings, Typer, httpx, Jinja2, structlog, pytest + pytest-vcr, ruff, mypy `--strict`, `uv` como runner.

**Spec:** `docs/superpowers/specs/2026-05-25-investment-bot-design.md` (§4–§7, §9, §12). Estado real auditado: `docs/plano/estado.py` (auditoría del 16-08-2026, commit a2fa9db).

## Global Constraints

- `uv run mypy src` debe salir `Success` (config `--strict`).
- `uv run ruff check src tests` debe salir `All checks passed!` (`line-length = 100`).
- `uv run pytest -q` completo y verde al final de **cada** tarea. Baseline actual: **676 passed**.
- Conventional Commits, un commit por tarea salvo indicación: `feat(...)`, `fix(...)`, `docs(...)`.
- Adapters de ingest puros: `download → parse → upsert`; funciones reciben paths/conexiones, sin estado global.
- Tests de integración con cassettes VCR / fixtures; **cero** llamadas de red en CI. La única excepción es la Task 13 (corrida real), que es operación manual, no test.
- Degradación grácil (spec §13.2): un dato ausente no revienta la corrida.
- No inventar números: un assumption sin resolver queda `Sourced(value=None, source=UNRESOLVED)`.

## Decisiones de alcance (del usuario, 2026-08-17)

- **Solo acciones de bolsa de USA.** Universo = S&P 500. Damodaran solo dataset US (que es el único que las URLs bajan de verdad). Esto vuelve **irrelevantes para esta versión**: las ocho regiones de Damodaran, la ADR 0005 (moneda: en US-only, cotización = reporte = USD), la conversión FX de los ratios, y la sustitución cross-region (queda como rama muerta honesta).
- **FMP tier gratis (~250 requests/día).** El refresh debe cortar limpio al chocar el límite y resumir al día siguiente (el diseño incremental ya existe; falta que el 429 no se cuente como "falla de datos"). La carga inicial del S&P 500 completo toma varios días; es aceptable y se documenta.
- **Story type: versión mínima.** Cablear `age_years` y ramificar crecimiento/margen para `high-growth` y `cyclical`. Sin Altman Z, sin consenso de analistas, sin derivar P(quiebra).
- **Portfolio (IBKR) diferido.** No se toca `portfolio/` en este plan.

**Fuera de alcance explícito** (queda como está, documentado en Task 14): wiring de `sync_trades`, evento de cruce intrínseco/precio, detectores huérfanos de eventos, corporate actions, Altman Z, consenso de analistas, INDEX.md, encabezado de reproducibilidad, bootstrap/cron/log a archivo/backup, series con huecos (`engine._tuple` descarta nulos — riesgo bajo con datos FMP de S&P 500), refinamiento de los scores de quality/growth del ranking, pytest-cov.

## File Structure

**Fase 1 — Capa A con datos reales**
- Modify: `src/bot/ingest/universe_default.csv` — reemplazar los 451 tickers sintéticos por el S&P 500 real.
- Modify: `src/bot/ingest/fmp.py` — `FmpRateLimitError`, captura de `ipoDate` (Task 7).
- Modify: `src/bot/ingest/universe.py` — corte limpio por rate limit, estado `deferred`.
- Modify: `src/bot/cli.py` — `--limit` en refresh, reporte de deferred, guard `--region US`.
- Modify: `src/bot/ingest/sec_edgar.py` — `upsert_company` que preserva columnas que SEC no trae.

**Fase 2 — ADR 0006**
- Modify: `src/bot/screener/engine.py` — compuerta de cobertura, trap-skip eliminatorio, `ScreenResult.no_coverage` + `rejected`.
- Modify: `src/bot/screener/persist.py`, `src/bot/storage/schema.sql` — persistir rechazados (`passed BOOLEAN`, `rank` nullable).
- Modify: `src/bot/reporting/screen_report.py` — línea de cobertura.

**Fase 3 — Valuador conectado**
- Modify: `src/bot/storage/schema.sql` — `companies.ipo_date DATE`.
- Modify: `src/bot/valuator/analysis.py` — edad desde `ipo_date`.
- Modify: `src/bot/valuator/assumptions.py` — `STORY_PATTERN`, margen como path, branching por arquetipo.
- Modify: `src/bot/reporting/analysis_report.py` + `src/bot/reporting/templates/` — mostrar el path de margen.
- Modify: `src/bot/config.py` — `assumptions_dir`.
- Create: `config/assumptions/README.md` + `config/assumptions/_EXAMPLE.yaml.example`.

**Fase 4 — screen → analyze**
- Modify: `src/bot/cli.py` — `analyze` variádico + `--from-screen`.

**Fase 5 — Verificación**
- Modify: `src/bot/cli.py` — doctor honesto.
- Create: `tests/e2e/test_pipeline.py` — refresh (fixtures) → screen → analyze sobre una sola DB.
- Create: `.env.example`; Modify: `README.md` — quickstart real.
- Modify: `docs/adr/0005-*.md`, `docs/adr/0006-*.md`, `docs/plano/estado.py`, `CONTEXT.md`.

---

## Fase 1 — Capa A lista para datos reales de USA

### Task 1: Universo real — S&P 500

**Files:**
- Modify: `src/bot/ingest/universe_default.csv`
- Test: `tests/unit/test_universe_csv.py` (nuevo)

**Interfaces:**
- Consumes: `load_universe` / `default_universe_path` de `bot.ingest.universe` (sin cambios).
- Produces: el CSV empaquetado con ~503 tickers reales del S&P 500, formato FMP (`BRK-B`, no `BRK.B`). Tasks 12 y 13 lo consumen.

- [ ] **Step 1: Generar el CSV desde la lista mantenida de datahub**

```bash
cd /home/nicolasr/Projects/investment-bot
curl -sL https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv -o /tmp/claude-1000/-home-nicolasr-Projects-investment-bot/57e5d7db-d61f-4de5-a002-9c58faa3595a/scratchpad/constituents.csv
uv run python - <<'EOF'
import csv
from datetime import date
from pathlib import Path

src = Path("/tmp/claude-1000/-home-nicolasr-Projects-investment-bot/57e5d7db-d61f-4de5-a002-9c58faa3595a/scratchpad/constituents.csv")
dst = Path("src/bot/ingest/universe_default.csv")
with src.open() as f:
    rows = list(csv.DictReader(f))
tickers = sorted({r["Symbol"].strip().upper().replace(".", "-") for r in rows if r["Symbol"].strip()})
assert 490 <= len(tickers) <= 510, f"unexpected count: {len(tickers)}"
lines = [
    f"# S&P 500 constituents — fuente: github.com/datasets/s-and-p-500-companies, {date.today().isoformat()}",
    "# Tickers en formato FMP (punto -> guion: BRK-B). Universo US-only de esta version.",
    "ticker",
    *tickers,
]
dst.write_text("\n".join(lines) + "\n")
print(len(tickers), "tickers written")
EOF
```

Expected: `50x tickers written` (entre 490 y 510). Si la URL falla, la alternativa es el mismo dataset en `https://datahub.io/core/s-and-p-500-companies/r/constituents.csv`.

- [ ] **Step 2: Escribir el test que fija el contrato del CSV**

`tests/unit/test_universe_csv.py`:

```python
"""The shipped default universe must be the real S&P 500, in FMP ticker format."""

from bot.ingest.universe import default_universe_path, load_universe


def test_default_universe_is_real_sp500() -> None:
    tickers = load_universe(default_universe_path())
    assert 490 <= len(tickers) <= 510
    # Miembros permanentes que detectan un archivo sintético o truncado.
    for known in ("AAPL", "MSFT", "JNJ", "JPM", "XOM"):
        assert known in tickers
    # Formato FMP: guion, nunca punto (BRK.B -> BRK-B).
    assert "BRK-B" in tickers
    assert not any("." in t for t in tickers)


def test_default_universe_has_no_duplicates() -> None:
    tickers = load_universe(default_universe_path())
    assert len(tickers) == len(set(tickers))
```

- [ ] **Step 3: Correr los tests nuevos y la suite**

Run: `uv run pytest tests/unit/test_universe_csv.py -v && uv run pytest -q`
Expected: los 2 nuevos PASS. Si algún test existente aserta sobre el contenido del CSV viejo (buscar con `grep -rn "universe_default" tests/`), actualizalo a este contrato — el archivo sintético deja de existir.

- [ ] **Step 4: Commit**

```bash
git add src/bot/ingest/universe_default.csv tests/unit/test_universe_csv.py
git commit -m "feat(universe): replace the 451 synthetic tickers with the real S&P 500"
```

---

### Task 2: Rate limit de FMP — cortar limpio y resumir mañana

El tier gratis de FMP devuelve HTTP 429 al agotar ~250 requests/día. Hoy cada 429 se cuenta como "falla de datos" del ticker: una corrida de 500 tickers registra cientos de fallas falsas, sigue golpeando la API y sale con código 2. El corte debe ser: primer 429 → parar la corrida, marcar lo no intentado como `deferred` (no `failed`), y que el estado agregado se calcule solo sobre lo intentado.

**Files:**
- Modify: `src/bot/ingest/fmp.py` (clase de error, `_get`)
- Modify: `src/bot/ingest/universe.py` (`TickerOutcome`, `UniverseRefreshResult`, `_run_bulk_refresh`, `_refresh_one`, `_refresh_one_price`, `_refresh_one_currency`)
- Modify: `src/bot/cli.py` (`--limit`, reporte de deferred)
- Test: `tests/unit/test_universe_rate_limit.py` (nuevo), `tests/unit/test_cli_refresh_fmp.py`

**Interfaces:**
- Produces: `FmpRateLimitError(RuntimeError)` en `bot.ingest.fmp`; `TickerOutcome.status` admite `"deferred"`; `UniverseRefreshResult.deferred: int` (property derivada de outcomes); `bot refresh --fmp/--prices --limit N`.
- Consumes: nada nuevo.

- [ ] **Step 1: Test rojo — el cliente convierte 429 en FmpRateLimitError**

En `tests/unit/test_universe_rate_limit.py`:

```python
"""FMP free-tier rate limiting: stop cleanly, defer the rest, resume tomorrow."""

import httpx
import pytest

from bot.ingest.fmp import FmpClient, FmpRateLimitError


def test_fmp_client_raises_rate_limit_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FmpClient(api_key="k")

    def fake_get(path: str, params: object = None) -> httpx.Response:
        return httpx.Response(429, request=httpx.Request("GET", "https://x/"), json={"Error": "Limit"})

    monkeypatch.setattr(client._client, "get", fake_get)
    with pytest.raises(FmpRateLimitError):
        client.lookup_company("AAPL")
```

Run: `uv run pytest tests/unit/test_universe_rate_limit.py -v` → FAIL (`ImportError: FmpRateLimitError`).

- [ ] **Step 2: Implementar el error en el cliente**

En `src/bot/ingest/fmp.py`, arriba de `FmpClient`:

```python
class FmpRateLimitError(RuntimeError):
    """FMP devolvió HTTP 429: se agotó la cuota diaria del API key.

    No es una falla del ticker ni un error de datos: la corrida debe cortar y
    el resto del universo queda diferido para la próxima corrida (el refresh es
    incremental, así que retomarlo es gratis).
    """
```

Y en `FmpClient._get`, antes de `raise_for_status()`:

```python
        if r.status_code == 429:
            raise FmpRateLimitError(
                "FMP rate limit (HTTP 429): cuota diaria agotada; reintentá mañana"
            )
```

- [ ] **Step 3: Test rojo — el bulk corta y difiere el resto**

Agregar al mismo archivo:

```python
import duckdb

from bot.ingest.base import IngestResult
from bot.ingest.universe import refresh_universe_from_fmp
from bot.storage.db import apply_schema


def _ok_result(source: str = "fmp") -> IngestResult:
    from datetime import datetime

    now = datetime.now()
    return IngestResult(source=source, started_at=now, finished_at=now, status="success", rows_affected=1)


def test_bulk_refresh_stops_on_rate_limit_and_defers_the_rest() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    calls: list[str] = []

    def importer(conn: object, *, ticker: str, api_key: str) -> IngestResult:
        calls.append(ticker)
        if ticker == "CCC":
            raise FmpRateLimitError("quota")
        return _ok_result()

    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAA", "BBB", "CCC", "DDD", "EEE"],
        importer=importer,
        latest_filing_probe=lambda t: None,
    )
    assert calls == ["AAA", "BBB", "CCC"]  # DDD/EEE nunca se intentan
    assert result.imported == 2
    assert result.deferred == 3  # CCC (rate-limited) + DDD + EEE
    assert result.failed == 0
    assert result.status == "success"  # 0 fallas sobre lo intentado
```

Run: FAIL (`AttributeError: deferred` / el 429 se cuenta como failed).

- [ ] **Step 4: Implementar el corte en `universe.py`**

1. En `TickerOutcome`, ampliar el comentario de `status` con `"deferred"`: no intentado (o interrumpido) por rate limit.
2. En `UniverseRefreshResult`, agregar la property:

```python
    @property
    def deferred(self) -> int:
        """Tickers no intentados porque la cuota diaria de FMP se agotó."""
        return sum(1 for o in self.outcomes if o.status == "deferred")
```

y cambiar `failure_rate` para calcular sobre lo intentado:

```python
    @property
    def failure_rate(self) -> float:
        """Fracción de lo *intentado* que falló (0.0 cuando no se intentó nada)."""
        attempted = self.total - self.deferred
        return self.failed / attempted if attempted else 0.0
```

3. En `_refresh_one`, `_refresh_one_price` y `_refresh_one_currency`, antes del `except Exception` genérico agregar:

```python
        except FmpRateLimitError:
            raise
```

(con el import `from bot.ingest.fmp import FmpRateLimitError` ya presente vía el módulo).

4. En `_run_bulk_refresh`, envolver el `process` del loop:

```python
    rate_limited = False
    for index, item in enumerate(items, start=1):
        if rate_limited:
            outcomes.append(TickerOutcome(ticker=item.upper(), status="deferred"))
            continue
        try:
            outcome = process(item)
        except FmpRateLimitError as exc:
            log.warning(f"{label}.refresh.rate_limited", item=item, error=str(exc))
            rate_limited = True
            outcomes.append(TickerOutcome(ticker=item.upper(), status="deferred"))
            continue
        ...
```

y en el conteo, sumar `deferred` como su propia categoría (ni imported, ni skipped, ni failed). `_resolve_status` no cambia: recibe la nueva `failure_rate` sobre intentados. En `_log_bulk_refresh`, si hubo deferred agregarlo al `error_message` del summary (`"rate limited: N deferred"`).

- [ ] **Step 5: `--limit` y reporte en el CLI**

En `src/bot/cli.py`, agregar a `refresh`:

```python
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Procesar a lo sumo N tickers de --fmp/--prices (para el tier gratis de FMP).",
    ),
```

En `_refresh_fmp_universe` y `_refresh_prices`, después de `tickers = load_universe(path)`:

```python
    if limit is not None:
        tickers = tickers[:limit]
```

(pasar `limit` como parámetro a ambas funciones). En `_report_universe_refresh`, agregar tras la línea de resumen:

```python
    if result.deferred:
        typer.echo(
            f"NOTE — {result.deferred} tickers deferred (FMP daily quota); "
            "volvé a correr el mismo comando mañana para continuar.",
        )
```

Test en `tests/unit/test_cli_refresh_fmp.py` (seguir el patrón de inyección existente en ese archivo): una corrida con deferred > 0 y 0 failed sale con código **0** y imprime `deferred`.

- [ ] **Step 6: Suite completa + commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: verde. Los tests existentes de `test_universe_refresh.py` no deben romper (el camino sin 429 no cambia).

```bash
git add src/bot/ingest/fmp.py src/bot/ingest/universe.py src/bot/cli.py tests/unit/test_universe_rate_limit.py tests/unit/test_cli_refresh_fmp.py
git commit -m "feat(ingest): stop cleanly on FMP 429, defer the rest, add refresh --limit"
```

---

### Task 3: `bot show --fetch` deja de borrar el mapeo sectorial

`sec_edgar.upsert_company` hace DELETE + INSERT con solo las columnas que SEC trae. La fila de SEC no trae `industry` ni `industry_damodaran`, así que un `bot show AAPL` sobre un ticker ya importado por FMP borra el mapeo y lo saca del universo del screener (con la coverage gate de Task 5, además, lo elimina explícitamente).

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`upsert_company`)
- Test: `tests/unit/test_sec_edgar_importer.py`

**Interfaces:**
- Produces: `upsert_company(conn, company)` con semántica de merge: una columna ausente o `None` en la fila nueva conserva el valor existente en la DB. Misma firma.
- Consumes: nada nuevo. `fmp.py` importa este mismo `upsert_company` — el merge lo beneficia igual (FMP sí manda todas sus columnas con valor).

- [ ] **Step 1: Test rojo**

En `tests/unit/test_sec_edgar_importer.py`:

```python
def test_upsert_company_preserves_columns_the_new_row_does_not_carry() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, currency, source) "
        "VALUES ('AAPL', 'Apple Inc.', 'US', 'Consumer Electronics', 'Computers/Peripherals', 'USD', 'fmp')"
    )
    # La fila de SEC no trae industria ni moneda.
    upsert_company(conn, {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193", "source": "sec_edgar"})
    row = conn.execute(
        "SELECT industry_damodaran, industry, currency, cik, source FROM companies WHERE ticker = 'AAPL'"
    ).fetchone()
    assert row == ("Computers/Peripherals", "Consumer Electronics", "USD", "0000320193", "sec_edgar")
```

Run: FAIL (`industry_damodaran` sale `None`).

- [ ] **Step 2: Implementar el merge**

Reemplazar `upsert_company` en `src/bot/ingest/sec_edgar.py`:

```python
def upsert_company(conn: duckdb.DuckDBPyConnection, company: dict[str, Any]) -> None:
    """Merge-replace the company row by ticker. Assumes called within a transaction.

    Un DELETE + INSERT crudo con solo las columnas del proveedor borraba lo que
    ese proveedor no trae: la fila de SEC no carga industria, así que un
    ``bot show --fetch`` sacaba del universo del screener a un ticker mapeado
    por FMP. Las columnas que la fila nueva no trae (o trae en ``None``)
    conservan el valor ya almacenado.
    """
    existing_row = conn.execute(
        "SELECT * FROM companies WHERE ticker = ?", [company["ticker"]]
    ).fetchone()
    merged = dict(company)
    if existing_row is not None:
        columns = [d[0] for d in conn.description]
        existing = dict(zip(columns, existing_row, strict=True))
        for col, value in existing.items():
            if merged.get(col) is None and value is not None:
                merged[col] = value
    merged.pop("last_updated_at", None)  # dejar que el DEFAULT la re-estampe
    cols = sorted(merged.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    conn.execute("DELETE FROM companies WHERE ticker = ?", [company["ticker"]])
    conn.execute(
        f"INSERT INTO companies ({col_list}) VALUES ({placeholders})",
        [merged[c] for c in cols],
    )
```

Nota: `conn.description` refleja el último `execute`; capturarlo inmediatamente después del SELECT, como arriba.

- [ ] **Step 3: Suite + commit**

Run: `uv run pytest tests/unit/test_sec_edgar_importer.py tests/integration/test_sec_edgar_import.py tests/unit/test_fmp_parser.py tests/integration/test_fmp_import.py -v && uv run pytest -q`
Expected: verde.

```bash
git add src/bot/ingest/sec_edgar.py tests/unit/test_sec_edgar_importer.py
git commit -m "fix(sec): merge-upsert companies so show --fetch stops wiping the industry mapping"
```

---

### Task 4: `refresh --region` deja de mentir — solo US

Las URLs de Damodaran son fijas y bajan datos de EE.UU.; pedir `--region Europe` guarda datos de EE.UU. etiquetados como europeos, sin fallar. En la versión US-only la opción honesta es rechazar cualquier región que no sea US.

**Files:**
- Modify: `src/bot/cli.py` (`refresh`)
- Test: `tests/unit/test_cli_refresh.py`

**Interfaces:**
- Produces: `bot refresh --damodaran --region Europe` → mensaje de error + exit 2, sin tocar la red ni la DB.

- [ ] **Step 1: Test rojo**

En `tests/unit/test_cli_refresh.py` (usar el `CliRunner` del archivo):

```python
def test_refresh_damodaran_rejects_non_us_region() -> None:
    result = runner.invoke(app, ["refresh", "--damodaran", "--region", "Europe"])
    assert result.exit_code == 2
    assert "US" in result.output
```

- [ ] **Step 2: Implementar el guard**

En `cli.refresh`, inmediatamente después del chequeo de "Specify what to refresh":

```python
    if damodaran and region.upper() != "US":
        typer.echo(
            f"--region {region}: esta versión es US-only. Las URLs de Damodaran "
            "apuntan al dataset de EE.UU.; pedir otra región guardaría datos de "
            "EE.UU. etiquetados con esa región. Usá --region US.",
            err=True,
        )
        raise typer.Exit(code=2)
```

- [ ] **Step 3: Suite + commit**

Run: `uv run pytest tests/unit/test_cli_refresh.py -v && uv run pytest -q` → verde.

```bash
git add src/bot/cli.py tests/unit/test_cli_refresh.py
git commit -m "fix(cli): reject refresh --damodaran with a non-US region instead of mislabelling US data"
```

---

## Fase 2 — El screener honesto (ADR 0006)

### Task 5: La compuerta de cobertura

Implementa la decisión completa de la ADR 0006: una empresa sin benchmark sectorial usable —`industry_damodaran` NULL, sin fila `damodaran_industry`, o fila con `wacc` NULL— **sale del universo** antes de evaluarse, y el run reporta cuántas se perdieron. Además el salteo de un trap detector pasa a ser eliminatorio (hoy absuelve).

**Files:**
- Modify: `src/bot/screener/engine.py` (`ScreenResult`, `run_screen`, `evaluate_company`, `_quality_metric`)
- Modify: `src/bot/reporting/screen_report.py` (`render_markdown`)
- Test: `tests/unit/test_screener_engine.py`, `tests/unit/test_reporting_screen.py`

**Interfaces:**
- Produces: `ScreenResult` gana `no_coverage: tuple[str, ...]` (tickers excluidos por cobertura, orden alfabético) con default `()` para no romper constructores existentes. `screened` sigue siendo el conteo de empresas *evaluadas* (ya no incluye las excluidas). Task 6 consume `no_coverage`; Task 12 aserta sobre el reporte.
- Consumes: `load_industry_benchmarks` (sin cambios: ya devuelve `None` sin fila).

- [ ] **Step 1: Tests rojos — las tres formas de no tener cobertura excluyen**

En `tests/unit/test_screener_engine.py`, siguiendo el patrón de seeding del archivo (helpers que insertan `companies` / `financials_annual` / `prices_daily` / `damodaran_industry`):

```python
def test_company_without_industry_mapping_leaves_the_universe(...) -> None:
    # seed una empresa completa pero con industry_damodaran NULL
    result = run_screen(conn, config, valuator=None)
    assert result.screened == 0
    assert result.no_coverage == ("NOMAP",)


def test_company_whose_industry_has_no_benchmark_row_leaves_the_universe(...) -> None:
    # seed con industry_damodaran = 'Software (System)' pero sin fila damodaran_industry
    ...
    assert result.no_coverage == ("NOBENCH",)


def test_company_whose_benchmark_has_null_wacc_leaves_the_universe(...) -> None:
    # seed con fila damodaran_industry cuyo wacc es NULL
    ...
    assert result.no_coverage == ("NULLWACC",)


def test_trap_detector_skip_is_eliminatory() -> None:
    # evaluate_company directo: benchmark con wacc None fuerza el skip del
    # roic_above_sector_wacc; el veredicto debe ser eliminación, no absolución.
    verdict = evaluate_company(company, benchmarks_sin_wacc, quality_gates=[], value_indicators=[], trap_detection=[RoicAboveSectorWacc()])
    assert not verdict.passed
    assert "roic_above_sector_wacc" in verdict.failed_gates
```

(Adaptar nombres de helpers a los que ya existen en el archivo; el test de skip usa `bot.screener.rules.RoicAboveSectorWacc` y un `CompanyData` mínimo con `roic=0.10`.)

Run: FAIL las cuatro.

- [ ] **Step 2: Implementar en el engine**

1. `ScreenResult`:

```python
    preset: str
    shortlist: tuple[ScreenedCompany, ...]
    screened: int
    no_coverage: tuple[str, ...] = ()
    """Tickers excluidos del universo por falta de benchmark sectorial usable
    (ADR 0006): sin ``industry_damodaran``, sin fila Damodaran, o WACC NULL."""
```

2. En `run_screen`, dentro del loop, después de resolver `benchmarks` del cache y **antes** de `evaluate_company`:

```python
        if benchmarks is None or benchmarks.wacc is None:
            no_coverage.append(row.ticker)
            continue
        screened += 1
```

(mover el `screened += 1` acá; inicializar `no_coverage: list[str] = []` arriba; pasar `no_coverage=tuple(sorted(no_coverage))` al `ScreenResult`). El snapshot `build_company_data` puede seguir construyéndose antes (necesita `company.industry` para el cache key) — solo la evaluación queda detrás de la compuerta.

3. En `evaluate_company`, el loop de traps pierde la absolución:

```python
    for detector in trap_detection:
        result = detector.evaluate(company, bench)
        if result.passed:
            passed_gates.append(detector.name)
        else:
            # ADR 0006: un trap que no puede evaluarse (skip) también elimina —
            # sin veredicto no hay candidato.
            failed_gates.append(detector.name)
            passed = False
```

4. En `_quality_metric`, ya no hay camino con `wacc` None para sobrevivientes; dejar la aritmética como está (los defaults quedan solo para empresas que igual serán eliminadas) pero actualizar el docstring: "tras la compuerta de cobertura, todo sobreviviente tiene ROIC y WACC sectorial reales".

- [ ] **Step 3: Reporte con la cobertura visible**

En `render_markdown`, cambiar la línea de resumen:

```python
        f"Generated: {stamp}  ·  Screened {result.screened} companies  ·  "
        f"Shortlist {len(result.shortlist)}  ·  "
        f"Excluded (no sector benchmark, ADR 0006): {len(result.no_coverage)}",
```

Test en `tests/unit/test_reporting_screen.py`: un `ScreenResult` con `no_coverage=("AAA", "BBB")` renderiza `Excluded (no sector benchmark, ADR 0006): 2`.

- [ ] **Step 4: Reparar tests existentes que asuman la absolución**

`uv run pytest -q` va a marcar los tests del engine que seedean empresas sin benchmark y esperaban que pasaran. Cada uno se arregla agregando la fila `damodaran_industry` con `wacc` real al seed — no relajando la compuerta. Revisar también `tests/integration/test_screen_cli.py`.

- [ ] **Step 5: Suite completa + commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src` → verde.

```bash
git add src/bot/screener/engine.py src/bot/reporting/screen_report.py tests/
git commit -m "feat(screener): coverage gate per ADR 0006 — no benchmark, no candidate, and the loss is reported"
```

---

### Task 6: `failed_gates` responde su pregunta — persistir a los eliminados

Hoy solo se materializan las sobrevivientes, así que `screener_candidates.failed_gates` jamás contiene un gate: la tabla no puede responder "¿por qué se cayó X?".

**Files:**
- Modify: `src/bot/storage/schema.sql` (`screener_candidates`: `rank` nullable, columna `passed`)
- Modify: `src/bot/screener/engine.py` (`ScreenResult.rejected`)
- Modify: `src/bot/screener/persist.py`
- Test: `tests/unit/test_screener_persist.py`, `tests/unit/test_screener_engine.py`

**Interfaces:**
- Produces: `RejectedCompany` (dataclass frozen: `ticker: str`, `failed_gates: tuple[str, ...]`) en `engine.py`; `ScreenResult.rejected: tuple[RejectedCompany, ...] = ()`. Los excluidos por cobertura entran a `rejected` con `failed_gates=("coverage_gate",)`. `persist_candidates` escribe sobrevivientes con `passed=TRUE` y rank 1..N, y rechazados con `passed=FALSE`, `rank NULL`, scores NULL.
- Consumes: `ScreenResult.no_coverage` de Task 5.

- [ ] **Step 1: Schema**

En `schema.sql`, en `screener_candidates`: `rank INTEGER NOT NULL` → `rank INTEGER`, y agregar `passed BOOLEAN NOT NULL DEFAULT TRUE,` antes de `created_at`. (No hay DB de producción todavía — `datos-reales` en la auditoría — así que no hace falta migración; la Task 13 crea la base desde cero.)

- [ ] **Step 2: Test rojo — el engine expone a los rechazados**

```python
def test_screen_result_carries_rejected_companies_with_their_failed_gates(...) -> None:
    # seed: una empresa que pasa todo y una que tripea un gate (p.ej. market cap ínfimo)
    result = run_screen(conn, config, valuator=None)
    rejected = {r.ticker: r.failed_gates for r in result.rejected}
    assert "TINY" in rejected
    assert any("market_cap" in g for g in rejected["TINY"])


def test_no_coverage_companies_appear_as_rejected_by_the_coverage_gate(...) -> None:
    result = run_screen(conn, config, valuator=None)
    rejected = {r.ticker: r.failed_gates for r in result.rejected}
    assert rejected["NOMAP"] == ("coverage_gate",)
```

- [ ] **Step 3: Implementar en el engine**

```python
@dataclass(frozen=True)
class RejectedCompany:
    """Una empresa que no sobrevivió el screen y por qué (spec §6, ADR 0006)."""

    ticker: str
    failed_gates: tuple[str, ...]
```

En `run_screen`: `rejected: list[RejectedCompany] = []`; en la rama de cobertura `rejected.append(RejectedCompany(row.ticker, ("coverage_gate",)))`; en `if not verdict.passed:` → `rejected.append(RejectedCompany(row.ticker, verdict.failed_gates))`; pasar `rejected=tuple(rejected)` al result (campo con default `()`).

- [ ] **Step 4: Test rojo + implementación en persist**

```python
def test_persist_writes_rejected_rows_with_passed_false() -> None:
    result = ScreenResult(
        preset="p",
        shortlist=(),
        screened=1,
        rejected=(RejectedCompany("BAD", ("min_market_cap",)),),
    )
    run_id = persist_candidates(conn, result)
    row = conn.execute(
        "SELECT passed, rank, failed_gates FROM screener_candidates WHERE run_id = ? AND ticker = 'BAD'",
        [run_id],
    ).fetchone()
    assert row == (False, None, ["min_market_cap"])
```

En `persist_candidates`, tras el loop de shortlist:

```python
    for company_rejected in result.rejected:
        conn.execute(
            "INSERT INTO screener_candidates "
            "(run_id, preset, ticker, rank, passed, failed_gates) "
            "VALUES (?, ?, ?, NULL, FALSE, ?)",
            [rid, result.preset, company_rejected.ticker, list(company_rejected.failed_gates)],
        )
```

y el INSERT de sobrevivientes gana la columna `passed` con `TRUE`.

- [ ] **Step 5: Suite + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests` → verde. Revisar que `analyze --from-screen` (Task 10, aún no existe) y cualquier SELECT existente sobre `screener_candidates` filtre `passed = TRUE` — hoy el único lector es el propio test suite.

```bash
git add src/bot/storage/schema.sql src/bot/screener/engine.py src/bot/screener/persist.py tests/
git commit -m "feat(screener): persist rejected companies so failed_gates can answer why a ticker fell"
```

---

## Fase 3 — El valuador conectado al story type

### Task 7: `age_years` deja de ser un parámetro fantasma

`age_years` está en la firma de `analyze` y nadie lo pasa: toda empresa se considera joven y la regla de edad del clasificador jamás descarta un high-growth. FMP publica `ipoDate` en el profile; se captura, se guarda, y `analyze` deriva la edad.

**Files:**
- Modify: `src/bot/storage/schema.sql` (`companies.ipo_date DATE`)
- Modify: `src/bot/ingest/fmp.py` (`CompanyInfo`, `lookup_company`, `_company_row`)
- Modify: `src/bot/valuator/analysis.py` (`_CompanyRow`, `_load_company`, `analyze`)
- Test: `tests/unit/test_fmp_parser.py`, `tests/unit/test_reporting_analysis.py` o el test unit del analyze

**Interfaces:**
- Produces: `companies.ipo_date` poblada por el importer de FMP; `analyze(..., age_years=None)` deriva la edad de `ipo_date` cuando el caller no la pasa. La firma no cambia.
- Consumes: el merge-upsert de Task 3 (una pasada posterior de SEC no borra `ipo_date`).

- [ ] **Step 1: Schema + captura en FMP (test rojo primero)**

Test en `tests/unit/test_fmp_parser.py`: un profile con `"ipoDate": "1980-12-12"` produce `CompanyInfo.ipo_date == date(1980, 12, 12)` y `_company_row` incluye `"ipo_date"`. Implementación:

- `schema.sql`: agregar `ipo_date        DATE,` a `companies` (después de `status`).
- `CompanyInfo`: campo `ipo_date: date | None`.
- `lookup_company`: parsear con el patrón del módulo:

```python
            ipo_date=_date_or_none(profile.get("ipoDate")),
```

con el helper (junto a `_str_or_none`):

```python
def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
```

- `_company_row`: agregar `"ipo_date": info.ipo_date,` (y `None` en la rama sin profile).

- [ ] **Step 2: Derivar la edad en `analyze` (test rojo primero)**

Test: seed una empresa con `ipo_date` de hace 40 años, revenue history con CAGR 20% → el story type NO es `high-growth` (la edad la descarta); misma empresa con `ipo_date` hace 5 años → sí. Implementación en `analysis.py`:

- `_CompanyRow` gana `ipo_date: date | None`; `_load_company` lo selecciona (`SELECT name, country, currency, industry_damodaran, ipo_date ...`).
- En `analyze`, antes de construir `ClassificationFinancials`:

```python
    from datetime import date as _date  # arriba: from datetime import date

    if age_years is None and company_row.ipo_date is not None:
        age_years = max(0, (_date.today() - company_row.ipo_date).days // 365)
```

- [ ] **Step 3: Suite + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests` → verde.

```bash
git add src/bot/storage/schema.sql src/bot/ingest/fmp.py src/bot/valuator/analysis.py tests/
git commit -m "feat(valuator): wire age_years from FMP ipoDate so the age rule can actually fire"
```

---

### Task 8: El story type cambia la proyección (versión mínima)

El hallazgo más grande de la auditoría: la clasificación se calcula bien y después solo se guarda la etiqueta. Versión mínima acordada: ramificar **crecimiento** y **margen** para `high-growth` y `cyclical`; `mature-stable` y `mature-decline` conservan la resolución actual (histórico/sector); `distressed` queda documentado como pendiente (necesita Altman Z).

| Arquetipo | Crecimiento (path 5 años) | Margen operativo (path 5 años) |
|---|---|---|
| high-growth | fade lineal: promedio histórico → PBI nominal | ramp lineal: margen propio actual → mediana sectorial |
| cyclical | promedio histórico (ya promedia el ciclo) — sin cambio | promedio del propio ciclo (media de la historia de márgenes) |
| mature-stable / mature-decline | histórico plano — sin cambio | mediana sectorial plana — sin cambio |
| distressed | sin cambio (pendiente Altman Z) | sin cambio |

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (fuente `STORY_PATTERN`, `AssumptionInputs`, `load_assumption_inputs`, `Assumptions.operating_margin` como path, `resolve_assumptions`, `_resolve_revenue_growth`, `_resolve_operating_margin` nuevo, `to_dcf_assumptions`)
- Modify: `src/bot/valuator/analysis.py` (pasar el story type efectivo — ver Step 4)
- Modify: `src/bot/reporting/analysis_report.py` + template (mostrar el path de margen como `13.0% → 18.5%`)
- Test: `tests/unit/test_valuator_assumptions.py`, `tests/unit/test_reporting_analysis.py`

**Interfaces:**
- Produces:
  - `AssumptionSource.STORY_PATTERN = "story_pattern"` (nuevo miembro, emitido por los dos resolvers ramificados — actualizar el test de miembros-alcanzables que fijó la Task 2.4 del plan de remediación).
  - `AssumptionInputs` gana `company_operating_margin: float | None = None` y `operating_margin_history: tuple[float, ...] = ()`.
  - `Assumptions.operating_margin: Sourced[tuple[float, ...] | None]` (antes escalar). `to_dcf_assumptions` alinea el largo del path de margen al de crecimiento (padding con el último valor).
  - `resolve_assumptions` resuelve el story type efectivo **antes** de resolver crecimiento/margen y ramifica con él.
- Consumes: `StoryType` (existente), `gdp_nominal` (existente).

- [ ] **Step 1: Tests rojos — el contrato de la tabla de arriba**

En `tests/unit/test_valuator_assumptions.py` (usar los helpers de seed del archivo):

```python
def test_high_growth_revenue_path_fades_from_history_to_gdp(...) -> None:
    # historia con crecimiento promedio 30%, gdp_nominal 4%, clasificada high-growth
    a = resolve_assumptions("T", conn, gdp_nominal=0.04, auto_story_type=StoryType.HIGH_GROWTH)
    path = a.revenue_growth.value
    assert a.revenue_growth.source == AssumptionSource.STORY_PATTERN
    assert path[0] == pytest.approx(0.30, abs=0.01)
    assert path[-1] == pytest.approx(0.04, abs=1e-9)
    assert all(a >= b for a, b in itertools.pairwise(path))  # monótono descendente


def test_high_growth_margin_ramps_from_company_to_sector(...) -> None:
    # margen propio 8%, mediana sectorial 20%
    a = resolve_assumptions("T", conn, auto_story_type=StoryType.HIGH_GROWTH)
    path = a.operating_margin.value
    assert a.operating_margin.source == AssumptionSource.STORY_PATTERN
    assert path[0] == pytest.approx(0.08, abs=1e-9)
    assert path[-1] == pytest.approx(0.20, abs=1e-9)


def test_cyclical_margin_averages_the_cycle_not_the_current_year(...) -> None:
    # historia de márgenes [0.02, 0.18, 0.04, 0.16] -> media 0.10; año actual 0.16
    a = resolve_assumptions("T", conn, auto_story_type=StoryType.CYCLICAL)
    assert a.operating_margin.value == (pytest.approx(0.10),) * 5
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE


def test_mature_stable_keeps_sector_margin_and_historical_growth(...) -> None:
    a = resolve_assumptions("T", conn, auto_story_type=StoryType.MATURE_STABLE)
    assert a.operating_margin.source == AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    assert a.revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE


def test_manual_override_beats_the_story_pattern(...) -> None:
    # override YAML con operating_margin: 0.25 y story_type high-growth
    assert a.operating_margin.value == (0.25,) * 5
    assert a.operating_margin.source == AssumptionSource.MANUAL
```

Run: FAIL.

- [ ] **Step 2: Inputs nuevos y tipo del margen**

1. `AssumptionInputs` gana los dos campos (defaults arriba). En `load_assumption_inputs`, una consulta más:

```python
    margin_rows = conn.execute(
        "SELECT ebit, revenue FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    margins = tuple(
        float(e) / float(r) for e, r in margin_rows if e is not None and r is not None and r != 0.0
    )
```

con `operating_margin_history=margins` y `company_operating_margin=margins[-1] if margins else None`.

2. `Assumptions.operating_margin: Sourced[tuple[float, ...] | None]`. En `to_dcf_assumptions`:

```python
        growth = _require(self.revenue_growth, "revenue_growth")
        margin_path = _require(self.operating_margin, "operating_margin")
        if len(margin_path) < len(growth):
            margin_path = margin_path + (margin_path[-1],) * (len(growth) - len(margin_path))
        return DCFAssumptions(
            revenue_growth=growth,
            operating_margin=margin_path[: len(growth)],
            ...
        )
```

3. Nuevo miembro del enum:

```python
    #: El valor sale del patrón de proyección del arquetipo (spec §7.1): un path
    #: derivado de datos de la empresa y del sector, no un escalar copiado.
    STORY_PATTERN = "story_pattern"
```

- [ ] **Step 3: Los resolvers ramificados**

En `resolve_assumptions`, resolver el story efectivo primero y ramificar:

```python
    story = _resolve_story_type(override, auto_story_type)
    story_type = StoryType(story) if story in {s.value for s in StoryType} else None

    revenue_growth = _resolve_revenue_growth(
        db_inputs.historical_growth_path, override, gdp_nominal, story_type=story_type
    )
    operating_margin = _resolve_operating_margin(
        override,
        sector,
        story_type=story_type,
        company_margin=db_inputs.company_operating_margin,
        margin_history=db_inputs.operating_margin_history,
    )
```

`_resolve_revenue_growth` gana la rama:

```python
def _linear_path(start: float, end: float, n: int = _HORIZON) -> tuple[float, ...]:
    """Interpolación lineal inclusiva de ``start`` a ``end`` en ``n`` pasos."""
    if n == 1:
        return (end,)
    step = (end - start) / (n - 1)
    return tuple(start + step * i for i in range(n))
```

```python
    # (dentro de _resolve_revenue_growth, tras el override manual)
    if story_type is StoryType.HIGH_GROWTH and historical is not None:
        # §7.1: crecimiento rápido decayendo hacia la economía — fade lineal del
        # promedio histórico al PBI nominal sobre el horizonte explícito.
        return Sourced(
            value=_linear_path(historical[0], gdp_nominal),
            source=AssumptionSource.STORY_PATTERN,
        )
```

Nuevo `_resolve_operating_margin` (reemplaza el `_resolve_sector_scalar` para esta clave; las otras tres claves siguen usando `_resolve_sector_scalar` sin cambios):

```python
def _resolve_operating_margin(
    override: dict[str, Any],
    sector: _SectorDefaults,
    *,
    story_type: StoryType | None,
    company_margin: float | None,
    margin_history: tuple[float, ...],
) -> Sourced[tuple[float, ...] | None]:
    """Margen operativo como *path*, ramificado por arquetipo (spec §7.1).

    high-growth: ramp lineal del margen propio actual a la mediana sectorial —
    la mejora de márgenes es la mitad de la historia de un high-growth.
    cyclical: la media del propio ciclo, no el año actual.
    Resto: mediana sectorial plana (el comportamiento previo).
    Un override manual (escalar o lista) siempre gana.
    """
    manual = _override_path_field(override, "operating_margin")
    if manual is not None:
        return manual
    sector_margin = sector.row.op_margin if sector.row is not None else None
    if (
        story_type is StoryType.HIGH_GROWTH
        and company_margin is not None
        and sector_margin is not None
    ):
        return Sourced(
            value=_linear_path(company_margin, sector_margin),
            source=AssumptionSource.STORY_PATTERN,
        )
    if story_type is StoryType.CYCLICAL and len(margin_history) >= 4:
        cycle_avg = sum(margin_history) / len(margin_history)
        return Sourced(
            value=(cycle_avg,) * _HORIZON, source=AssumptionSource.HISTORICAL_AVERAGE
        )
    if sector_margin is None:
        return Sourced(value=None, source=AssumptionSource.UNRESOLVED)
    return Sourced(value=(sector_margin,) * _HORIZON, source=sector.source)
```

- [ ] **Step 4: Propagar el tipo nuevo**

`uv run mypy src` marca cada consumidor de `assumptions.operating_margin` que asuma escalar. Conocidos:

- `analysis.py`: el comentario sobre `company_operating_margin` sigue válido (sigue usando el margen realizado, no el assumption) — sin cambio de lógica.
- `reporting/analysis_report.py` + template: donde se renderiza el margen, mostrar `path[0]` si el path es constante, y `"{path[0]:.1%} → {path[-1]:.1%}"` si varía. Test en `test_reporting_analysis.py`.
- `sensitivity.py`: perturba `DCFAssumptions.operating_margin` (ya es tuple) — sin cambio.

- [ ] **Step 5: Suite completa + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests` → verde. El test de miembros-alcanzables del enum suma `"story_pattern"` a su conjunto esperado.

```bash
git add src/bot/valuator/ src/bot/reporting/ tests/
git commit -m "feat(valuator): story type drives the projection — growth fade and margin paths for high-growth and cyclical"
```

---

### Task 9: Overrides por convención, y el screener los respeta

El help del CLI ya promete `config/assumptions/<TICKER>.yaml`; el directorio no existe y solo `--override` con ruta explícita funciona. Además el camino del screener (segundo pase DCF) nunca pasa overrides, así que `bot screen` y `bot analyze` pueden dar números distintos para el mismo ticker.

**Files:**
- Modify: `src/bot/config.py` (`assumptions_dir`)
- Modify: `src/bot/cli.py` (`analyze`, `screen`)
- Modify: `src/bot/screener/engine.py` (`run_screen`, `_batch_dcf_margins`)
- Create: `config/assumptions/README.md`, `config/assumptions/_EXAMPLE.yaml.example`
- Test: `tests/unit/test_cli_analyze.py`, `tests/unit/test_screener_engine.py`

**Interfaces:**
- Produces: `Settings.assumptions_dir: Path = Path("./config/assumptions")`; `analyze` sin `--override` busca `<assumptions_dir>/<TICKER>.yaml`; `run_screen(..., assumptions_dir: Path | None = None)` propaga el mismo directorio al valuador batcheado.
- Consumes: `_load_override` (existente — ya trata ruta inexistente como "sin overrides").

- [ ] **Step 1: Test rojo — analyze descubre el override por convención**

En `tests/unit/test_cli_analyze.py` (patrón del archivo: DB seedeada + `CliRunner` + `BOT_*` env):

```python
def test_analyze_picks_up_config_assumptions_by_convention(tmp_path, ...) -> None:
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text("notes: convention override\n")
    # env: BOT_ASSUMPTIONS_DIR=str(assumptions_dir)
    result = runner.invoke(app, ["analyze", "AAPL"], env=...)
    assert result.exit_code == 0
    report = (reports_dir / ... / "AAPL.md").read_text()
    assert "convention override" in report
```

- [ ] **Step 2: Implementar**

1. `config.py`:

```python
    assumptions_dir: Path = Field(
        default=Path("./config/assumptions"),
        description="Directorio de overrides por convención: <TICKER>.yaml (spec §7.6).",
    )
```

2. `cli.analyze`, antes de `run_analysis`:

```python
    if override is None:
        conventional = settings.assumptions_dir / f"{ticker}.yaml"
        if conventional.exists():
            override = conventional
```

3. `engine.run_screen` gana `assumptions_dir: Path | None = None` y lo pasa a `_batch_dcf_margins(conn, shortlist_tickers, assumptions_dir)`; dentro:

```python
        override_path = None
        if assumptions_dir is not None:
            candidate_path = assumptions_dir / f"{ticker}.yaml"
            if candidate_path.exists():
                override_path = candidate_path
        analysis = analyze(ticker, conn, override_path=override_path, company=inputs)
```

4. `cli.screen`: `run_screen(conn, screener_config, top=top, assumptions_dir=settings.assumptions_dir)`.

5. `config/assumptions/README.md` (dos líneas: qué es, que `_EXAMPLE.yaml.example` lista las claves) y `_EXAMPLE.yaml.example` con las 13 claves de `_OVERRIDE_KEYS` comentadas con una línea cada una y un ejemplo activo:

```yaml
# Copiá este archivo a <TICKER>.yaml (p.ej. AAPL.yaml) y descomentá lo que quieras fijar.
# revenue_growth: [0.12, 0.10, 0.08, 0.06, 0.04]   # path anual, o escalar que se repite
# operating_margin: 0.22
# sales_to_capital: 2.5
# terminal_growth: 0.03
# cost_of_equity: 0.09
# pretax_cost_of_debt: 0.05
# equity_weight: 0.85                                # debt_weight se deriva
# tax_rate: 0.21
# probability_of_bankruptcy: 0.15
# distress_value_per_share: 4.0
# story_type: high-growth                            # high-growth | mature-stable | mature-decline | cyclical | distressed
notes: ejemplo — borrá esta línea
```

- [ ] **Step 3: Test del lado screener + suite + commit**

Test en `test_screener_engine.py`: con `assumptions_dir` apuntando a un dir con `<TICKER>.yaml` que fija `operating_margin`, el `margin_of_safety` del shortlist cambia respecto de la corrida sin dir (inyectar seeds deterministas).

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests` → verde.

```bash
git add src/bot/config.py src/bot/cli.py src/bot/screener/engine.py config/assumptions/ tests/
git commit -m "feat(assumptions): convention-based overrides in config/assumptions, honoured by analyze and the screen second pass"
```

---

## Fase 4 — Conectar screen → analyze

### Task 10: `analyze` variádico + `--from-screen`

La conexión literal entre fases: analizar en un solo comando lo que el screener acaba de shortlistear.

**Files:**
- Modify: `src/bot/cli.py` (`analyze`)
- Test: `tests/unit/test_cli_analyze.py`

**Interfaces:**
- Produces: `bot analyze AAPL MSFT` (variádico); `bot analyze --from-screen` toma los tickers del último run persistido con `passed = TRUE`, en orden de rank. `--override` explícito solo es válido con exactamente un ticker (con varios, cada uno usa su override por convención).
- Consumes: `screener_candidates.passed` (Task 6), `assumptions_dir` (Task 9).

- [ ] **Step 1: Tests rojos**

```python
def test_analyze_accepts_multiple_tickers(...) -> None:
    result = runner.invoke(app, ["analyze", "AAPL", "MSFT"], env=...)
    assert result.exit_code == 0
    assert (out_dir / "AAPL.md").exists() and (out_dir / "MSFT.md").exists()


def test_analyze_from_screen_uses_the_latest_run(...) -> None:
    # persistir dos runs; el último con shortlist (MSFT rank 1, AAPL rank 2)
    result = runner.invoke(app, ["analyze", "--from-screen"], env=...)
    assert result.exit_code == 0
    assert result.output.index("MSFT") < result.output.index("AAPL")


def test_analyze_from_screen_without_runs_fails_clearly(...) -> None:
    result = runner.invoke(app, ["analyze", "--from-screen"], env=...)
    assert result.exit_code == 2
    assert "bot screen" in result.output


def test_analyze_explicit_override_with_many_tickers_is_rejected(...) -> None:
    result = runner.invoke(app, ["analyze", "AAPL", "MSFT", "--override", "x.yaml"], env=...)
    assert result.exit_code == 2
```

- [ ] **Step 2: Implementar**

Reescribir la firma de `analyze`:

```python
@app.command()
def analyze(
    tickers: list[str] = typer.Argument(  # noqa: B008
        None, help="Uno o más tickers (e.g. AAPL MSFT). Omitir con --from-screen."
    ),
    from_screen: bool = typer.Option(
        False, "--from-screen", help="Analizar la shortlist del último screen persistido."
    ),
    override: Path | None = typer.Option(  # noqa: B008
        None, "--override", help="Override YAML explícito (solo con un único ticker)."
    ),
) -> None:
```

Cuerpo: validar la combinación (`--from-screen` con tickers → error 2; sin tickers y sin flag → error 2; `--override` con len(tickers) != 1 → error 2). Con `--from-screen`:

```python
        rows = conn.execute(
            "SELECT ticker FROM screener_candidates "
            "WHERE passed AND run_id = ("
            "  SELECT run_id FROM screener_candidates ORDER BY created_at DESC LIMIT 1"
            ") ORDER BY rank"
        ).fetchall()
        if not rows:
            typer.echo("No hay ningún screen persistido — corré `bot screen` primero.", err=True)
            raise typer.Exit(code=2)
        tickers = [str(r[0]) for r in rows]
```

Extraer el cuerpo actual (analizar + escribir MD/HTML + echo del MoS) a un helper `_analyze_one(conn, settings, ticker, override) -> int` que devuelve un exit code por ticker (mapeando `LookupError` → 2, `ValueError` → 1 como hoy, pero **sin abortar el batch**: imprimir el error y seguir). El comando sale con el peor código.

- [ ] **Step 3: Suite + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests` → verde (los tests viejos de `analyze` single-ticker deben seguir pasando con la firma variádica).

```bash
git add src/bot/cli.py tests/unit/test_cli_analyze.py
git commit -m "feat(cli): analyze takes many tickers and --from-screen closes the screen->analyze loop"
```

---

## Fase 5 — Operación y verificación de punta a punta

### Task 11: `bot doctor` honesto

Dos mentiras: reporta la API key de FMP faltante y sale con código 0 (la key es requerida por `Settings`, pero un `BOT_FMP_API_KEY=""` vacío pasa la validación y revienta recién en el refresh); y da por bueno un esquema con 8 tablas cuando `schema.sql` define 15.

**Files:**
- Modify: `src/bot/cli.py` (`doctor`)
- Test: `tests/unit/test_cli_doctor.py`

- [ ] **Step 1: Tests rojos**

```python
def test_doctor_fails_when_fmp_key_is_blank(...) -> None:
    result = runner.invoke(app, ["doctor"], env={..., "BOT_FMP_API_KEY": ""})
    assert result.exit_code == 1
    assert "FMP" in result.output


def test_doctor_expects_the_full_schema(...) -> None:
    # DB con el esquema aplicado -> OK y el output menciona el conteo real
    result = runner.invoke(app, ["doctor"], env=...)
    assert result.exit_code == 0
```

- [ ] **Step 2: Implementar**

En `doctor`: tras imprimir el estado de la key, agregar `if not settings.fmp_api_key.strip(): issues.append("FMP API key vacía — refresh --fmp no puede funcionar (BOT_FMP_API_KEY).")`. Para el esquema, derivar el número esperado del propio schema en vez de otra constante mágica:

```python
        expected_tables = _schema_table_count()
        if tables < expected_tables:
            issues.append(
                f"DB has {tables} tables, schema defines {expected_tables} — schema incomplete."
            )
```

con el helper en `storage/db.py` (junto a `apply_schema`, que ya sabe leer `schema.sql`):

```python
def schema_table_count() -> int:
    """Cantidad de tablas que define ``schema.sql`` (para chequeos de salud)."""
    return _SCHEMA_SQL.count("CREATE TABLE IF NOT EXISTS")
```

(usar la variable/carga del SQL que ese módulo ya tenga; si lee el archivo on-demand, contar sobre esa lectura).

- [ ] **Step 3: Suite + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests` → verde.

```bash
git add src/bot/cli.py src/bot/storage/db.py tests/unit/test_cli_doctor.py
git commit -m "fix(cli): doctor exits non-zero on a blank FMP key and checks the real table count"
```

---

### Task 12: El test de punta a punta (spec §12)

El único test que fuerza a refresh, screen y analyze a compartir una base — el que habría descubierto la mitad de la auditoría. Sin red: Damodaran desde los fixtures existentes, fundamentals/precios sembrados vía los importers con payloads fabricados (patrón de `tests/integration/test_fmp_import.py`).

**Files:**
- Create: `tests/e2e/__init__.py`, `tests/e2e/test_pipeline.py`

**Interfaces:**
- Consumes: `import_damodaran` (con fixtures de `tests/fixtures/damodaran/` vía el patrón de descarga parcheada de `test_damodaran_import.py`), `import_company_from_fmp` (con `FmpClient` fake del patrón de `test_fmp_import.py`), CLI `screen` y `analyze` vía `CliRunner` con `BOT_DB_PATH` apuntando a la DB compartida.

- [ ] **Step 1: Escribir el test (rojo si algo de las tareas previas quedó mal cableado)**

`tests/e2e/test_pipeline.py`, un solo test largo y lineal — el punto es la cadena, no la unidad:

```python
"""E2E (spec §12): refresh -> screen -> analyze sobre UNA base compartida, sin red.

Siembra Damodaran desde fixtures y dos empresas US vía el importer de FMP con un
cliente fake; después ejercita los comandos reales del CLI contra esa DB y
verifica que el screen shortlistea, que --from-screen analiza, y que los
artefactos §6.1/§7.7 quedan escritos con números adentro.
"""


def test_pipeline_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports = tmp_path / "reports"
    env = {
        "BOT_DB_PATH": str(db_path),
        "BOT_REPORTS_DIR": str(reports),
        "BOT_SEC_USER_AGENT": "test test@example.com",
        "BOT_FMP_API_KEY": "test-key",
        "BOT_PRESETS_DIR": "config/presets",
    }
    conn = connect(db_path)
    apply_schema(conn)

    # 1. Capa A: Damodaran desde fixtures (patrón de test_damodaran_import) +
    #    dos empresas: una que debe sobrevivir el screen, una que debe caer.
    _seed_damodaran_from_fixtures(conn)
    _seed_company_via_fmp_importer(conn, ticker="GOODCO", ...)   # sólida y barata
    _seed_company_via_fmp_importer(conn, ticker="TRAPCO", ...)   # margen colapsando
    conn.close()

    # 2. Capa B por el CLI real.
    result = runner.invoke(app, ["screen", "--preset", "damodaran_value"], env=env)
    assert result.exit_code == 0, result.output
    screen_md = next((reports).rglob("screen/damodaran_value.md")).read_text()
    assert "GOODCO" in screen_md
    assert "TRAPCO" not in screen_md
    assert "Excluded (no sector benchmark" in screen_md

    # 3. La conexión de fases: analyze --from-screen sobre la misma DB.
    result = runner.invoke(app, ["analyze", "--from-screen"], env=env)
    assert result.exit_code == 0, result.output
    analysis_md = next((reports).rglob("analysis/GOODCO.md")).read_text()
    assert "margin of safety" in analysis_md.lower() or "Intrinsic" in result.output

    # 4. La DB compartida quedó con la historia completa.
    conn = connect(db_path)
    assert conn.execute("SELECT count(*) FROM screener_candidates WHERE passed").fetchone()[0] >= 1
    assert conn.execute("SELECT count(*) FROM screener_candidates WHERE NOT passed").fetchone()[0] >= 1
    assert conn.execute("SELECT count(*) FROM refresh_log").fetchone()[0] >= 1
```

Los helpers `_seed_*` copian el patrón de los tests de integración existentes (leer esos archivos antes de escribirlos); los datos de `GOODCO`/`TRAPCO` se fabrican para que el preset `damodaran_value` los admita/rechace de forma determinista (GOODCO: ROIC > WACC sectorial, FCF yield > 8%, márgenes estables; TRAPCO: margen contrayéndose > 200bps).

- [ ] **Step 2: Verde + registrar en pyproject si hace falta**

Run: `uv run pytest tests/e2e/ -v` → PASS. Si `pytest` no descubre `tests/e2e/` (revisar `[tool.pytest.ini_options] testpaths` en `pyproject.toml`), agregarlo.

- [ ] **Step 3: Suite completa + commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src` → verde.

```bash
git add tests/e2e/ pyproject.toml
git commit -m "test(e2e): the spec §12 pipeline test — refresh, screen and analyze share one database"
```

---

### Task 13: La corrida real

Los 676+ tests corren sobre fixtures. Esta tarea ejecuta el bot contra la red de verdad, arregla lo que se rompa (que algo se va a romper: `download` de Damodaran jamás se ejerció sin parchear), y deja el quickstart documentado. **Esta tarea es interactiva: necesita el `.env` del usuario con su API key de FMP y su User-Agent de SEC.**

**Files:**
- Create: `.env.example`
- Modify: `README.md` (sección Quickstart)
- Fixes que surjan: probablemente `src/bot/ingest/damodaran.py` (formato real de los .xls de Stern)

- [ ] **Step 1: `.env.example` y verificación del entorno**

```bash
cat > .env.example <<'EOF'
# Copiá a .env y completá. Settings: src/bot/config.py (prefijo BOT_).
BOT_SEC_USER_AGENT="Nombre Apellido email@example.com"
BOT_FMP_API_KEY=""
# BOT_DB_PATH=./bot.duckdb
# BOT_REPORTS_DIR=./reports
EOF
git add .env.example && git commit -m "docs: add .env.example for the real-data quickstart"
```

Pedirle al usuario que cree `.env` (si no existe) y correr `uv run bot doctor` → debe salir 0.

- [ ] **Step 2: Damodaran contra la red real**

Run: `uv run bot refresh --damodaran`
Expected: `OK — imported N rows` con N ≈ 90+ industrias + ~150 países. Si el parser falla contra los archivos reales de Stern (primer contacto real): aplicar la skill superpowers:systematic-debugging, arreglar el parser con un test nuevo que fije el caso real (guardar el archivo descargado como fixture), y commitear como `fix(damodaran): ...`. Verificar después:

```bash
uv run python -c "
import duckdb; c = duckdb.connect('bot.duckdb')
print(c.execute('SELECT count(*), count(wacc) FROM damodaran_industry').fetchone())
print(c.execute('SELECT count(*) FROM damodaran_country').fetchone())"
```

`count(wacc)` debe ser cercano a `count(*)` — un WACC mayormente NULL dejaría a todo el universo fuera por la coverage gate.

- [ ] **Step 3: Primer lote del universo (tier gratis)**

Run: `uv run bot refresh --fmp --limit 30 && uv run bot refresh --prices --limit 30`
Expected: `SUCCESS — 30 tickers: ~30 imported ...`; si aparece `deferred`, es el rate limit actuando como se diseñó en Task 2 — anotar cuántos entraron. Verificar el mapeo sectorial: 

```bash
uv run python -c "
import duckdb; c = duckdb.connect('bot.duckdb')
print(c.execute('SELECT count(*), count(industry_damodaran), count(ipo_date) FROM companies').fetchone())"
```

`count(industry_damodaran)` ≈ `count(*)` (el mapping cubre 89/94 industrias). Si una industria de FMP queda sin mapear, agregar la fila al CSV de mapping y commitearla.

- [ ] **Step 4: screen + analyze reales**

Run: `uv run bot screen --preset damodaran_value --top 10`
Expected: exit 0, el reporte en `reports/<hoy>/screen/damodaran_value.md` con shortlist no vacía (o vacía con la línea de cobertura explicando cuántas quedaron fuera — con 30 tickers cargados es posible; en ese caso cargar otro lote mañana). Después:

Run: `uv run bot analyze --from-screen`
Expected: exit 0, un `<TICKER>.md` + `.html` por candidato, con MoS impreso. Abrir un HTML y verificar el tornado.

Cada falla real de esta etapa se trata como bug nuevo: diagnóstico, test que lo fija, fix, commit. No parchear a mano la DB.

- [ ] **Step 5: Quickstart en el README + commit**

Agregar al `README.md` la sección:

```markdown
## Quickstart (US-only, FMP tier gratis)

1. `cp .env.example .env` y completá tu User-Agent de SEC y tu API key de FMP.
2. `uv run bot doctor` — todo OK antes de seguir.
3. `uv run bot refresh --damodaran` — benchmarks sectoriales de EE.UU. (una vez al año alcanza).
4. `uv run bot refresh --fmp --limit 30 && uv run bot refresh --prices --limit 30` — carga ~30
   tickers del S&P 500 por día (límite del tier gratis: ~250 requests/día). La carga completa
   del universo toma ~2 semanas de corridas diarias; el refresh es incremental y retoma solo.
5. `uv run bot screen --preset damodaran_value --top 10` — la shortlist mecánica (§6).
6. `uv run bot analyze --from-screen` — el DCF y el reporte §7.7 de cada candidata.
```

```bash
git add README.md
git commit -m "docs: real-data quickstart for the US-only free-tier setup"
```

---

### Task 14: Cerrar la documentación — ADRs y los dos planos

CONTEXT.md lo exige: si una etapa implementa una ADR, decilo en la ADR; y los dos planos se actualizan al terminar una etapa (el de estado, contra el código, no contra el spec).

**Files:**
- Modify: `docs/adr/0006-unmeasurable-companies-leave-the-universe.md` — Status: `Accepted (2026-08-11). Implemented (<fecha>, coverage gate en screener/engine.py).`
- Modify: `docs/adr/0005-currency-handling-and-valuation-currency.md` — agregar al Status una nota: sigue `Accepted` y **no implementada**; bajo el alcance US-only actual (universo S&P 500, cotización = reporte = USD) sus consecuencias no se manifiestan, y se vuelve bloqueante recién al reabrir M2 global.
- Modify: `CONTEXT.md` — actualizar "Active plan" a este plan; una línea en la intro: "Versión actual: US-only (S&P 500)".
- Modify: `docs/plano/estado.py` — re-auditar los ítems tocados por este plan **contra el código en HEAD** (no contra este documento): `universo`, `sec-import`, `da-regiones`, `coverage-gate`, `trap-roic`, `failed-gates`, `story-uso`, `story-edad`, `overrides`, `cli-falta` (parcial), `doctor`, `e2e`, `datos-reales`, `adr-0006`, y los `BLOQUES` y `BRECHAS` afectados. Actualizar `AUDITADO_EN`/`AUDITADO_EL`. Regenerar y verificar con los builders del directorio (`docs/plano/README.md` documenta el comando; `build.py` falla solo si la arquitectura divergió).

- [ ] **Step 1: Editar los cuatro archivos según lo de arriba**
- [ ] **Step 2: Regenerar los planos y verificar que `build.py` no proteste**
- [ ] **Step 3: Commit**

```bash
git add docs/adr/ CONTEXT.md docs/plano/
git commit -m "docs: ADR 0006 implemented, ADR 0005 scoped out under US-only, estado re-audited"
```

---

## Self-Review

- **Cobertura del objetivo:** refresh real (T1, T2, T4, T13) → screen honesto (T5, T6) → analyze conectado (T7, T8, T9) → cadena screen→analyze (T10) → verificación (T11, T12, T13) → docs (T14). Los muertos de la auditoría dentro del alcance quedan todos con tarea; los fuera de alcance están listados explícitamente arriba.
- **Consistencia de tipos:** `ScreenResult.no_coverage`/`rejected` con defaults `()` (T5/T6 no rompen constructores previos); `Assumptions.operating_margin` cambia a path en T8 y sus consumidores están enumerados; `resolve_assumptions` mantiene la firma pública (los params nuevos van por `AssumptionInputs`).
- **Orden de dependencias:** T3 antes de T7 (el merge preserva `ipo_date`); T5 antes de T6 (`no_coverage`); T6 antes de T10 (`passed`); T9 antes de T10 (override por convención en batch); T12 después de todo lo funcional; T13 después de T12.
