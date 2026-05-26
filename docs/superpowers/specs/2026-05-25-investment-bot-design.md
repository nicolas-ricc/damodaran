# Investment Bot — Design Spec

**Fecha**: 2026-05-25
**Autor**: Nicolás Riccomini (con Claude vía `superpowers:brainstorming`)
**Estado**: Diseño aprobado, pendiente review final antes de pasar a plan de implementación.

---

## 1. Resumen ejecutivo

Bot de inversiones personal, operado por CLI, que sirve dos propósitos:

1. **Screener + ranking** (parte A): correr filtros sobre un universo global de empresas para identificar candidatos infravalorados según una filosofía inspirada en Aswath Damodaran (cheap + quality + growth, evitando value traps).
2. **Portfolio monitor** (parte C): vigilar la cartera real del usuario en Interactive Brokers UK, detectar eventos relevantes (filings nuevos, cambios en valuación intrínseca, deterioro de fundamentals) y producir reportes diarios.

**No incluye**: day trading, ejecución automática de órdenes, análisis técnico, alertas por movimiento de precio, dashboard web, multi-usuario.

**Filosofía operativa**: precio ≠ valor. Los reportes muestran supuestos explícitos, sensitivity, y trazabilidad total de cada decisión. El bot no opera; sugiere candidatos para que el humano investigue.

**Diferencia con un screener tradicional**: la separación estricta entre datos crudos, screening mecánico, y análisis interpretativo (ver §3) — y la integración de DCF con story types como parte del flujo normal, no como anexo.

---

## 2. Alcance y decisiones de producto

| Dimensión | Decisión |
|---|---|
| Tipo de bot | A (screener + ranking) + C (portfolio monitor) |
| Profundidad del análisis | Filtro cuantitativo + DCF simplificado por candidato. LLM-as-analyst diferido a Fase 2. |
| Universo | Global (~50.000 empresas), datos diarios EOD, sin tiempo real |
| Broker | Interactive Brokers UK (solo lectura de portfolio en Fase 1) |
| Interfaz | CLI + reportes Markdown/HTML/CSV en el sistema de archivos. Sin email, sin Telegram, sin web. |
| Modo de operación | Local en máquina del usuario, schedule vía cron |
| Datos pagos aceptados | Sí, ~USD 50-100/mes (Financial Modeling Prep Ultimate o equivalente) |

---

## 3. Arquitectura en cuatro capas

Separación deliberada entre datos crudos, screening mecánico, y análisis interpretativo. Cada capa es un módulo Python aislado con interfaz explícita, intercambiable sin tocar las otras.

```
┌──────────────────────────────────────────────────────────────┐
│ CAPA A — Datos crudos de Damodaran                           │
│ Importación de datasets de NYU Stern. Hechos, sin opinión.   │
└──────────────────────────────────────────────────────────────┘
                              │  (benchmarks por industria/país)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ CAPA B — Screener mecánico numérico                          │
│ Filtros cuantitativos sobre el universo entero (~50k).       │
│ Quality gates → value indicators → trap detection → ranking. │
│ Configuración declarativa via YAML. Cero subjetividad.       │
└──────────────────────────────────────────────────────────────┘
                              │  (top 100-300 candidatos)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ CAPA C — Análisis profundo Damodaran-style                   │
│ DCF por story type, supuestos explícitos con source,         │
│ sensitivity analysis obligatorio, narrative consistency      │
│ flags cuantitativos. Aquí vive la filosofía y lo subjetivo.  │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  Portfolio monitor (parte C)
                  consume A+B+C para vigilar posiciones reales
```

**Por qué esta separación**:
- Costo computacional: B barato sobre 50k empresas; C caro pero solo sobre 200.
- Auditabilidad: ante una shortlist mala, podés saber en qué capa falló.
- Sustituibilidad: cambiar de filosofía de inversión (B) o de modelo de valuación (C) sin tocar las demás. LLM analyst de Fase 2 se enchufa como extensión de C.
- Honestidad: el código deja explícito qué es mecánica objetiva (B) vs interpretación subjetiva (C).

---

## 4. Capa de datos

### 4.1 Proveedores

| Proveedor | Responsabilidad | Costo | Refresh |
|---|---|---|---|
| **SEC EDGAR** | Fundamentals oficiales US (10-K/10-Q/8-K) | Gratis | Event-driven (nuevo filing) |
| **Financial Modeling Prep** (plan Ultimate) | Fundamentals globales normalizados, precios EOD, ratios | ~USD 70/mes | Diario (precios), semanal (fundamentals) |
| **IBKR Client Portal API** | Portfolio (posiciones, cash, P&L, trades) | Incluido en cuenta | Diario |
| **Damodaran datasets** (NYU Stern) | Benchmarks sectoriales/país, betas, ERPs, WACC, márgenes, ratios | Gratis | Anual + verificación mensual |

EOD Historical Data queda como alternativo a FMP, intercambiable detrás del mismo adapter. La selección final puede revisarse después del MVP según cobertura observada.

### 4.2 Schema interno (DuckDB)

Tablas centrales:

- `companies` — ticker, name, country, industry_damodaran, ISIN, exchange, status (active/delisted/acquired)
- `financials_annual` — revenue, EBIT, EBITDA, net income, total_debt, cash, capex, working_capital, shares, ...
- `financials_quarterly` — idem trimestral
- `prices_daily` — close, volume, market_cap por ticker/fecha
- `damodaran_industry` — wacc, beta_unlevered, op_margin, ROIC, sales_to_capital, payout_ratio, PE, EV/EBITDA por industria/región/año
- `damodaran_country` — ERP, country_risk_premium, tax_rate, risk_free_rate por país/año
- `portfolio_snapshots` — append-only, snapshot diario de posiciones IBKR
- `trades` — ejecuciones desde IBKR (append-only)
- `events_log` — bitácora de eventos detectados por el portfolio monitor
- Auxiliares: `industry_mapping`, `currencies` (FX históricas), `filings_log`, `screener_candidates`

### 4.3 Decisiones explícitas

1. **Mapeo de industrias proveedor → Damodaran**: CSV mantenido a mano (~95 industrias). Esfuerzo único de 2-4 horas + ajustes ocasionales.
2. **Normalización a USD**: todos los financials se convierten a USD usando FX al cierre del período fiscal. Los datasets de Damodaran ya están en USD.
3. **Restated financials**: guardamos versión original y restatement con flag. El screener usa siempre la última; queda trazabilidad histórica.
4. **Survivorship bias**: las empresas que dejan de cotizar quedan en cache con `status` apropiado. Crítico para futuros backtests.

### 4.4 Caching y refresh

Principio: nunca re-pedir un dato vigente. Refresh **incremental**, no full:

- Precios: append-only por fecha.
- Fundamentals: invalidación por evento (nuevo filing detectado), no por TTL.
- Damodaran: hash-check mensual del archivo en NYU Stern; re-import completo si cambió (swap atómico).
- Portfolio: snapshot completo diario (es chico).

### 4.5 Por qué DuckDB

Columnar, embebido, optimizado para queries analíticas sobre fundamentals históricos. Un solo archivo (`bot.duckdb`), backup = `cp`. Sin servidor, sin auth. ~10-50× más rápido que SQLite en este perfil de queries; sin la complejidad operativa de Postgres.

---

## 5. Capa A — Datasets de Damodaran

### 5.1 Qué contienen (y qué no)

**NO contienen** datos por empresa, precios, ni reportes financieros. Son agregados de calibración por industria y país, actualizados cada enero en `pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html`.

Cobertura geográfica (versiones separadas de la mayoría de tablas):
- US, Europa, Mercados Emergentes, Japón, China, India, Australia/NZ/Canadá, Global agregado (~47k empresas)

Datos por industria (~95 sectores Damodaran):
- Cost of capital (cost of equity, cost of debt, WACC)
- Betas: raw, levered, unlevered
- Estructura de capital típica del sector
- Márgenes (operating, net, gross)
- Retornos (ROE, ROIC, ROC)
- Múltiplos (PE, PBV, EV/EBITDA, EV/Sales, EV/Invested Capital)
- Tasas efectivas de impuestos
- Reinvestment rate, sales-to-capital ratio
- Working capital y R&D como % de revenue

Datos por país (~150 países):
- Equity risk premium (ERP)
- Country risk premium
- Tasas corporativas
- Risk-free rate por moneda

### 5.2 Responsabilidad del módulo

Solo importación, validación, y lookups. Sin lógica de negocio.

Interfaz mínima:
- `get_industry_benchmark(industry, region, year) → dict`
- `get_country_risk(country, year) → dict`

---

## 6. Capa B — Screener mecánico

### 6.1 Estructura en capas de filtrado

```
Universo (~50k empresas)
    │
    ▼  Quality gates (eliminatorios)
    ▼  Value indicators (al menos uno, eliminatorio)
    ▼  Trap detection (eliminatorios)
    ▼  Ranking score
Shortlist top 20-30 → reporte
```

### 6.2 Quality gates (default)

- Market cap > USD 100M (configurable)
- ≥ 5 años de financials disponibles
- Excluir financial services (banks, insurance) por default
- Net Debt / EBITDA < 4.0
- Interest coverage (EBIT/Interest) > 2.0 — proxy de "deuda dentro de capacidad"
- Operating cashflow > 0 en ≥ 4 de los últimos 5 años
- Goodwill / Total Assets < 50%

### 6.3 Value indicators (al menos uno)

Todos relativos al sector vía datasets Damodaran:

- PE < industry_median × 0.7
- EV/EBITDA < industry_median × 0.7
- P/BV < industry_median × 0.7 **y** ROE > industry_median (combinación clásica de value real, no trap)
- FCF Yield > 8%

### 6.4 Trap detection (eliminatorios)

- Revenue declinando > 5% anual promedio últimos 3 años
- Operating margin contrayéndose > 200bps en los últimos 3 años
- **ROIC < WACC sectorial** (la empresa destruye valor — filtro central Damodaran)
- Accruals altos (Sloan ratio > 10%)
- Share count creciendo > 5% anual sin M&A justificado
- Auditor changes recientes o late filings (cuando el dato está disponible)

### 6.5 Ranking score

Sobre candidatos que pasan las tres capas:

```
score = 0.40 × value_score      (qué tan barata vs sector)
      + 0.30 × quality_score    (ROIC vs WACC, ROE, margin stability)
      + 0.20 × growth_score     (revenue/FCF growth sostenido)
      + 0.10 × margin_of_safety (intrinsic_value DCF / price — viene de Capa C)
```

Cada sub-score calculado por percentiles dentro del universo filtrado (no thresholds absolutos).

### 6.6 Configuración declarativa

Todo en `config/screener_config.yaml`. Cada regla del YAML mapea a una clase Python testeable en aislamiento. Presets out-of-the-box (todos editables):

- `damodaran_value` (default)
- `deep_value` (más Graham que Damodaran)
- `qarp` — Quality at Reasonable Price (más Buffett-tardío)

### 6.7 Limitación honesta

El screener cuantitativo no puede juzgar narrativa cualitativamente. Lo más cerca que llega es vía proxies (growth sectorial via Damodaran, R&D intensity, addressable market via industry size). El gap real lo cubre Fase 2 (LLM analyst) o lectura humana del 10-K.

---

## 7. Capa C — Análisis profundo Damodaran-style

### 7.1 Story types

Cinco arquetipos, cada uno con patrón distinto de proyección:

| Story type | Proyección |
|---|---|
| `high-growth` | Growth alto decreciendo, márgenes mejorando hacia sector, reinvestment alto al principio |
| `mature-stable` | Growth ≈ GDP nominal, márgenes en promedio sectorial, reinvestment = depreciación |
| `mature-decline` | Growth negativo controlado, márgenes erosionándose, reinvestment mínimo |
| `cyclical` | Promediar a través del ciclo (no usar año actual), reinvestment irregular |
| `distressed` | Probabilidad explícita de quiebra, valuación condicional a supervivencia |

Auto-asignación por reglas (crecimiento histórico, edad, σ(earnings), deuda, sector). Override manual en `config/assumptions/<TICKER>.yaml`.

### 7.2 Modelo DCF de dos etapas

Fórmula única, lo que cambia por story type es la proyección de inputs:

```
                   N
                  ─────
EV =               \      FCFF_t            FCFF_{N+1}
                    \    ─────────  +  ─────────────────────  ÷ (1+WACC)^N
                    /    (1+WACC)^t    (WACC − g_terminal)
                  ─────
                  t=1

Equity = EV − Net Debt + ajustes (minoritarios, cross-holdings)
Per share = Equity / Shares diluidas

FCFF = EBIT × (1−tax) − Reinvestment
Reinvestment = ΔWC + Capex − Depreciation ≈ ΔRevenue / sales_to_capital
```

### 7.3 Seis supuestos críticos con source explícito

Cada supuesto tiene `source ∈ {manual, analyst_consensus, sector_default_damodaran, rule_based, historical_average}`. El reporte muestra siempre cuál es cuál.

| Supuesto | Default | Override común |
|---|---|---|
| Revenue growth path (años 1-5) | analyst_consensus → converge a GDP nominal país en y10 | Manual cuando consensus está sesgado |
| Operating margin steady-state | Sector default Damodaran | Manual si hay razón estructural |
| Sales-to-capital ratio | Sector default Damodaran | Manual |
| WACC | CAPM con beta sectorial + ERP país (ambos Damodaran) + estructura de capital de la empresa | Raro, solo si estructura atípica |
| Terminal growth (g) | `min(risk_free_rate_país_damodaran, GDP nominal)` | Casi nunca |
| Probabilidad de quiebra | 0 (excepto distressed: derivada de rating/Altman Z) | Manual con info cualitativa |

### 7.4 Sensitivity analysis (obligatorio)

Cada reporte de análisis incluye:

1. **Tornado**: impacto en intrinsic value de mover cada supuesto ±20%, ordenado por impacto.
2. **Tabla 2D**: grilla 5×5 sobre los dos supuestos más sensibles (típicamente growth × margin) con margin of safety por celda.
3. **Margin of safety headline**: con supuestos default — pero el reporte deja claro que es un punto en una nube.

### 7.5 Narrative flags cuantitativos

Proxies de "story↔numbers consistency" (verde/amarillo/rojo):

- **Story-margin consistency**: si `high-growth` pero margins > sector, flag amarillo.
- **Growth-reinvestment consistency**: si growth implícito no se soporta con reinvestment proyectado, flag rojo.
- **Beta vs business risk**: si beta sectorial < 1 pero leverage operativo+financiero altos, flag amarillo.
- **Terminal value share > 80%**: flag amarillo (valuación frágil, depende casi todo de perpetuidad).
- **Country exposure vs ERP listado**: si revenue mayoritariamente fuera del país de listado y ERP weighted > listado + 300bps, flag rojo.

No entran al ranking — son señales para que el humano lea y decida.

### 7.6 Override manual

`config/assumptions/<TICKER>.yaml` con story_type, overrides numéricos, y notas en texto libre. El reporte incluye sección "Manual overrides aplicados" con las notas y valores cambiados — trazabilidad total.

### 7.7 Output

`reports/YYYY-MM-DD/analysis/<TICKER>.md` con secciones: resumen ejecutivo, story type + razones, supuestos (con source), DCF detallado año a año, sensitivity (tornado + 2D), narrative flags, manual overrides si existen, sanity check vs múltiplos sectoriales.

---

## 8. Portfolio monitor

### 8.1 Sync con IBKR

**API elegida**: Client Portal API (REST), no TWS API.

- HTTP/JSON, más simple de operar
- Auth OAuth + sesión renovable
- IBKR provee Docker oficial `ibkr/cp-gateway` corriendo en localhost
- Trade-off: requiere re-login interactivo cada ~24h (10 segundos en browser). Aceptable.

Si la fricción de re-login molesta, migración natural a TWS API con IB Gateway headless.

### 8.2 Datos sincronizados diariamente

- Posiciones (ticker, qty, avg_cost, market_value, currency)
- Cash balances por moneda
- Trades nuevos desde la corrida anterior
- Dividendos / corporate actions

### 8.3 Eventos detectados

**Vienen de IBKR**:
- Nueva posición abierta / cerrada
- Cambio de tamaño > 10% (configurable)
- Dividendo / split / corporate action
- Cambio de moneda base

**Derivados de las capas A/B/C** (lo valioso):
- **Filing nuevo** para una posición → auto-corre `bot analyze <ticker>`, deja reporte actualizado
- **Intrinsic value cruzó precio** (en cualquier dirección)
- **Narrative flag nuevo en rojo** sobre una posición
- **Caída debajo de quality gate** (ej: Net Debt/EBITDA cruzó 4×, ROIC cayó debajo de WACC)
- **Industria recalibrada** por nuevo dataset Damodaran (WACC sectorial cambió > 100bps)
- **Concentración**: posición > 15% del portfolio por apreciación

**Explícitamente NO detectados** (anti-ruido):
- Movimientos de precio per se — si tu valuación no cambió, el precio no es información sobre la empresa.
- Noticias del feed — un bot Damodaraniano no debería empujar a reaccionar a titulares.

### 8.4 Output

- `reports/YYYY-MM-DD/portfolio.md`: resumen, posiciones actuales, eventos detectados, acciones sugeridas
- `reports/YYYY-MM-DD/alerts.md`: solo eventos nuevos (vacío si no hay)
- `events_log` en DuckDB: bitácora completa para auditoría histórica

---

## 9. CLI y estructura de reportes

### 9.1 Estructura de carpetas

```
~/investment-bot/
├── bot.duckdb
├── config/
│   ├── screener_config.yaml
│   ├── presets/{damodaran_value,deep_value,qarp}.yaml
│   ├── assumptions/<TICKER>.yaml
│   └── industry_mapping.csv
├── reports/
│   └── YYYY-MM-DD/
│       ├── INDEX.md
│       ├── portfolio.md
│       ├── alerts.md
│       ├── screen/<preset>.{md,csv}
│       └── analysis/<TICKER>.{md,html}
└── logs/YYYY-MM-DD.log
```

Cada día = carpeta autocontenida e inmutable. Reportes en Markdown (verdad primaria), HTML opcional con gráficos (tornado, sensitivity 2D), CSV para shortlists.

### 9.2 Comandos CLI (Typer)

```
bot refresh [--full | --damodaran | --portfolio]
bot screen [--preset NAME | --config PATH] [--top N]
bot analyze <TICKER>... [--from-screen NAME] [--override PATH]
bot portfolio [--history | --concentration]
bot status
bot show <TICKER>
bot doctor
bot config validate
bot config edit <screener|preset>
```

Convenciones:
- Stdout: resumen humano; detalle en reportes.
- Exit codes: 0 OK, 1 error operativo, 2 data error.
- `--json` global para machine-readable output.
- `--dry-run` donde aplique.

### 9.3 Schedule (cron)

```
0 9  * * 1-5    bot refresh && bot portfolio    # días hábiles
0 10 * * 6      bot refresh && bot screen       # sábado
```

---

## 10. Stack técnico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12+ |
| Package manager | uv |
| Storage | DuckDB |
| CLI | Typer |
| HTTP | httpx |
| Data | Polars |
| Validation | Pydantic v2 |
| Plotting | Matplotlib (estáticos) + Plotly mínimo (heatmaps interactivos) |
| Templating | Jinja2 |
| Testing | pytest + pytest-vcr |
| Quality | ruff + mypy --strict |
| Logging | structlog |
| Secrets | .env + python-dotenv |
| Scheduling | cron del sistema |

**Explícitamente excluido**: web framework, ORM, scheduler externo, Docker para la app (solo para IBKR gateway), SDKs de LLM en Fase 1.

---

## 11. Layout del repo

```
investment-bot/
├── pyproject.toml
├── uv.lock
├── README.md
├── .env.example
├── .gitignore
├── CONTEXT.md
├── docs/
│   ├── adr/
│   └── superpowers/specs/
├── src/bot/
│   ├── cli.py
│   ├── config.py
│   ├── storage/{db.py, schema.sql}
│   ├── ingest/{base.py, sec_edgar.py, fmp.py, eod.py, ibkr.py, damodaran.py}
│   ├── screener/{rules.py, engine.py}
│   ├── valuator/{story_types.py, dcf.py, assumptions.py, sensitivity.py, narrative_flags.py}
│   ├── portfolio/{sync.py, diff.py}
│   ├── reporting/{markdown.py, html.py, templates/}
│   └── utils/{fx.py, dates.py, logging.py}
├── tests/{unit, integration, fixtures}
└── scripts/{install_cron.sh, bootstrap.sh}
```

---

## 12. Testing strategy

Tres niveles:

1. **Unit (rápidos, sin I/O)**: funciones puras de Capa B (cada regla) y Capa C (DCF, sensitivity, story type classifier, narrative flags). Casos numéricos hardcodeados verificados contra Excel.
2. **Integration con VCR cassettes**: cada adapter de ingest tiene tests con respuestas grabadas. Regrabables cuando la API cambia.
3. **End-to-end**: `refresh → screen → analyze` sobre fixture mini-universe de 5 empresas. < 10 segundos.

**Cobertura objetivo**: 100% en `valuator/` y `screener/rules.py`. El resto: lo que caiga naturalmente.

---

## 13. Operación

### 13.1 Bootstrap (`scripts/bootstrap.sh`)

1. Crea `bot.duckdb` y corre migraciones.
2. Pide API keys (FMP, IBKR) y las guarda en `.env`.
3. Descarga e importa datasets Damodaran.
4. Levanta `ibkr/cp-gateway` y guía por el OAuth de IBKR.
5. Corre `bot doctor` para verificar.

### 13.2 Manejo de errores

Principio: **degrade gracefully, alert loudly**. Failures parciales se logean y se reportan al final del run. Si > 5% del universo falló, exit code 2 → cron alerta.

### 13.3 Reproducibilidad

Cada reporte incluye en header las versiones de datos usadas (fecha último filing, versión dataset Damodaran, snapshot portfolio). Re-corridas son reproducibles dado el mismo estado del cache.

### 13.4 Backup

`bot.duckdb` es el único archivo crítico. Rsync semanal a otro disco/cloud. El resto regenerable.

---

## 14. Estimación

Part-time: ~2-3 meses. Full-time: ~4-6 semanas.

- Esqueleto + ingest SEC + Damodaran + storage: 2-3 semanas part-time
- Screener (Capa B) completo con presets: 1-2 semanas
- Valuator (Capa C) con DCF + sensitivity + flags: 2-3 semanas (lo más delicado)
- IBKR portfolio + diff: 1 semana
- Reportes + CLI + bootstrap: 1 semana
- Tests + ops: distribuidos

---

## 15. Fuera de alcance (Fase 1)

- **LLM analyst (Capa D)**: lectura automatizada de 10-K / earnings calls con resumen tipo *Narrative and Numbers*. Diferido a Fase 2.
- **Ejecución de órdenes vía IBKR**: solo lectura en Fase 1.
- **Backtesting** del screener contra histórico. Estructura de datos (survivorship-aware) lo permite, pero el motor de backtest no es parte del MVP.
- **Dashboard web**: si después de meses de uso se justifica más interactividad, se evalúa entonces.
- **Notificaciones push** (email, Telegram): toda la salida es archivo en disco. Si se quiere push, módulo `notifier` aparte que lea `alerts.md`.
- **Análisis de bancos / aseguradoras**: contabilidad lo bastante distinta como para necesitar screener separado. Excluidos por default; configurable.

---

## 16. Riesgos conocidos

1. **Mapeo industrias proveedor → Damodaran**: trabajo manual sostenido. Industrias nuevas en FMP/EOD requieren actualizar el CSV.
2. **Calidad de fundamentals internacionales**: variable por país. Gaps de cobertura pueden requerir cambiar de proveedor.
3. **IBKR Client Portal session re-auth**: fricción operativa diaria. Tolerable, migración a TWS posible si molesta.
4. **DCF garbage-in/garbage-out**: el valor del bot depende críticamente de la calidad de los supuestos. La sensitivity analysis y los narrative flags mitigan, pero no eliminan, el riesgo de confiar en un intrinsic value derivado de un consensus de analistas sesgado.
5. **No detectar fraudes contables**: ningún screener cuantitativo es robusto a fraude. Los filtros de quality (accruals, cashflow) ayudan, pero la lectura humana sigue siendo necesaria.
