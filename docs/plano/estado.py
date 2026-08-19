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

AUDITADO_EN = "c3a67e9"
AUDITADO_EL = "19 de agosto de 2026"

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
 ("da-parse", "Parseo de Damodaran", "hecho", "ingest/damodaran.py:549,580",
  "Industria, país y columnas derivadas. Corta la segunda tabla del archivo de país, que traía 21 ERP incorrectos."),
 ("da-download", "Descarga de datasets", "a-medias", "ingest/damodaran.py:608",
  "Es la única puerta de entrada de todos los benchmarks del bot, y está parcheada en los cinco tests que la tocan. Nunca se ejerció contra la red real."),
 ("da-regiones", "Las ocho regiones", "falta", "ingest/damodaran.py:59-60",
  "Sin cambios: las URLs siguen fijas y apuntan a Estados Unidos, y --region sigue siendo una etiqueta y no un selector de archivo. Ya no es una limitación oculta: refresh --damodaran ahora rechaza --region != US con exit 2 (cli.py), así que el gap queda declarado en vez de producir filas europeas con datos de EE.UU. Bajo el alcance US-only actual es irrelevante; vuelve a importar si M2 global reabre."),
 ("da-riskfree", "Risk-free por país", "a-medias", "ingest/damodaran.py:759-770",
  "Se toma un solo escalar del encabezado del archivo de EE.UU. y se escribe en las ~150 filas de país. Es exactamente lo que la ADR 0005 manda eliminar, y el valuador lo consume tal cual."),
 ("sec-parse", "SEC EDGAR: cliente y parseo", "hecho", "ingest/sec_edgar.py:20,118",
  None),
 ("sec-import", "SEC EDGAR: importador", "a-medias", "ingest/sec_edgar.py:268,390",
  "Su único llamador sigue siendo «bot show --fetch»; ningún refresh lo usa. Pero el bug de borrado ya no existe: upsert_company (líneas 268-295) hace merge-preserve por columna en vez de DELETE+INSERT crudo, así que un show sobre un ticker importado por FMP ya no le borra industry/industry_damodaran/currency/ipo_date."),
 ("fmp-todo", "FMP: cliente, fundamentals y precios", "hecho", "ingest/fmp.py:57,306,599",
  "Refresco incremental con marca de agua por fecha. Es el adapter más completo."),
 ("ibkr-pos", "IBKR: posiciones y efectivo", "hecho", "ingest/ibkr.py:205,211",
  None),
 ("ibkr-trades", "IBKR: historial de operaciones", "muerto", "portfolio/trades.py:63",
  "168 líneas con marca de agua incremental, deduplicación por id de ejecución y siete tests. Cero llamadores en producción. La tabla trades nunca se escribe en un uso real."),
 ("ibkr-corp", "IBKR: dividendos y splits", "falta", "docs/adr/0004:43",
  "El socket de TWS no trae corporate actions; haría falta el Flex Web Service. La tabla existe y alguien la lee, pero nadie la escribe."),
 ("universo", "El universo", "hecho", "ingest/universe_default.csv:1-3; tests/unit/test_universe_csv.py",
  "Los 451 tickers sintéticos se fueron: el CSV de fábrica son los 503 componentes reales del S&P 500 en formato FMP (guion, no punto — BRK-B), con test dedicado que verifica el conteo, miembros permanentes y el formato. Sigue siendo US-only por decisión de alcance (ver ADR 0006): el spec apunta a 50.000 empresas globales, y ese salto queda fuera de esta etapa."),
 ("mapeo", "Mapeo de industrias", "hecho", "ingest/industry_mapping.py:124",
  "144 filas, todas del proveedor FMP, cubriendo 89 de las 94 industrias de Damodaran."),
 ("fx", "Tipos de cambio", "a-medias", "utils/fx.py:104",
  "La descarga y la búsqueda están completas. La conversión tiene solo dos consumidores, así que PE, P/BV, EV/EBITDA y FCF yield siguen mezclando precio en moneda de cotización con cifras en moneda de reporte."),
 ("storage", "Conexión y esquema", "a-medias", "storage/db.py:24",
  "Sin versionado ni migraciones. Agregar una columna a una base existente es una operación nula que revienta después, en ejecución."),
 ("tablas", "Las quince tablas", "a-medias", "storage/schema.sql",
  "Trece se escriben. corporate_actions no tiene ningún escritor y trades tiene uno que nadie llama. Tres columnas quedan siempre nulas: reinvestment_rate, payout_ratio e isin."),
]),

"capa-b": ("Capa B · screener", "dieciséis reglas, cero subjetividad", [
 ("gates-7", "Los siete quality gates", "hecho", "screener/rules.py:120-319",
  "Los siete con aritmética real y tests dedicados. Ninguno es un esbozo."),
 ("value-4", "Los cuatro value indicators", "hecho", "screener/rules.py:346-491",
  "Tres son relativos al sector y se saltean sin mediana. FCF yield es absoluto, y es el único que puede admitir a una empresa sin cobertura sectorial."),
 ("traps-4", "Cuatro de los cinco trap detectors", "hecho", "screener/rules.py:521-719",
  "Ingresos, margen, accruals y dilución. El tope de dilución no implementa la excepción por adquisición justificada que pide el spec, y lo dice en su propio docstring."),
 ("trap-roic", "ROIC contra WACC", "hecho", "screener/rules.py:601-624; screener/engine.py:603-611,714-720",
  "El filtro central del método ya es eliminatorio de punta a punta. La regla sigue skipeando cuando falta la mediana de WACC (rules.py:617-620), pero ese caso ya no llega a evaluate_company: la compuerta de cobertura (ADR 0006) saca a la empresa del universo antes, así que todo sobreviviente tiene WACC sectorial real y, si el detector skipea o falla, engine.py:608-611 lo trata como eliminación, no como aprobación."),
 ("coverage-gate", "La compuerta de cobertura", "hecho", "screener/engine.py:696-720; reporting/screen_report.py:123",
  "Implementada tal como la decide la ADR: antes de evaluar, si el benchmark falta o su wacc es NULL, la empresa se registra en no_coverage y en rejected con razón ('coverage_gate',) y nunca entra a evaluate_company (engine.py:714-720). El reporte imprime «Excluded (no sector benchmark, ADR 0006): N» (screen_report.py:123). Cubierto además por el e2e (NOCOVCO cae por este gate)."),
 ("registro", "Registro, configuración y presets", "hecho", "screener/config.py:140",
  "Los tres presets cargan y construyen sin error. qarp usa quince reglas: omite EV/EBITDA sin comentarlo."),
 ("motor", "El motor de dos pases", "hecho", "screener/engine.py:596",
  None),
 ("motor-trap", "La rama que elimina por trampa", "a-medias", "screener/engine.py:570",
  "Treinta y cinco tests de trampas a nivel regla, y ni uno que verifique que el motor efectivamente saca a la empresa. Es la única lógica eliminatoria sin cobertura de integración."),
 ("ranking-p", "Percentiles y pesos", "hecho", "screener/ranking.py:139",
  None),
 ("ranking-growth", "El score de crecimiento", "a-medias", "screener/engine.py:518",
  "Es el 20% del ranking y se calcula solo con el crecimiento compuesto de ingresos. El flujo de caja que promete el docstring nunca entra, y no hay ventana: una empresa con doce años y otra con cinco se comparan sobre horizontes distintos."),
 ("ranking-quality", "El score de calidad", "a-medias", "screener/engine.py:509",
  "El 30% del ranking. Le falta la estabilidad de márgenes que promete, y suma un diferencial (ROIC menos WACC) a un nivel (ROE), que son cosas de dimensiones distintas."),
 ("tax", "La tasa impositiva del ROIC", "muerto", "screener/engine.py:302",
  "Resuelve la tasa por país desde una columna que el ingest no llena, así que toda empresa cae al 21% por defecto. El ROIC del mundo entero se calcula con una constante estadounidense."),
 ("failed-gates", "El registro de por qué se cayó", "hecho", "screener/persist.py:57-77; storage/schema.sql",
  "Ya no solo se materializan las sobrevivientes: persist_candidates ahora escribe también result.rejected, con passed=FALSE, rank NULL y failed_gates real (el gate/trampa/coverage_gate que la sacó). rank y passed en el schema son nullable para admitir la fila de rechazo. La tabla ahora sí responde la pregunta para la que existe."),
 ("huecos", "Series con huecos", "a-medias", "screener/engine.py:338",
  "Las series descartan los nulos en vez de preservarlos. Un año con caja operativa nula hace que el gate reporte historia insuficiente y elimine a la empresa por un hueco de datos, no por caja negativa."),
]),

"capa-c": ("Capa C · valuador", "acá vive la filosofía", [
 ("classify", "El clasificador de story type", "hecho", "valuator/story_types.py:161",
  "Los cinco arquetipos son alcanzables y están testeados."),
 ("story-uso", "El story type como patrón de proyección", "a-medias", "valuator/assumptions.py:601-687",
  "Ya no es solo una etiqueta: dos supuestos se ramifican de verdad por arquetipo. _resolve_revenue_growth (601-631) hace un high-growth fadear linealmente de su crecimiento histórico al PBI nominal en vez de quedar plano; _resolve_operating_margin (650-687) hace un high-growth subir en rampa de su margen propio al del sector, y un cyclical usar el promedio del ciclo (≥4 años) en vez del margen del último año. Sigue faltando el resto de la tabla del spec: sales-to-capital, crecimiento terminal y valuación condicional a supervivencia no se ramifican por story type."),
 ("story-edad", "La señal de edad", "hecho", "valuator/analysis.py:466-469",
  "Ya no es un parámetro que nadie pasa: cuando el caller no fuerza age_years explícito, se deriva de company_row.ipo_date (poblado ahora vía CompanyInfo/ingest/fmp.py) como (hoy − ipo_date) en años, y ese valor alimenta el clasificador de story type. Cubierto por tests de valuator/analysis."),
 ("story-altman", "La señal de Altman Z", "falta", "valuator/story_types.py:147",
  "El clasificador la lee y no existe ningún cálculo de Altman Z en todo el repo. Es la misma causa raíz que deja sin derivar la probabilidad de quiebra."),
 ("a-crecimiento", "Supuesto: crecimiento de ingresos", "a-medias", "valuator/assumptions.py:358",
  "El spec pide consenso de analistas convergiendo al PBI en el año diez. El código usa el promedio histórico de la propia empresa, plano sobre cinco años. El enum ni siquiera tiene el valor analyst_consensus."),
 ("a-sector", "Supuestos: margen, sales-to-capital, crecimiento terminal", "hecho", "valuator/assumptions.py:498,638",
  "Los tres coinciden con lo que promete el spec."),
 ("a-wacc", "Supuesto: WACC", "a-medias", "valuator/dcf.py:150",
  "No es un supuesto resuelto: se recompone de partes. El costo del patrimonio y el de la deuda se leen de la fila sectorial, y los pesos salen del apalancamiento del sector, no del de la empresa."),
 ("a-quiebra", "Supuesto: probabilidad de quiebra", "muerto", "valuator/assumptions.py:674",
  "Devuelve cero siempre, salvo override manual. No mira rating, ni Altman Z, ni siquiera el story type. El valor de liquidación tampoco se resuelve y ni se renderiza."),
 ("a-crossregion", "Sustitución entre regiones", "hecho", "valuator/assumptions.py:327",
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
 ("overrides", "Overrides por convención", "hecho", "config.py:49; cli.py:383,448; screener/engine.py:642,757",
  "Ya llegan por convención, no solo por --override explícito: Settings.assumptions_dir (config.py:49, default config/assumptions/) se usa en bot analyze (cli.py:383, <TICKER>.yaml automático) y en el segundo pase del screener (cli.py:448 → engine.py:642,757, cada candidato del shortlist con <TICKER>.yaml se valúa con ese override). config/assumptions/README.md y _EXAMPLE.yaml.example documentan las claves."),
]),

"salida": ("Salida", "reportes y vigilancia", [
 ("ev-vivos", "Seis eventos que sí disparan", "hecho", "portfolio/events.py:143,386",
  "Posición abierta, cerrada, cambio de tamaño, filing nuevo, bandera roja y concentración."),
 ("ev-corp", "Dividendo y split", "muerto", "portfolio/events.py:235",
  "El detector está cableado y lee una tabla que nadie escribe."),
 ("ev-cruce", "El valor intrínseco cruzó el precio", "muerto", "portfolio/command.py:96",
  "El evento estrella del producto. El detector es correcto y está cableado, pero necesita la valuación anterior y el único productor en producción llama sin pasarla, así que devuelve nulo siempre. Los tests de integración lo cubren inyectando la línea de base a mano, y por eso el hueco queda invisible en verde."),
 ("ev-huerfanos", "Caída de quality gate y recalibración sectorial", "muerto", "portfolio/events.py:419,448",
  "Dos detectores escritos, documentados y con tests unitarios que compute_events nunca invoca. No les falta un insumo: nadie los llama."),
 ("ev-ruido", "Bandera roja nueva", "a-medias", "portfolio/events.py:366",
  "Sin línea de base, toda bandera roja se reporta como nueva en cada corrida. Su propio docstring dice que evita justamente eso."),
 ("ev-ventana", "Filing nuevo", "a-medias", "portfolio/events.py:288",
  "La ventana filtra por fecha de presentación y no por fecha de ingesta. Un 10-K presentado hace tres semanas e importado hoy no dispara nunca, y no vuelve a caer en una ventana futura."),
 ("sync", "Sincronización de la cartera", "hecho", "portfolio/sync.py:135",
  "Posiciones, efectivo y valuación con precios y tipo de cambio, idempotente por fecha y cuenta."),
 ("rep-portfolio", "El reporte de cartera", "hecho", "portfolio/report.py:241",
  "Resumen, posiciones, P&L, concentración e historia. alerts.md se escribe siempre, aun sin eventos."),
 ("rep-html", "El HTML con gráficos", "hecho", "reporting/html.py:78,131",
  "Supera lo que pide el spec: tornado real de Matplotlib inlineado como PNG, más un mapa de calor interactivo de Plotly con el JavaScript embebido. Abre sin conexión."),
 ("rep-index", "INDEX.md", "falta", "spec §9.1",
  "La portada que contesta qué pasó hoy. Cero referencias en el código."),
 ("rep-repro", "El encabezado de reproducibilidad", "falta", "spec §13.3",
  "Los reportes llevan fecha de generación y nada más. Sin versión del dataset ni fecha del último filing, dos corridas distintas producen encabezados indistinguibles."),
 ("cli-8", "Los ocho comandos", "hecho", "cli.py:56-479",
  "Los ocho responden y tienen al menos un test que los ejecuta. analyze acepta un solo ticker y portfolio no sincroniza operaciones."),
 ("cli-falta", "Comandos y opciones que faltan", "a-medias", "cli.py:300-365; spec §9.2",
  "El analyze variádico y --from-screen ya existen (cli.py:300-365: uno o más tickers, o el shortlist del último screen persistido ordenado por rank). Lo que sigue faltando: config validate, config edit, --json global, --dry-run, refresh --portfolio."),
 ("doctor", "bot doctor", "hecho", "cli.py:507-558; storage/db.py:30-33; tests/unit/test_cli_doctor.py",
  "Los dos defectos de la auditoría anterior están corregidos: con BOT_FMP_API_KEY vacía agrega un issue y sale con code 1 (ya no code 0), y el conteo de tablas esperado ya no es un ocho hardcodeado — schema_table_count() (storage/db.py:30) lo deriva contando CREATE TABLE en schema.sql (hoy 15). Cinco tests dedicados."),
]),

"proyecto": ("El proyecto", "hitos, decisiones y operación", [
 ("m1", "M1 · esqueleto, Damodaran y SEC", "hecho", "719 tests verdes", None),
 ("m2", "M2 · universo global y FMP", "a-medias", "universe_default.csv",
  "El universo ya es real: 503 tickers del S&P 500 en vez de 451 sintéticos. Lo que sigue pendiente es la corrida real contra la red (no hay bot.duckdb cargado) y la expansión global — una sola región de Damodaran, ahora una decisión de alcance explícita (US-only, ver ADR 0006) y no un límite oculto."),
 ("m3", "M3 · screener", "hecho", "screener/", "La compuerta de cobertura (ADR 0006) ya está implementada."),
 ("m4", "M4 · valuador", "hecho", "valuator/", "El story type ya rama crecimiento y margen; le sigue faltando sales-to-capital, crecimiento terminal y valuación condicional a supervivencia."),
 ("m5", "M5 · IBKR", "a-medias", "portfolio/", "Falta cablear las operaciones (diferido por decisión de alcance, no un olvido); las corporate actions requieren otro servicio."),
 ("adr-ok", "ADR 0001, 0002 y 0004", "hecho", "docs/adr/",
  "DuckDB, SEC antes que FMP, y TWS solo lectura: las tres implementadas. La 0003 fue revertida limpiamente por la 0004."),
 ("adr-0005", "ADR 0005 · moneda de valuación", "falta", "docs/adr/0005",
  "Aceptada y sin código: la columna ambigua sigue, no hay columnas de moneda de cotización y de reporte, y el broadcast del risk-free sigue exactamente donde estaba. Bajo el alcance US-only actual (universo S&P 500, cotización = reporte = USD) sus consecuencias no se manifiestan — no es un bug activo hoy — pero vuelve a ser bloqueante en cuanto M2 global reabra. La propia ADR ya lo dice así en su Status."),
 ("adr-0006", "ADR 0006 · empresas no medibles", "hecho", "screener/engine.py:696-720; reporting/screen_report.py:123; screener/persist.py",
  "Implementada: la compuerta de cobertura excluye antes de evaluar (engine.py:714-720), el reporte cuenta las excluidas (screen_report.py:123), y los rechazos —coverage_gate incluido— quedan persistidos con su razón real (persist.py). El bug que la ADR describía ya no está vivo. Ver también coverage-gate en Capa B."),
 ("errores", "Degradar de a poco, avisar fuerte", "hecho", "ingest/universe.py:48",
  "El exit code 2 cuando falla más del 5% del universo está implementado y agregado por fuente. Es la pieza operativa mejor ejecutada."),
 ("bootstrap", "scripts/bootstrap.sh", "falta", "spec §13.1", "El directorio scripts/ no existe."),
 ("cron", "scripts/install_cron.sh", "falta", "spec §9.3", None),
 ("logs", "Log a archivo", "falta", "utils/logging.py:25",
  "Todo va a stdout y en formato de consola, nunca JSON. Un cron corriendo esto no deja rastro auditable."),
 ("backup", "Respaldo", "falta", "spec §13.4", None),
 ("e2e", "La prueba de punta a punta", "hecho", "tests/e2e/test_pipeline.py",
  "Existe: siembra Damodaran desde fixtures y tres empresas US (GOODCO sobrevive, TRAPCO cae por trampa de margen, NOCOVCO cae por la compuerta de cobertura ADR 0006) sobre una base compartida, y ejercita los comandos reales de CLI screen y analyze --from-screen contra esa base, verificando shortlist, artefactos y las tablas screener_candidates/refresh_log. Sin red: sigue sin ser una corrida contra FMP/SEC/Damodaran reales (ver datos-reales)."),
 ("cov", "Medición de cobertura", "falta", "pyproject.toml",
  "pytest-cov no está instalado ni configurado. El objetivo de 100% en valuator y en rules.py está escrito en el spec y en CONTEXT.md, y nunca se midió con las herramientas de este repo."),
 ("datos-reales", "Correr contra datos reales", "falta", "notes/2026-08-14",
  "Sigue sin haber bot.duckdb ni reports/ generados por una corrida real. Los 719 tests (incluido el e2e nuevo) corren sobre fixtures y fakes duck-typed, con .env.example y un quickstart de README (c3a67e9) que documentan cómo correrlo contra FMP/SEC/Damodaran reales, pero nadie lo ejecutó todavía en este repo. La suite prueba que el código es consistente consigo mismo, no que sepa leer lo que FMP y Stern devuelven de verdad."),
 ("alcance", "El fuera de alcance", "hecho", "spec §15",
  "Seis ítems diferidos, cero código embrionario, ni un import especulativo. La disciplina de alcance es el punto más fuerte del proyecto."),
]),
}

BRECHAS = [
 ("Cree que decidió cómo maneja monedas, para cualquier universo.",
  "La ADR 0005 sigue aceptada y sin código: una sola columna ambigua, y el risk-free de Estados Unidos sigue difundiéndose. Bajo el universo US-only actual (S&P 500, cotización = reporte = USD) esto no produce un número incorrecto hoy — la ADR ya lo declara así — pero es deuda diferida, no resuelta: vuelve a ser bloqueante en cuanto M2 global reabra."),
 ("Cree que el story type cambia toda la proyección.",
  "Ya no es solo una etiqueta: crecimiento (fade a PBI en high-growth) y margen operativo (rampa a sector en high-growth, promedio de ciclo en cyclical) sí se ramifican por arquetipo. Pero sales-to-capital, crecimiento terminal y la valuación condicional a supervivencia siguen sin ramificarse — la tabla del spec está a medio llenar, no vacía."),
 ("Cree que apunta a cincuenta mil empresas.",
  "El universo de fábrica ya no es sintético: son los 503 componentes reales del S&P 500. Pero sigue siendo un universo, no cincuenta mil — la expansión global (M2) sigue sin datos, y sigue una sola región de Damodaran."),
 ("Cree que tiene 100% de cobertura donde importa.",
  "Está escrito en el spec y en CONTEXT.md. pytest-cov no está instalado: ese número nunca se midió."),
 ("Cree que es operable por cron.",
  "Sin bootstrap, sin instalador, sin log a archivo, sin respaldo. La ADR 0004 eligió TWS justamente por la compatibilidad con cron."),
 ("Cree que sus reportes son reproducibles.",
  "Llevan fecha de generación y nada más. Dos corridas distintas producen encabezados idénticos."),
 ("Cree que M5 sincroniza operaciones.",
  "sync_trades está escrito, tipado y cubierto por siete tests. Nadie lo llama — diferido por decisión de alcance de este plan, no un olvido nuevo."),
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
