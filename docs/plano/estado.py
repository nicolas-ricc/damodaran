"""Inventario de estado: qué está hecho de verdad y qué no.

Los estados salen de una auditoría contra el código (no contra el spec), hecha
sobre el commit que declara AUDITADO_EN. Es una foto, no una verdad permanente:
cuando el código avance, esto miente hasta que se vuelva a auditar.

Cuatro estados, y el tercero es el que importa:

    hecho     existe, algo lo llama, y tiene tests
    a-medias  existe pero le falta una parte sustantiva
    muerto    el código existe y nada lo llama, o nada lo alimenta
    falta     solo vive en el spec o en una ADR
"""
from html import escape as esc

AUDITADO_EN = "cda2603"
AUDITADO_EL = "28 de octubre de 2026"

ESTADOS = [
    ("hecho", "hecho", "existe, algo lo llama, y tiene tests"),
    ("a-medias", "a medias", "existe pero le falta una parte sustantiva"),
    ("muerto", "declarado, muerto", "el código existe y nada lo llama, o nada lo alimenta"),
    ("falta", "falta", "solo vive en el spec o en una ADR"),
]

# Estado agregado de cada bloque de la axonometría del nivel 1.
BLOQUES = {
    "damodaran": "a-medias", "sec": "a-medias", "fmp": "hecho", "ibkr": "a-medias",
    "adapters": "hecho", "duckdb": "a-medias",
    "gates": "hecho", "value": "hecho", "traps": "a-medias", "ranking": "a-medias",
    "story": "a-medias", "assumptions": "a-medias", "dcf": "a-medias",
    "sensitivity": "hecho", "flags": "a-medias",
    "monitor": "a-medias", "events": "a-medias", "reports": "a-medias",
}

# (id, nombre, estado, evidencia, nota)
INVENTARIO = {
"capa-a": ("Capa A · datos", "de dónde salen los hechos", [
 ("da-parse", "Parseo de Damodaran", "hecho", "ingest/damodaran.py:528,559",
  "Industria, país y columnas derivadas. Corta la segunda tabla del archivo de país, que traía 21 ERP incorrectos."),
 ("da-download", "Descarga de datasets", "a-medias", "ingest/damodaran.py:587",
  "Es la única puerta de entrada de todos los benchmarks del bot, y está parcheada en los cinco tests que la tocan. Nunca se ejerció contra la red real."),
 ("da-regiones", "Las ocho regiones", "falta", "ingest/damodaran.py:59-60",
  "Sin cambios: las URLs siguen fijas y apuntan a Estados Unidos, y --region sigue siendo una etiqueta y no un selector de archivo. Ya no es una limitación oculta: refresh --damodaran ahora rechaza --region != US con exit 2 (cli.py), así que el gap queda declarado en vez de producir filas europeas con datos de EE.UU. Bajo el alcance US-only actual es irrelevante; vuelve a importar si M2 global reabre."),
 ("da-riskfree", "Risk-free por moneda", "hecho", "reference/currencies.py; valuator/assumptions.py:961-973",
  "El importador ya no lee el escalar del encabezado de wacc.xls ni escribe risk_free_rate en damodaran_country (la columna se elimina, con un ALTER para bases existentes). La tasa libre de riesgo y el PBI nominal salen por moneda de config/currencies.yaml, una tabla curada a mano a partir de la tabla de enero de Damodaran y del WEO del FMI (no se importa), cargada por load_currency_table. El valuador la busca por la moneda de la última fila anual no reexpresada (#109)."),
 ("sec-parse", "SEC EDGAR: cliente y parseo", "hecho", "ingest/sec_edgar.py:39,229",
  "Los hechos XBRL se atribuyen por su propio período (start/end), no por los fy/fp del filing que los trajo: anual = hecho de duración de 350 a 380 días, trimestral = de 80 a 100 días (parse_company_facts:229, _collect_period_rows:365). fiscal_year es el año calendario del fin del período; el año que termina 2014-02-01 es fiscal_year 2014. Si dos fines anuales caen en el mismo año calendario se conserva el posterior y se registra sec_edgar.fiscal_year_collision. El (fiscal_year, fiscal_quarter) trimestral sale de la distancia a los fines anuales vecinos (_fiscal_quarter_key:317); fy/fp del primer filing quedan solo como respaldo."),
 ("sec-import", "SEC EDGAR: importador", "hecho", "ingest/sec_edgar.py:493,615",
  "Ya no es solo «bot show --fetch»: refresh_universe (ingest/universe.py:298-300) llama upsert_company/upsert_financials_annual/upsert_financials_quarterly directamente para cualquier proveedor que pase por el puerto, y EdgarStooqProvider (ingest/edgar_stooq.py) es ese llamador real en el camino por defecto. El bug de borrado sigue corregido: upsert_company hace merge-preserve por columna en vez de DELETE+INSERT crudo."),
 ("fmp-todo", "FMP: cliente, fundamentals y precios", "hecho", "ingest/fmp.py:44,239",
  "FmpProvider (239) implementa el puerto MarketDataProvider (ingest/provider.py) sobre FmpClient (44): fundamentals, daily_prices, fx_rates y latest_filing_date. El refresco incremental con marca de agua por fecha ya no vive acá — se movió a ingest/universe.py (latest_local_filing_date + _should_skip, _max_price_date; _refresh_one:662 lo salta salvo force, y bot refresh --fundamentals --force se saltea _should_skip y reimporta todo), que ahora es provider-agnóstico: FakeProvider implementa el mismo puerto para los tests (tests/fake_provider.py). Ya no es el proveedor por defecto (ver edgar-stooq): sigue disponible detrás de BOT_DATA_PROVIDER=fmp para M2."),
 ("edgar-stooq", "EdgarStooqProvider: el stack gratis por defecto", "hecho", "ingest/edgar_stooq.py:33; ingest/stooq.py:63; docs/adr/0007",
  "Implementa el mismo puerto MarketDataProvider componiendo SecEdgarClient (fundamentals, profile, dei shares) y StooqClient (EOD). Es el proveedor por defecto (BOT_DATA_PROVIDER=edgar-stooq); ver ADR 0007. La corrida real de esta tarea confirmó fundamentals (25/25 importados, dos pasadas) pero encontró que Stooq ahora antepone un reto JS anti-bot (proof-of-work) a las peticiones sin navegador — 404/200-con-reto en vez del límite diario documentado (StooqRateLimitError). El código clasifica esa falla correctamente como fallo de proveedor (no como un crash), pero no hay forma de superar el reto sin un navegador real; queda registrado como riesgo operativo del proveedor, no como bug de ingest."),
 ("ibkr-pos", "IBKR: posiciones y efectivo", "hecho", "ingest/ibkr.py:205,211",
  None),
 ("ibkr-trades", "IBKR: historial de operaciones", "hecho", "portfolio/trades.py:63; portfolio/command.py",
  "run_portfolio lo llama en cada bot portfolio, después del snapshot: marca de agua incremental por cuenta, deduplicación por id de ejecución. Tests unitarios con cliente simulado y de integración sobre run_portfolio. Solo ve los fills de la sesión de TWS: el historial se acumula corrida a corrida."),
 ("ibkr-corp", "IBKR: dividendos y splits", "a-medias", "ingest/ibkr_flex.py; portfolio/command.py",
  "El importador del Flex Web Service (#56) escribe corporate_actions en cada bot portfolio cuando hay token y query id. Está construido contra un statement sintético: falta validarlo contra una descarga real (#110)."),
 ("universo", "El universo", "hecho", "ingest/universe_default.csv:1-3; tests/unit/test_universe_csv.py",
  "Los 451 tickers sintéticos se fueron: el CSV de fábrica son los 503 componentes reales del S&P 500 en formato FMP (guion, no punto — BRK-B), con test dedicado que verifica el conteo, miembros permanentes y el formato. Sigue siendo US-only por decisión de alcance (ver ADR 0006): el spec apunta a 50.000 empresas globales, y ese salto queda fuera de esta etapa. La corrida real de esta tarea confirmó fundamentals contra el universo real (25 tickers vía --limit, más una segunda pasada hasta agotar sesión, ver ADR 0007 y datos-reales)."),
 ("mapeo", "Mapeo de industrias", "hecho", "ingest/industry_mapping.py:124; ingest/industry_mapping.csv",
  "337 filas: las 144 originales de FMP (89 de las 94 industrias de Damodaran) más 193 de edgar_stooq, agregadas en dos pasadas de esta tarea contra el universo real completo (503 tickers, 0 diferidos): 25 tickers dejaron 14 SIC sin mapear y una segunda corrida contra los 503 completos dejó 137 más — casi todas variantes de puntuación/coma del mismo SIC de EDGAR (p. ej. \"Biological Products (No Diagnostic Substances)\" sin coma vs. \"Biological Products, (No Diagnostic Substances)\" con coma), porque el resolver normaliza mayúsculas/espacios/guiones pero no comas. Cada label del lado derecho ya existía del lado FMP (test_edgar_stooq_damodaran_labels_are_already_known_labels sigue en verde sin extender el comentario de racionalidad)."),
 ("fx", "Tipos de cambio", "a-medias", "utils/fx.py:104",
  "La descarga y la búsqueda están completas. La conversión tiene solo dos consumidores, así que PE, P/BV, EV/EBITDA y FCF yield siguen mezclando precio en moneda de cotización con cifras en moneda de reporte."),
 ("storage", "Conexión y esquema", "a-medias", "storage/db.py:24",
  "Sin versionado ni migraciones. Agregar una columna a una base existente es una operación nula que revienta después, en ejecución."),
 ("tablas", "Las quince tablas", "a-medias", "storage/schema.sql",
  "Las quince se escriben; corporate_actions solo cuando hay token y query id de Flex (#56). Tres columnas quedan siempre nulas: reinvestment_rate, payout_ratio e isin."),
]),

"capa-b": ("Capa B · screener", "dieciséis reglas, cero subjetividad", [
 ("gates-7", "Los siete quality gates", "hecho", "screener/rules.py:120-319",
  "Los siete con aritmética real y tests dedicados. Ninguno es un esbozo."),
 ("value-4", "Los cuatro value indicators", "hecho", "screener/rules.py:346-491",
  "Tres son relativos al sector y se saltean sin mediana. FCF yield es absoluto, y es el único que puede admitir a una empresa sin cobertura sectorial."),
 ("traps-4", "Cuatro de los cinco trap detectors", "hecho", "screener/rules.py:521-719",
  "Ingresos, margen, accruals y dilución. El tope de dilución no implementa la excepción por adquisición justificada que pide el spec, y lo dice en su propio docstring."),
 ("trap-roic", "ROIC contra WACC", "hecho", "screener/rules.py:601-624; screener/engine.py:698-707,815-829",
  "El filtro central del método ya es eliminatorio de punta a punta. La regla sigue skipeando cuando falta la mediana de WACC (rules.py:617-620), pero ese caso ya no llega a evaluate_company: la compuerta de cobertura (ADR 0006) saca a la empresa del universo antes, así que todo sobreviviente tiene WACC sectorial real y, si el detector skipea o falla, engine.py:704-707 lo trata como eliminación, no como aprobación."),
 ("coverage-gate", "La compuerta de cobertura", "hecho", "screener/engine.py:54-63,231-235,815-829; reporting/screen_report.py:123",
  "Implementada tal como la decide la ADR: antes de evaluar, la empresa que no se puede medir se registra en no_coverage y en rejected con una sola razón con nombre (CoverageReason, por precedencia): industry_unmapped, benchmark_missing (sin benchmark o wacc NULL) y, desde #109, currency_uncovered (la moneda de valuación no está en config/currencies.yaml). Nunca entra a evaluate_company (engine.py:815-829). El reporte y la CLI imprimen «Excluded by coverage gate (ADR 0006): N (industry_unmapped a · benchmark_missing b · currency_uncovered c)» (format_coverage_counts, engine.py:231; screen_report.py:123). Cubierto además por el e2e (NOCOVCO cae por este gate)."),
 ("registro", "Registro, configuración y presets", "hecho", "screener/config.py:140",
  "Los tres presets cargan y construyen sin error. qarp usa quince reglas: omite EV/EBITDA sin comentarlo."),
 ("motor", "El motor de dos pases", "hecho", "screener/engine.py:731",
  None),
 ("motor-trap", "La rama que elimina por trampa", "a-medias", "screener/engine.py:698-707",
  "Treinta y cinco tests de trampas a nivel regla, y ni uno que verifique que el motor efectivamente saca a la empresa. Es la única lógica eliminatoria sin cobertura de integración."),
 ("ranking-p", "Percentiles y pesos", "hecho", "screener/ranking.py:139",
  None),
 ("ranking-growth", "El score de crecimiento", "a-medias", "screener/engine.py:652",
  "Es el 20% del ranking y se calcula solo con el crecimiento compuesto de ingresos. El flujo de caja que promete el docstring nunca entra, y no hay ventana: una empresa con doce años y otra con cinco se comparan sobre horizontes distintos."),
 ("ranking-quality", "El score de calidad", "a-medias", "screener/engine.py:639",
  "El 30% del ranking. Le falta la estabilidad de márgenes que promete, y suma un diferencial (ROIC menos WACC) a un nivel (ROE), que son cosas de dimensiones distintas."),
 ("tax", "La tasa impositiva del ROIC", "muerto", "screener/engine.py:390",
  "Resuelve la tasa por país desde una columna que el ingest no llena, así que toda empresa cae al 21% por defecto. El ROIC del mundo entero se calcula con una constante estadounidense."),
 ("failed-gates", "El registro de por qué se cayó", "hecho", "screener/persist.py:57-77; storage/schema.sql",
  "Ya no solo se materializan las sobrevivientes: persist_candidates ahora escribe también result.rejected, con passed=FALSE, rank NULL y failed_gates real (el gate/trampa o la razón de cobertura que la sacó). rank y passed en el schema son nullable para admitir la fila de rechazo. La tabla ahora sí responde la pregunta para la que existe."),
 ("huecos", "Series con huecos", "a-medias", "screener/engine.py:424",
  "Las series descartan los nulos en vez de preservarlos. Un año con caja operativa nula hace que el gate reporte historia insuficiente y elimine a la empresa por un hueco de datos, no por caja negativa."),
]),

"capa-c": ("Capa C · valuador", "acá vive la filosofía", [
 ("classify", "El clasificador de story type", "hecho", "valuator/story_types.py:161",
  "Los cinco arquetipos son alcanzables y están testeados."),
 ("story-uso", "El story type como patrón de proyección", "a-medias", "valuator/assumptions.py:811-904",
  "Ya no es solo una etiqueta: dos supuestos se ramifican de verdad por arquetipo. _resolve_revenue_growth (811-847) hace un high-growth fadear linealmente de su crecimiento histórico al PBI nominal en vez de quedar plano; _resolve_operating_margin (865-904) hace un high-growth subir en rampa de su margen propio al del sector, y un cyclical usar el promedio del ciclo (≥4 años) en vez del margen del último año. Sigue faltando el resto de la tabla del spec: sales-to-capital y valuación condicional a supervivencia no se ramifican por story type; el crecimiento terminal tampoco se ramifica por arquetipo, solo por moneda (min de risk-free y PBI)."),
 ("story-edad", "La señal de edad", "hecho", "valuator/analysis.py:466-469",
  "Ya no es un parámetro que nadie pasa: cuando el caller no fuerza age_years explícito, se deriva de company_row.ipo_date (poblado ahora vía CompanyInfo/ingest/fmp.py) como (hoy − ipo_date) en años, y ese valor alimenta el clasificador de story type. Cubierto por tests de valuator/analysis."),
 ("story-altman", "La señal de Altman Z", "falta", "valuator/story_types.py:147",
  "El clasificador la lee y no existe ningún cálculo de Altman Z en todo el repo. Es la misma causa raíz que deja sin derivar la probabilidad de quiebra."),
 ("a-crecimiento", "Supuesto: crecimiento de ingresos", "a-medias", "valuator/assumptions.py:811",
  "El spec pide consenso de analistas convergiendo al PBI en el año diez. El código usa el promedio histórico de la propia empresa, plano sobre cinco años. El enum ni siquiera tiene el valor analyst_consensus."),
 ("a-sector", "Supuestos: margen, sales-to-capital, crecimiento terminal", "hecho", "valuator/assumptions.py:849,865,961",
  "Los tres coinciden con lo que promete el spec. El crecimiento terminal es min(risk-free, PBI nominal) de la moneda de valuación (_resolve_terminal_growth, 961-973); si la moneda no está en config/currencies.yaml queda UNRESOLVED, sin respaldo en USD."),
 ("a-wacc", "Supuesto: WACC", "a-medias", "valuator/dcf.py:150",
  "No es un supuesto resuelto: se recompone de partes. El costo del patrimonio y el de la deuda se leen de la fila sectorial, y los pesos salen del apalancamiento del sector, no del de la empresa."),
 ("a-quiebra", "Supuesto: probabilidad de quiebra", "muerto", "valuator/assumptions.py:999",
  "Devuelve cero siempre, salvo override manual. No mira rating, ni Altman Z, ni siquiera el story type. El valor de liquidación tampoco se resuelve y ni se renderiza."),
 ("a-crossregion", "Sustitución entre regiones", "hecho", "valuator/assumptions.py:528",
  "Existe y está declarada honestamente. Pero como solo se ingesta el dataset de Estados Unidos, es el caso normal y no la excepción: el WACC de una empresa europea es el de su industria en EE.UU."),
 ("dcf-core", "El DCF de dos etapas", "hecho", "valuator/dcf.py:198",
  "Proyección año a año, valor terminal, puente de enterprise value a patrimonio."),
 ("dcf-ajustes", "Ajustes por minoritarios y participaciones", "falta", "valuator/dcf.py:56",
  "El campo existe con valor cero y no tiene ningún camino de entrada: ni el pipeline lo llena ni está entre las claves de override, así que un YAML que lo intente falla. El docstring afirma que un override puede proveerlo, y es falso."),
 ("dcf-quiebra", "La mezcla por probabilidad de quiebra", "muerto", "valuator/dcf.py:239",
  "La aritmética está escrita y testeada. El insumo llega siempre en cero."),
 ("sens", "Tornado y grilla", "hecho", "valuator/sensitivity.py:178,221",
  "Siete ejes disponibles, celdas fuera de dominio devueltas como nulas."),
 ("flags-4", "Cuatro banderas narrativas", "hecho", "valuator/narrative_flags.py:185",
  "Solo growth_reinvestment puede emitir rojo. story_margin devuelve verde automático para cuatro de los cinco arquetipos, sin evaluar nada."),
 ("flag-pais", "La bandera de riesgo país", "muerto", "valuator/analysis.py:530",
  "El orquestador deja sus tres insumos sin setear, a propósito y con comentario. Sale gris el 100% de las veces. De los dos rojos que promete el spec, este es el que está muerto."),
 ("overrides", "Overrides por convención", "hecho", "config.py:87; cli.py:470,543; screener/engine.py:142,870",
  "Ya llegan por convención, no solo por --override explícito: Settings.assumptions_dir (config.py:87, default config/assumptions/) se usa en bot analyze (cli.py:470, <TICKER>.yaml automático) y en el segundo pase del screener (cli.py:543 → engine.py:142,870, cada candidato del shortlist con <TICKER>.yaml se valúa con ese override). config/assumptions/README.md y _EXAMPLE.yaml.example documentan las claves."),
]),

"salida": ("Salida", "reportes y vigilancia", [
 ("ev-vivos", "Diez eventos que sí disparan", "hecho", "portfolio/events.py:125,188,251,302,346,377,410,439,573",
  "Posición abierta, cerrada y cambio de tamaño (los tres salen de detect_position_changes, events.py:125), cambio de moneda, filing nuevo, cruce del valor intrínseco, bandera roja, caída de quality gate, recalibración sectorial y concentración. compute_events los saca de las posiciones, los filings y la diferencia entre las marcas de dos días."),
 ("ev-corp", "Dividendo y split", "a-medias", "portfolio/events.py:217,544; ingest/ibkr_flex.py",
  "El detector ya tiene quien le escriba la tabla: el importador de Flex (#56). Dispara solo con token configurado y no está validado contra datos reales (#110)."),
 ("ev-cruce", "El valor intrínseco cruzó el precio", "hecho", "portfolio/marks.py:105; portfolio/events.py:302,666",
  "El evento estrella del producto. mark_holdings guarda en holding_marks el valor intrínseco y el precio de cada posición en cada corrida de bot portfolio, antes de calcular eventos; compute_events compara la marca de hoy con la anterior y dispara en las dos direcciones. Límites: la primera corrida tras el cambio no tiene marca previa, así que ese día no hay cruce; y un día en que el valuador falla deja la marca en nulo y rompe la cadena de línea de base. Ver también #83 (repetir la corrida el mismo día duplica eventos) y #84 (símbolo de IBKR contra ticker)."),
 ("ev-huerfanos", "Caída de quality gate y recalibración sectorial", "hecho", "portfolio/events.py:439,410,683,691; portfolio/command.py:115; cli.py:562",
  "Los dos detectores ya los llama compute_events. Las marcas guardan los gates que falló cada posición (quality_gates y trap_detection del preset damodaran_value, que bot portfolio carga) y el WACC sectorial. Límites: sin marca previa el primer día no hay evento, y la cadena se corta cuando un ticker no tiene datos de screener (failed_gates nulo) o su sector no tiene benchmark (sector_wacc nulo); estos dos campos no dependen de que el valuador ande. Ver #83 y #84."),
 ("ev-ruido", "Bandera roja nueva", "hecho", "portfolio/events.py:346,675",
  "Solo dispara si la bandera es roja hoy y no lo era en la marca anterior; ya no se repite en cada corrida. Sin marca previa (primer día, o ticker recién comprado) todas cuentan como nuevas. Es a propósito: una marca previa sin banderas conocidas (día con el valuador caído) cuenta como vacía, así que tras un día sin valuación las rojas vigentes vuelven a salir como nuevas; si el nulo es el de hoy, no hay eventos. Ver #83 y #84."),
 ("ev-ventana", "Filing nuevo", "hecho", "portfolio/events.py:251,498,526; ingest/sec_edgar.py:595",
  "La ventana usa también la fecha de ingesta, inclusiva (filings_log.fetched_at, que upsert_filings conserva en los conflictos), y se deduplica contra events_log. Un 10-K presentado hace semanas e importado hoy dispara una vez. Ver #83 y #84."),
 ("sync", "Sincronización de la cartera", "hecho", "portfolio/sync.py:135",
  "Posiciones, efectivo y valuación con precios y tipo de cambio, idempotente por fecha y cuenta."),
 ("rep-portfolio", "El reporte de cartera", "hecho", "portfolio/report.py:241",
  "Resumen, posiciones, P&L, concentración y revisiones sugeridas (posiciones sobre el umbral); con --history agrega la historia y con --concentration el desglose. alerts.md se escribe siempre y queda vacío (cero bytes) en un día sin eventos. Si TWS no responde, bot portfolio sale con code 1 y un mensaje de una línea."),
 ("notifier", "Notificador opcional", "hecho", "notifier/__init__.py; notifier/email.py; notifier/telegram.py; cli.py",
  "BOT_NOTIFIER elige email o Telegram; bot portfolio manda alerts.md si no está vacío (config mal puesta sale con code 2 antes de sincronizar; si el envío falla, code 1 con los reportes ya escritos). Sin reintentos, y los tests usan transportes simulados."),
 ("rep-html", "El HTML con gráficos", "hecho", "reporting/html.py:78,131",
  "Supera lo que pide el spec: tornado real de Matplotlib inlineado como PNG, más un mapa de calor interactivo de Plotly con el JavaScript embebido. Abre sin conexión."),
 ("web-viewer", "El visor web de solo lectura", "hecho", "web/site.py; .github/workflows/site.yml",
  "bot analyze escribe reports/<fecha>/analysis/<TICKER>.json (schema_version 1) y bot site lo convierte en un sitio estático htmx: índice, 30 fragmentos rows/, 30 listas completas l/ para filtrar y ordenar sin JavaScript, y páginas c/ y f/ por ticker y fecha. El workflow site.yml corre en cada push a master (ruff, mypy, pytest, bot site) y publica en GitHub Pages. Requisito manual: Settings, Pages, Source = GitHub Actions. Es una superficie de lectura: no opera el bot (ADR 0008)."),
 ("rep-index", "INDEX.md", "falta", "spec §9.1",
  "La portada que contesta qué pasó hoy. Cero referencias en el código."),
 ("rep-repro", "El encabezado de reproducibilidad", "falta", "spec §13.3",
  "Los reportes llevan fecha de generación y nada más. Sin versión del dataset ni fecha del último filing, dos corridas distintas producen encabezados indistinguibles."),
 ("cli-8", "Los nueve comandos", "hecho", "cli.py:93-735; tests/unit/test_cli_site.py",
  "Los nueve responden y tienen al menos un test que los ejecuta: version, refresh, show, analyze, screen, portfolio, doctor, status y site. bot site (cli.py:717) no usa Settings ni variables de entorno: lee reports/ y escribe el sitio estático."),
 ("cli-falta", "Comandos y opciones que faltan", "a-medias", "cli.py:332-369; spec §9.2",
  "El analyze variádico y --from-screen ya existen (cli.py:332-369: uno o más tickers, o el shortlist del último screen persistido ordenado por rank). Lo que sigue faltando: config validate, config edit, --json global, --dry-run, refresh --portfolio. BOT_DATA_PROVIDER (edgar-stooq por defecto, fmp opcional) ya existe como variable de entorno pero no como opción de CLI expuesta ni validada por config validate, porque ese comando no existe."),
 ("doctor", "bot doctor", "hecho", "cli.py:507-558; storage/db.py:30-33; tests/unit/test_cli_doctor.py",
  "Los dos defectos de la auditoría anterior están corregidos: con BOT_FMP_API_KEY vacía agrega un issue y sale con code 1 (ya no code 0), y el conteo de tablas esperado ya no es un ocho hardcodeado — schema_table_count() (storage/db.py:30) lo deriva contando CREATE TABLE en schema.sql (hoy 15). Cinco tests dedicados. La corrida real de esta tarea lo confirmó reportando el proveedor por defecto (edgar-stooq) sin exigir BOT_FMP_API_KEY."),
]),

"proyecto": ("El proyecto", "hitos, decisiones y operación", [
 ("m1", "M1 · esqueleto, Damodaran y SEC", "hecho", "739 tests verdes", None),
 ("m2", "M2 · universo global y stack de datos", "a-medias", "universe_default.csv; docs/adr/0007",
  "El universo ya es real: 503 tickers del S&P 500 en vez de 451 sintéticos, y ya hubo dos corridas reales contra la red (FMP el 2026-09-02, el stack gratis edgar-stooq el 2026-09-09; ver datos-reales). El proveedor por defecto pasó de FMP a la composición SEC EDGAR + Stooq ($0/mes, ADR 0007); FMP queda disponible detrás de BOT_DATA_PROVIDER=fmp para cuando M2 reabra la expansión global — sigue siendo US-only por naturaleza (EDGAR no cubre fuera de EE.UU.) y una sola región de Damodaran, ambas decisiones de alcance explícitas (ver ADR 0006) y no límites ocultos."),
 ("m3", "M3 · screener", "hecho", "screener/", "La compuerta de cobertura (ADR 0006) ya está implementada, con tres razones con nombre."),
 ("m4", "M4 · valuador", "hecho", "valuator/", "El story type ya rama crecimiento y margen; le sigue faltando sales-to-capital y valuación condicional a supervivencia. El crecimiento terminal ya sale de la moneda de valuación (min entre risk-free y PBI de esa moneda)."),
 ("m5", "M5 · IBKR", "a-medias", "portfolio/", "Las operaciones ya se sincronizan en cada bot portfolio (#27); las corporate actions llegan por el Flex Web Service (#56), sin validar aún contra datos reales (#110)."),
 ("adr-ok", "ADR 0001, 0002 y 0004", "hecho", "docs/adr/",
  "DuckDB, SEC antes que FMP, y TWS solo lectura: las tres implementadas. La 0003 fue revertida limpiamente por la 0004."),
 ("adr-0005", "ADR 0005 · moneda de valuación", "a-medias", "docs/adr/0005",
  "Solo el §4 está implementado (#109): el broadcast del risk-free se eliminó y la valuación usa la tasa y el PBI de la moneda de valuación, de config/currencies.yaml. Los §1–§3 siguen sin código: la columna companies.currency sigue siendo ambigua, no hay columnas separadas de moneda de cotización y de reporte, y el precio no se convierte a la moneda de valuación. Bajo el alcance US-only actual (cotización = reporte = USD) esas consecuencias no se manifiestan, pero vuelven a ser bloqueantes en cuanto M2 global reabra. La propia ADR lo dice así en su Status."),
 ("adr-0006", "ADR 0006 · empresas no medibles", "hecho", "screener/engine.py:815-829; reporting/screen_report.py:123; screener/persist.py",
  "Implementada: la compuerta de cobertura excluye antes de evaluar (engine.py:815-829), el reporte cuenta las excluidas por razón (screen_report.py:123), y los rechazos —razón de cobertura incluida— quedan persistidos con su razón real (persist.py). El bug que la ADR describía ya no está vivo. Ver también coverage-gate en Capa B."),
 ("errores", "Degradar de a poco, avisar fuerte", "hecho", "ingest/universe.py:48",
  "El exit code 2 cuando falla más del 5% del universo está implementado y agregado por fuente. Es la pieza operativa mejor ejecutada."),
 ("bootstrap", "scripts/bootstrap.sh", "hecho", "scripts/bootstrap.sh",
  "Crea .env desde .env.example y pide solo las dos claves obligatorias que falten (BOT_SEC_USER_AGENT, BOT_TIINGO_API_KEY); --yes las toma del entorno. Carga Damodaran, imprime el checklist de TWS y corre bot doctor, cuyo exit code es el suyo. Re-ejecutable sin cambios. Tests en tests/integration/test_scripts.py (#33)."),
 ("cron", "scripts/install_cron.sh", "hecho", "scripts/install_cron.sh; scripts/daily.sh; scripts/weekly.sh",
  "Instala dos líneas marcadas (# bot-daily, # bot-weekly), idempotente; --remove borra solo esas. daily.sh (precios en rondas horarias, del más viejo al más nuevo, hasta que no quede ninguno diferido por el límite de Tiingo (#136); luego FX y portfolio) y weekly.sh (refresh --all, luego screen) loguean a .cache/*.log con el exit code del bot (#33)."),
 ("logs", "Log a archivo", "falta", "utils/logging.py:25",
  "Todo va a stdout y en formato de consola, nunca JSON. Un cron corriendo esto no deja rastro auditable."),
 ("backup", "Respaldo", "falta", "spec §13.4", None),
 ("e2e", "La prueba de punta a punta", "hecho", "tests/e2e/test_pipeline.py",
  "Existe: siembra Damodaran desde fixtures y tres empresas US (GOODCO sobrevive, TRAPCO cae por trampa de margen, NOCOVCO cae por la compuerta de cobertura ADR 0006) a través de la orquestación real de refresco (refresh_universe/refresh_prices, ingest/universe.py) contra un FakeProvider (tests/fake_provider.py) — el mismo puerto MarketDataProvider que implementa FmpProvider en producción — sobre una base compartida, y ejercita los comandos reales de CLI screen y analyze --from-screen contra esa base, verificando shortlist, artefactos y las tablas screener_candidates/refresh_log. Sin red: sigue sin ser una corrida contra FMP/SEC/Damodaran reales (ver datos-reales)."),
 ("cov", "Medición de cobertura", "falta", "pyproject.toml",
  "pytest-cov no está instalado ni configurado. El objetivo de 100% en valuator y en rules.py está escrito en el spec y en CONTEXT.md, y nunca se midió con las herramientas de este repo."),
 ("datos-reales", "Correr contra datos reales", "hecho", "docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md#corrida-real; docs/superpowers/plans/2026-09-09-free-data-stack-edgar-stooq.md#real-run",
  "Dos corridas reales atestiguadas contra la red, no contra fixtures. La primera (2026-09-02, Tarea 13) contra FMP dejó bot.duckdb y reports/ en el repo: 3/25 fundamentals importados (cobertura de símbolos del tier gratis), 3/25 precios importados con 13 diferidos por 429 real, screen y analyze corridos de punta a punta. La segunda (2026-09-09, Tarea 8 de este plan) contra el stack gratis por defecto (edgar-stooq) usó bot-freestack.duckdb/reports-freestack (fuera de git, para no pisar la corrida anterior): fundamentals 25/25 importado sin fallos en dos pasadas; precios 0/25 — Stooq ahora exige un reto JS anti-bot (proof-of-work) a cualquier cliente sin navegador, un modo de falla más duro que el límite diario documentado que StooqRateLimitError sabe manejar. screen y analyze corrieron sobre esos datos parciales (0 candidatos, sin precio no hay market cap). La suite ya no solo prueba que el código es consistente consigo mismo: probó contra los tres servicios reales (Damodaran, SEC EDGAR, FMP) y contra dos de tres del stack por defecto (Damodaran, SEC EDGAR); Stooq quedó bloqueado por el proveedor, no por el código."),
 ("alcance", "El fuera de alcance", "hecho", "spec §15",
  "Seis ítems diferidos, cero código embrionario, ni un import especulativo. La disciplina de alcance es el punto más fuerte del proyecto."),
]),
}

BRECHAS = [
 ("Cree que decidió cómo maneja monedas, para cualquier universo.",
  "De la ADR 0005 solo el §4 está implementado (#109): el risk-free y el techo de PBI ya salen por moneda de valuación. Siguen sin código los §1–§3: una sola columna ambigua (companies.currency) y ninguna conversión del precio a la moneda de valuación. Bajo el universo US-only actual (S&P 500, cotización = reporte = USD) esto no produce un número incorrecto hoy — la ADR ya lo declara así — pero es deuda diferida, no resuelta: vuelve a ser bloqueante en cuanto M2 global reabra."),
 ("Cree que el story type cambia toda la proyección.",
  "Ya no es solo una etiqueta: crecimiento (fade a PBI en high-growth) y margen operativo (rampa a sector en high-growth, promedio de ciclo en cyclical) sí se ramifican por arquetipo. Pero sales-to-capital, crecimiento terminal y la valuación condicional a supervivencia siguen sin ramificarse — la tabla del spec está a medio llenar, no vacía."),
 ("Cree que apunta a cincuenta mil empresas.",
  "El universo de fábrica ya no es sintético: son los 503 componentes reales del S&P 500. Pero sigue siendo un universo, no cincuenta mil — la expansión global (M2) sigue sin datos, y sigue una sola región de Damodaran."),
 ("Cree que tiene 100% de cobertura donde importa.",
  "Está escrito en el spec y en CONTEXT.md. pytest-cov no está instalado: ese número nunca se midió."),
 ("Cree que es operable por cron.",
  "Ya hay bootstrap, instalador de cron y wrappers que loguean a .cache/*.log (#33), pero el log es la salida de consola tal cual: sin log estructurado del CLI ni respaldo. La ADR 0004 eligió TWS justamente por la compatibilidad con cron."),
 ("Cree que sus reportes son reproducibles.",
  "Llevan fecha de generación y nada más. Dos corridas distintas producen encabezados idénticos."),
]


def contar():
    c = {k: 0 for k, _, _ in ESTADOS}
    for _, _, items in INVENTARIO.values():
        for it in items:
            c[it[2]] += 1
    return c


def css_bloques():
    """Tiñe cada bloque de la axonometría según su estado agregado."""
    out = []
    for nid, est in BLOQUES.items():
        out.append(f'#svg-sistema [data-node="{nid}"] .blk-top{{fill:var(--e-{est}-hi)}}')
        out.append(f'#svg-sistema [data-node="{nid}"] .blk-right{{fill:var(--e-{est}-md)}}')
        out.append(f'#svg-sistema [data-node="{nid}"] .blk-left{{fill:var(--e-{est}-lo)}}')
        out.append(f'#svg-sistema [data-node="{nid}"] polygon{{stroke:var(--e-{est})}}')
    return "\n".join(out)


def txt(x, y, s, cls="t-b", anchor="start"):
    return (f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">'
            f'{esc(s)}</text>')


def wrap(texto, n):
    out, cur = [], ""
    for w in texto.split():
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= n:
            cur += " " + w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def plan_inventario(capa):
    """Una banda por capa: un chip por componente, coloreado por estado."""
    _titulo, _sub, items = INVENTARIO[capa]
    o, y = [], 16
    for cid, nombre, estado, evidencia, nota in items:
        alto = 46 if not nota else 46 + 14 * len(wrap(nota, 108))
        cuerpo = (f'<rect class="chip e-{estado}" x="20" y="{y}" width="900" '
                  f'height="{alto}" rx="2"/>'
                  f'<rect class="tick e-{estado}" x="20" y="{y}" width="7" '
                  f'height="{alto}"/>')
        cuerpo += txt(42, y + 22, nombre, "t-b")
        cuerpo += txt(910, y + 22, dict((k, n) for k, n, _ in ESTADOS)[estado],
                      f"t-e e-{estado}-t", "end")
        cuerpo += txt(42, y + 38, evidencia, "t-m")
        if nota:
            for k, ln in enumerate(wrap(nota, 108)):
                cuerpo += txt(42, y + 56 + k * 14, ln, "t-s")
        o.append(f'<g class="fila" data-id="{cid}" role="group" '
                 f'aria-label="{esc(nombre)}. Estado: {estado}.">{cuerpo}</g>')
        y += alto + 8
    return "".join(o), f"0 0 940 {y + 20}"
