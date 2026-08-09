# Remediación investment-bot: wiring, limpieza y bugs bloqueantes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar el código que ya existe y funciona pero nadie invoca, borrar el código inerte, y arreglar los bugs que contaminan la lectura del sistema — para que el estado real del bot sea legible sin auditoría.

**Architecture:** Tres fases secuenciales sobre una base mergeada. Fase 1 sólo cablea módulos existentes (cero lógica nueva de negocio). Fase 2 borra campos y reglas sin fuente de datos. Fase 3 arregla bugs que producen números o etiquetas falsas. Cada tarea es TDD: test rojo, implementación mínima, test verde, commit.

**Tech Stack:** Python 3.14, DuckDB, Pydantic v2 / pydantic-settings, Typer, Jinja2, structlog, pytest + pytest-vcr, ruff, mypy `--strict`, `uv` como runner.

## Global Constraints

- Type hints obligatorios en todo el código; `uv run mypy src` debe salir `Success` (config: `--strict`).
- `uv run ruff check src tests` debe salir `All checks passed!`. `line-length = 100`.
- `uv run pytest -q` debe pasar completo al final de **cada** tarea. Baseline post-merge: **558 passed**.
- Conventional Commits, un commit por tarea (o por paso cuando la tarea lo indique): `feat(scope): ...`, `fix(scope): ...`, `refactor(scope): ...`, `docs(scope): ...`.
- Cada adaptador de ingest sigue siendo un módulo puro: `download → parse → upsert`. Las funciones reciben paths/conexiones, sin estado global.
- Los tests de integración usan cassettes VCR; **nunca** llamadas de red en CI.
- Degradación grácil (spec §13.2): un dato ausente nunca revienta la corrida; se loguea y el consumidor decide.
- No inventar números: si un assumption no se resuelve, `Sourced.value` queda `None` y el reporte muestra el hueco.

## Estado de partida verificado

| Hecho | Verificación |
|---|---|
| `build/backlog-m2-m6` está 18 commits adelante de `master`, 1 atrás | `git rev-list --count master..build/backlog-m2-m6` = 18 |
| El merge es limpio | `git merge-tree --write-tree master build/backlog-m2-m6` sin conflictos |
| La branch está verde | 558 passed, ruff clean, mypy clean (42 archivos) |
| `master` está verde pero con matemática vieja | 429 passed, ruff clean, mypy clean (35 archivos) |

**Ya arreglado en la branch — NO re-implementar:** market_cap→USD en el gate (`engine._market_cap_usd`), tax rate por país en ROIC (`engine._resolve_tax_rate`, `DEFAULT_TAX_RATE = 0.21`), percentiles sobre el universo completo (`ranking.rescore_with_margins`), sentinela `None` en sensitivity fuera de dominio, `import_damodaran` con una sola fila de `refresh_log`, N+1 del segundo pase (`_batch_dcf_margins`).

## File Structure

**Fase 0 — merge y decisiones registradas**
- Modify: `docs/adr/0003-client-portal-api-over-tws.md` — marcar `Superseded`.
- Create: `docs/adr/0004-tws-api-via-ib-async.md` — la decisión que se tomó de verdad.
- Modify: `CONTEXT.md:31` — corregir el servicio externo de M5.

**Fase 1 — conectar (wiring)**
- Create: `config/industry_mapping.csv` — mapa proveedor→Damodaran (~95 industries destino).
- Create: `src/bot/ingest/industry_mapping.py` — carga + normalización + lookup. Responsabilidad única: resolver un string de industria de proveedor a la taxonomía Damodaran.
- Create: `src/bot/reference/sectors.py` — sets canónicos derivados de la taxonomía Damodaran (financieras, cíclicas). Sin I/O, sin DB.
- Modify: `src/bot/config.py` — `industry_mapping_path`.
- Modify: `src/bot/ingest/fmp.py` (`_company_row`), `src/bot/ingest/sec_edgar.py` (`parse_company_facts`) — poblar `industry_damodaran`.
- Modify: `src/bot/screener/engine.py` (`build_company_data`) — poblar `is_financial_services`.
- Modify: `src/bot/ingest/damodaran.py` — column maps ampliados, escalares pre-header, hoja `Country Tax Rates`, registro de datasets adicionales.
- Modify: `src/bot/storage/schema.sql` — `fx_rate_to_usd`, `market_cap_usd`, `close_usd`.
- Modify: `src/bot/valuator/analysis.py` — cablear `is_cyclical_sector`.

**Fase 2 — borrar muerto**
- Modify: `src/bot/screener/types.py`, `src/bot/screener/rules.py`, los 3 presets, `tests/unit/test_screener_trap_detection.py`.
- Modify: `src/bot/valuator/assumptions.py`, `src/bot/valuator/story_types.py`, `src/bot/reporting/templates/analysis.md.j2`.

**Fase 3 — bugs**
- Modify: `src/bot/valuator/sensitivity.py`, `src/bot/valuator/narrative_flags.py`, `src/bot/valuator/analysis.py`, `src/bot/valuator/assumptions.py`, `src/bot/reporting/analysis_report.py`, `tests/integration/test_screen_cli.py`.

---

## Fase 0 — Base mergeada y decisiones registradas

### Task 0.1: Mergear `build/backlog-m2-m6` en `master`

**Files:**
- No source changes; solo historia de git.

**Interfaces:**
- Consumes: nada.
- Produces: un `master` que contiene `src/bot/portfolio/*`, `src/bot/ingest/ibkr.py`, `_market_cap_usd`, `_resolve_tax_rate`, `rescore_with_margins`, `refresh --prices/--fx/--all`. Todas las tareas siguientes asumen estos símbolos presentes.

- [ ] **Step 1: Verificar que el merge sigue siendo limpio**

```bash
cd /home/nicolasr/Projects/investment-bot
git fetch origin
git status --porcelain
git rev-list --count master..build/backlog-m2-m6
git merge-tree --write-tree master build/backlog-m2-m6 >/dev/null && echo "CLEAN" || echo "CONFLICTS"
```

Esperado: `18`, y `CLEAN`. Si el working tree tiene cambios (hay dos archivos en `.claude/workflows/` modificados/sin trackear), commitealos o stasheálos antes de seguir — no los mezcles con el merge.

- [ ] **Step 2: Mergear**

```bash
git merge --no-ff build/backlog-m2-m6 -m "merge(m5): land IBKR portfolio + M2/M3 correctness fixes

Brings 18 commits that PR #49 left behind: all of M5 (#25-#29, #55) plus the
screener/valuator correctness fixes (USD market cap, per-country tax rate in
ROIC, full-universe percentiles, sensitivity sentinel) and the refresh
--prices/--fx/--all CLI wiring.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Verificar la suite completa sobre el merge**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: `558 passed`, `All checks passed!`, `Success: no issues found in 42 source files`.

Si el conteo no es 558, **detenete y reportá** antes de continuar: el merge trajo algo inesperado.

- [ ] **Step 4: Confirmar que el módulo de portfolio es importable**

Run: `uv run python -c "from bot.portfolio import command, events, report, sync, trades; from bot.ingest import ibkr; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Push**

```bash
git push origin master
```

---

### Task 0.2: Registrar la decisión TWS y corregir la documentación stale

**Files:**
- Create: `docs/adr/0004-tws-api-via-ib-async.md`
- Modify: `docs/adr/0003-client-portal-api-over-tws.md`
- Modify: `CONTEXT.md:31`

**Interfaces:**
- Consumes: `Settings.ibkr_host` / `ibkr_port` / `ibkr_client_id` de `src/bot/config.py`.
- Produces: nada en código. Es la referencia que las tareas siguientes citan cuando hablan de IBKR.

- [ ] **Step 1: Leer el ADR 0003 y el formato usado por 0001/0002**

Run: `cat docs/adr/0001-use-duckdb.md docs/adr/0003-client-portal-api-over-tws.md`

Copiá exactamente la estructura de secciones que usan (`## Status`, `## Context`, `## Decision`, `## Consequences` o la que sea) para que el 0004 sea consistente.

- [ ] **Step 2: Marcar el 0003 como superseded**

Editá la línea de status del 0003 para que diga, respetando el formato del archivo:

```markdown
Superseded by [ADR 0004](0004-tws-api-via-ib-async.md) (2026-08-09).
```

No borres el cuerpo: el razonamiento original es parte del registro histórico. Agregá al final del archivo:

```markdown
## Why this was superseded

The Client Portal API requires a Dockerised `cp-gateway` plus a browser OAuth
handshake whose session must be re-established interactively. That is incompatible
with a headless, cron-driven daily sync (spec §9.3). The TWS socket API reached
through `ib_async` needs only a running TWS/IB Gateway with the Read-Only API
toggle enabled, and no browser step. See ADR 0004.
```

- [ ] **Step 3: Escribir el ADR 0004**

```markdown
# ADR 0004 — IBKR portfolio sync over the TWS socket API via `ib_async`

## Status

Accepted (2026-08-09). Supersedes [ADR 0003](0003-client-portal-api-over-tws.md).

## Context

M5 needs a daily, unattended, read-only sync of positions, cash balances and
trades from Interactive Brokers (spec §8.1/§8.2). ADR 0003 chose the Client Portal
API (REST). Implementing it surfaced two blockers:

1. The gateway is a Docker container that must be running and reachable.
2. Authentication is a browser OAuth flow whose session expires and must be
   re-established interactively — incompatible with the cron schedule in §9.3.

## Decision

Use the **TWS socket API** through the `ib_async` library (`ib-async>=2.1.0`),
against a locally running TWS or IB Gateway.

- Host/port/client id are configuration, not constants: `BOT_IBKR_HOST`
  (default `127.0.0.1`), `BOT_IBKR_PORT` (default `7496` = live TWS; `7497` paper,
  `4001`/`4002` IB Gateway live/paper), `BOT_IBKR_CLIENT_ID` (default `1`).
- The client is **read-only by construction**: `src/bot/ingest/ibkr.py` exposes
  only `accounts`, `positions`, `cash_balances` and `trades`. There are no order
  placement methods. Operationally, TWS's "Read-Only API" toggle must be enabled.

## Consequences

Positive:
- No Docker, no browser step; the daily cron works unattended once TWS is up.
- `ib_async` is asyncio-native and matches the rest of the codebase's typing.

Negative:
- Requires a TWS/IB Gateway process running on the same host. This is acceptable
  for a single-user local tool (spec §2) but rules out a server deployment where
  no desktop session exists.
- **Trade history is session-limited.** The socket returns only the current
  session's fills, so `trades` cannot be backfilled historically. Documented in
  `src/bot/storage/schema.sql` above the `trades` table.
- **Corporate actions are out of reach.** Dividends and splits need the IBKR Flex
  Web Service, not the socket. The `corporate_actions` table is created but stays
  empty, so the `DIVIDEND` and `SPLIT` events in spec §8.3 cannot fire yet.

## Alternatives rejected

- **Client Portal API** — the original ADR 0003 choice; rejected for the
  interactive-auth reason above.
- **IBKR Flex Web Service alone** — good for historical statements and corporate
  actions, but it is a batch report API with no live positions, so it cannot serve
  the daily snapshot on its own. It remains the candidate for closing the
  corporate-actions gap later.
```

- [ ] **Step 4: Corregir `CONTEXT.md`**

Reemplazá la línea 31:

```markdown
- **Interactive Brokers Client Portal API** (M5): portfolio sync, read-only.
```

por:

```markdown
- **Interactive Brokers TWS API** via `ib_async` (M5): portfolio sync, read-only. Needs a local TWS/IB Gateway on `BOT_IBKR_PORT` (default 7496). See [ADR 0004](docs/adr/0004-tws-api-via-ib-async.md).
```

- [ ] **Step 5: Verificar que no queden referencias stale al Client Portal fuera del spec y del ADR 0003**

Run: `grep -rn "Client Portal" --include="*.md" --include="*.py" . | grep -v "^./docs/adr/000[34]" | grep -v "^./docs/superpowers/specs/"`
Expected: sin resultados.

El spec (`docs/superpowers/specs/2026-05-25-investment-bot-design.md` §8.1, §13.1, §16.3) queda deliberadamente sin tocar: es el documento de diseño original y el ADR 0004 es el mecanismo correcto para registrar la divergencia. Anotalo en el commit.

- [ ] **Step 6: Commit**

```bash
git add docs/adr/0003-client-portal-api-over-tws.md docs/adr/0004-tws-api-via-ib-async.md CONTEXT.md
git commit -m "docs(adr): record the TWS-over-Client-Portal decision (ADR 0004)

ADR 0003 still claimed Client Portal API while the M5 implementation shipped the
TWS socket API via ib_async. Supersede 0003, add 0004 with the real rationale and
its consequences (session-limited trades, corporate actions out of reach), and fix
the stale external-services line in CONTEXT.md.

Spec §8.1/§13.1/§16.3 intentionally left as-is: the ADR is the record of divergence.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Fase 1 — Conectar lo que ya existe

Ninguna tarea de esta fase inventa lógica de negocio nueva. Todas cablean módulos ya escritos y testeados que hoy nadie invoca, o pueblan columnas que los consumidores ya hacen `SELECT`.

### Task 1.1: Mapa de industrias proveedor→Damodaran

Es la tarea keystone de la fase: hoy `companies.industry_damodaran` **nunca se escribe** en producción, y lo leen `screener/engine.py:450`, `valuator/assumptions.py:213` y `valuator/analysis.py:214`. Sin esto, `load_industry_benchmarks` devuelve `None` para casi toda empresa real, `_EMPTY_BENCHMARKS` hace que **todas** las reglas sector-relativas hagan skip, y una empresa puede llegar al shortlist con sólo `fcf_yield_above` sin que el filtro central de Damodaran (ROIC vs WACC) se aplique nunca.

**Files:**
- Create: `src/bot/ingest/industry_mapping.py`
- Create: `config/industry_mapping.csv`
- Create: `tests/unit/test_industry_mapping.py`
- Modify: `src/bot/config.py` (agregar `industry_mapping_path` después de `presets_dir`)

**Interfaces:**
- Consumes: `bot.config.Settings`.
- Produces:
  - `IndustryMapping` — envoltorio inmutable con `.resolve(provider: str, industry: str | None) -> str | None`.
  - `load_industry_mapping(path: Path | None = None) -> IndustryMapping`
  - `default_mapping_path() -> Path`
  - `normalize_industry_label(raw: str) -> str`
  - `DAMODARAN_INDUSTRIES: frozenset[str]` — las 96 etiquetas canónicas del dataset `wacc.xls`.
  - Task 1.2 consume `IndustryMapping.resolve`; Task 1.3 consume `DAMODARAN_INDUSTRIES` para validar.

- [ ] **Step 1: Escribir el test que falla**

Create `tests/unit/test_industry_mapping.py`:

```python
"""Provider→Damodaran industry mapping (spec §4.3.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.ingest.industry_mapping import (
    DAMODARAN_INDUSTRIES,
    IndustryMapping,
    default_mapping_path,
    load_industry_mapping,
    normalize_industry_label,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "industry_mapping.csv"
    path.write_text(body)
    return path


def test_normalize_collapses_case_whitespace_and_dashes() -> None:
    # FMP is inconsistent about the dash it emits between a family and a variant.
    assert normalize_industry_label("Banks—Diversified") == "banks-diversified"
    assert normalize_industry_label("Banks – Diversified") == "banks-diversified"
    assert normalize_industry_label("banks - diversified") == "banks-diversified"
    assert normalize_industry_label("  Software—Application  ") == "software-application"


def test_resolve_exact_match(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Semiconductors,Semiconductor\n",
    )
    mapping = load_industry_mapping(path)
    assert mapping.resolve("fmp", "Semiconductors") == "Semiconductor"


def test_resolve_is_dash_and_case_insensitive(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Banks—Diversified,Bank (Money Center)\n",
    )
    mapping = load_industry_mapping(path)
    assert mapping.resolve("FMP", "banks - diversified") == "Bank (Money Center)"


def test_resolve_unmapped_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, "provider,provider_industry,damodaran_industry\n")
    mapping = load_industry_mapping(path)
    assert mapping.resolve("fmp", "Blockchain Widgets") is None


def test_resolve_none_industry_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, "provider,provider_industry,damodaran_industry\n")
    assert load_industry_mapping(path).resolve("fmp", None) is None


def test_missing_file_degrades_to_empty_mapping(tmp_path: Path) -> None:
    # Graceful degradation (spec §13.2): no mapping file must not break ingest.
    mapping = load_industry_mapping(tmp_path / "absent.csv")
    assert mapping.resolve("fmp", "Semiconductors") is None
    assert len(mapping) == 0


def test_rejects_unknown_damodaran_industry(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Semiconductors,Semiconductorz\n",
    )
    with pytest.raises(ValueError, match="not a Damodaran industry"):
        load_industry_mapping(path)


def test_rejects_duplicate_provider_industry(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Semiconductors,Semiconductor\n"
        "fmp,semiconductors,Steel\n",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_industry_mapping(path)


def test_rejects_missing_column(tmp_path: Path) -> None:
    path = _write(tmp_path, "provider,provider_industry\nfmp,Semiconductors\n")
    with pytest.raises(ValueError, match="damodaran_industry"):
        load_industry_mapping(path)


def test_shipped_mapping_loads_and_covers_the_cassette_industries() -> None:
    mapping = load_industry_mapping(default_mapping_path())
    # Every FMP industry string present in the committed VCR cassettes must map,
    # otherwise the integration tests screen against empty benchmarks.
    for fmp_industry in (
        "Consumer Electronics",
        "Semiconductors",
        "Software",
        "Packaged Foods",
        "Auto Manufacturers",
    ):
        assert mapping.resolve("fmp", fmp_industry) is not None, fmp_industry


def test_damodaran_industries_is_the_canonical_taxonomy() -> None:
    assert "Semiconductor" in DAMODARAN_INDUSTRIES
    assert "Financial Svcs. (Non-bank & Insurance)" in DAMODARAN_INDUSTRIES
    # The aggregate rows of wacc.xls are not industries a company belongs to.
    assert "Total Market" not in DAMODARAN_INDUSTRIES
    assert len(DAMODARAN_INDUSTRIES) == 94


def test_mapping_is_immutable() -> None:
    mapping = load_industry_mapping(default_mapping_path())
    with pytest.raises(AttributeError):
        mapping.foo = 1  # type: ignore[attr-defined]
    assert isinstance(mapping, IndustryMapping)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `uv run pytest tests/unit/test_industry_mapping.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'bot.ingest.industry_mapping'`.

- [ ] **Step 3: Implementar el módulo**

Create `src/bot/ingest/industry_mapping.py`:

```python
"""Provider industry label → Damodaran industry taxonomy (spec §4.3.1).

Every sector-relative comparison in the bot keys off ``companies.industry_damodaran``:
the screener's value indicators and the ROIC-vs-WACC trap detector look their medians
up by it (``screener/benchmarks.py``), and the valuator resolves five of its six
critical assumptions from it (``valuator/assumptions.py``). Providers use their own
taxonomy — FMP emits Yahoo-style labels like ``"Semiconductors"`` — which never match
Damodaran's ``"Semiconductor"``. This module is the single translation point.

The mapping is a user-editable CSV so a new provider label can be mapped without a
code change. Resolution is deliberately forgiving on formatting (case, whitespace,
dash variants) because providers are inconsistent about it, but strict on the target:
a ``damodaran_industry`` that is not in the published taxonomy fails at load time
rather than silently producing a company whose benchmarks never resolve.

Missing file → empty mapping, logged as a warning. Ingest must degrade, not die
(spec §13.2); the cost is that sector-relative rules skip, which the screener
already handles.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_REQUIRED_COLUMNS = ("provider", "provider_industry", "damodaran_industry")

#: Dash characters providers use interchangeably between an industry family and its
#: variant (em dash, en dash, hyphen-minus, non-breaking hyphen).
_DASHES = "—–‑"

#: The 94 industry labels of Damodaran's ``wacc.xls`` "Industry Averages" sheet,
#: excluding the two aggregate rows ("Total Market", "Total Market (without
#: financials)") which are not industries a company can belong to.
DAMODARAN_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Advertising",
        "Aerospace/Defense",
        "Air Transport",
        "Apparel",
        "Auto & Truck",
        "Auto Parts",
        "Bank (Money Center)",
        "Banks (Regional)",
        "Beverage (Alcoholic)",
        "Beverage (Soft)",
        "Broadcasting",
        "Brokerage & Investment Banking",
        "Building Materials",
        "Business & Consumer Services",
        "Cable TV",
        "Chemical (Basic)",
        "Chemical (Diversified)",
        "Chemical (Specialty)",
        "Coal & Related Energy",
        "Computer Services",
        "Computers/Peripherals",
        "Construction Supplies",
        "Diversified",
        "Drugs (Biotechnology)",
        "Drugs (Pharmaceutical)",
        "Education",
        "Electrical Equipment",
        "Electronics (Consumer & Office)",
        "Electronics (General)",
        "Engineering/Construction",
        "Entertainment",
        "Environmental & Waste Services",
        "Farming/Agriculture",
        "Financial Svcs. (Non-bank & Insurance)",
        "Food Processing",
        "Food Wholesalers",
        "Furn/Home Furnishings",
        "Green & Renewable Energy",
        "Healthcare Products",
        "Healthcare Support Services",
        "Heathcare Information and Technology",
        "Homebuilding",
        "Hospitals/Healthcare Facilities",
        "Hotel/Gaming",
        "Household Products",
        "Information Services",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
        "Investments & Asset Management",
        "Machinery",
        "Metals & Mining",
        "Office Equipment & Services",
        "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)",
        "Oil/Gas Distribution",
        "Oilfield Svcs/Equip.",
        "Packaging & Container",
        "Paper/Forest Products",
        "Power",
        "Precious Metals",
        "Publishing & Newspapers",
        "R.E.I.T.",
        "Real Estate (Development)",
        "Real Estate (General/Diversified)",
        "Real Estate (Operations & Services)",
        "Recreation",
        "Reinsurance",
        "Restaurant/Dining",
        "Retail (Automotive)",
        "Retail (Building Supply)",
        "Retail (Distributors)",
        "Retail (General)",
        "Retail (Grocery and Food)",
        "Retail (REITs)",
        "Retail (Special Lines)",
        "Rubber& Tires",
        "Semiconductor",
        "Semiconductor Equip",
        "Shipbuilding & Marine",
        "Shoe",
        "Software (Entertainment)",
        "Software (Internet)",
        "Software (System & Application)",
        "Steel",
        "Telecom (Wireless)",
        "Telecom. Equipment",
        "Telecom. Services",
        "Tobacco",
        "Transportation",
        "Transportation (Railroads)",
        "Trucking",
        "Utility (General)",
        "Utility (Water)",
    }
)


def normalize_industry_label(raw: str) -> str:
    """Fold a provider label to a comparison key.

    Lower-cases, collapses internal whitespace, and normalises every dash variant
    (and any spaces hugging it) to a single ``-`` so ``"Banks—Diversified"``,
    ``"Banks – Diversified"`` and ``"banks - diversified"`` all agree.
    """
    text = raw.strip().lower()
    for dash in _DASHES:
        text = text.replace(dash, "-")
    text = " ".join(text.split())
    while " -" in text or "- " in text:
        text = text.replace(" -", "-").replace("- ", "-")
    return text


@dataclass(frozen=True)
class IndustryMapping:
    """Immutable provider→Damodaran lookup, keyed by (provider, normalised label)."""

    _entries: dict[tuple[str, str], str]

    def resolve(self, provider: str, industry: str | None) -> str | None:
        """Return the Damodaran industry for ``industry``, or ``None`` if unmapped."""
        if industry is None:
            return None
        key = (provider.strip().lower(), normalize_industry_label(industry))
        return self._entries.get(key)

    def __len__(self) -> int:
        return len(self._entries)


def default_mapping_path() -> Path:
    """Path of the mapping CSV shipped with the repo (``config/industry_mapping.csv``)."""
    packaged = Path(str(resources.files("bot.ingest").joinpath("industry_mapping.csv")))
    if packaged.exists():
        return packaged
    return Path("config/industry_mapping.csv")


def load_industry_mapping(path: Path | None = None) -> IndustryMapping:
    """Load the provider→Damodaran mapping CSV.

    Args:
        path: CSV location; defaults to :func:`default_mapping_path`.

    Returns:
        The loaded mapping, or an empty mapping when the file does not exist.

    Raises:
        ValueError: On a missing required column, a duplicate
            ``(provider, provider_industry)`` pair, or a ``damodaran_industry``
            outside :data:`DAMODARAN_INDUSTRIES`.
    """
    target = path if path is not None else default_mapping_path()
    if not target.exists():
        log.warning("industry_mapping.absent", path=str(target))
        return IndustryMapping(_entries={})

    with target.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in _REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise ValueError(
                f"{target}: missing required column(s): {', '.join(missing)}"
            )
        entries: dict[tuple[str, str], str] = {}
        for lineno, row in enumerate(reader, start=2):
            provider = (row["provider"] or "").strip().lower()
            provider_industry = (row["provider_industry"] or "").strip()
            damodaran = (row["damodaran_industry"] or "").strip()
            if not provider or not provider_industry or not damodaran:
                continue
            if damodaran not in DAMODARAN_INDUSTRIES:
                raise ValueError(
                    f"{target}:{lineno}: {damodaran!r} is not a Damodaran industry"
                )
            key = (provider, normalize_industry_label(provider_industry))
            if key in entries:
                raise ValueError(
                    f"{target}:{lineno}: duplicate mapping for "
                    f"provider {provider!r} industry {provider_industry!r}"
                )
            entries[key] = damodaran

    log.info("industry_mapping.loaded", path=str(target), entries=len(entries))
    return IndustryMapping(_entries=entries)
```

- [ ] **Step 4: Escribir el CSV de mapeo**

Create `config/industry_mapping.csv`. Cubre la taxonomía FMP/Yahoo que el bot va a ver en la práctica; lo no mapeado degrada a `None` (reglas sector-relativas hacen skip), que es el comportamiento de hoy pero ahora explícito.

```csv
provider,provider_industry,damodaran_industry
fmp,Advertising Agencies,Advertising
fmp,Aerospace & Defense,Aerospace/Defense
fmp,Agricultural Inputs,Farming/Agriculture
fmp,Airlines,Air Transport
fmp,Airports & Air Services,Air Transport
fmp,Aluminum,Metals & Mining
fmp,Apparel Manufacturing,Apparel
fmp,Apparel Retail,Retail (Special Lines)
fmp,Asset Management,Investments & Asset Management
fmp,Auto & Truck Dealerships,Retail (Automotive)
fmp,Auto Manufacturers,Auto & Truck
fmp,Auto Parts,Auto Parts
fmp,Banks—Diversified,Bank (Money Center)
fmp,Banks—Regional,Banks (Regional)
fmp,Beverages—Brewers,Beverage (Alcoholic)
fmp,Beverages—Non-Alcoholic,Beverage (Soft)
fmp,Beverages—Wineries & Distilleries,Beverage (Alcoholic)
fmp,Biotechnology,Drugs (Biotechnology)
fmp,Broadcasting,Broadcasting
fmp,Building Materials,Building Materials
fmp,Building Products & Equipment,Construction Supplies
fmp,Business Equipment & Supplies,Office Equipment & Services
fmp,Capital Markets,Brokerage & Investment Banking
fmp,Chemicals,Chemical (Basic)
fmp,Coking Coal,Coal & Related Energy
fmp,Communication Equipment,Telecom. Equipment
fmp,Computer Hardware,Computers/Peripherals
fmp,Confectioners,Food Processing
fmp,Conglomerates,Diversified
fmp,Consulting Services,Business & Consumer Services
fmp,Consumer Electronics,Electronics (Consumer & Office)
fmp,Copper,Metals & Mining
fmp,Credit Services,Financial Svcs. (Non-bank & Insurance)
fmp,Department Stores,Retail (General)
fmp,Diagnostics & Research,Healthcare Products
fmp,Discount Stores,Retail (General)
fmp,Drug Manufacturers—General,Drugs (Pharmaceutical)
fmp,Drug Manufacturers—Specialty & Generic,Drugs (Pharmaceutical)
fmp,Education & Training Services,Education
fmp,Electrical Equipment & Parts,Electrical Equipment
fmp,Electronic Components,Electronics (General)
fmp,Electronic Gaming & Multimedia,Software (Entertainment)
fmp,Electronics & Computer Distribution,Retail (Distributors)
fmp,Engineering & Construction,Engineering/Construction
fmp,Entertainment,Entertainment
fmp,Farm & Heavy Construction Machinery,Machinery
fmp,Farm Products,Farming/Agriculture
fmp,Financial Conglomerates,Financial Svcs. (Non-bank & Insurance)
fmp,Financial Data & Stock Exchanges,Financial Svcs. (Non-bank & Insurance)
fmp,Food Distribution,Food Wholesalers
fmp,Footwear & Accessories,Shoe
fmp,Furnishings Fixtures & Appliances,Furn/Home Furnishings
fmp,Gambling,Hotel/Gaming
fmp,Gold,Precious Metals
fmp,Grocery Stores,Retail (Grocery and Food)
fmp,Health Information Services,Heathcare Information and Technology
fmp,Healthcare Plans,Healthcare Support Services
fmp,Home Improvement Retail,Retail (Building Supply)
fmp,Household & Personal Products,Household Products
fmp,Industrial Distribution,Retail (Distributors)
fmp,Information Technology Services,Computer Services
fmp,Insurance Brokers,Insurance (General)
fmp,Insurance—Diversified,Insurance (General)
fmp,Insurance—Life,Insurance (Life)
fmp,Insurance—Property & Casualty,Insurance (Prop/Cas.)
fmp,Insurance—Reinsurance,Reinsurance
fmp,Insurance—Specialty,Insurance (General)
fmp,Integrated Freight & Logistics,Transportation
fmp,Internet Content & Information,Software (Internet)
fmp,Internet Retail,Retail (Special Lines)
fmp,Leisure,Recreation
fmp,Lodging,Hotel/Gaming
fmp,Lumber & Wood Production,Paper/Forest Products
fmp,Luxury Goods,Retail (Special Lines)
fmp,Marine Shipping,Shipbuilding & Marine
fmp,Medical Care Facilities,Hospitals/Healthcare Facilities
fmp,Medical Devices,Healthcare Products
fmp,Medical Distribution,Healthcare Support Services
fmp,Medical Instruments & Supplies,Healthcare Products
fmp,Metal Fabrication,Metals & Mining
fmp,Mortgage Finance,Financial Svcs. (Non-bank & Insurance)
fmp,Oil & Gas Drilling,Oilfield Svcs/Equip.
fmp,Oil & Gas E&P,Oil/Gas (Production and Exploration)
fmp,Oil & Gas Equipment & Services,Oilfield Svcs/Equip.
fmp,Oil & Gas Integrated,Oil/Gas (Integrated)
fmp,Oil & Gas Midstream,Oil/Gas Distribution
fmp,Oil & Gas Refining & Marketing,Oil/Gas (Integrated)
fmp,Other Industrial Metals & Mining,Metals & Mining
fmp,Other Precious Metals & Mining,Precious Metals
fmp,Packaged Foods,Food Processing
fmp,Packaging & Containers,Packaging & Container
fmp,Paper & Paper Products,Paper/Forest Products
fmp,Personal Services,Business & Consumer Services
fmp,Pharmaceutical Retailers,Retail (Special Lines)
fmp,Pollution & Treatment Controls,Environmental & Waste Services
fmp,Publishing,Publishing & Newspapers
fmp,Railroads,Transportation (Railroads)
fmp,Real Estate—Development,Real Estate (Development)
fmp,Real Estate—Diversified,Real Estate (General/Diversified)
fmp,Real Estate Services,Real Estate (Operations & Services)
fmp,Recreational Vehicles,Recreation
fmp,REIT—Diversified,R.E.I.T.
fmp,REIT—Healthcare Facilities,R.E.I.T.
fmp,REIT—Hotel & Motel,R.E.I.T.
fmp,REIT—Industrial,R.E.I.T.
fmp,REIT—Mortgage,R.E.I.T.
fmp,REIT—Office,R.E.I.T.
fmp,REIT—Residential,R.E.I.T.
fmp,REIT—Retail,R.E.I.T.
fmp,REIT—Specialty,R.E.I.T.
fmp,Rental & Leasing Services,Business & Consumer Services
fmp,Residential Construction,Homebuilding
fmp,Resorts & Casinos,Hotel/Gaming
fmp,Restaurants,Restaurant/Dining
fmp,Scientific & Technical Instruments,Electronics (General)
fmp,Security & Protection Services,Business & Consumer Services
fmp,Semiconductor Equipment & Materials,Semiconductor Equip
fmp,Semiconductors,Semiconductor
fmp,Silver,Precious Metals
fmp,Software,Software (System & Application)
fmp,Software—Application,Software (System & Application)
fmp,Software—Infrastructure,Software (System & Application)
fmp,Solar,Green & Renewable Energy
fmp,Specialty Business Services,Business & Consumer Services
fmp,Specialty Chemicals,Chemical (Specialty)
fmp,Specialty Industrial Machinery,Machinery
fmp,Specialty Retail,Retail (Special Lines)
fmp,Staffing & Employment Services,Business & Consumer Services
fmp,Steel,Steel
fmp,Telecom Services,Telecom. Services
fmp,Textile Manufacturing,Apparel
fmp,Thermal Coal,Coal & Related Energy
fmp,Tobacco,Tobacco
fmp,Tools & Accessories,Machinery
fmp,Travel Services,Recreation
fmp,Trucking,Trucking
fmp,Uranium,Coal & Related Energy
fmp,Utilities—Diversified,Utility (General)
fmp,Utilities—Independent Power Producers,Power
fmp,Utilities—Regulated Electric,Power
fmp,Utilities—Regulated Gas,Utility (General)
fmp,Utilities—Regulated Water,Utility (Water)
fmp,Waste Management,Environmental & Waste Services
fmp,Wireless Telecommunication Services,Telecom (Wireless)
```

- [ ] **Step 5: Empaquetar el CSV y agregar el setting**

En `pyproject.toml`, dentro de `[tool.hatch.build.targets.wheel.force-include]`, agregá la línea (seguí el patrón de `universe_default.csv`):

```toml
"src/bot/ingest/industry_mapping.csv" = "bot/ingest/industry_mapping.csv"
```

Copiá el CSV a la ubicación empaquetada (la de `config/` es la editable por el usuario; la empaquetada es el default que viaja con la wheel):

```bash
cp config/industry_mapping.csv src/bot/ingest/industry_mapping.csv
```

En `src/bot/config.py`, agregá el campo inmediatamente después de `presets_dir`:

```python
    industry_mapping_path: Path = Field(
        default=Path("./config/industry_mapping.csv"),
        description=(
            "CSV mapping provider industry labels to the Damodaran taxonomy "
            "(spec §4.3.1). Falls back to the copy shipped with the package."
        ),
    )
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/unit/test_industry_mapping.py tests/unit/test_config.py -q`
Expected: PASS, todos.

Si `test_damodaran_industries_is_the_canonical_taxonomy` falla por el conteo, verificá contra el fixture real antes de tocar el número:

```bash
uv run python -c "
import xlrd
sh = xlrd.open_workbook('tests/fixtures/damodaran/wacc_sample.xls').sheet_by_name('Industry Averages')
names = [sh.cell_value(r,0) for r in range(19, sh.nrows) if sh.cell_value(r,0)]
print(len(names), len([n for n in names if not n.startswith('Total Market')]))
"
```

- [ ] **Step 7: Correr la suite completa y commitear**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: `568 passed` (558 + 10 nuevos), clean, clean.

```bash
git add src/bot/ingest/industry_mapping.py src/bot/ingest/industry_mapping.csv \
        config/industry_mapping.csv tests/unit/test_industry_mapping.py \
        src/bot/config.py pyproject.toml
git commit -m "feat(ingest): provider→Damodaran industry mapping (§4.3.1)

companies.industry_damodaran is read by the screener engine and both valuator
modules but no importer ever wrote it, so load_industry_benchmarks returned None
for every real company and every sector-relative rule silently skipped. Add the
translation layer: a user-editable CSV, a forgiving normaliser for provider dash/
case inconsistency, and strict validation of the target against the published
94-industry taxonomy. Missing file degrades to an empty mapping (§13.2).

Wiring into the importers is the next commit.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.2: Poblar `industry_damodaran` en el importer de FMP

**Files:**
- Modify: `src/bot/ingest/fmp.py` — `_company_row` y `import_company_from_fmp`
- Modify: `tests/unit/test_fmp_parser.py` — agregar los tests de abajo al final
- Modify: `tests/integration/test_fmp_import.py` — assertion end-to-end

**Interfaces:**
- Consumes: `IndustryMapping`, `load_industry_mapping` de Task 1.1.
- Produces: `companies.industry_damodaran` poblado para toda empresa importada vía FMP. `_company_row(ticker, info, currency, *, mapping)` gana un parámetro keyword-only. `import_company_from_fmp(..., mapping: IndustryMapping | None = None)` — `None` carga el default.

- [ ] **Step 1: Escribir los tests que fallan**

Agregá al final de `tests/unit/test_fmp_parser.py`:

```python
def test_company_row_maps_industry_to_damodaran() -> None:
    from bot.ingest.fmp import CompanyInfo, _company_row
    from bot.ingest.industry_mapping import IndustryMapping, normalize_industry_label

    mapping = IndustryMapping(
        _entries={("fmp", normalize_industry_label("Semiconductors")): "Semiconductor"}
    )
    info = CompanyInfo(
        ticker="NVDA",
        name="NVIDIA Corp",
        country="US",
        exchange="NASDAQ",
        industry="Semiconductors",
        currency="USD",
    )
    row = _company_row("NVDA", info, "USD", mapping=mapping)
    assert row["industry"] == "Semiconductors"
    assert row["industry_damodaran"] == "Semiconductor"


def test_company_row_unmapped_industry_leaves_damodaran_none() -> None:
    from bot.ingest.fmp import CompanyInfo, _company_row
    from bot.ingest.industry_mapping import IndustryMapping

    info = CompanyInfo(
        ticker="WEIRD",
        name="Weird Co",
        country="US",
        exchange="NYSE",
        industry="Blockchain Widgets",
        currency="USD",
    )
    row = _company_row("WEIRD", info, "USD", mapping=IndustryMapping(_entries={}))
    assert row["industry"] == "Blockchain Widgets"
    assert row["industry_damodaran"] is None


def test_company_row_without_profile_has_no_damodaran_industry() -> None:
    from bot.ingest.fmp import _company_row
    from bot.ingest.industry_mapping import IndustryMapping

    row = _company_row("GHOST", None, "USD", mapping=IndustryMapping(_entries={}))
    assert row.get("industry_damodaran") is None
```

Ajustá la construcción de `CompanyInfo` a su firma real: leela primero con
`grep -n "class CompanyInfo" -A 12 src/bot/ingest/fmp.py` y usá los nombres de campo exactos.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `uv run pytest tests/unit/test_fmp_parser.py -q -k "damodaran or profile"`
Expected: FAIL con `TypeError: _company_row() got an unexpected keyword argument 'mapping'`.

- [ ] **Step 3: Implementar**

En `src/bot/ingest/fmp.py`, agregá el import:

```python
from bot.ingest.industry_mapping import IndustryMapping, load_industry_mapping
```

Cambiá `_company_row` para que reciba el mapping y emita la columna. La regla: `industry` guarda siempre el label crudo del proveedor (trazabilidad), `industry_damodaran` el traducido o `None`.

```python
def _company_row(
    ticker: str,
    info: CompanyInfo | None,
    currency: str | None,
    *,
    mapping: IndustryMapping,
) -> dict[str, Any]:
    """Build the ``companies`` row from the FMP profile (+ parsed currency fallback).

    ``currency`` is preferred; the parsed ``reportedCurrency`` is the fallback so
    a company row always carries a currency even if the profile omits it.

    ``industry`` keeps the provider's own label for traceability;
    ``industry_damodaran`` carries the translated label the sector-relative rules
    and the valuator key off (spec §4.3.1), or ``None`` when unmapped.
    """
    if info is None:
        return {
            "ticker": ticker,
            "name": ticker,
            "currency": currency,
            "source": "fmp",
            "status": "active",
            "industry_damodaran": None,
        }
    return {
        "ticker": ticker,
        "name": info.name,
        "country": info.country,
        "exchange": info.exchange,
        "industry": info.industry,
        "industry_damodaran": mapping.resolve("fmp", info.industry),
        "currency": info.currency or currency,
        "status": "active" if info.is_actively_trading else "inactive",
        "source": "fmp",
    }
```

Preservá exactamente la expresión de `status` que ya estaba (la de arriba es el patrón; usá la real del archivo, alrededor de `fmp.py:724`) y el resto de las claves tal como están.

En `import_company_from_fmp`, agregá el parámetro y pasalo:

```python
def import_company_from_fmp(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    api_key: str,
    client: FmpClient | None = None,
    mapping: IndustryMapping | None = None,
) -> IngestResult:
```

Y en el cuerpo, antes de construir la fila:

```python
    resolved_mapping = mapping if mapping is not None else load_industry_mapping()
```

…y reemplazá la llamada existente por `_company_row(ticker, info, currency, mapping=resolved_mapping)`.

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/unit/test_fmp_parser.py -q`
Expected: PASS.

- [ ] **Step 5: Assertion end-to-end en el test de integración**

En `tests/integration/test_fmp_import.py`, dentro del test que ya importa una empresa con cassette, agregá:

```python
    industry, damodaran = conn.execute(
        "SELECT industry, industry_damodaran FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()
    # The provider label is kept verbatim; the mapped label is what every
    # sector-relative rule and the valuator actually key off (spec §4.3.1).
    assert industry is not None
    assert damodaran is not None, f"{industry!r} did not map to a Damodaran industry"
```

Leé el test primero para tomar el nombre real de la variable del ticker y de la conexión.

- [ ] **Step 6: Verificar que la cadena completa resuelve benchmarks**

Run: `uv run pytest tests/integration/test_fmp_import.py -q`
Expected: PASS. Si `damodaran is None`, el label de la cassette no está en el CSV: agregalo a **ambas** copias del CSV (`config/` y `src/bot/ingest/`) y volvé a correr.

- [ ] **Step 7: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: `571 passed`, clean, clean.

```bash
git add src/bot/ingest/fmp.py tests/unit/test_fmp_parser.py tests/integration/test_fmp_import.py
git commit -m "feat(ingest): write industry_damodaran on FMP company import

Closes the wiring gap: the mapping from the previous commit is now applied at
ingest, so companies.industry_damodaran is populated for every FMP-imported
company. The raw provider label stays in companies.industry for traceability.

Sector medians (value indicators, ROIC-vs-WACC trap detector) and five of the six
valuator assumptions resolve for real companies for the first time.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.3: Poblar `is_financial_services` y cablear `is_cyclical_sector`

Dos campos muertos que **sí** tienen fuente de datos una vez que existe `industry_damodaran`: la exclusión de financieras hoy es sólo un substring match de `bank`/`insurance`, así que `"Investments & Asset Management"`, `"Brokerage & Investment Banking"`, `"Financial Svcs. (Non-bank & Insurance)"`, `"Reinsurance"` y `"R.E.I.T."` pasan el gate. Y `is_cyclical_sector` nunca se pasa desde el CLI, así que `StoryType.CYCLICAL` es inalcanzable.

**Files:**
- Create: `src/bot/reference/__init__.py`
- Create: `src/bot/reference/sectors.py`
- Create: `tests/unit/test_reference_sectors.py`
- Modify: `src/bot/screener/engine.py` — `build_company_data`
- Modify: `src/bot/valuator/analysis.py` — `analyze`
- Modify: `tests/unit/test_screener_engine.py`, `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Consumes: `DAMODARAN_INDUSTRIES` de Task 1.1.
- Produces:
  - `FINANCIAL_SERVICES_INDUSTRIES: frozenset[str]`
  - `CYCLICAL_INDUSTRIES: frozenset[str]`
  - `is_financial_services(industry: str | None) -> bool`
  - `is_cyclical(industry: str | None) -> bool`

- [ ] **Step 1: Escribir el test que falla**

Create `tests/unit/test_reference_sectors.py`:

```python
"""Canonical sector classifications over the Damodaran taxonomy."""

from __future__ import annotations

from bot.ingest.industry_mapping import DAMODARAN_INDUSTRIES
from bot.reference.sectors import (
    CYCLICAL_INDUSTRIES,
    FINANCIAL_SERVICES_INDUSTRIES,
    is_cyclical,
    is_financial_services,
)


def test_every_classified_industry_is_in_the_taxonomy() -> None:
    # A typo here would silently classify nothing, so pin it.
    assert FINANCIAL_SERVICES_INDUSTRIES <= DAMODARAN_INDUSTRIES
    assert CYCLICAL_INDUSTRIES <= DAMODARAN_INDUSTRIES


def test_financials_the_substring_match_used_to_miss() -> None:
    # These are exactly the labels that "bank"/"insurance" substring matching
    # let through before this module existed.
    for industry in (
        "Investments & Asset Management",
        "Brokerage & Investment Banking",
        "Financial Svcs. (Non-bank & Insurance)",
        "Reinsurance",
        "R.E.I.T.",
    ):
        assert is_financial_services(industry), industry


def test_obvious_financials_still_classified() -> None:
    for industry in (
        "Bank (Money Center)",
        "Banks (Regional)",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
    ):
        assert is_financial_services(industry), industry


def test_non_financials_not_classified() -> None:
    for industry in ("Semiconductor", "Software (System & Application)", "Steel"):
        assert not is_financial_services(industry)


def test_cyclicals_classified() -> None:
    for industry in (
        "Auto & Truck",
        "Steel",
        "Semiconductor",
        "Oil/Gas (Production and Exploration)",
        "Homebuilding",
        "Metals & Mining",
    ):
        assert is_cyclical(industry), industry


def test_defensives_not_cyclical() -> None:
    for industry in (
        "Household Products",
        "Food Processing",
        "Utility (Water)",
        "Tobacco",
        "Drugs (Pharmaceutical)",
    ):
        assert not is_cyclical(industry), industry


def test_none_industry_is_neither() -> None:
    assert not is_financial_services(None)
    assert not is_cyclical(None)


def test_classification_is_exact_not_substring() -> None:
    # "Bank" appears inside "Brokerage & Investment Banking"; exactness matters
    # so an unmapped free-text label cannot accidentally classify.
    assert not is_financial_services("Investment Bank of Nowhere")
    assert not is_cyclical("Steel Drums Appreciation Society")
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_reference_sectors.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'bot.reference'`.

- [ ] **Step 3: Implementar**

Create `src/bot/reference/__init__.py`:

```python
"""Static reference data derived from the Damodaran taxonomy (no I/O, no DB)."""
```

Create `src/bot/reference/sectors.py`:

```python
"""Sector classifications over the Damodaran industry taxonomy.

Two questions the rest of the bot asks about an industry, answered in one place so
the answers cannot drift:

- **Is it financial services?** The §6.2 quality gate excludes banks and insurers
  because their balance sheets make the leverage and cashflow gates meaningless.
  Substring-matching ``"bank"``/``"insurance"`` misses
  ``"Investments & Asset Management"``, ``"Brokerage & Investment Banking"``,
  ``"Financial Svcs. (Non-bank & Insurance)"``, ``"Reinsurance"`` and ``"R.E.I.T."``.
- **Is it cyclical?** ``StoryType.CYCLICAL`` (§7.1) needs a sector signal; without
  one the classifier can never reach that archetype.

Membership is exact against the published labels, never substring: an unmapped
free-text provider label must not accidentally classify. Both sets are asserted to
be subsets of :data:`DAMODARAN_INDUSTRIES` by the tests, so a typo fails loudly.
"""

from __future__ import annotations

#: Industries whose balance sheets make the §6.2 leverage / cashflow gates
#: meaningless. Excluded by the default screener preset.
FINANCIAL_SERVICES_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Bank (Money Center)",
        "Banks (Regional)",
        "Brokerage & Investment Banking",
        "Financial Svcs. (Non-bank & Insurance)",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
        "Investments & Asset Management",
        "R.E.I.T.",
        "Reinsurance",
        "Retail (REITs)",
    }
)

#: Industries whose earnings swing with the economic cycle, so a single year's
#: margin or growth rate is a poor guide to the next (spec §7.1).
CYCLICAL_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Air Transport",
        "Auto & Truck",
        "Auto Parts",
        "Building Materials",
        "Chemical (Basic)",
        "Coal & Related Energy",
        "Construction Supplies",
        "Engineering/Construction",
        "Furn/Home Furnishings",
        "Homebuilding",
        "Hotel/Gaming",
        "Machinery",
        "Metals & Mining",
        "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)",
        "Oilfield Svcs/Equip.",
        "Paper/Forest Products",
        "Precious Metals",
        "Real Estate (Development)",
        "Retail (Automotive)",
        "Rubber& Tires",
        "Semiconductor",
        "Semiconductor Equip",
        "Shipbuilding & Marine",
        "Steel",
        "Transportation",
        "Trucking",
    }
)


def is_financial_services(industry: str | None) -> bool:
    """Whether ``industry`` is a Damodaran financial-services label (exact match)."""
    return industry in FINANCIAL_SERVICES_INDUSTRIES


def is_cyclical(industry: str | None) -> bool:
    """Whether ``industry`` is a Damodaran cyclical label (exact match)."""
    return industry in CYCLICAL_INDUSTRIES
```

- [ ] **Step 4: Correr y verificar que pasa**

Run: `uv run pytest tests/unit/test_reference_sectors.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Cablear `is_financial_services` en `build_company_data`**

En `src/bot/screener/engine.py`, agregá el import:

```python
from bot.reference.sectors import is_financial_services as industry_is_financial_services
```

En `build_company_data`, el label de industria ya se resuelve en la línea `industry = company.industry_damodaran or company.industry`. Clasificá **sólo** desde el label Damodaran — un label crudo de proveedor no debe clasificar:

```python
    industry = company.industry_damodaran or company.industry
    return CompanyData(
        ticker=company.ticker,
        name=company.name,
        industry=industry,
        region=_resolve_region(conn, company.country),
        market_cap=_market_cap_usd(conn, market_cap, currency, as_of),
        years_of_financials=len(annual),
        is_financial_services=industry_is_financial_services(company.industry_damodaran),
        net_debt=net_debt,
```

…dejando el resto de los argumentos exactamente como están.

Agregá a `tests/unit/test_screener_engine.py`:

```python
def test_build_company_data_flags_financial_services(conn: duckdb.DuckDBPyConnection) -> None:
    row = _CompanyRow(
        ticker="JPM",
        name="JPMorgan",
        country="United States",
        industry="Banks—Diversified",
        industry_damodaran="Bank (Money Center)",
    )
    data = build_company_data(conn, row, [], market_cap=None, close=None)
    assert data.is_financial_services is True


def test_build_company_data_does_not_classify_from_a_raw_provider_label(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Unmapped: classification must not fall back to the provider string.
    row = _CompanyRow(
        ticker="UNK",
        name="Unknown Bank Co",
        country="United States",
        industry="Banks—Diversified",
        industry_damodaran=None,
    )
    data = build_company_data(conn, row, [], market_cap=None, close=None)
    assert data.is_financial_services is False
```

Usá el import y el fixture de conexión que el archivo ya tiene (`_CompanyRow` viene de `bot.screener.engine`; mirá cómo lo construyen los tests existentes alrededor de `test_screener_engine.py:343`).

- [ ] **Step 6: Cablear `is_cyclical_sector` en `analyze`**

En `src/bot/valuator/analysis.py`, agregá el import:

```python
from bot.reference.sectors import is_cyclical
```

El problema: `analyze` recibe `is_cyclical_sector: bool = False` y los dos call sites de `engine.py` (líneas 72 y 104) nunca lo pasan. `company_row` ya carga `industry_damodaran` (`analysis.py:113`, `:128`). Derivalo cuando el caller no lo fuerza — cambiá el default a `None` para distinguir "no lo sé, derivalo" de "forzado a False":

```python
def analyze(
    ticker: str,
    conn: duckdb.DuckDBPyConnection,
    override_path: Path | None = None,
    *,
    is_cyclical_sector: bool | None = None,
    age_years: int | None = None,
    company: ValuationInput | None = None,
) -> Analysis:
```

Y en el cuerpo, justo antes de construir `ClassificationFinancials`:

```python
    # Derived from the company's Damodaran industry unless the caller forces it,
    # so StoryType.CYCLICAL is reachable from the CLI and the screener (§7.1).
    cyclical = (
        is_cyclical(company_row.industry_damodaran)
        if is_cyclical_sector is None
        else is_cyclical_sector
    )
```

…y reemplazá `SectorContext(is_cyclical=is_cyclical_sector)` por `SectorContext(is_cyclical=cyclical)`.

Actualizá el docstring del parámetro para decir que `None` = derivar del sector.

Agregá a `tests/unit/test_valuator_analysis.py`:

```python
def test_cyclical_story_reachable_from_the_sector(conn: duckdb.DuckDBPyConnection) -> None:
    # A steel company with volatile earnings must classify as cyclical without the
    # caller passing anything: the sector signal now comes from the DB.
    _seed_company(conn, ticker="STEEL", industry_damodaran="Steel")
    _seed_volatile_financials(conn, ticker="STEEL")
    result = analyze("STEEL", conn)
    assert result.story_type == StoryType.CYCLICAL.value


def test_caller_can_still_force_non_cyclical(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn, ticker="STEEL2", industry_damodaran="Steel")
    _seed_volatile_financials(conn, ticker="STEEL2")
    result = analyze("STEEL2", conn, is_cyclical_sector=False)
    assert result.story_type != StoryType.CYCLICAL.value
```

Los helpers `_seed_company` / `_seed_volatile_financials`: reusá los seeders que el archivo ya tiene. Si no existe uno que produzca earnings con CV > 0.50 (el umbral `_CYCLICAL_EARNINGS_CV`), escribilo con una serie explícita, por ejemplo `earnings_history=(100.0, 20.0, 180.0, 10.0, 150.0)`, y verificá el CV a mano antes de asumir que dispara.

- [ ] **Step 7: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS todo. Si algún test de screener existente empieza a fallar porque una empresa fixture ahora se excluye por financiera, es el fix funcionando: ajustá el fixture y anotalo en el commit.

```bash
git add src/bot/reference/ tests/unit/test_reference_sectors.py \
        src/bot/screener/engine.py tests/unit/test_screener_engine.py \
        src/bot/valuator/analysis.py tests/unit/test_valuator_analysis.py
git commit -m "feat(screener,valuator): classify financials and cyclicals from the taxonomy

is_financial_services was never populated, so the §6.2 exclusion was a substring
match on bank/insurance that let Investments & Asset Management, Brokerage &
Investment Banking, Financial Svcs. (Non-bank & Insurance), Reinsurance and REITs
through. is_cyclical_sector was never passed from any call site, so
StoryType.CYCLICAL was unreachable.

Both now derive from companies.industry_damodaran via an exact-match reference
module. Classification never falls back to a raw provider label.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.4: Cerrar el column map de Damodaran — desbloquea el DCF

> **Esta es la tarea más importante del plan.** Verificado reproduciendo el pipeline con el column map actual: `operating_margin`, `sales_to_capital`, `equity_weight` y `debt_weight` quedan `None`, y `Assumptions.to_dcf_assumptions()` los exige vía `_require`, así que levanta `ValueError: assumption 'operating_margin' is unresolved`. **`bot analyze` falla para toda empresa real, y en el screener toda candidata cae al placeholder de MoS = 0.5.** Los 558 tests pasan porque los fixtures insertan filas de `damodaran_industry` con esas columnas pobladas a mano.

`wacc.xls` **no** tiene columnas de márgenes ni múltiplos (headers verificados sobre el fixture: `Industry Name, Number of Firms, Beta, Cost of Equity, E/(D+E), Std Dev in Stock, Cost of Debt, Tax Rate, After-tax Cost of Debt, D/(D+E), Cost of Capital, Cost of Capital (Local Currency)`). Lo que sí se puede cerrar desde los dos archivos que ya se descargan:

| Columna DB | Fuente verificada |
|---|---|
| `debt_to_equity` | derivada de `D/(D+E)`: `D/E = w / (1 - w)` — **desbloquea equity/debt weights** |
| `beta_unlevered` | derivada: `beta_levered / (1 + (1 - tax_rate) * D/E)` |
| `damodaran_country.tax_rate` | hoja `Country Tax Rates` del mismo `ctryprem.xls` (header fila 0: `Country`, `Tax Rate`) |
| `damodaran_country.risk_free_rate` | celda pre-header de `wacc.xls` fila 8 col 3 (`'Long Term Treasury bond rate ='` = `0.0395`) |

`op_margin` y `sales_to_capital` necesitan datasets adicionales → Task 1.5.

**Files:**
- Modify: `src/bot/ingest/damodaran.py`
- Modify: `tests/unit/test_damodaran_parser.py`
- Create: `tests/unit/test_damodaran_derived.py`

**Interfaces:**
- Consumes: `_load_rows`, `_load_to_records`, `_to_normalized_rows`, `_coerce_value` (existentes).
- Produces:
  - `derive_industry_columns(row: dict[str, Any]) -> dict[str, Any]` — agrega `debt_to_equity` y `beta_unlevered` in-place-free.
  - `parse_country_tax_rates(path: Path) -> dict[str, float]`
  - `parse_preheader_scalar(path: Path, sheet_name: str, label: str) -> float | None`
  - `DEFAULT_INDUSTRY_COLUMN_MAP` gana `debt_weight_raw: "D/(D+E)"`.

- [ ] **Step 1: Escribir el test de regresión que prueba el bloqueo**

Create `tests/unit/test_damodaran_derived.py`:

```python
"""Damodaran columns derived from what the published files actually carry.

The published wacc.xls has no debt-to-equity column — it has D/(D+E). Without
deriving it, valuator/assumptions.py resolves equity_weight/debt_weight to None and
to_dcf_assumptions() raises, making the whole DCF unreachable in production.
"""

from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pytest

from bot.ingest.damodaran import (
    derive_industry_columns,
    parse_country_tax_rates,
    parse_preheader_scalar,
)
from bot.storage.db import apply_schema

_WACC_FIXTURE = Path("tests/fixtures/damodaran/wacc_sample.xls")
_CTRY_FIXTURE = Path("tests/fixtures/damodaran/ctryprem_sample.xls")


def test_debt_to_equity_derived_from_debt_weight() -> None:
    # D/(D+E) = 0.2 -> D/E = 0.2 / 0.8 = 0.25
    row = derive_industry_columns({"debt_weight_raw": 0.2, "beta_levered": 1.0, "tax_rate": 0.25})
    assert row["debt_to_equity"] == pytest.approx(0.25)


def test_debt_to_equity_zero_debt() -> None:
    row = derive_industry_columns({"debt_weight_raw": 0.0})
    assert row["debt_to_equity"] == pytest.approx(0.0)


def test_debt_to_equity_all_debt_is_undefined_not_infinite() -> None:
    # D/(D+E) = 1 means zero equity: D/E is undefined, not inf. Must not poison
    # the DB with a non-finite double.
    row = derive_industry_columns({"debt_weight_raw": 1.0})
    assert row["debt_to_equity"] is None


def test_debt_to_equity_absent_input_leaves_column_absent() -> None:
    row = derive_industry_columns({"beta_levered": 1.1})
    assert row.get("debt_to_equity") is None


def test_beta_unlevered_derived() -> None:
    # bl / (1 + (1-t) * D/E) = 1.2 / (1 + 0.75 * 0.25) = 1.2 / 1.1875
    row = derive_industry_columns(
        {"debt_weight_raw": 0.2, "beta_levered": 1.2, "tax_rate": 0.25}
    )
    assert row["beta_unlevered"] == pytest.approx(1.2 / 1.1875)


def test_beta_unlevered_needs_beta_and_leverage() -> None:
    assert derive_industry_columns({"beta_levered": 1.2}).get("beta_unlevered") is None
    assert derive_industry_columns({"debt_weight_raw": 0.2}).get("beta_unlevered") is None


def test_derive_does_not_mutate_its_input() -> None:
    original = {"debt_weight_raw": 0.2, "beta_levered": 1.0, "tax_rate": 0.25}
    snapshot = dict(original)
    derive_industry_columns(original)
    assert original == snapshot


def test_derive_drops_the_helper_column() -> None:
    # debt_weight_raw is a parsing artefact, not a DB column.
    row = derive_industry_columns({"debt_weight_raw": 0.2})
    assert "debt_weight_raw" not in row


@pytest.mark.skipif(not _CTRY_FIXTURE.exists(), reason="country fixture absent")
def test_parse_country_tax_rates_from_the_real_workbook() -> None:
    rates = parse_country_tax_rates(_CTRY_FIXTURE)
    assert rates["Australia"] == pytest.approx(0.30)
    assert rates["Bahamas"] == pytest.approx(0.0)
    assert rates["Argentina"] == pytest.approx(0.35)
    assert all(0.0 <= v <= 1.0 for v in rates.values())
    assert "Country" not in rates


@pytest.mark.skipif(not _WACC_FIXTURE.exists(), reason="industry fixture absent")
def test_parse_preheader_scalar_finds_the_risk_free_rate() -> None:
    rfr = parse_preheader_scalar(
        _WACC_FIXTURE, "Industry Averages", "Long Term Treasury bond rate ="
    )
    assert rfr == pytest.approx(0.0395)


@pytest.mark.skipif(not _WACC_FIXTURE.exists(), reason="industry fixture absent")
def test_parse_preheader_scalar_unknown_label_returns_none() -> None:
    assert parse_preheader_scalar(_WACC_FIXTURE, "Industry Averages", "Nope =") is None


@pytest.mark.skipif(
    not (_WACC_FIXTURE.exists() and _CTRY_FIXTURE.exists()), reason="fixtures absent"
)
def test_dcf_assumptions_resolve_after_the_real_import() -> None:
    """The regression this task exists for: analyze() must not raise.

    Imports both real fixtures, then resolves the assumption bundle for a company
    in a mapped industry and projects it onto the pure DCF inputs. Before this
    task that projection raised ValueError on operating_margin / sales_to_capital
    / equity_weight, so `bot analyze` failed for every real company.
    """
    from bot.ingest.damodaran import import_damodaran_from_files
    from bot.valuator.assumptions import resolve_assumptions

    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
    )
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES ('SEMI', 'Semi Co', 'United States', 'Semiconductors', 'Semiconductor', 'fmp')"
    )
    for year, revenue in ((2022, 100.0), (2023, 115.0), (2024, 130.0)):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, shares_diluted, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["SEMI", year, revenue, revenue * 0.25, 10.0, "fmp"],
        )

    assumptions = resolve_assumptions("SEMI", conn)
    assert assumptions.equity_weight.value is not None
    assert assumptions.debt_weight.value is not None
    weights = assumptions.equity_weight.value + assumptions.debt_weight.value
    assert weights == pytest.approx(1.0), "equity + debt weights must be a partition"
    assert math.isfinite(assumptions.debt_weight.value)
```

Nota: la última assertion sobre `operating_margin` / `sales_to_capital` se agrega en Task 1.5, que es la que trae esas columnas. Esta tarea cierra los weights.

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_damodaran_derived.py -q`
Expected: FAIL con `ImportError: cannot import name 'derive_industry_columns'`.

- [ ] **Step 3: Implementar las derivaciones y los parsers**

En `src/bot/ingest/damodaran.py`, extendé el column map con la columna cruda de leverage:

```python
DEFAULT_INDUSTRY_COLUMN_MAP: dict[str, str] = {
    "industry": "Industry Name",
    "beta_levered": "Beta",
    "cost_of_equity": "Cost of Equity",
    "cost_of_debt": "Cost of Debt",
    "tax_rate": "Tax Rate",
    # "Cost of Capital" is labelled "WACC" in the DB schema
    "wacc": "Cost of Capital",
    # Parsing artefact, not a DB column: the published file carries D/(D+E) and
    # `derive_industry_columns` turns it into debt_to_equity + beta_unlevered.
    "debt_weight_raw": "D/(D+E)",
}
```

Agregá las tres funciones nuevas:

```python
#: Label of the pre-header cell of wacc.xls carrying the long-term government bond
#: rate. It is an input to Damodaran's sheet, not a column, so it needs its own
#: extraction path.
RISK_FREE_RATE_LABEL = "Long Term Treasury bond rate ="

#: Sheet of ctryprem.xls carrying per-country corporate tax rates. The main
#: "ERPs by country" sheet has no tax column.
COUNTRY_TAX_SHEET = "Country Tax Rates"


def derive_industry_columns(row: dict[str, Any]) -> dict[str, Any]:
    """Return ``row`` with the industry columns the published file only implies.

    ``wacc.xls`` publishes ``D/(D+E)``, not debt-to-equity, and no unlevered beta.
    Both are what the valuator actually needs: ``debt_to_equity`` is the only input
    from which ``_resolve_weights`` can build the equity/debt split, without which
    every assumption bundle fails to project onto the DCF.

    - ``debt_to_equity = w / (1 - w)`` where ``w = D/(D+E)``. ``w == 1`` (zero
      equity) leaves it ``None``: the ratio is undefined, and a non-finite double
      must never reach the DB.
    - ``beta_unlevered = beta_levered / (1 + (1 - tax_rate) * D/E)`` (Hamada).

    Pure: the input is not mutated. The ``debt_weight_raw`` parsing artefact is
    dropped from the result.
    """
    out = dict(row)
    weight = out.pop("debt_weight_raw", None)

    debt_to_equity: float | None = None
    if isinstance(weight, (int, float)) and 0.0 <= float(weight) < 1.0:
        w = float(weight)
        debt_to_equity = w / (1.0 - w)
    if debt_to_equity is not None:
        out["debt_to_equity"] = debt_to_equity

    beta_levered = out.get("beta_levered")
    if debt_to_equity is not None and isinstance(beta_levered, (int, float)):
        tax_rate = out.get("tax_rate")
        t = float(tax_rate) if isinstance(tax_rate, (int, float)) else 0.0
        out["beta_unlevered"] = float(beta_levered) / (1.0 + (1.0 - t) * debt_to_equity)

    return out


def parse_country_tax_rates(path: Path) -> dict[str, float]:
    """Country → corporate tax rate from the ``Country Tax Rates`` sheet.

    The sheet's header sits on row 0 with ``Country`` / ``Tax Rate`` in the first two
    columns (a second, unrelated country/year block sits further right and is
    ignored). Rows whose rate is not a fraction in ``[0, 1]`` are skipped rather
    than trusted.
    """
    rows, _sheet = _load_rows(path, COUNTRY_TAX_SHEET)
    out: dict[str, float] = {}
    for raw in rows[1:]:
        if len(raw) < 2:
            continue
        country = raw[0]
        rate = _coerce_value(raw[1])
        if not isinstance(country, str) or not country.strip():
            continue
        if not isinstance(rate, (int, float)):
            continue
        value = float(rate)
        if not 0.0 <= value <= 1.0:
            continue
        out[country.strip()] = value
    return out


def parse_preheader_scalar(path: Path, sheet_name: str, label: str) -> float | None:
    """Scalar input stored in a pre-header cell, found by its adjacent label.

    Damodaran's sheets carry inputs (the risk-free rate, the mature-market ERP)
    above the data header as ``label``/``value`` cell pairs rather than as columns.
    Scans for a cell whose text starts with ``label`` and returns the first numeric
    cell to its right on the same row. ``None`` when the label is absent.
    """
    rows, _sheet = _load_rows(path, sheet_name)
    needle = label.strip().lower()
    for raw in rows:
        for index, cell in enumerate(raw):
            if not isinstance(cell, str) or not cell.strip().lower().startswith(needle):
                continue
            for candidate in raw[index + 1 :]:
                value = _coerce_value(candidate)
                if isinstance(value, (int, float)):
                    return float(value)
    return None
```

- [ ] **Step 4: Aplicar las derivaciones en el import**

En `_import_files_into_run`, después de normalizar las filas de industria y antes del upsert, mapeá cada fila por `derive_industry_columns`, y enriquecé las filas de país con tax rate y risk-free rate. Leé la función primero (`grep -n "_import_files_into_run" -A 40 src/bot/ingest/damodaran.py`) y aplicá:

```python
    industry_rows = [derive_industry_columns(row) for row in industry_rows]

    tax_rates = parse_country_tax_rates(country_path)
    risk_free_rate = parse_preheader_scalar(
        industry_path, "Industry Averages", RISK_FREE_RATE_LABEL
    )
    for row in country_rows:
        country = row.get("country")
        if isinstance(country, str) and country in tax_rates:
            row["tax_rate"] = tax_rates[country]
        if risk_free_rate is not None:
            row["risk_free_rate"] = risk_free_rate
```

`parse_country_tax_rates` puede levantar si la hoja no existe en un archivo futuro; envolvela para degradar (spec §13.2):

```python
    try:
        tax_rates = parse_country_tax_rates(country_path)
    except (KeyError, ValueError) as exc:
        log.warning("damodaran.country_tax_sheet.unavailable", error=str(exc))
        tax_rates = {}
```

Verificá el nombre exacto del logger que el módulo ya usa antes de escribir `log.warning`.

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/unit/test_damodaran_derived.py tests/unit/test_damodaran_parser.py tests/integration/test_damodaran_import.py -q`
Expected: PASS.

Si `test_dcf_assumptions_resolve_after_the_real_import` falla en la assertion de weights, imprimí lo que se importó de verdad antes de tocar la derivación:

```bash
uv run python -c "
import duckdb
from pathlib import Path
from bot.storage.db import apply_schema
from bot.ingest.damodaran import import_damodaran_from_files
conn = duckdb.connect(':memory:'); apply_schema(conn)
import_damodaran_from_files(conn,
    industry_path=Path('tests/fixtures/damodaran/wacc_sample.xls'),
    country_path=Path('tests/fixtures/damodaran/ctryprem_sample.xls'),
    region='US', year=2026)
print(conn.execute('SELECT industry, beta_levered, beta_unlevered, debt_to_equity, tax_rate FROM damodaran_industry WHERE industry = ?', ['Semiconductor']).fetchall())
print(conn.execute('SELECT country, erp, risk_free_rate, tax_rate FROM damodaran_country WHERE country = ?', ['United States']).fetchall())
"
```

- [ ] **Step 6: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/ingest/damodaran.py tests/unit/test_damodaran_derived.py
git commit -m "fix(ingest): derive debt_to_equity so the DCF is reachable at all

wacc.xls publishes D/(D+E), not debt-to-equity, and the column map ignored it. With
damodaran_industry.debt_to_equity always NULL, _resolve_weights returned (None,
None) and to_dcf_assumptions() raised — so \`bot analyze\` failed for every real
company and every screener candidate fell back to the MoS placeholder. The 558
tests passed only because fixtures hand-populate the column.

Derive debt_to_equity (guarding the zero-equity case against a non-finite double)
and beta_unlevered via Hamada. Also fill the two country columns the published
files carry outside the main sheet: tax_rate from the Country Tax Rates sheet and
risk_free_rate from the pre-header input cell.

op_margin and sales_to_capital need additional datasets — next commit.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.5: Datasets Damodaran adicionales para las columnas que faltan

Después de 1.4 siguen `None` dos assumptions **requeridas** (`operating_margin`, `sales_to_capital`) y todos los múltiplos que usa el sanity check §7.7 y las value indicators §6.3 (`pe`, `pbv`, `ev_ebitda`, `roe`, `roic`, `net_margin`, `ev_sales`). No están en `wacc.xls`: viven en otros archivos de la misma librería de datasets.

**Esta tarea empieza con un paso de descubrimiento.** No hardcodees nombres de hoja ni strings de header adivinados: la tarea provee el script que los imprime y vos registrás lo observado en el registro de datasets. Un header equivocado produce una columna silenciosamente `NULL`, que es exactamente el bug que estamos cerrando.

**Files:**
- Modify: `src/bot/ingest/damodaran.py`
- Create: `tests/unit/test_damodaran_datasets.py`
- Create: `tests/fixtures/damodaran/` — un `.xls` sample por dataset nuevo

**Interfaces:**
- Consumes: `_load_to_records`, `_to_normalized_rows`, `derive_industry_columns`, `download_dataset`.
- Produces:
  - `INDUSTRY_DATASETS: tuple[IndustryDataset, ...]` — registro declarativo.
  - `IndustryDataset` — dataclass frozen: `key`, `url`, `sheet_keywords`, `column_map`.
  - `merge_industry_datasets(parts: Sequence[list[dict[str, Any]]]) -> list[dict[str, Any]]` — outer join por `industry`.

- [ ] **Step 1: Descubrir hojas y headers reales**

Corré este script. Descarga cada candidato a un directorio temporal e imprime nombres de hoja, fila de header detectada y los headers.

```bash
uv run python - <<'PY'
from pathlib import Path
from bot.ingest.damodaran import download_dataset, _load_rows, _find_header_row, _pick_sheet

BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
CANDIDATES = ["margin.xls", "capex.xls", "pedata.xls", "vebitda.xls", "pbvdata.xls", "eva.xls"]
dest = Path("/tmp/damodaran-discovery"); dest.mkdir(parents=True, exist_ok=True)

for name in CANDIDATES:
    try:
        path = download_dataset(BASE + name, dest / name)
    except Exception as exc:
        print(f"\n### {name}: DOWNLOAD FAILED: {type(exc).__name__}: {exc}")
        continue
    try:
        import xlrd
        wb = xlrd.open_workbook(path)
        print(f"\n### {name}\nsheets: {wb.sheet_names()}")
    except Exception as exc:
        print(f"\n### {name}: sheet listing failed: {exc}")
        continue
    for sheet in wb.sheet_names():
        rows, _ = _load_rows(path, sheet)
        idx = _find_header_row(rows)
        if idx is None:
            continue
        headers = [c for c in rows[idx] if isinstance(c, str) and c.strip()]
        if any("industry" in h.lower() for h in headers):
            print(f"  sheet={sheet!r} header_row={idx}")
            print(f"  headers={headers}")
PY
```

Verificá primero los nombres reales de los helpers privados (`grep -n "^def _find_header_row\|^def _pick_sheet" src/bot/ingest/damodaran.py`) y ajustá el script.

**Registrá el resultado** en el docstring del registro que escribís en el Step 3: URL, nombre de hoja y string de header exacto por cada columna. Si un candidato 404ea, sacalo del registro y anotá en el commit qué columna queda sin fuente.

- [ ] **Step 2: Guardar fixtures y escribir el test que falla**

Para cada dataset que respondió, recortá un sample pequeño a `tests/fixtures/damodaran/<key>_sample.xls` siguiendo el patrón de los dos que ya existen (mismas hojas, header en la misma fila, un puñado de industries incluyendo `Semiconductor` y `Software (System & Application)`).

Create `tests/unit/test_damodaran_datasets.py`:

```python
"""Additional Damodaran industry datasets (margins, sales-to-capital, multiples).

wacc.xls carries only cost-of-capital columns. operating_margin and
sales_to_capital are *required* by to_dcf_assumptions, and the multiples feed the
§6.3 value indicators and the §7.7 sanity check. Each lives in its own published
file, merged here on the industry label.
"""

from __future__ import annotations

from typing import Any

import pytest

from bot.ingest.damodaran import (
    INDUSTRY_DATASETS,
    merge_industry_datasets,
)


def test_registry_covers_every_column_the_consumers_select() -> None:
    # These are the columns valuator/assumptions.py, valuator/analysis.py and
    # screener/benchmarks.py actually SELECT. Every one needs a source.
    required = {
        "op_margin",
        "net_margin",
        "sales_to_capital",
        "pe",
        "pbv",
        "ev_ebitda",
        "ev_sales",
        "roe",
        "roic",
    }
    covered: set[str] = set()
    for dataset in INDUSTRY_DATASETS:
        covered |= set(dataset.column_map) - {"industry"}
    missing = required - covered
    assert not missing, f"no dataset supplies: {sorted(missing)}"


def test_registry_keys_are_unique() -> None:
    keys = [d.key for d in INDUSTRY_DATASETS]
    assert len(keys) == len(set(keys))


def test_merge_is_an_outer_join_on_industry() -> None:
    a: list[dict[str, Any]] = [
        {"industry": "Semiconductor", "wacc": 0.09},
        {"industry": "Steel", "wacc": 0.08},
    ]
    b: list[dict[str, Any]] = [
        {"industry": "Semiconductor", "op_margin": 0.25},
        {"industry": "Software (System & Application)", "op_margin": 0.18},
    ]
    merged = {row["industry"]: row for row in merge_industry_datasets([a, b])}
    assert merged["Semiconductor"]["wacc"] == pytest.approx(0.09)
    assert merged["Semiconductor"]["op_margin"] == pytest.approx(0.25)
    assert merged["Steel"]["wacc"] == pytest.approx(0.08)
    assert "op_margin" not in merged["Steel"]
    assert merged["Software (System & Application)"]["op_margin"] == pytest.approx(0.18)


def test_merge_later_dataset_does_not_overwrite_a_present_value() -> None:
    # The cost-of-capital file is authoritative for tax_rate; a later file that
    # happens to carry the same column must not clobber it.
    merged = merge_industry_datasets(
        [[{"industry": "Steel", "tax_rate": 0.25}], [{"industry": "Steel", "tax_rate": 0.99}]]
    )
    assert merged[0]["tax_rate"] == pytest.approx(0.25)


def test_merge_skips_rows_without_an_industry() -> None:
    merged = merge_industry_datasets([[{"op_margin": 0.2}, {"industry": "Steel"}]])
    assert [r["industry"] for r in merged] == ["Steel"]


def test_merge_of_nothing_is_empty() -> None:
    assert merge_industry_datasets([]) == []
```

- [ ] **Step 3: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_damodaran_datasets.py -q`
Expected: FAIL con `ImportError: cannot import name 'INDUSTRY_DATASETS'`.

- [ ] **Step 4: Implementar el registro y el merge**

En `src/bot/ingest/damodaran.py`. Los `column_map` de abajo se llenan con **lo que observaste en el Step 1** — el esqueleto lleva las claves DB destino y un comentario por dataset; reemplazá cada string de header por el exacto.

```python
@dataclass(frozen=True)
class IndustryDataset:
    """One published Damodaran industry file and how to read it.

    Attributes:
        key: Short identifier, also the fixture filename stem.
        url: Published location.
        sheet_keywords: Passed to the existing sheet auto-detection.
        column_map: DB column → exact header string, as observed in the file.
            ``industry`` must be first: ``_to_normalized_rows`` treats the first
            key as the primary key of the row.
    """

    key: str
    url: str
    sheet_keywords: tuple[str, ...]
    column_map: dict[str, str]


_DATASET_BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"

#: Industry datasets merged into ``damodaran_industry``, in precedence order: an
#: earlier dataset's value for a column wins over a later one's.
#:
#: Sheet names and header strings below were observed directly from the published
#: files (see the discovery step in the plan) — do NOT guess them: a wrong header
#: silently yields a NULL column, which is the failure mode this registry exists
#: to eliminate.
INDUSTRY_DATASETS: tuple[IndustryDataset, ...] = (
    IndustryDataset(
        key="wacc",
        url=_DATASET_BASE + "wacc.xls",
        sheet_keywords=("industry", "average"),
        column_map=DEFAULT_INDUSTRY_COLUMN_MAP,
    ),
    # margin.xls — operating and net margins.
    IndustryDataset(
        key="margin",
        url=_DATASET_BASE + "margin.xls",
        sheet_keywords=("industry", "margin"),
        column_map={
            "industry": "Industry Name",
            "op_margin": "<observed header for pre-tax operating margin>",
            "net_margin": "<observed header for net margin>",
        },
    ),
    # capex.xls — sales-to-capital / reinvestment.
    IndustryDataset(
        key="capex",
        url=_DATASET_BASE + "capex.xls",
        sheet_keywords=("industry",),
        column_map={
            "industry": "Industry Name",
            "sales_to_capital": "<observed header for sales/capital>",
            "reinvestment_rate": "<observed header for reinvestment rate>",
        },
    ),
    # pedata.xls — earnings multiples.
    IndustryDataset(
        key="pedata",
        url=_DATASET_BASE + "pedata.xls",
        sheet_keywords=("industry",),
        column_map={"industry": "Industry Name", "pe": "<observed header for current PE>"},
    ),
    # pbvdata.xls — book multiples and ROE.
    IndustryDataset(
        key="pbvdata",
        url=_DATASET_BASE + "pbvdata.xls",
        sheet_keywords=("industry",),
        column_map={
            "industry": "Industry Name",
            "pbv": "<observed header for PBV>",
            "roe": "<observed header for ROE>",
        },
    ),
    # vebitda.xls — enterprise-value multiples.
    IndustryDataset(
        key="vebitda",
        url=_DATASET_BASE + "vebitda.xls",
        sheet_keywords=("industry",),
        column_map={
            "industry": "Industry Name",
            "ev_ebitda": "<observed header for EV/EBITDA>",
            "ev_sales": "<observed header for EV/Sales>",
        },
    ),
    # eva.xls — returns on capital.
    IndustryDataset(
        key="eva",
        url=_DATASET_BASE + "eva.xls",
        sheet_keywords=("industry",),
        column_map={"industry": "Industry Name", "roic": "<observed header for ROIC>"},
    ),
)


def merge_industry_datasets(
    parts: Sequence[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Outer-join per-dataset industry rows on the ``industry`` label.

    Earlier datasets win: a column already carrying a non-``None`` value is not
    overwritten by a later dataset, so the cost-of-capital file stays authoritative
    for the columns it publishes. Rows without an ``industry`` are dropped. Insertion
    order of first appearance is preserved so the output is deterministic.
    """
    merged: dict[str, dict[str, Any]] = {}
    for part in parts:
        for row in part:
            industry = row.get("industry")
            if not isinstance(industry, str) or not industry.strip():
                continue
            target = merged.setdefault(industry, {"industry": industry})
            for column, value in row.items():
                if column == "industry" or value is None:
                    continue
                if target.get(column) is None:
                    target[column] = value
    return list(merged.values())
```

Agregá `Sequence` al import de `collections.abc` y `dataclass` si no están ya.

- [ ] **Step 5: Cablear el registro en el import**

Refactorizá `import_damodaran` para iterar `INDUSTRY_DATASETS`: descargar cada uno, parsearlo con su `column_map`, y mergear antes del upsert. Un dataset que falla al descargar o parsear se saltea con warning y el resultado queda `partial` — no aborta la corrida (spec §13.2). Mantené `import_damodaran_from_files` funcionando con los dos archivos que ya recibe (es el que usan los tests), agregando un parámetro opcional para los extras:

```python
def import_damodaran_from_files(
    conn: duckdb.DuckDBPyConnection,
    *,
    industry_path: Path,
    country_path: Path,
    region: str,
    year: int,
    extra_industry_paths: dict[str, Path] | None = None,
) -> IngestResult:
```

donde las claves de `extra_industry_paths` son los `key` del registro. Así los tests existentes siguen pasando sin cambios y los nuevos pueden inyectar fixtures.

- [ ] **Step 6: Extender el test de regresión del DCF**

En `tests/unit/test_damodaran_derived.py`, ahora que las columnas existen, agregá al final de `test_dcf_assumptions_resolve_after_the_real_import` (pasando los fixtures nuevos vía `extra_industry_paths`):

```python
    # The projection that used to raise: all six critical assumptions resolve.
    dcf_inputs = assumptions.to_dcf_assumptions()
    assert dcf_inputs.operating_margin, "operating margin path must be non-empty"
    assert dcf_inputs.sales_to_capital > 0.0
    assert 0.0 < dcf_inputs.terminal_growth < 1.0
```

- [ ] **Step 7: Verificar el smoke test real end-to-end**

Este es el criterio de aceptación de la fase: `bot analyze` tiene que producir un reporte contra datos importados de verdad.

Run: `uv run pytest tests/unit/test_damodaran_datasets.py tests/unit/test_damodaran_derived.py tests/unit/test_cli_analyze.py -q`
Expected: PASS.

- [ ] **Step 8: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/ingest/damodaran.py tests/unit/test_damodaran_datasets.py \
        tests/unit/test_damodaran_derived.py tests/fixtures/damodaran/
git commit -m "feat(ingest): merge the additional Damodaran industry datasets

wacc.xls carries only cost-of-capital columns, so op_margin, sales_to_capital and
every multiple stayed NULL. operating_margin and sales_to_capital are *required* by
to_dcf_assumptions, so together with the previous commit this is what makes the DCF
run on real data; the multiples feed the §6.3 value indicators and the §7.7 sanity
check.

Declarative registry (url + sheet + observed header strings per dataset) merged
outer-join on the industry label, earlier datasets winning. A dataset that fails to
download degrades to a partial run rather than aborting (§13.2).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.6: Normalización a USD en el ingest

`src/bot/utils/fx.py` está impecablemente testeado (nearest-prior con feriados, nunca mira al futuro, `LookupError` explícito) y hoy **su único consumidor en producción es `engine._market_cap_usd`**, que convierte en el punto de consumo. La decisión tomada es convertir en el ingest con columnas USD explícitas, conservando el valor local.

> **Refinamiento de alcance, declarado explícitamente.** La opción elegida era "columnas USD explícitas (ej. `revenue`, `revenue_usd`)". Aplicada literalmente a `financials_annual` significa duplicar 20 columnas monetarias. Este plan implementa: columnas `*_usd` explícitas para las magnitudes que **sí** se comparan en absoluto entre empresas (`market_cap_usd`, `close_usd`), más `fx_rate_to_usd` por fila en las tres tablas para que cualquier consumidor futuro convierta con trazabilidad y sin re-consultar FX. Razón: las reglas del screener que leen las otras 18 columnas lo hacen como ratios currency-self-consistent (net_debt/EBITDA, goodwill/assets, accruals/assets), y el DCF trabaja íntegramente en una moneda y divide por acciones, así que su valor por acción ya es comparable contra el precio local — convertirlas no arregla ningún bug y ensancha la tabla al doble. Si preferís las 20 columnas completas, es un cambio aditivo sobre esta base.

**Files:**
- Modify: `src/bot/storage/schema.sql`
- Modify: `src/bot/ingest/fmp.py` — `upsert_prices_daily`, `import_prices_from_fmp`
- Modify: `src/bot/screener/engine.py` — `_load_latest_prices`, `build_company_data`
- Create: `tests/unit/test_prices_usd.py`
- Modify: `tests/integration/test_prices_import.py`

**Interfaces:**
- Consumes: `bot.utils.fx.get_fx_rate`.
- Produces: `prices_daily.market_cap_usd`, `prices_daily.close_usd`, `prices_daily.fx_rate_to_usd`, `financials_annual.fx_rate_to_usd`, `financials_quarterly.fx_rate_to_usd`. `build_company_data` deja de convertir en vuelo y lee `market_cap_usd`.

- [ ] **Step 1: Escribir el test que falla**

Create `tests/unit/test_prices_usd.py`:

```python
"""USD normalisation at ingest for the absolute-magnitude price columns (§4.3.2)."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from bot.ingest.fmp import upsert_prices_daily
from bot.storage.db import apply_schema
from bot.utils.fx import upsert_fx_rates


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    apply_schema(connection)
    return connection


def _row(d: str = "2026-03-02") -> dict[str, object]:
    return {"date": d, "close": 200.0, "volume": 1_000.0, "market_cap": 2_000_000.0}


def test_usd_listing_needs_no_rate(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_prices_daily(conn, ticker="AAPL", rows=[_row()], currency="USD")
    close_usd, cap_usd, rate = conn.execute(
        "SELECT close_usd, market_cap_usd, fx_rate_to_usd FROM prices_daily "
        "WHERE ticker = 'AAPL'"
    ).fetchone()
    assert close_usd == pytest.approx(200.0)
    assert cap_usd == pytest.approx(2_000_000.0)
    assert rate == pytest.approx(1.0)


def test_foreign_listing_is_converted(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_fx_rates(conn, currency="EUR", rows=[{"date": "2026-03-02", "rate_to_usd": 1.10}])
    upsert_prices_daily(conn, ticker="SAP.DE", rows=[_row()], currency="EUR")
    close_usd, cap_usd, rate = conn.execute(
        "SELECT close_usd, market_cap_usd, fx_rate_to_usd FROM prices_daily "
        "WHERE ticker = 'SAP.DE'"
    ).fetchone()
    assert rate == pytest.approx(1.10)
    assert close_usd == pytest.approx(220.0)
    assert cap_usd == pytest.approx(2_200_000.0)


def test_local_values_are_preserved(conn: duckdb.DuckDBPyConnection) -> None:
    # Auditability: the figure as quoted must survive alongside the conversion.
    upsert_fx_rates(conn, currency="EUR", rows=[{"date": "2026-03-02", "rate_to_usd": 1.10}])
    upsert_prices_daily(conn, ticker="SAP.DE", rows=[_row()], currency="EUR")
    close, cap, currency = conn.execute(
        "SELECT close, market_cap, currency FROM prices_daily WHERE ticker = 'SAP.DE'"
    ).fetchone()
    assert close == pytest.approx(200.0)
    assert cap == pytest.approx(2_000_000.0)
    assert currency == "EUR"


def test_missing_rate_leaves_usd_null_and_does_not_raise(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Graceful degradation (§13.2): no FX row must not abort a price import. The
    # gate that needs USD then sees NULL and skips, rather than comparing a JPY
    # market cap against a USD threshold.
    upsert_prices_daily(conn, ticker="7203.T", rows=[_row()], currency="JPY")
    close_usd, cap_usd, rate = conn.execute(
        "SELECT close_usd, market_cap_usd, fx_rate_to_usd FROM prices_daily "
        "WHERE ticker = '7203.T'"
    ).fetchone()
    assert close_usd is None
    assert cap_usd is None
    assert rate is None


def test_unknown_currency_leaves_usd_null(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_prices_daily(conn, ticker="NOCCY", rows=[_row()], currency=None)
    cap_usd = conn.execute(
        "SELECT market_cap_usd FROM prices_daily WHERE ticker = 'NOCCY'"
    ).fetchone()[0]
    assert cap_usd is None


def test_rate_is_the_nearest_prior_not_a_future_one(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    upsert_fx_rates(
        conn,
        currency="EUR",
        rows=[
            {"date": "2026-02-27", "rate_to_usd": 1.05},
            {"date": "2026-03-05", "rate_to_usd": 1.30},
        ],
    )
    upsert_prices_daily(conn, ticker="SAP.DE", rows=[_row("2026-03-02")], currency="EUR")
    rate = conn.execute(
        "SELECT fx_rate_to_usd FROM prices_daily WHERE ticker = 'SAP.DE'"
    ).fetchone()[0]
    assert rate == pytest.approx(1.05), "must not borrow a later rate"


def test_reimport_refreshes_the_conversion(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_prices_daily(conn, ticker="SAP.DE", rows=[_row()], currency="EUR")
    assert (
        conn.execute(
            "SELECT market_cap_usd FROM prices_daily WHERE ticker = 'SAP.DE'"
        ).fetchone()[0]
        is None
    )
    upsert_fx_rates(conn, currency="EUR", rows=[{"date": "2026-03-02", "rate_to_usd": 1.10}])
    upsert_prices_daily(conn, ticker="SAP.DE", rows=[_row()], currency="EUR")
    assert conn.execute(
        "SELECT market_cap_usd FROM prices_daily WHERE ticker = 'SAP.DE'"
    ).fetchone()[0] == pytest.approx(2_200_000.0)


def test_date_objects_accepted(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_fx_rates(conn, currency="EUR", rows=[{"date": date(2026, 3, 2), "rate_to_usd": 1.10}])
    upsert_prices_daily(conn, ticker="SAP.DE", rows=[_row()], currency="EUR")
    assert conn.execute(
        "SELECT fx_rate_to_usd FROM prices_daily WHERE ticker = 'SAP.DE'"
    ).fetchone()[0] == pytest.approx(1.10)
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_prices_usd.py -q`
Expected: FAIL con `Binder Error: Referenced column "close_usd" not found`.

- [ ] **Step 3: Extender el schema**

En `src/bot/storage/schema.sql`, agregá a `prices_daily` (después de `currency`):

```sql
    close_usd       DOUBLE,
    market_cap_usd  DOUBLE,
    fx_rate_to_usd  DOUBLE,
```

Y a `financials_annual` y `financials_quarterly` (después de `currency` en cada una):

```sql
    fx_rate_to_usd  DOUBLE,
```

Agregá un comentario arriba de `prices_daily` explicando la convención:

```sql
-- `close` / `market_cap` are as quoted, in `currency`. The `*_usd` columns carry
-- the same figures converted at `fx_rate_to_usd`, the nearest-prior rate on `date`
-- (spec §4.3.2). All three USD columns are NULL together when no rate is available:
-- a consumer needing USD skips, rather than comparing a foreign figure against a
-- USD threshold. Currency-self-consistent ratios read the local columns.
```

`apply_schema` es idempotente vía `CREATE TABLE IF NOT EXISTS`, así que una DB existente **no** gana las columnas. Agregá las sentencias de migración siguiendo el patrón que ya use el archivo para migraciones (buscá con `grep -n "ALTER TABLE" src/bot/storage/schema.sql`); si no hay ninguna, agregalas al final:

```sql
ALTER TABLE prices_daily ADD COLUMN IF NOT EXISTS close_usd DOUBLE;
ALTER TABLE prices_daily ADD COLUMN IF NOT EXISTS market_cap_usd DOUBLE;
ALTER TABLE prices_daily ADD COLUMN IF NOT EXISTS fx_rate_to_usd DOUBLE;
ALTER TABLE financials_annual ADD COLUMN IF NOT EXISTS fx_rate_to_usd DOUBLE;
ALTER TABLE financials_quarterly ADD COLUMN IF NOT EXISTS fx_rate_to_usd DOUBLE;
```

Verificá que DuckDB acepta `ADD COLUMN IF NOT EXISTS` en la versión pineada; si no, envolvé cada `ALTER` con un chequeo previo contra `information_schema.columns` en `apply_schema`.

- [ ] **Step 4: Convertir en `upsert_prices_daily`**

En `src/bot/ingest/fmp.py`, agregá el import:

```python
from bot.utils.fx import get_fx_rate
```

Extendé `upsert_prices_daily`. La conversión usa `get_fx_rate` (no `to_usd`) porque necesitamos guardar la tasa además del valor, y porque `to_usd` levanta `LookupError` cuando no hay tasa mientras que acá queremos degradar a `NULL`:

```python
        rate: float | None = None
        if currency is not None:
            rate = get_fx_rate(conn, currency, parsed_date)
        close = _float_or_none(r.get("close"))
        market_cap = _float_or_none(r.get("market_cap"))
        close_usd = close * rate if close is not None and rate is not None else None
        market_cap_usd = (
            market_cap * rate if market_cap is not None and rate is not None else None
        )
```

Y extendé el `INSERT`:

```sql
INSERT INTO prices_daily
    (ticker, date, close, volume, market_cap, currency,
     close_usd, market_cap_usd, fx_rate_to_usd, source)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

`parsed_date` tiene que ser el `datetime.date` de la fila; la función ya normaliza la fecha a ISO para el `DELETE` — reusá ese valor parseado en lugar de re-parsear.

- [ ] **Step 5: Leer la columna en el screener en vez de convertir en vuelo**

En `src/bot/screener/engine.py`:
1. Agregá `market_cap_usd` al `SELECT` de `_load_latest_prices` y al dataclass de la fila de precio.
2. Reemplazá el parámetro `market_cap=_market_cap_usd(conn, market_cap, currency, as_of)` de `build_company_data` por `market_cap=market_cap_usd`, agregando `market_cap_usd: float | None` como parámetro keyword-only.
3. Borrá `_market_cap_usd` y su import de `to_usd` si queda sin uso (`grep -n "_market_cap_usd\|to_usd" src/bot/screener/engine.py`).
4. `market_cap` (local) se sigue pasando porque `ev_ebitda` y `fcf_yield` lo usan como ratio.

Actualizá el docstring de `CompanyData.market_cap` en `src/bot/screener/types.py`: ya no dice "deferred (G2 #2)", ahora la conversión pasa en el ingest.

Ajustá los tests de `test_screener_engine.py` que llaman `build_company_data` para pasar `market_cap_usd=...`.

- [ ] **Step 6: Assertion en el test de integración**

En `tests/integration/test_prices_import.py`, agregá:

```python
def test_usd_columns_populated_for_a_usd_listing(...) -> None:
    # Reuse the existing cassette-backed import in this module, then:
    rows = conn.execute(
        "SELECT close, close_usd, fx_rate_to_usd FROM prices_daily "
        "WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        [ticker],
    ).fetchone()
    close, close_usd, rate = rows
    assert rate == pytest.approx(1.0)
    assert close_usd == pytest.approx(close)
```

Adaptá la firma y los nombres al patrón real del archivo.

- [ ] **Step 7: Correr y verificar**

Run: `uv run pytest tests/unit/test_prices_usd.py tests/unit/test_screener_engine.py tests/integration/test_prices_import.py -q`
Expected: PASS.

- [ ] **Step 8: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/storage/schema.sql src/bot/ingest/fmp.py src/bot/screener/engine.py \
        src/bot/screener/types.py tests/unit/test_prices_usd.py \
        tests/unit/test_screener_engine.py tests/integration/test_prices_import.py
git commit -m "feat(ingest): normalise prices to USD at ingest (§4.3.2)

utils/fx.py was fully tested with a single production caller that converted at the
point of consumption. Move the conversion to ingest: prices_daily gains close_usd,
market_cap_usd and fx_rate_to_usd (nearest-prior rate on the price date), with the
as-quoted figures and currency preserved for auditability. All three USD columns are
NULL together when no rate exists, so a consumer needing USD skips rather than
comparing a foreign figure against a USD threshold.

financials_annual/quarterly gain fx_rate_to_usd for traceability; their monetary
columns stay local because every rule reading them does so as a
currency-self-consistent ratio and the DCF is single-currency end to end.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Fase 2 — Borrar el código muerto

Criterio aplicado: se conecta lo conectable (hecho en Fase 1), se borra lo que no tiene fuente de datos, y cada borrado deja un issue de backlog. El objetivo es que el código refleje sólo lo que realmente corre.

### Task 2.1: Borrar la regla de auditor/late-filings y sus campos

`AuditorChangesAndLateFilings` siempre devuelve `passed=True`: `auditor_changed` y `late_filings` no se pueblan en ningún lado (verificado: 100% de los hits son `types.py`, `rules.py` y tests). Poblarlos requiere scrapear los formularios 8-K item 4.01 y NT-10K de SEC — fuera de alcance hoy. Una regla eliminatoria que nunca elimina es peor que su ausencia: da la impresión de que el governance filter del §6.4 está activo.

**Files:**
- Modify: `src/bot/screener/types.py`, `src/bot/screener/rules.py`
- Modify: `config/presets/damodaran_value.yaml:69`, `deep_value.yaml:77`, `qarp.yaml:76`
- Modify: `tests/unit/test_screener_trap_detection.py` (borrar el bloque de líneas ~318-365)

**Interfaces:**
- Consumes: nada.
- Produces: `AuditorChangesAndLateFilings` y el nombre de registro `auditor_changes_and_late_filings` dejan de existir. `get_rule("auditor_changes_and_late_filings")` levanta `KeyError` — el loader de config ya rechaza nombres desconocidos, así que un preset stale falla al cargar en vez de silenciosamente no filtrar.

- [ ] **Step 1: Escribir el test que fija el borrado**

Agregá a `tests/unit/test_screener_rules.py`:

```python
def test_auditor_rule_is_gone_and_fails_loudly() -> None:
    # Deleted in Fase 2: the flags it read had no production data source, so it
    # always passed. A stale preset referencing it must fail at load, not silently
    # skip a governance filter it never applied.
    from bot.screener.rules import get_rule, registered_rules

    assert "auditor_changes_and_late_filings" not in registered_rules()
    with pytest.raises(KeyError, match="unknown rule"):
        get_rule("auditor_changes_and_late_filings")
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_screener_rules.py -q -k auditor`
Expected: FAIL — `assert 'auditor_changes_and_late_filings' not in {...}`.

- [ ] **Step 3: Borrar**

1. `src/bot/screener/rules.py`: borrá la clase `AuditorChangesAndLateFilings` completa (última del archivo, ~líneas 728-750).
2. `src/bot/screener/types.py`: borrá los campos `auditor_changed` y `late_filings` con sus docstrings (líneas ~67-73).
3. Los tres presets: borrá la línea `- name: auditor_changes_and_late_filings` de la sección `trap_detection`.
4. `tests/unit/test_screener_trap_detection.py`: borrá los 5 tests que la ejercitan y su import.

- [ ] **Step 4: Correr y verificar**

Run: `uv run pytest tests/unit/test_screener_rules.py tests/unit/test_screener_trap_detection.py tests/unit/test_screener_config.py -q`
Expected: PASS. `test_screener_config.py` tiene tests que pinnean los defaults del spec — si alguno cuenta las reglas de trap detection, actualizá el conteo.

- [ ] **Step 5: Abrir el issue de backlog**

```bash
gh issue create \
  --title "Governance trap detector: auditor changes + late filings need a SEC data source" \
  --body "Spec §6.4 lists auditor changes and late filings as trap-detection signals.
The rule and its \`CompanyData\` fields were deleted in the Fase 2 cleanup
(plan: docs/superpowers/plans/2026-08-09-remediacion-wiring-limpieza-bugs.md)
because nothing populated them, so the rule always returned passed=True — an
eliminatory gate that never eliminated.

To restore it, ingest needs:
- **Auditor change**: SEC 8-K item 4.01 filings per CIK.
- **Late filing**: NT 10-K / NT 10-Q forms in the filing history.

Both are reachable from the EDGAR submissions endpoint already used by
\`src/bot/ingest/sec_edgar.py\`, but only for US filers — non-US companies
imported via FMP would have no equivalent, so the rule must skip rather than
fail for them.

Re-add the rule together with its data source, not before." \
  --label enhancement
```

Agregá el issue al project Backlog (`nicolas-ricc/projects/2`) siguiendo `~/.claude/docs/agents/issue-tracker.md`.

- [ ] **Step 6: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/screener/rules.py src/bot/screener/types.py config/presets/ \
        tests/unit/test_screener_rules.py tests/unit/test_screener_trap_detection.py
git commit -m "refactor(screener): delete the auditor/late-filing trap detector

The rule read auditor_changed and late_filings, which no production code ever
populated, so it returned passed=True for every company — an eliminatory §6.4 gate
that never eliminated, while reading as an active governance filter.

Deleted with its two CompanyData fields, its preset references and its tests. The
config loader rejects unknown rule names, so a stale preset now fails loudly at load
instead of silently skipping a filter it never applied. Tracked for re-introduction
with a real SEC data source.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.2: Borrar el escape de M&A en la regla de dilución

`had_recent_ma` nunca se puebla, así que la rama que lo lee es inalcanzable y la regla es un cap incondicional del 5%. Dejarlo sugiere que la calificación "sin M&A justificado" del §6.4 está implementada.

**Files:**
- Modify: `src/bot/screener/types.py`, `src/bot/screener/rules.py`
- Modify: `tests/unit/test_screener_trap_detection.py` (borrar el test de línea ~281)

**Interfaces:**
- Consumes: nada.
- Produces: `ShareCountNotDiluting` sin la rama de M&A; su docstring documenta el cap como incondicional.

- [ ] **Step 1: Escribir el test que fija el borrado**

Agregá a `tests/unit/test_screener_trap_detection.py`:

```python
def test_share_count_dilution_cap_is_unconditional() -> None:
    from dataclasses import fields

    from bot.screener.types import CompanyData

    # The M&A escape hatch was deleted: nothing populated had_recent_ma, so the
    # branch was unreachable and the cap was always unconditional.
    assert "had_recent_ma" not in {f.name for f in fields(CompanyData)}
    result = ShareCountNotDiluting().evaluate(
        _company(share_count_history=(100.0, 110.0, 121.0)), _benchmarks()
    )
    assert result.passed is False
    assert "M&A" not in result.reason
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_screener_trap_detection.py -q -k unconditional`
Expected: FAIL — el campo todavía existe.

- [ ] **Step 3: Borrar**

En `src/bot/screener/rules.py`, borrá el bloque:

```python
        if company.had_recent_ma:
            return RuleResult(
                passed=True,
                reason=(
                    f"avg share-count growth {avg_growth:.3f} exceeds "
                    f"{self.max_annual_growth:.3f} but justified by recent M&A"
                ),
            )
```

Y el mensaje final pasa a ser incondicional:

```python
        return RuleResult(
            passed=False,
            reason=(
                f"avg share-count growth {avg_growth:.3f} > maximum "
                f"{self.max_annual_growth:.3f}"
            ),
        )
```

Actualizá el docstring de la clase: borrá la frase del escape de M&A y agregá:

```
    The cap is unconditional. Spec §6.4 qualifies it with "sin M&A justificado",
    but no data source distinguishes stock-funded M&A from ordinary issuance, so
    the qualification is not implemented rather than faked.
```

Borrá el campo `had_recent_ma` de `src/bot/screener/types.py` y el test de línea ~281.

- [ ] **Step 4: Correr y verificar**

Run: `uv run pytest tests/unit/test_screener_trap_detection.py -q`
Expected: PASS.

- [ ] **Step 5: Abrir el issue de backlog**

```bash
gh issue create \
  --title "Dilution trap detector: distinguish stock-funded M&A from ordinary issuance" \
  --body "Spec §6.4 caps average share-count growth at 5% *sin M&A justificado*. The
\`had_recent_ma\` escape hatch was deleted in the Fase 2 cleanup
(plan: docs/superpowers/plans/2026-08-09-remediacion-wiring-limpieza-bugs.md)
because nothing populated it, leaving an unreachable branch.

Restoring the qualification needs a source for material acquisitions. Candidates:
- \`acquisitionsNet\` in the FMP cash-flow statement already parsed by
  \`parse_fmp_fundamentals\` — a large negative value in the same fiscal year as the
  issuance is a usable proxy, and needs no new endpoint.
- SEC 8-K item 2.01 (completion of acquisition) for US filers.

The FMP proxy is the cheaper path: the field is in a payload the bot already
fetches. Wire it, then restore the branch with a threshold (e.g. acquisitions >
some fraction of total assets)." \
  --label enhancement
```

- [ ] **Step 6: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/screener/rules.py src/bot/screener/types.py \
        tests/unit/test_screener_trap_detection.py
git commit -m "refactor(screener): drop the unreachable M&A escape from the dilution cap

had_recent_ma was never populated, so the branch reading it could not execute and
the 5% cap was already unconditional. The docstring now says so, instead of
implying §6.4's 'sin M&A justificado' qualification is implemented.

Tracked: acquisitionsNet is already in the FMP cash-flow payload the bot parses, so
restoring the qualification is a wiring job, not a new integration.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.3: Eliminar el `wacc` sectorial redundante — mata el bug del doble WACC

`Assumptions.wacc` se resuelve del sector y se imprime en la §3 del reporte, pero `to_dcf_assumptions()` **lo ignora**: el DCF reconstruye el WACC de sus componentes vía `_wacc()`, y ese es el que sale en la §1. Los dos números difieren en general, así que el reporte se contradice consigo mismo. El campo es código muerto respecto del cálculo; borrarlo es el fix.

**Files:**
- Modify: `src/bot/valuator/assumptions.py`
- Modify: `src/bot/reporting/templates/analysis.md.j2`
- Modify: `tests/unit/test_valuator_assumptions.py`, `tests/unit/test_reporting_analysis.py`

**Interfaces:**
- Consumes: `DCFResult.wacc`, `DCFResult.equity_weight`, `DCFResult.debt_weight` (ya existen).
- Produces: `Assumptions` sin campo `wacc`. La §3 del reporte muestra los **componentes** con su source (cost of equity, pretax cost of debt, equity/debt weights) y el WACC compuesto sale una sola vez, del resultado del DCF.

- [ ] **Step 1: Escribir el test que falla**

Agregá a `tests/unit/test_reporting_analysis.py`:

```python
def test_report_shows_exactly_one_wacc(conn: duckdb.DuckDBPyConnection) -> None:
    # There used to be two: a sector-resolved Assumptions.wacc in §3 and the
    # DCF-computed one in §1, which disagree. Only the computed one is real.
    analysis = _analysis(conn)
    md = render_analysis(analysis)
    assert md.count("| WACC ") == 0, "no assumptions-table WACC row"
    computed = f"{analysis.dcf_result.wacc:.1%}"
    assert computed in md


def test_report_shows_the_sourced_wacc_components(conn: duckdb.DuckDBPyConnection) -> None:
    # The components are what actually carry provenance, so they are what §7.3
    # traceability needs in the table.
    md = render_analysis(_analysis(conn))
    for label in ("Cost of equity", "Pre-tax cost of debt", "Equity weight", "Debt weight"):
        assert label in md, label
```

Y a `tests/unit/test_valuator_assumptions.py`:

```python
def test_assumptions_has_no_redundant_wacc_field() -> None:
    from dataclasses import fields

    from bot.valuator.assumptions import Assumptions

    # Deleted: to_dcf_assumptions() ignored it and the DCF recomputes WACC from
    # its components, so the field only ever produced a contradictory report.
    assert "wacc" not in {f.name for f in fields(Assumptions)}
```

Usá los helpers `_analysis` / fixtures que los archivos ya tienen.

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_reporting_analysis.py tests/unit/test_valuator_assumptions.py -q -k "wacc"`
Expected: FAIL.

- [ ] **Step 3: Borrar el campo**

En `src/bot/valuator/assumptions.py`:
1. Borrá `wacc: Sourced[float | None]` del dataclass `Assumptions`.
2. Borrá la línea `wacc = _resolve_sector_scalar(override, sector, key="wacc", attr="wacc")` de `resolve_assumptions` y el argumento `wacc=wacc` del constructor.
3. Dejá `_SectorRow.wacc` — `screener/benchmarks.py` lo usa para el trap detector ROIC-vs-WACC, que es un consumidor legítimo y distinto.
4. En el docstring del módulo, agregá una nota:

```
The DCF's WACC is *computed* from its components (``cost_of_equity``,
``pretax_cost_of_debt``, the weights and the tax rate) by ``dcf._wacc``; there is
deliberately no resolved ``wacc`` assumption. Damodaran publishes a sector WACC and
an earlier version of this module carried it, but the DCF ignored it, so the report
printed two disagreeing numbers. The sector WACC still has one legitimate consumer:
the §6.4 ROIC-vs-WACC trap detector, which reads it from ``damodaran_industry``
directly.
```

Actualizá los tests de `test_valuator_assumptions.py` que asertaban sobre `assumptions.wacc`. Ojo con el override: si algún test pasa `wacc:` en el YAML, ahora es una clave desconocida — se ignora silenciosamente (eso se arregla en Task 3.x).

- [ ] **Step 4: Reemplazar la fila del template**

En `src/bot/reporting/templates/analysis.md.j2`, en la tabla de la §3, borrá la fila del WACC y agregá las cuatro de componentes:

```jinja
| Cost of equity | {{ a.assumptions.cost_of_equity.value | pct }} | {{ a.assumptions.cost_of_equity.source }} |
| Pre-tax cost of debt | {{ a.assumptions.pretax_cost_of_debt.value | pct }} | {{ a.assumptions.pretax_cost_of_debt.source }} |
| Equity weight | {{ a.assumptions.equity_weight.value | pct }} | {{ a.assumptions.equity_weight.source }} |
| Debt weight | {{ a.assumptions.debt_weight.value | pct }} | {{ a.assumptions.debt_weight.source }} |
```

Esto cierra además el hueco de trazabilidad del §7.7: los cuatro componentes tienen `Sourced` pero no se mostraban.

Y en la §1, aclará que el WACC es derivado:

```jinja
- **WACC (computed from the components in §3):** {{ a.dcf_result.wacc | pct }} (equity {{ a.dcf_result.equity_weight | pct }} / debt {{ a.dcf_result.debt_weight | pct }})
```

- [ ] **Step 5: Correr y verificar**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py tests/unit/test_valuator_analysis.py tests/unit/test_reporting_analysis.py tests/unit/test_reporting_html.py tests/unit/test_cli_analyze.py -q`
Expected: PASS.

- [ ] **Step 6: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/valuator/assumptions.py src/bot/reporting/templates/analysis.md.j2 \
        tests/unit/test_valuator_assumptions.py tests/unit/test_reporting_analysis.py
git commit -m "fix(valuator): one WACC per report, computed from its components

Assumptions.wacc was resolved from the Damodaran sector row and printed in report
§3, while to_dcf_assumptions() ignored it and the DCF recomputed WACC from
cost_of_equity / pretax_cost_of_debt / weights / tax for report §1. The two
generally disagree, so the report contradicted itself.

Delete the redundant field. §3 now lists the four sourced components — closing a
§7.7 traceability gap, since each carries a Sourced provenance that was never
displayed — and the composite WACC appears once, in §1, labelled as derived.

The sector WACC keeps its one legitimate consumer: the §6.4 ROIC-vs-WACC detector.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.4: Campos declarados y nunca leídos

Barrido final. Tres casos, con tratamiento distinto según si tienen fuente de datos posible:

| Símbolo | Estado | Acción |
|---|---|---|
| `ClassificationFinancials.debt_to_equity` | declarado, `_is_distressed` no lo lee | **borrar** |
| `AssumptionSource.ANALYST_CONSENSUS` | miembro del enum que nada emite nunca | **borrar** + issue |
| `Financials.adjustments`, `DCFAssumptions.distress_value_per_share` | nunca seteados por el pipeline, pero son inputs puros con tests propios | **conservar**, documentar |

Los dos últimos no son código muerto en el mismo sentido: son perillas del modelo puro, testeadas, que el pipeline todavía no alimenta. Borrarlas sacaría capacidad del DCF. Se documentan como no-cableadas.

**Files:**
- Modify: `src/bot/valuator/story_types.py`, `src/bot/valuator/assumptions.py`, `src/bot/valuator/dcf.py`
- Modify: `tests/unit/test_valuator_story_types.py`, `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: nada.
- Produces: `ClassificationFinancials` sin `debt_to_equity`; `AssumptionSource` con 4 miembros.

- [ ] **Step 1: Escribir el test que falla**

Agregá a `tests/unit/test_valuator_assumptions.py`:

```python
def test_assumption_source_has_no_unreachable_member() -> None:
    from bot.valuator.assumptions import AssumptionSource

    # ANALYST_CONSENSUS was never emitted by any resolver: revenue growth comes
    # from the historical average. Deleted so the enum describes what can happen.
    assert {s.value for s in AssumptionSource} == {
        "manual",
        "sector_default_damodaran",
        "rule_based",
        "historical_average",
    }
```

Y a `tests/unit/test_valuator_story_types.py`:

```python
def test_classification_financials_has_no_unread_field() -> None:
    from dataclasses import fields

    from bot.valuator.story_types import ClassificationFinancials

    # debt_to_equity was declared but _is_distressed reads only altman_z and
    # interest_coverage.
    assert "debt_to_equity" not in {f.name for f in fields(ClassificationFinancials)}
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py tests/unit/test_valuator_story_types.py -q -k "unreachable or unread"`
Expected: FAIL, ambos.

- [ ] **Step 3: Borrar**

1. `src/bot/valuator/story_types.py`: borrá `debt_to_equity: float | None = None` de `ClassificationFinancials`. Verificá que ningún test lo pase por keyword (`grep -n "debt_to_equity" tests/unit/test_valuator_story_types.py`).
2. `src/bot/valuator/assumptions.py`: borrá `ANALYST_CONSENSUS = "analyst_consensus"` del enum. Agregá al docstring de `_resolve_revenue_growth`:

```
Spec §7.3 wants analyst consensus for years 1-5 with convergence to nominal GDP by
year 10. Neither is implemented: the path is the historical average repeated over a
5-year horizon, sourced as HISTORICAL_AVERAGE. There is no ANALYST_CONSENSUS source
because nothing can emit it — FMP's analyst-estimates endpoint is not wired.
```

- [ ] **Step 4: Documentar las perillas no cableadas**

En `src/bot/valuator/dcf.py`, agregá al docstring de `Financials`:

```
``adjustments`` (minority interests, cross-holdings) is a supported input of the
equity bridge that the analysis pipeline does not populate: no ingest path supplies
either figure, so it defaults to 0.0. It is kept because the bridge is arithmetically
correct with it and a manual override can supply it.
```

Y al de `Assumptions`:

```
``distress_value_per_share`` pairs with ``probability_of_bankruptcy`` to blend a
going-concern value with a liquidation value. Neither is populated automatically —
§7.3's rating/Altman-Z derivation for distressed companies is not implemented — so
both come from a manual override or stay at 0.0.
```

- [ ] **Step 5: Correr y verificar**

Run: `uv run pytest tests/unit/test_valuator_story_types.py tests/unit/test_valuator_assumptions.py tests/unit/test_valuator_dcf.py -q`
Expected: PASS.

- [ ] **Step 6: Abrir el issue de backlog**

```bash
gh issue create \
  --title "Revenue growth: wire FMP analyst estimates and the 10-year fade to GDP (§7.3)" \
  --body "Spec §7.3 specifies revenue growth for years 1-5 from analyst consensus,
converging to nominal country GDP by year 10. Neither is implemented: the path is the
arithmetic mean of historical YoY growth, repeated flat over a 5-year horizon
(\`_historical_growth_path\`), and \`AssumptionSource.ANALYST_CONSENSUS\` was deleted
in the Fase 2 cleanup because nothing could emit it
(plan: docs/superpowers/plans/2026-08-09-remediacion-wiring-limpieza-bugs.md).

Three separate pieces of work:
1. **Analyst consensus** — FMP has an analyst-estimates endpoint; add a client
   method, and re-add the enum member when a resolver can emit it.
2. **10-year horizon with fade** — \`_HORIZON\` is hardcoded to 5. Extend to 10 and
   interpolate from the year-1 rate to nominal GDP by year 10.
3. **Growth definition** — the historical path uses the arithmetic mean of YoY
   rates, which is upward-biased for volatile revenue, while the story classifier
   uses CAGR. Pick one." \
  --label enhancement
```

- [ ] **Step 7: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/valuator/story_types.py src/bot/valuator/assumptions.py src/bot/valuator/dcf.py \
        tests/unit/test_valuator_story_types.py tests/unit/test_valuator_assumptions.py
git commit -m "refactor(valuator): delete unread fields, document the unwired knobs

ClassificationFinancials.debt_to_equity was declared but _is_distressed reads only
altman_z and interest_coverage. AssumptionSource.ANALYST_CONSENSUS was an enum member
no resolver could ever emit.

Financials.adjustments and Assumptions.distress_value_per_share are kept: they are
tested pure inputs of the equity bridge and the distress blend that the pipeline does
not feed yet. Their docstrings now say so, so 'unused' is not mistaken for 'broken'.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Fase 3 — Bugs bloqueantes y contaminantes

Cada uno produce un número o una etiqueta que el lector va a creer. Ordenados por cuánto ensucian la lectura del sistema.

### Task 3.1: La grilla 2-D reporta margin of safety contra el precio, no contra sí misma

`sensitivity.py:259` calcula `intrinsic_value / base_intrinsic`. La celda central es 1.00x por construcción y no dice nada sobre sub/sobrevaluación, mientras el titular del reporte usa `intrinsic / price`. Dos cantidades distintas con el mismo nombre en un reporte, y la misma cantidad equivocada va al heatmap HTML.

**Files:**
- Modify: `src/bot/valuator/sensitivity.py`, `src/bot/valuator/analysis.py`
- Modify: `src/bot/reporting/analysis_report.py`, `src/bot/reporting/templates/analysis.md.j2`, `src/bot/reporting/html.py`
- Modify: `tests/unit/test_valuator_sensitivity.py`

**Interfaces:**
- Consumes: `Analysis.current_price`.
- Produces: `grid_2d(financials, base_assumptions, axis_a, axis_b, *, reference_price: float | None = None) -> Grid2D`. `GridCell.margin_of_safety` pasa a ser `intrinsic / reference_price`, o `None` cuando no hay precio. `Grid2D` gana `reference_price: float | None`.

- [ ] **Step 1: Escribir el test que falla**

Agregá a `tests/unit/test_valuator_sensitivity.py`:

```python
def test_grid_margin_of_safety_is_versus_price() -> None:
    financials = _financials()
    assumptions = _assumptions()
    base = dcf(financials, assumptions).intrinsic_value
    price = base / 2.0  # deeply undervalued: every cell should be well above 1

    grid = grid_2d(
        financials,
        assumptions,
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
        reference_price=price,
    )
    centre = grid.cells[2][2]
    assert centre.intrinsic_value == pytest.approx(base)
    # The centre cell used to be 1.00x by construction, which told the reader
    # nothing. It must now carry the real base-case margin of safety.
    assert centre.margin_of_safety == pytest.approx(2.0)
    assert grid.reference_price == pytest.approx(price)


def test_grid_margin_of_safety_none_without_a_price() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
    )
    assert grid.reference_price is None
    assert all(cell.margin_of_safety is None for row in grid.cells for cell in row)
    # Intrinsic values are still computed: the grid is useful without a price.
    assert grid.cells[2][2].intrinsic_value is not None


def test_grid_margin_of_safety_none_for_an_out_of_domain_cell() -> None:
    # A cell whose terminal growth crosses WACC has no intrinsic value, so no MoS.
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.TERMINAL_GROWTH,
        SensitivityAxis.COST_OF_EQUITY,
        reference_price=10.0,
    )
    for row in grid.cells:
        for cell in row:
            if cell.intrinsic_value is None:
                assert cell.margin_of_safety is None


def test_grid_margin_of_safety_none_for_a_non_positive_price() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
        reference_price=0.0,
    )
    assert all(cell.margin_of_safety is None for row in grid.cells for cell in row)


def test_grid_centre_matches_the_headline_margin_of_safety(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # The invariant the old code violated: one number, one meaning.
    from bot.valuator.analysis import analyze

    analysis = _seeded_analysis(conn)
    assert analysis.margin_of_safety is not None
    assert analysis.grid.cells[2][2].margin_of_safety == pytest.approx(
        analysis.margin_of_safety
    )
```

Usá los helpers `_financials` / `_assumptions` que el archivo ya tiene; para el último test reusá un seeder de `tests/unit/test_valuator_analysis.py` o movelo a `tests/conftest.py` si hace falta compartirlo.

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_valuator_sensitivity.py -q -k "versus_price or centre"`
Expected: FAIL con `TypeError: grid_2d() got an unexpected keyword argument 'reference_price'`.

- [ ] **Step 3: Implementar**

En `src/bot/valuator/sensitivity.py`, agregá el campo a `Grid2D`:

```python
    reference_price: float | None = None
```

Cambiá `grid_2d`:

```python
def grid_2d(
    financials: Financials,
    base_assumptions: Assumptions,
    axis_a: SensitivityAxis,
    axis_b: SensitivityAxis,
    *,
    reference_price: float | None = None,
) -> Grid2D:
    """Build a 5x5 margin-of-safety grid over two assumptions (spec §7.4).

    Each cell's ``margin_of_safety`` is ``intrinsic_value / reference_price`` — the
    same quantity as the report's headline margin of safety, so the centre cell
    equals it exactly. Without a ``reference_price`` (or with a non-positive one)
    every cell's margin is ``None`` while intrinsic values are still computed: the
    grid remains readable as a value surface.

    A cell whose scaled assumptions leave the model's domain (terminal growth at or
    above WACC) has no intrinsic value, hence no margin of safety.
    """
```

Y el cuerpo del cálculo por celda:

```python
            intrinsic_value = _safe_intrinsic(financials, cell_assumptions)
            # Margin of safety is value-over-price, identical in meaning to the
            # report headline. It needs an in-domain cell and a positive price.
            margin_of_safety = (
                intrinsic_value / reference_price
                if intrinsic_value is not None
                and reference_price is not None
                and reference_price > 0.0
                else None
            )
```

Borrá el cálculo de `base_intrinsic` si queda sin uso, y pasá `reference_price=reference_price` al constructor de `Grid2D`.

- [ ] **Step 4: Pasar el precio desde `analyze`**

En `src/bot/valuator/analysis.py`, la llamada actual es `grid = grid_2d(financials, dcf_assumptions, axis_a, axis_b)`. Cambiala a:

```python
    grid = grid_2d(
        financials, dcf_assumptions, axis_a, axis_b, reference_price=current_price
    )
```

`current_price` ya está en scope (se asigna desde `inputs.current_price`).

- [ ] **Step 5: Corregir las etiquetas del reporte**

En `src/bot/reporting/templates/analysis.md.j2`, el encabezado de la §5 dice `margin of safety vs base`. Cambialo:

```jinja
### 2-D grid — {{ a.grid.axis_a }} (rows) × {{ a.grid.axis_b }} (cols), margin of safety (intrinsic ÷ price)
{% if a.grid.reference_price is none %}
_No current price available — the grid below shows intrinsic values only._
{% endif %}
```

En `src/bot/reporting/analysis_report.py`, `_grid_table` formatea `cell.margin_of_safety` con `_fmt_ratio`. Cuando `reference_price is None`, toda la grilla sería `—`, lo que pierde información: hacé que caiga a `intrinsic_value` formateado con `_fmt_money`. Leé `_grid_table` (líneas ~86-103) y agregá esa rama.

En `src/bot/reporting/html.py`, `sensitivity_heatmap_html` colorea por `margin_of_safety`; agregá el mismo fallback y actualizá el título/colorbar del heatmap para que diga "margin of safety (intrinsic ÷ price)".

- [ ] **Step 6: Correr y verificar**

Run: `uv run pytest tests/unit/test_valuator_sensitivity.py tests/unit/test_valuator_analysis.py tests/unit/test_reporting_analysis.py tests/unit/test_reporting_html.py -q`
Expected: PASS. El test existente que fijaba `centre cell == base` (línea ~177) va a fallar: reemplazalo por el invariante nuevo (celda central == MoS del titular).

- [ ] **Step 7: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/valuator/sensitivity.py src/bot/valuator/analysis.py \
        src/bot/reporting/analysis_report.py src/bot/reporting/html.py \
        src/bot/reporting/templates/analysis.md.j2 tests/unit/test_valuator_sensitivity.py
git commit -m "fix(valuator): the 2-D grid's margin of safety is versus price

grid_2d computed intrinsic / base_intrinsic, so the centre cell was 1.00x by
construction and said nothing about under/overvaluation, while the report headline
used intrinsic / price. Two different quantities under one name in one report, and
the same wrong one fed the Plotly heatmap.

Cells now carry intrinsic / reference_price, so the centre cell equals the headline
margin of safety exactly — pinned by a test. Without a price the margins are None and
the grid falls back to showing intrinsic values, which is still a useful surface.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.2: Los dos narrative flags muertos

- `country_exposure`: `analysis.py:475-476` pasa `erp_weighted=sector.erp, erp_listing=sector.erp` — **el mismo número**, así que el gap es siempre exactamente 0 y el flag no puede ponerse rojo nunca. Y `foreign_revenue_share` nunca se setea, así que igual corta en verde con "figures unavailable". Pasar dos veces el mismo ERP finge un cálculo que no existe.
- `beta_business_risk`: lee `assumptions.debt_weight`, que es el peso derivado del **D/E sectorial**, no el apalancamiento de la empresa. La empresa tiene `total_debt` y `total_equity` en `financials_annual`: el dato existe.

No hay fuente para revenue por geografía (FMP no la da en los endpoints que el bot usa), así que `country_exposure` no se puede calcular de verdad. La corrección honesta es dejar de fingir: que el flag reporte explícitamente "no evaluado" en vez de verde.

**Files:**
- Modify: `src/bot/valuator/narrative_flags.py`, `src/bot/valuator/analysis.py`
- Modify: `tests/unit/test_valuator_narrative_flags.py`, `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Consumes: `ValuationInput.latest` (`total_debt`, `total_equity`).
- Produces: `FlagColor` gana `UNKNOWN = "unknown"`. `NarrativeContext` gana `company_debt_weight: float | None`. `beta_business_risk_flag` lee `context.company_debt_weight` en vez de `assumptions.debt_weight`.

- [ ] **Step 1: Escribir el test que falla**

Agregá a `tests/unit/test_valuator_narrative_flags.py`:

```python
def test_country_exposure_is_unknown_not_green_without_data() -> None:
    # It used to return GREEN with "figures unavailable", which reads as "checked
    # and fine". A check that did not run must not look like a pass.
    flag = country_exposure_flag(
        _financials(), _assumptions(), _result(), NarrativeContext()
    )
    assert flag.color is FlagColor.UNKNOWN
    assert "not evaluated" in flag.reason


def test_country_exposure_red_when_the_data_is_present() -> None:
    flag = country_exposure_flag(
        _financials(),
        _assumptions(),
        _result(),
        NarrativeContext(
            foreign_revenue_share=0.70, erp_weighted=0.09, erp_listing=0.045
        ),
    )
    assert flag.color is FlagColor.RED


def test_country_exposure_green_when_the_gap_is_small() -> None:
    flag = country_exposure_flag(
        _financials(),
        _assumptions(),
        _result(),
        NarrativeContext(
            foreign_revenue_share=0.70, erp_weighted=0.046, erp_listing=0.045
        ),
    )
    assert flag.color is FlagColor.GREEN


def test_beta_business_risk_uses_the_company_leverage() -> None:
    # The company is debt-heavy (55%) while its sector's D/E implies a light
    # structure. The flag must read the company's own leverage.
    flag = beta_business_risk_flag(
        _financials(),
        _assumptions(debt_weight=0.10),
        _result(),
        NarrativeContext(
            sector_beta=0.8, operating_leverage=2.0, company_debt_weight=0.55
        ),
    )
    assert flag.color is FlagColor.YELLOW
    assert "55%" in flag.reason


def test_beta_business_risk_unknown_without_company_leverage() -> None:
    flag = beta_business_risk_flag(
        _financials(),
        _assumptions(),
        _result(),
        NarrativeContext(sector_beta=0.8, operating_leverage=2.0),
    )
    assert flag.color is FlagColor.UNKNOWN
```

Y a `tests/unit/test_valuator_analysis.py`:

```python
def test_pipeline_does_not_fake_the_erp_gap(conn: duckdb.DuckDBPyConnection) -> None:
    # analysis.py used to pass the same sector ERP as both the weighted and the
    # listing ERP, making the gap identically zero.
    analysis = _seeded_analysis(conn)
    flag = next(f for f in analysis.narrative_flags if f.name == "country_exposure")
    assert flag.color is FlagColor.UNKNOWN


def test_pipeline_supplies_the_company_leverage(conn: duckdb.DuckDBPyConnection) -> None:
    analysis = _seeded_analysis(conn)
    flag = next(f for f in analysis.narrative_flags if f.name == "beta_business_risk")
    assert flag.color is not FlagColor.UNKNOWN
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_valuator_narrative_flags.py -q -k "unknown or company_leverage"`
Expected: FAIL con `AttributeError: UNKNOWN`.

- [ ] **Step 3: Implementar**

En `src/bot/valuator/narrative_flags.py`:

1. Agregá el color:

```python
class FlagColor(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"
    """The check could not run for lack of data. Deliberately distinct from GREEN:
    an un-run check must never read as a pass (spec §7.5)."""
```

2. Agregá el campo a `NarrativeContext`:

```python
    company_debt_weight: float | None = None
    """The company's own debt / (debt + equity) from its latest balance sheet.
    Distinct from ``Assumptions.debt_weight``, which is derived from the *sector's*
    D/E and drives the WACC."""
```

3. En `country_exposure_flag`, cambiá la rama de datos ausentes:

```python
    if foreign is None or erp_weighted is None or erp_listing is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.UNKNOWN,
            reason=(
                "not evaluated: needs revenue by geography and a revenue-weighted "
                "ERP; no ingest path supplies either"
            ),
        )
```

4. En `beta_business_risk_flag`, reemplazá `financial_leverage = assumptions.debt_weight` por el del contexto, y devolvé `UNKNOWN` cuando falte:

```python
    beta = context.sector_beta
    operating_leverage = context.operating_leverage
    financial_leverage = context.company_debt_weight
    if beta is None or operating_leverage is None or financial_leverage is None:
        return NarrativeFlag(
            name=name,
            color=FlagColor.UNKNOWN,
            reason="not evaluated: sector beta, operating leverage or company leverage unavailable",
        )
```

Actualizá el docstring para decir que el apalancamiento financiero es el de la empresa, no el sectorial.

- [ ] **Step 4: Cablear desde `analyze`**

En `src/bot/valuator/analysis.py`, calculá el apalancamiento de la empresa y **borrá** los dos ERP falsos:

```python
    # The company's own capital structure, not the sector's (which drives WACC).
    company_debt_weight: float | None = None
    if latest.total_debt is not None and latest.total_equity is not None:
        invested = latest.total_debt + latest.total_equity
        if invested > 0.0:
            company_debt_weight = latest.total_debt / invested

    context = NarrativeContext(
        story_type=story_type,
        company_operating_margin=assumptions.operating_margin.value,
        sector_operating_margin=sector.op_margin,
        sector_beta=sector.beta_levered,
        operating_leverage=_operating_leverage(revenue_history, ebit_history),
        company_debt_weight=company_debt_weight,
        # erp_weighted / erp_listing deliberately unset: a revenue-weighted ERP
        # needs revenue by geography, which no ingest path supplies. Passing the
        # sector ERP as both made the gap identically zero — a fake calculation.
    )
```

Verificá que `latest` expone `total_debt` y `total_equity`; si el dataclass de `ValuationInput.latest` no los tiene, agregalos al `SELECT` de `load_valuation_input` y al dataclass.

- [ ] **Step 5: Manejar el color nuevo en el reporte**

Los templates iteran `a.narrative_flags` y renderizan `f.color`, así que `unknown` sale sin cambios. En `src/bot/reporting/html.py`, si `_STYLE` colorea por clase de flag, agregá una regla para `unknown` (gris, distinto de verde). Chequealo con `grep -n "green\|yellow\|red" src/bot/reporting/html.py`.

- [ ] **Step 6: Correr y verificar**

Run: `uv run pytest tests/unit/test_valuator_narrative_flags.py tests/unit/test_valuator_analysis.py tests/unit/test_reporting_analysis.py -q`
Expected: PASS. Los tests existentes que asertaban `GREEN` para esos dos flags con contexto vacío tienen que pasar a `UNKNOWN`.

- [ ] **Step 7: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/valuator/narrative_flags.py src/bot/valuator/analysis.py \
        src/bot/reporting/html.py tests/unit/test_valuator_narrative_flags.py \
        tests/unit/test_valuator_analysis.py
git commit -m "fix(valuator): stop faking the ERP gap, use the company's own leverage

Two of the five §7.5 flags were dead in the pipeline:

- country_exposure received the same sector ERP as both erp_weighted and
  erp_listing, so the gap was identically zero and the flag could never turn red;
  foreign_revenue_share was never set either. A revenue-weighted ERP needs revenue
  by geography, which no ingest path supplies, so the honest fix is to stop passing
  the fake inputs and report the check as not evaluated.
- beta_business_risk read Assumptions.debt_weight, derived from the *sector's* D/E,
  as if it were the company's financial leverage. The company's total_debt and
  total_equity are on its balance sheet; use those.

New FlagColor.UNKNOWN keeps an un-run check from reading as a pass, which GREEN with
'figures unavailable' did.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.3: Procedencia honesta y overrides que no se pierden en silencio

Tres defectos en `assumptions.py`, todos del mismo tipo: el módulo afirma cosas que no son.

1. `_resolve_sector_scalar` estampa `SECTOR_DEFAULT_DAMODARAN` **incluso cuando el valor es `None`** — un assumption sin resolver reporta una procedencia de la que nunca vino.
2. `_resolve_weights` honra los pesos manuales **sólo si están los dos**: quien setea sólo `equity_weight` lo pierde en silencio.
3. `_load_override` sólo valida que el YAML sea un mapping: una clave mal escrita (`wacc_`, `terminal_grow`) se ignora sin decir nada, y el usuario cree que su override se aplicó.

**Files:**
- Modify: `src/bot/valuator/assumptions.py`
- Modify: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `Sourced.source` es `None`-safe vía un miembro nuevo `AssumptionSource.UNRESOLVED = "unresolved"`. `_load_override` levanta `ValueError` en claves desconocidas. `_resolve_weights` acepta un override parcial.

- [ ] **Step 1: Escribir el test que falla**

Agregá a `tests/unit/test_valuator_assumptions.py`:

```python
def test_unresolved_assumption_reports_unresolved_not_a_sector_default(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # A company whose industry has no Damodaran row: the assumption has no value,
    # so claiming it came from the sector defaults is a lie the report would print.
    _seed_company(conn, ticker="OBSCURE", industry_damodaran="Obscure")
    assumptions = resolve_assumptions("OBSCURE", conn)
    assert assumptions.operating_margin.value is None
    assert assumptions.operating_margin.source is AssumptionSource.UNRESOLVED


def test_resolved_assumption_still_reports_the_sector(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn, ticker="SEMI", industry_damodaran="Software")
    _seed_sector(conn, industry="Software", op_margin=0.22)
    assumptions = resolve_assumptions("SEMI", conn)
    assert assumptions.operating_margin.value == pytest.approx(0.22)
    assert assumptions.operating_margin.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_partial_weight_override_is_honoured(conn: duckdb.DuckDBPyConnection, tmp_path) -> None:
    # Setting only equity_weight used to be discarded silently. The complement is
    # implied: weights partition capital.
    _seed_company(conn, ticker="LEV", industry_damodaran="Software")
    _seed_sector(conn, industry="Software", debt_to_equity=0.25)
    override = tmp_path / "LEV.yaml"
    override.write_text("equity_weight: 0.7\n")
    assumptions = resolve_assumptions("LEV", conn, override_path=override)
    assert assumptions.equity_weight.value == pytest.approx(0.7)
    assert assumptions.debt_weight.value == pytest.approx(0.3)
    assert assumptions.equity_weight.source is AssumptionSource.MANUAL
    assert assumptions.debt_weight.source is AssumptionSource.MANUAL


def test_weights_always_partition(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn, ticker="W", industry_damodaran="Software")
    _seed_sector(conn, industry="Software", debt_to_equity=0.25)
    a = resolve_assumptions("W", conn)
    assert a.equity_weight.value is not None and a.debt_weight.value is not None
    assert a.equity_weight.value + a.debt_weight.value == pytest.approx(1.0)


def test_unknown_override_key_is_rejected(conn: duckdb.DuckDBPyConnection, tmp_path) -> None:
    # A typo used to be ignored, so the user believed an override applied that did not.
    _seed_company(conn, ticker="TYPO", industry_damodaran="Software")
    override = tmp_path / "TYPO.yaml"
    override.write_text("terminal_grow: 0.02\n")
    with pytest.raises(ValueError, match="unknown override key"):
        resolve_assumptions("TYPO", conn, override_path=override)


def test_unknown_override_key_error_lists_the_valid_ones(
    conn: duckdb.DuckDBPyConnection, tmp_path
) -> None:
    _seed_company(conn, ticker="TYPO2", industry_damodaran="Software")
    override = tmp_path / "TYPO2.yaml"
    override.write_text("wacc: 0.09\n")
    with pytest.raises(ValueError, match="terminal_growth"):
        resolve_assumptions("TYPO2", conn, override_path=override)


def test_every_documented_override_key_is_accepted(
    conn: duckdb.DuckDBPyConnection, tmp_path
) -> None:
    _seed_company(conn, ticker="ALL", industry_damodaran="Software")
    override = tmp_path / "ALL.yaml"
    override.write_text(
        "revenue_growth: [0.1, 0.09, 0.08, 0.07, 0.06]\n"
        "operating_margin: 0.2\n"
        "sales_to_capital: 2.0\n"
        "terminal_growth: 0.02\n"
        "cost_of_equity: 0.09\n"
        "pretax_cost_of_debt: 0.05\n"
        "equity_weight: 0.8\n"
        "debt_weight: 0.2\n"
        "tax_rate: 0.25\n"
        "probability_of_bankruptcy: 0.05\n"
        "story_type: high-growth\n"
        "notes: manual review\n"
    )
    assumptions = resolve_assumptions("ALL", conn, override_path=override)
    assert assumptions.story_type == "high-growth"
    assert assumptions.notes == "manual review"
```

`_seed_sector` puede no existir con esa firma; leé los seeders del archivo y adaptá.

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -q -k "unresolved or partial_weight or unknown_override"`
Expected: FAIL.

- [ ] **Step 3: Implementar**

En `src/bot/valuator/assumptions.py`:

1. Agregá el miembro al enum:

```python
    UNRESOLVED = "unresolved"
    """No layer produced a value. The report shows the gap instead of a number, and
    must not attribute the gap to a source it never came from."""
```

> **Dependencia con Task 2.4.** Esa tarea agregó `test_assumption_source_has_no_unreachable_member`, que fija el conjunto exacto de miembros del enum en cuatro. Actualizalo acá para incluir `"unresolved"` — el punto del test es que no haya miembros *inalcanzables*, y `UNRESOLVED` sí se emite:
>
> ```python
>     assert {s.value for s in AssumptionSource} == {
>         "manual",
>         "sector_default_damodaran",
>         "rule_based",
>         "historical_average",
>         "unresolved",
>     }
> ```

2. `_resolve_sector_scalar` — la procedencia sigue al valor:

```python
    value = getattr(sector, attr) if sector is not None else None
    if value is None:
        return Sourced(value=None, source=AssumptionSource.UNRESOLVED)
    return Sourced(value=value, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)
```

3. `_resolve_weights` — override parcial, y el complemento implícito:

```python
def _resolve_weights(
    override: dict[str, Any], sector: _SectorRow | None
) -> tuple[Sourced[float | None], Sourced[float | None]]:
    """Resolve the equity/debt split of the capital structure.

    The two weights partition invested capital, so either one determines the other:
    a manual override of just one is honoured and the complement is derived (both
    reported as MANUAL). With no override, the split comes from the sector's D/E.
    """
    manual_equity = _override_scalar(override, "equity_weight")
    manual_debt = _override_scalar(override, "debt_weight")
    manual_src = AssumptionSource.MANUAL
    if manual_equity is not None and manual_equity.value is not None:
        equity = manual_equity.value
        debt = manual_debt.value if manual_debt is not None and manual_debt.value is not None else 1.0 - equity
        return Sourced(value=equity, source=manual_src), Sourced(value=debt, source=manual_src)
    if manual_debt is not None and manual_debt.value is not None:
        debt = manual_debt.value
        return (
            Sourced(value=1.0 - debt, source=manual_src),
            Sourced(value=debt, source=manual_src),
        )
    if sector is not None and sector.debt_to_equity is not None:
        d_to_e = sector.debt_to_equity
        debt_weight = d_to_e / (1.0 + d_to_e)
        src = AssumptionSource.SECTOR_DEFAULT_DAMODARAN
        return (
            Sourced(value=1.0 - debt_weight, source=src),
            Sourced(value=debt_weight, source=src),
        )
    unresolved = AssumptionSource.UNRESOLVED
    return Sourced(value=None, source=unresolved), Sourced(value=None, source=unresolved)
```

4. Validación de claves en `_load_override`:

```python
#: Every key a `config/assumptions/<TICKER>.yaml` may carry (spec §7.6). Anything
#: else is a typo: silently ignoring it would let a user believe an override applied.
_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "revenue_growth",
        "operating_margin",
        "sales_to_capital",
        "terminal_growth",
        "cost_of_equity",
        "pretax_cost_of_debt",
        "equity_weight",
        "debt_weight",
        "tax_rate",
        "probability_of_bankruptcy",
        "distress_value_per_share",
        "story_type",
        "notes",
    }
)
```

Y al final de `_load_override`, antes del return:

```python
    unknown = sorted(set(loaded) - _OVERRIDE_KEYS)
    if unknown:
        valid = ", ".join(sorted(_OVERRIDE_KEYS))
        raise ValueError(
            f"{override_path}: unknown override key(s): {', '.join(unknown)}. "
            f"Valid keys: {valid}"
        )
```

Aplicá el mismo tratamiento `UNRESOLVED` a `_resolve_revenue_growth` y `_resolve_tax_rate` cuando no resuelven.

- [ ] **Step 4: Correr y verificar**

Run: `uv run pytest tests/unit/test_valuator_assumptions.py tests/unit/test_valuator_analysis.py tests/unit/test_cli_analyze.py -q`
Expected: PASS. Los tests que asertaban `SECTOR_DEFAULT_DAMODARAN` con valor `None` pasan a `UNRESOLVED`.

- [ ] **Step 5: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/valuator/assumptions.py tests/unit/test_valuator_assumptions.py
git commit -m "fix(valuator): honest provenance, partial weight overrides, strict override keys

Three ways the assumptions module asserted things that were not true:

- _resolve_sector_scalar stamped SECTOR_DEFAULT_DAMODARAN even when the value was
  None, so an unresolved assumption reported a source it never came from. New
  AssumptionSource.UNRESOLVED makes the provenance follow the value.
- _resolve_weights honoured manual weights only when both were given, silently
  discarding an override of just one. The weights partition capital, so either
  determines the other; the complement is now derived.
- _load_override accepted any mapping, so a mistyped key was ignored and the user
  believed an override applied. Unknown keys now raise, listing the valid ones.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.4: Honestidad del reporte — story reasons, formato y el test falso

Barrido final de cosas que el lector cree:

1. `_story_reasons` se construye siempre desde `auto_story`, así que con un `story_type` manual el reporte muestra el tipo X en el encabezado de la §2 y "classified as Y" en su propia lista de razones.
2. `_fmt_money` aplica escala B/M/K a valores **por acción**: un intrínseco de 1.500 se renderiza como `1.50K`.
3. `tests/integration/test_screen_cli.py:177` afirma `0 <= score <= 100`, invariante que la implementación explícitamente no garantiza (el componente de MoS es absoluto y sin techo). Es un test que codifica una propiedad falsa: pasa sólo porque los fixtures mantienen MoS ≤ 1.

**Files:**
- Modify: `src/bot/valuator/analysis.py`, `src/bot/reporting/analysis_report.py`
- Modify: `src/bot/reporting/templates/analysis.md.j2`
- Modify: `tests/integration/test_screen_cli.py`, `tests/unit/test_reporting_analysis.py`

**Interfaces:**
- Consumes: `Analysis.story_type`, `Assumptions.story_type`.
- Produces: `_story_reasons` recibe si el tipo fue overrideado. Nuevo filtro Jinja `per_share`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregá a `tests/unit/test_reporting_analysis.py`:

```python
def test_manual_story_type_does_not_contradict_its_reasons(
    conn: duckdb.DuckDBPyConnection, tmp_path
) -> None:
    override = tmp_path / "X.yaml"
    override.write_text("story_type: distressed\n")
    analysis = _seeded_analysis(conn, override_path=override)
    assert analysis.story_type == "distressed"
    md = render_analysis(analysis)
    # The reasons used to describe the auto-classification, contradicting the
    # heading two lines above.
    assert "manually overridden" in md
    for other in ("mature-stable", "high-growth", "cyclical", "mature-decline"):
        assert f"classified as {other}" not in md


def test_per_share_values_are_not_scaled_to_thousands() -> None:
    from bot.reporting.analysis_report import _fmt_per_share

    # A per-share price of 1500 is 1500, not "1.50K".
    assert _fmt_per_share(1500.0) == "1500.00"
    assert _fmt_per_share(12.3456) == "12.35"
    assert _fmt_per_share(None) == "—"


def test_report_renders_per_share_values_unscaled(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    analysis = _seeded_analysis(conn, intrinsic_per_share=1500.0)
    md = render_analysis(analysis)
    assert "1500.00" in md
    assert "1.50K" not in md
```

Y reemplazá la assertion falsa en `tests/integration/test_screen_cli.py:177`:

```python
        # The composite has no 0-100 ceiling by design: the margin-of-safety term is
        # an absolute, unbounded intrinsic/price ratio, so a deeply undervalued
        # candidate scores above 100. Only the floor is guaranteed.
        assert score >= 0.0
```

Y agregá el test que fija el techo real:

```python
def test_composite_can_exceed_100_for_a_deeply_undervalued_candidate() -> None:
    from bot.screener.ranking import Candidate, RankingWeights, rank

    scored = rank(
        [
            Candidate(
                ticker="CHEAP",
                value_metric=1.0,
                quality_metric=1.0,
                growth_metric=1.0,
                margin_of_safety=3.0,
            )
        ],
        RankingWeights(),
    )
    # 100 * (0.4 + 0.3 + 0.2 + 0.1*3.0) = 120
    assert scored[0].score == pytest.approx(120.0)
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `uv run pytest tests/unit/test_reporting_analysis.py -q -k "contradict or per_share"`
Expected: FAIL con `ImportError: cannot import name '_fmt_per_share'`.

- [ ] **Step 3: Arreglar las story reasons**

En `src/bot/valuator/analysis.py`, `_story_reasons(auto_story, revenue_history, age_years)` se llama siempre con `auto_story`. Agregá el flag de override:

```python
def _story_reasons(
    story_type: StoryType,
    revenue_history: tuple[float, ...],
    age_years: int | None,
    *,
    overridden: bool,
) -> tuple[str, ...]:
    """Human-readable reasons for the story type shown in report §2.

    When the type was manually overridden the auto-classification's reasons no
    longer explain it, so they are replaced by the override notice — otherwise the
    report states one type in its heading and justifies a different one below it.
    """
    if overridden:
        return (
            f"manually overridden in the assumptions file; the classifier would "
            f"have said {story_type.value}",
        )
    ...  # el cuerpo existente, sin cambios
```

Y en `analyze`, la llamada:

```python
        story_reasons=_story_reasons(
            auto_story,
            revenue_history,
            age_years,
            overridden=assumptions.story_type is not None
            and assumptions.story_type != auto_story.value,
        ),
```

- [ ] **Step 4: Arreglar el formato por acción**

En `src/bot/reporting/analysis_report.py`, agregá el formateador y registralo:

```python
def _fmt_per_share(value: float | None) -> str:
    """Format a per-share figure at full magnitude.

    Distinct from :func:`_fmt_money`, whose B/M/K scaling is right for
    enterprise-scale aggregates and wrong for a share price: a per-share intrinsic
    value of 1500 must not render as "1.50K".
    """
    if value is None:
        return _DASH
    return f"{value:.2f}"
```

Registralo en el entorno Jinja junto a los otros filtros: `env.filters["per_share"] = _fmt_per_share`.

En `src/bot/reporting/templates/analysis.md.j2`, cambiá a `| per_share` las tres magnitudes por acción de la §1:

```jinja
- **Intrinsic value (per share):** {{ a.dcf_result.intrinsic_value | per_share }}
{% if a.current_price is not none -%}
- **Current price:** {{ a.current_price | per_share }}
```

Y en la §5, el tornado (`intrinsic_low`, `intrinsic_high`, `impact`) también es por acción → `| per_share`. Las magnitudes de la §4 (revenue, EBIT, EV, equity value, net debt) siguen con `| money`.

En `src/bot/reporting/analysis_report.py`, `_grid_table` usa `_fmt_money` en el fallback de intrínsecos por acción de la Task 3.1 → cambialo a `_fmt_per_share`.

- [ ] **Step 5: Correr y verificar**

Run: `uv run pytest tests/unit/test_reporting_analysis.py tests/unit/test_reporting_html.py tests/unit/test_valuator_analysis.py tests/integration/test_screen_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Suite completa y commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

```bash
git add src/bot/valuator/analysis.py src/bot/reporting/analysis_report.py \
        src/bot/reporting/templates/analysis.md.j2 \
        tests/unit/test_reporting_analysis.py tests/integration/test_screen_cli.py
git commit -m "fix(reporting): non-contradictory story reasons, unscaled per-share values

- _story_reasons was always built from the auto-classification, so a manually
  overridden story_type produced a report stating one type in its §2 heading and
  justifying a different one directly below it.
- _fmt_money's B/M/K scaling was applied to per-share figures, rendering a 1500
  intrinsic value as '1.50K'. New per_share filter for the §1 headline and the
  tornado; enterprise-scale aggregates keep money.
- Replaced the integration assertion 0 <= score <= 100 with score >= 0: the
  composite has no upper ceiling by design because the margin-of-safety term is an
  absolute unbounded ratio. The old assertion encoded a property the implementation
  does not guarantee and passed only because the fixtures kept MoS <= 1. Added a
  test pinning the real behaviour (MoS 3.0 -> score 120).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Criterio de aceptación de las tres fases

Cuando las 16 tareas estén hechas, esto tiene que ser cierto — es la "vista clara" que pedías:

- [ ] `uv run pytest -q && uv run ruff check src tests && uv run mypy src` verde.
- [ ] `bot refresh --all` puebla `damodaran_industry` con `op_margin`, `sales_to_capital`, `debt_to_equity`, `pe`, `pbv`, `ev_ebitda`, `roe`, `roic` no-nulos, y `damodaran_country` con `risk_free_rate` y `tax_rate`.
- [ ] Toda empresa importada tiene `industry_damodaran` poblado o, si no mapea, aparece en un log de industrias sin mapear.
- [ ] `bot analyze <TICKER>` produce un reporte **sin levantar** para una empresa real — hoy falla siempre.
- [ ] El reporte muestra un solo WACC, los cuatro componentes con su procedencia, la celda central de la grilla igual al MoS del titular, y `unknown` (no verde) en los checks que no corrieron.
- [ ] `bot screen --preset damodaran_value` produce candidatas cuyo `margin_of_safety` no es el placeholder 0.5 para todas.
- [ ] Ningún campo de `CompanyData` queda sin poblar por el pipeline.
- [ ] Todo assumption sin resolver reporta `unresolved`, nunca una procedencia falsa.

Verificación manual sugerida al cerrar (necesita `BOT_FMP_API_KEY`):

```bash
uv run bot refresh --all
uv run bot screen --preset damodaran_value --top 25
uv run bot analyze AAPL
uv run python -c "
import duckdb
conn = duckdb.connect('bot.duckdb')
print('sin industry_damodaran:', conn.execute('SELECT count(*) FROM companies WHERE industry_damodaran IS NULL').fetchone()[0])
print('columnas Damodaran nulas:', conn.execute('''
  SELECT count(*) FROM damodaran_industry
  WHERE op_margin IS NULL OR sales_to_capital IS NULL OR debt_to_equity IS NULL
''').fetchone()[0])
"
```

---

## Fuera de alcance de este plan

Quedan pendientes y **no** se abordan acá; cada uno merece su propio plan porque son features, no wiring ni bugs:

1. **§7.1 story type → patrón de proyección.** Los 5 arquetipos se clasifican y reportan pero no cambian la proyección: todos reciben los mismos 5 años planos. Es el hueco de spec más grande que queda.
2. **§7.3 fade a GDP en y10** y **P(bankruptcy) derivada de rating/Altman-Z para distressed** (issue abierto en Task 2.4).
3. **§6.5 sub-scores incompletos**: falta estabilidad de márgenes en `quality_score` y crecimiento de FCF en `growth_score`.
4. **CLI faltante**: `bot config validate` / `edit`, `refresh --portfolio`, `analyze` variádico, `--from-screen`, `--json`, `--dry-run`, `--full` (hoy `--all`).
5. **Ops (§9.3, §13)**: `scripts/bootstrap.sh`, `scripts/install_cron.sh`, backup, logging a archivo, `INDEX.md` diario, headers de reproducibilidad en los reportes.
6. **Testing (§12)**: el e2e `refresh → screen → analyze` sobre el mini-universo de 5 empresas, y `pytest-cov` con el gate de 100% en `valuator/` y `screener/rules.py`.
7. **Cassettes de FMP sintéticas**: las 4 familias se auto-documentan como "MUST be re-recorded against the live FMP API before production use". Drift del lado de FMP es invisible hoy.
8. **Corporate actions vía IBKR Flex** — desbloquea 2 de los eventos del §8.3 (issue implícito en ADR 0004).
9. **§4.3.3 restated financials**: la PK soporta dos versiones pero el upsert borra por ticker antes de insertar, así que la versión original se descarta.
10. **§4.3.4 survivorship**: `status` escribe `active`/`inactive`, no el vocabulario `active`/`delisted`/`acquired` del spec, y no hay pase de detección de delisting.
11. **§5.2 boundary**: los lookups de Damodaran son SQL ad-hoc en 4 módulos en vez de vivir en el módulo Damodaran.
12. **`--region` de `bot refresh --damodaran`** descarga los archivos US y los etiqueta con la región pedida.
