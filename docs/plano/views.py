"""Los planos de nivel 2, uno por capa, más la vista del código.

El grafo de la vista "El código" se deriva de codemap.py, no se escribe a mano:
si el repo cambia y aparece o desaparece una arista o una tensión, esto falla.
"""
import sys
from html import escape as esc

import codemap


def wrap(s, n):
    """Corta por palabras, nunca por la mitad de una."""
    out, cur = [], ""
    for w in s.split():
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


def txt(x, y, s, cls="t-b", anchor="start"):
    return (f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">'
            f'{esc(s)}</text>')


def hot(node, role, x, y, w, h, svg, aria):
    return (f'<g class="hot" data-ficha="{node}" data-role="{role}" tabindex="0" '
            f'role="button" aria-label="{esc(aria)}">'
            f'<rect class="hit" x="{x}" y="{y}" width="{w}" height="{h}"/>{svg}</g>')


def chip(node, role, x, y, w, h, title, sub, aria=None, lines=None):
    body = (f'<rect class="chip-box chip-{role} dimmable" x="{x}" y="{y}" '
            f'width="{w}" height="{h}" rx="2"/>')
    body += txt(x + 13, y + 24, title, "t-b")
    ys = y + 41
    for ln in (lines or (wrap(sub, max(12, int((w - 28) / 5.7))) if sub else [])):
        body += txt(x + 13, ys, ln, "t-s")
        ys += 14
    return hot(node, role, x, y, w, h, body, aria or f"{title}. {sub or ''}")


def band(x, y, w, h, label, note=None, role=None):
    out = (f'<rect class="band dimmable" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
           + txt(x + 16, y + 25, label, "t-h" + (f" role-{role}" if role else "")))
    if note:
        out += txt(x + w - 16, y + 25, note, "t-n", "end")
    return out


def arrow(x1, y1, x2, y2, cls="edge"):
    return f'<path class="{cls} dimmable" d="M{x1} {y1}L{x2} {y2}" marker-end="url(#ar2)"/>'


def vflow(x, y1, y2):
    return arrow(x, y1, x, y2)


# ────────────────────────────── Capa B ──────────────────────────────
GATES = [
    ("g-cap", "Capitalización", "más de USD 100 M"),
    ("g-hist", "Historia", "al menos 5 años"),
    ("g-sect", "Sectores", "fuera bancos y aseguradoras"),
    ("g-debt", "Apalancamiento", "deuda neta / EBITDA < 4"),
    ("g-cover", "Cobertura", "EBIT / intereses > 2"),
    ("g-ocf", "Caja operativa", "positiva 4 de los últimos 5"),
    ("g-gw", "Goodwill", "menos del 50% del activo"),
]
# P/BV con ROE va última: es la que recibe la flecha de las medianas del sector
VALUES = [
    ("v-pe", "PE", "< 0,7 × la mediana del sector"),
    ("v-ev", "EV / EBITDA", "< 0,7 × la mediana del sector"),
    ("v-fcf", "FCF yield", "más del 8%, sin mirar al sector"),
    ("v-pbv", "P/BV con ROE", "barata y más rentable que sus pares"),
]
# ROIC contra WACC va última de la primera fila: recibe la flecha del WACC sectorial
TRAPS = [
    ("t-rev", "Ingresos", "no caen más de 5% anual en 3 años"),
    ("t-margin", "Margen operativo", "no se contrae más de 200 pb"),
    ("t-sloan", "Accruals", "ratio de Sloan por debajo de 10%"),
    ("t-roic", "ROIC contra WACC", "tiene que rendir más de lo que cuesta"),
    ("t-dilution", "Dilución", "acciones no crecen más de 5% anual"),
]


def plan_b():
    o = []
    CX, XS, CW = 490, [56, 278, 500, 722], 208
    o.append('<rect class="box-fill dimmable" x="52" y="34" width="876" height="46" rx="2"/>')
    o.append(txt(66, 56, "Universo medido", "t-h"))
    o.append(txt(66, 72, "solo empresas con benchmark sectorial utilizable", "t-s"))
    o.append(vflow(CX, 80, 100))

    o.append(band(46, 104, 888, 190, "Quality gates", "las 7 son eliminatorias", "elimina"))
    for i, (nid, t, sb) in enumerate(GATES[:4]):
        o.append(chip(nid, "elimina", XS[i], 140, CW, 62, t, sb))
    for i, (nid, t, sb) in enumerate(GATES[4:]):
        o.append(chip(nid, "elimina", XS[i], 214, CW, 62, t, sb))
    o.append(arrow(56, 262, 20, 282))
    o.append(txt(14, 300, "sin escala", "t-s role-elimina", "end"))
    o.append(txt(14, 314, "ni estructura sana", "t-s role-elimina", "end"))
    o.append(vflow(CX, 294, 318))

    o.append(band(46, 322, 888, 150, "Value indicators",
                  "alcanza con que pase una", "selecciona"))
    for i, (nid, t, sb) in enumerate(VALUES):
        o.append(chip(nid, "selecciona", XS[i], 356, CW, 80, t, sb))
    o.append(arrow(56, 420, 20, 440))
    o.append(txt(14, 458, "caras contra", "t-s role-selecciona", "end"))
    o.append(txt(14, 472, "su propio sector", "t-s role-selecciona", "end"))
    o.append(vflow(CX, 472, 496))

    o.append(band(46, 500, 888, 200, "Trap detection", "por qué está barata", "elimina"))
    for i, (nid, t, sb) in enumerate(TRAPS[:4]):
        o.append(chip(nid, "elimina", XS[i], 534, CW, 72, t, sb))
    o.append(chip(TRAPS[4][0], "elimina", XS[0], 618, CW, 72, TRAPS[4][1], TRAPS[4][2]))
    o.append(arrow(56, 670, 20, 690))
    o.append(txt(14, 708, "baratas por", "t-s role-elimina", "end"))
    o.append(txt(14, 722, "una buena razón", "t-s role-elimina", "end"))
    o.append(vflow(CX, 700, 724))

    o.append(band(46, 728, 888, 168, "Ranking", "ordena, no descarta", "selecciona"))
    cur = 62
    for nm, pct, alt in [("valor", 40, 0), ("calidad", 30, 0),
                         ("crecimiento", 20, 0), ("MoS", 10, 1)]:
        w = 780 * pct / 100
        o.append(f'<rect class="dimmable" x="{cur:.1f}" y="766" width="{w:.1f}" '
                 f'height="30" fill="var(--p-selecciona)" opacity="{".14" if alt else ".40"}"/>')
        o.append(f'<rect class="dimmable" x="{cur:.1f}" y="766" width="{w:.1f}" height="30" '
                 f'fill="none" stroke="var(--p-selecciona)" stroke-width="1.5"/>')
        o.append(txt(cur + w / 2, 786, f"{pct}", "t-num", "middle"))
        o.append(txt(cur + w / 2, 814, nm, "t-s", "middle"))
        cur += w
    o.append(txt(62, 844, "Valor, calidad y crecimiento se calculan como percentiles dentro "
                 "del universo ya filtrado, no contra umbrales fijos.", "t-n"))
    o.append(txt(62, 862, "El margen de seguridad es la excepción: entra como cociente crudo "
                 "y llega desde la Capa C. Por eso el bucle.", "t-n"))
    o.append(vflow(CX, 896, 920))

    o.append('<rect class="box-fill dimmable" x="370" y="924" width="240" height="52" rx="2"/>')
    o.append(txt(384, 948, "Shortlist", "t-h"))
    o.append(txt(384, 965, "20 a 30 nombres para leer", "t-s"))

    # tronco de benchmarks: una sola bajante con dos derivaciones,
    # cada una a la regla que de verdad usa ese dato
    o.append('<path class="edge edge-datos dimmable" d="M972 128V572"/>')
    o.append('<path class="edge edge-datos dimmable" d="M972 396h-34" marker-end="url(#ar2)"/>')
    o.append('<path class="edge edge-datos dimmable" d="M972 572h-34" marker-end="url(#ar2)"/>')
    o.append(txt(986, 116, "damodaran_industry", "t-m role-datos"))
    o.append(txt(986, 392, "medianas del sector", "t-s"))
    o.append(txt(986, 568, "WACC del sector", "t-s"))
    return "".join(o), "-130 0 1310 1000"


# ────────────────────────────── Capa C ──────────────────────────────
STORIES = [
    ("s-hg", "high-growth", "crecimiento alto que baja",
     "M8,44 C22,10 38,6 62,14 S104,34 122,38"),
    ("s-ms", "mature-stable", "paralelo al PBI nominal",
     "M8,30 C34,28 56,26 82,25 S112,24 122,24"),
    ("s-md", "mature-decline", "negativo y controlado",
     "M8,16 C34,20 58,28 84,36 S112,44 122,48"),
    ("s-cy", "cyclical", "promediar el ciclo entero",
     "M8,30 C22,8 34,8 46,30 S66,52 78,30 S98,8 110,26 L122,32"),
    ("s-ds", "distressed", "condicional a que sobreviva",
     "M8,22 C22,26 32,34 44,44 M58,46 L64,46 M78,44 C92,40 104,36 122,34"),
]
ASSUMPTIONS = [
    ("a-growth", "Crecimiento de ingresos", "hoy: promedio histórico, plano",
     "historical_average"),
    ("a-margin", "Margen operativo", "el de largo plazo es el del sector",
     "sector_default_damodaran"),
    ("a-s2c", "Sales-to-capital", "cuánta venta compra cada peso reinvertido",
     "sector_default_damodaran"),
    ("a-wacc", "WACC", "se recompone de sus partes, no se resuelve",
     "sector_default_damodaran"),
    ("a-g", "Crecimiento terminal", "el menor entre tasa libre de riesgo y PBI",
     "rule_based"),
    ("a-default", "Probabilidad de quiebra", "cero salvo en distressed", "rule_based"),
]
FLAGS = [
    ("f-story", "story_margin", "amarillo", "warn", ["story_margin"]),
    ("f-growth", "growth_reinvestment", "rojo", "bad", ["growth_", "reinvestment"]),
    ("f-beta", "beta_business_risk", "amarillo", "warn", ["beta_business_", "risk"]),
    ("f-tv", "terminal_value_share", "amarillo", "warn", ["terminal_value_", "share"]),
    ("f-country", "country_exposure", "rojo", "bad", ["country_", "exposure"]),
]


def plan_c():
    o = []
    o.append(band(46, 30, 800, 220, "1 · Story type",
                  "la fórmula es una sola; cambia cómo se proyecta", "valua"))
    for i, (nid, name, note, path) in enumerate(STORIES):
        x = [58, 218, 378, 538, 698][i]
        inner = (f'<rect class="chip-box chip-valua dimmable" x="{x}" y="64" '
                 f'width="148" height="168" rx="2"/>'
                 f'<rect class="dimmable" x="{x + 11}" y="80" width="126" height="58" '
                 f'fill="var(--sheet)" stroke="var(--ink-faint)" stroke-width="1.1"/>'
                 f'<path class="axis dimmable" d="M{x + 11} 138h126"/>'
                 f'<path class="spark dimmable" stroke="var(--p-valua)" '
                 f'transform="translate({x + 11},80)" d="{path}"/>')
        inner += txt(x + 12, 160, name, "t-b")
        for k, ln in enumerate(wrap(note, 21)[:2]):
            inner += txt(x + 12, 178 + k * 14, ln, "t-s")
        o.append(hot(nid, "valua", x, 64, 148, 168, inner,
                     f"Story type {name}: {note}"))
    o.append(vflow(446, 250, 274))

    o.append(band(46, 278, 800, 250, "2 · Los seis supuestos",
                  "cada uno declara de dónde salió", "valua"))
    for i, (nid, name, note, src) in enumerate(ASSUMPTIONS):
        x, y = 58 + (i % 2) * 396, 316 + (i // 2) * 66
        inner = (f'<rect class="chip-box chip-valua dimmable" x="{x}" y="{y}" '
                 f'width="382" height="56" rx="2"/>')
        inner += txt(x + 13, y + 22, name, "t-b")
        inner += txt(x + 13, y + 38, note, "t-s")
        inner += txt(x + 369, y + 22, src, "t-m", "end")
        o.append(hot(nid, "valua", x, y, 382, 56, inner,
                     f"Supuesto {name}: {note}. Origen {src}"))
    o.append(vflow(446, 528, 552))

    o.append(band(46, 556, 800, 268, "3 · DCF de dos etapas",
                  "flujos explícitos, después perpetuidad", "valua"))
    base = 740
    o.append(f'<path class="axis dimmable" d="M290 {base}h530"/>')
    for i, h in enumerate([40, 52, 62, 70, 76]):
        x = 300 + i * 62
        o.append(f'<rect class="dimmable" x="{x}" y="{base - h}" width="42" height="{h}" '
                 f'fill="var(--p-valua)" opacity=".36" stroke="var(--p-valua)" '
                 f'stroke-width="1.4"/>')
        o.append(txt(x + 21, base + 16, f"año {i + 1}", "t-s", "middle"))
        o.append(f'<path class="thin dimmable" d="M{x + 21} {base - h - 6}V620" '
                 f'marker-end="url(#ar2)"/>')
    tx = 300 + 5 * 62 + 16
    o.append(f'<rect class="dimmable" x="{tx}" y="{base - 108}" width="132" height="108" '
             f'fill="var(--p-valua)" opacity=".14" stroke="var(--p-valua)" '
             f'stroke-width="1.4" stroke-dasharray="6 4"/>')
    o.append(txt(tx + 66, base - 62, "valor terminal", "t-b", "middle"))
    o.append(txt(tx + 66, base - 44, "todo lo que sigue", "t-s", "middle"))
    o.append(txt(tx + 66, base + 16, "perpetuidad", "t-s", "middle"))
    o.append(f'<path class="thin dimmable" d="M{tx + 66} {base - 114}V620" '
             f'marker-end="url(#ar2)"/>')
    o.append('<rect class="box-fill dimmable" x="74" y="592" width="180" height="52" rx="2"/>')
    o.append(txt(88, 614, "Valor hoy", "t-h"))
    o.append(txt(88, 631, "descontado al WACC", "t-s"))
    o.append('<path class="thin dimmable" d="M258 618h560"/>')
    o.append(hot("dcf-formula", "valua", 74, 592, 710, 60, "",
                 "Por qué dos etapas, y por qué la segunda suele valer más"))
    o.append(txt(74, 794, "FCFF = EBIT × (1 − impuestos) − reinversión", "t-m"))
    o.append(txt(74, 810, "Equity = EV − deuda neta, dividido acciones diluidas", "t-m"))
    o.append(vflow(446, 824, 848))

    o.append(band(46, 852, 800, 226, "4 · Sensitivity", "obligatoria, no opcional", "valua"))
    for i, (nm, wd) in enumerate([("crecimiento de ingresos", 168),
                                  ("margen operativo", 132),
                                  ("costo del patrimonio", 104),
                                  ("sales-to-capital", 62),
                                  ("crecimiento terminal", 34)]):
        y = 900 + i * 30
        o.append(f'<rect class="dimmable" x="{250 - wd / 2:.0f}" y="{y}" width="{wd}" '
                 f'height="18" fill="var(--p-valua)" opacity=".4" '
                 f'stroke="var(--p-valua)" stroke-width="1.3"/>')
        o.append(txt(250 + wd / 2 + 10, y + 14, nm, "t-s"))
    o.append('<path class="axis dimmable" d="M250 892V1046"/>')
    o.append(txt(250, 1062, "tornado: mover cada eje ±20%. Son siete, acá van cinco",
                 "t-s", "middle"))
    o.append(hot("sens-tornado", "valua", 100, 892, 320, 160, "",
                 "Tornado: cuál supuesto decide el resultado"))
    gx, gy, cell = 566, 898, 28
    for r in range(5):
        for c in range(5):
            o.append(f'<rect class="dimmable" x="{gx + c * cell}" y="{gy + r * cell}" '
                     f'width="{cell}" height="{cell}" fill="var(--p-valua)" '
                     f'opacity="{0.05 + (r + c) / 8.0 * 0.52:.2f}" '
                     f'stroke="var(--sheet)" stroke-width="1"/>')
    o.append(f'<rect class="dimmable" x="{gx}" y="{gy}" width="{cell * 5}" '
             f'height="{cell * 5}" fill="none" stroke="var(--p-valua)" stroke-width="1.4"/>')
    o.append(txt(gx + cell * 2.5, gy + cell * 5 + 18, "crecimiento →", "t-s", "middle"))
    o.append(txt(gx - 10, gy + cell * 2.5, "margen ↑", "t-s", "end"))
    o.append(txt(gx + 70, gy + cell * 5 + 36, "margen de seguridad en cada celda",
                 "t-s", "middle"))
    o.append(hot("sens-grid", "valua", gx - 8, gy - 8, 170, 168, "",
                 "Grilla 5 por 5 del margen de seguridad"))
    o.append(vflow(446, 1078, 1102))

    o.append(band(46, 1106, 800, 132, "5 · Narrative flags",
                  "no puntúan: son para que leas", "valua"))
    for i, (nid, name, level, tone, partes) in enumerate(FLAGS):
        x = 58 + i * 160
        inner = (f'<rect class="chip-box chip-valua dimmable" x="{x}" y="1142" '
                 f'width="148" height="76" rx="2"/>'
                 f'<circle class="dimmable" cx="{x + 20}" cy="1164" r="7" '
                 f'fill="var(--{tone})" opacity=".88"/>')
        inner += txt(x + 36, 1168, level, "t-s")
        for k, ln in enumerate(partes):
            inner += txt(x + 12, 1192 + k * 14, ln, "t-m")
        o.append(hot(nid, "valua", x, 1142, 148, 76, inner,
                     f"Narrative flag {name}, nivel {level}"))
    return "".join(o), "0 0 880 1282"


# ────────────────────────────── Fuentes ──────────────────────────────
SOURCES = [
    ("damodaran", "Damodaran", "NYU Stern", "gratis", "anual, con hash mensual",
     ["damodaran_industry", "damodaran_country"], "datos"),
    ("sec", "SEC EDGAR", "data.sec.gov", "gratis", "cuando aparece un filing",
     ["financials_annual", "filings_log"], "datos"),
    ("fmp", "FMP", "plan Ultimate", "~USD 70/mes", "precios, a diario",
     ["companies", "prices_daily"], "datos"),
    ("ibkr", "IBKR", "TWS local", "incluido", "snapshot, a diario",
     ["portfolio_snapshots", "trades"], "vigila"),
]


def plan_f():
    o = []
    for i, (nid, name, where, cost, refresh, tables, role) in enumerate(SOURCES):
        x = [46, 254, 462, 670][i]
        inner = (f'<rect class="chip-box chip-{role} dimmable" x="{x}" y="40" '
                 f'width="188" height="196" rx="2"/>')
        inner += txt(x + 14, 68, name, "t-h")
        inner += txt(x + 14, 86, where, "t-s")
        inner += f'<path class="thin dimmable" d="M{x + 14} 100h160"/>'
        inner += txt(x + 14, 122, "costo", "t-s")
        inner += txt(x + 174, 122, cost, "t-b", "end")
        inner += txt(x + 14, 144, "se refresca", "t-s")
        inner += txt(x + 174, 164, refresh, "t-s", "end")
        inner += f'<path class="thin dimmable" d="M{x + 14} 178h160"/>'
        for j, t in enumerate(tables):
            inner += txt(x + 14, 198 + j * 16, t, "t-m")
        o.append(hot(nid, role, x, 40, 188, 196, inner,
                     f"{name}, {where}. Costo {cost}. Se refresca {refresh}."))
        o.append(vflow(x + 94, 236, 300))

    o.append(band(46, 304, 812, 172, "Todo termina en un solo archivo",
                  "quince tablas en bot.duckdb", "datos"))
    grupos = [("referencia sectorial", ["damodaran_industry", "damodaran_country"]),
              ("empresas", ["companies", "financials_annual", "financials_quarterly"]),
              ("mercado", ["prices_daily", "currencies"]),
              ("cartera", ["portfolio_snapshots", "trades", "cash_balances"]),
              ("bitácora", ["events_log", "filings_log", "refresh_log"])]
    gx = 58
    for name, tables in grupos:
        o.append(txt(gx, 362, name, "t-b"))
        for j, t in enumerate(tables):
            o.append(txt(gx, 384 + j * 20, t, "t-m"))
        gx += 162
    o.append(txt(58, 452, "Falta una que no es tabla: el CSV de mapeo de industrias, que "
                "traduce la industria del proveedor a la de Damodaran. Se mantiene a mano.",
                "t-n"))
    return "".join(o), "0 0 880 504"


# ────────────────────────────── Capa A ──────────────────────────────
def plan_a():
    o = []
    for i, (nid, name, note) in enumerate([
            ("a-download", "download", "pedir solo lo que falta"),
            ("a-parse", "parse", "normalizar a un esquema propio"),
            ("a-upsert", "upsert", "escribir sin duplicar")]):
        x = 46 + i * 268
        inner = (f'<rect class="chip-box chip-datos dimmable" x="{x}" y="40" '
                 f'width="228" height="82" rx="2"/>')
        inner += txt(x + 14, 70, name, "t-h")
        inner += txt(x + 14, 92, note, "t-s")
        o.append(hot(nid, "datos", x, 40, 228, 82, inner, f"Etapa {name}: {note}"))
        if i < 2:
            o.append(arrow(x + 228, 81, x + 262, 81))
    o.append(txt(46, 150, "Tres de los cuatro adapters tienen esta forma. IBKR es la "
                "excepción: habla por socket y el que escribe es portfolio/sync.py.", "t-n"))

    o.append(band(46, 186, 812, 208, "Nunca se vuelve a pedir un dato vigente",
                  "el refresco es incremental", "datos"))
    for i, (name, note) in enumerate([
            ("Precios", "append-only por fecha: solo se agregan días nuevos."),
            ("Fundamentals", "se invalidan por evento, no por vencimiento: manda el filing."),
            ("Damodaran", "hash del archivo cada mes; si cambió, se reimporta entero."),
            ("Cartera", "snapshot completo todos los días, porque es chica.")]):
        y = 224 + i * 40
        o.append(txt(60, y + 14, name, "t-b"))
        o.append(txt(200, y + 14, note, "t-s"))
        if i < 3:
            o.append(f'<path class="thin dimmable" d="M60 {y + 26}h786"/>')

    o.append(band(46, 414, 812, 116, "Cuando algo falla",
                  "degradar de a poco, avisar fuerte", "datos"))
    o.append(txt(60, 462, "Las fallas parciales se registran y se reportan al final de la "
                "corrida. Si falla más del 5% del universo,", "t-s"))
    o.append(txt(60, 480, "el exit code 2 hace que el cron avise. El reemplazo es atómico: "
                "la base nunca queda a medias.", "t-s"))
    o.append(txt(60, 508, "Los tests de integración usan grabaciones, así que la CI jamás "
                "abre una conexión de red.", "t-n"))
    return "".join(o), "0 0 880 560"


# ────────────────────────────── Salida ──────────────────────────────
BROKER_EVENTS = [
    ("position_opened", ""), ("position_closed", ""), ("position_size_changed", ""),
    ("dividend", "hoy no se dispara"), ("split", "hoy no se dispara"),
    ("currency_changed", ""),
]
DERIVED_EVENTS = [
    ("new_filing", "y vuelve a correr el análisis solo"),
    ("intrinsic_value_crossed_price", "en cualquiera de las dos direcciones"),
    ("new_red_flag", "una bandera narrativa se puso en rojo"),
    ("below_quality_gate", "se cayó de un filtro que antes pasaba"),
    ("sector_recalibrated", "el WACC del sector se movió más de 100 pb"),
    ("concentration", "una posición pasó el 15% de la cartera"),
]


def plan_s():
    o = []
    o.append(band(46, 30, 386, 236, "Lo que ve el broker", "6 tipos", "vigila"))
    for i, (name, nota) in enumerate(BROKER_EVENTS):
        y = 70 + i * 32
        o.append(f'<circle class="dimmable" cx="66" cy="{y - 4}" r="4" '
                 f'fill="var(--p-vigila)" opacity=".6"/>')
        o.append(txt(82, y, name, "t-m"))
        if nota:
            o.append(txt(266, y, nota, "t-s role-elimina"))
    o.append(band(452, 30, 406, 236, "Lo que sale de cruzar con el análisis",
                  "6 tipos", "vigila"))
    for i, (name, note) in enumerate(DERIVED_EVENTS):
        y = 72 + i * 32
        o.append(f'<circle class="dimmable" cx="472" cy="{y - 4}" r="4" '
                 f'fill="var(--p-vigila)" opacity=".9"/>')
        o.append(txt(488, y, name, "t-m"))
        o.append(txt(488, y + 13, note, "t-s"))
    o.append(txt(46, 292, "Los seis de la izquierda son mecánicos, pero dos de ellos no "
                "pueden dispararse hoy: el socket de TWS no trae", "t-n"))
    o.append(txt(46, 308, "corporate actions. Los seis de la derecha son los que justifican "
                "tener un bot en vez de mirar la app del broker.", "t-n"))

    o.append(band(46, 336, 812, 132, "Lo que se decidió NO detectar", "a propósito", "elimina"))
    o.append(txt(60, 384, "Movimientos de precio por sí solos.", "t-b"))
    o.append(txt(60, 402, "Si tu valuación no cambió, el precio no te dijo nada sobre la "
                "empresa.", "t-s"))
    o.append(txt(60, 428, "Noticias del feed.", "t-b"))
    o.append(txt(60, 446, "Un bot damodaraniano no debería empujarte a reaccionar a "
                "titulares.", "t-s"))

    o.append(band(46, 488, 812, 172, "Una carpeta por día, inmutable", "reports/", "vigila"))
    for i, (f, note) in enumerate([
            ("INDEX.md", "qué pasó hoy"),
            ("portfolio.md", "posiciones y eventos"),
            ("alerts.md", "solo lo nuevo; vacío si no pasó nada"),
            ("screen/<preset>.md y .csv", "la shortlist del sábado"),
            ("analysis/<TICKER>.md y .html", "el DCF completo, con su sensitivity")]):
        y = 528 + i * 26
        o.append(txt(66, y, f, "t-m"))
        o.append(txt(300, y, note, "t-s"))
    o.append(txt(46, 686, "Cada reporte lleva en el encabezado las versiones de datos que "
                "usó, así que con el mismo cache la corrida se reproduce.", "t-n"))
    return "".join(o), "0 0 880 720"


# ────────────────────────────── El código ──────────────────────────────
NODOS = {
    "cli":       (352, 40, 296, 50, "cli.py", "el único orquestador", "datos"),
    "portfolio": (352, 148, 142, 50, "portfolio/", "monitor de cartera", "vigila"),
    "reporting": (506, 148, 142, 50, "reporting/", "markdown y html", "vigila"),
    "valuator":  (352, 256, 296, 50, "valuator/", "Capa C", "valua"),
    "screener":  (352, 364, 296, 50, "screener/", "Capa B", "selecciona"),
    "ingest":    (352, 472, 142, 50, "ingest/", "Capa A", "datos"),
    "storage":   (506, 472, 142, 50, "storage/", "la conexión", "datos"),
    "reference": (58, 168, 170, 46, "reference/", "vocabulario", "datos"),
    "utils":     (58, 268, 170, 46, "utils/", "fx, finance, log", "datos"),
    "config":    (58, 368, 170, 46, "config.py", "settings", "datos"),
}
PATRONES = [
    ("p-registry", "Registry con decorador", "screener/rules.py", "el YAML nombra, no importa"),
    ("p-strategy", "Strategy", "Rule.evaluate", "cada regla se testea sola"),
    ("p-spec", "Spec declarativo", "screener/config.py", "Pydantic valida antes de construir"),
    ("p-value", "Value object congelado", "screener/types.py", "datos, no conexiones"),
    ("p-adapter", "Adapter de forma fija", "ingest/*", "bajar, interpretar, escribir"),
    ("p-tx", "Context manager transaccional", "ingest/base.py", "o entra todo o no entra nada"),
    ("p-protocol", "Protocol estructural", "portfolio/events.py", "acoplar por forma"),
    ("p-seam", "Costura inyectable", "run_screen(valuator=…)", "el colaborador es un argumento"),
    ("p-source", "Procedencia declarada", "valuator/assumptions.py",
     "cada supuesto dice de dónde salió"),
]
TENSIONES = {
    ("screener", "valuator"): ("x-bc", "screener → valuator", "la Capa B importa la Capa C"),
    ("utils", "ingest"): ("x-utils", "utils → ingest", "una utilidad arrastra un proveedor"),
    ("bot.ingest.fmp", "bot.ingest.sec_edgar"):
        ("x-adapter", "fmp → sec_edgar", "un adapter depende de otro"),
}


def _lado(n, izq=True):
    x, y, w, h = NODOS[n][:4]
    return (x if izq else x + w, y + h / 2)


def _abajo(n):
    x, y, w, h = NODOS[n][:4]
    return (x + w / 2, y + h)


def _arriba(n):
    x, y, w, h = NODOS[n][:4]
    return (x + w / 2, y)


def _grafo_real():
    """Deriva las aristas del repo y verifica que el dibujo siga siendo cierto."""
    cm = codemap.cargar()
    pares = set()
    for a, destinos in cm['paquetes'].items():
        if a == 'cli':          # el orquestador se explica con una nota, no con 8 flechas
            continue
        for b in destinos:
            pares.add((a, b))
    faltan_ficha = [t for t in cm['tensiones']
                    if (t['de'], t['a']) not in TENSIONES]
    if faltan_ficha:
        sys.exit('tensiones sin ficha en views.py: '
                 + ', '.join(f'{t["de"]} -> {t["a"]}' for t in faltan_ficha))
    reales = {(t['de'], t['a']) for t in cm['tensiones']}
    sobran = [k for k in TENSIONES if k not in reales]
    if sobran:
        sys.exit('fichas de tensión que ya no corresponden a ninguna arista: '
                 + ', '.join(f'{a} -> {b}' for a, b in sobran))
    dibujables = {k for k in NODOS}
    return sorted((a, b, (a, b) in reales) for a, b in pares
                  if a in dibujables and b in dibujables)


def plan_codigo():
    o = []
    o.append(band(38, 118, 204, 320, "Compartido", None, "datos"))
    o.append(band(336, 118, 328, 420, "El flujo", None, "selecciona"))

    for nid, (x, y, w, h, name, note, role) in NODOS.items():
        inner = (f'<rect class="chip-box chip-{role} dimmable" x="{x}" y="{y}" '
                 f'width="{w}" height="{h}" rx="2"/>')
        inner += txt(x + 12, y + 24, name, "t-b")
        inner += txt(x + 12, y + 40, note, "t-s")
        o.append(hot("mod-" + nid, role, x, y, w, h, inner,
                     f"Paquete {name}: {note}"))

    for a, b, tension in _grafo_real():
        cls = "edge dimmable" + (" edge-tension" if tension else "")
        if b in ("reference", "utils", "config"):
            p0, p1 = _lado(a, True), _lado(b, False)
            mid = (p0[0] + p1[0]) / 2
            d = (f"M{p0[0]:.0f} {p0[1]:.0f} C{mid:.0f} {p0[1]:.0f} "
                 f"{mid:.0f} {p1[1]:.0f} {p1[0] + 4:.0f} {p1[1]:.0f}")
        elif a == "utils":
            p0, p1 = _lado(a, False), _lado(b, True)
            d = (f"M{p0[0]:.0f} {p0[1] + 12:.0f} C{p0[0] + 90:.0f} {p0[1] + 150:.0f} "
                 f"{p1[0] - 90:.0f} {p1[1]:.0f} {p1[0] - 4:.0f} {p1[1]:.0f}")
        elif tension:
            p0, p1 = _arriba(a), _abajo(b)
            d = (f"M{p0[0] + 70:.0f} {p0[1]:.0f} C{p0[0] + 140:.0f} {p0[1] - 14:.0f} "
                 f"{p1[0] + 140:.0f} {p1[1] + 14:.0f} {p1[0] + 70:.0f} {p1[1] + 4:.0f}")
        elif (a, b) == ("portfolio", "ingest"):
            p0, p1 = _lado(a, True), _lado(b, True)
            d = (f"M{p0[0]:.0f} {p0[1]:.0f} C{p0[0] - 60:.0f} {p0[1]:.0f} "
                 f"{p1[0] - 60:.0f} {p1[1]:.0f} {p1[0] - 4:.0f} {p1[1]:.0f}")
        else:
            p0, p1 = _abajo(a), _arriba(b)
            d = (f"M{p0[0]:.0f} {p0[1]:.0f} C{p0[0]:.0f} {p0[1] + 26:.0f} "
                 f"{p1[0]:.0f} {p1[1] - 26:.0f} {p1[0]:.0f} {p1[1] - 4:.0f}")
        o.append(f'<path class="{cls}" d="{d}" marker-end="url(#ar2)"/>')

    o.append(txt(684, 66, "importa de todas las capas", "t-s"))
    o.append(txt(684, 80, "y nadie lo importa a él", "t-s"))
    o.append(txt(684, 390, "la Capa B importa la Capa C:", "t-s role-elimina"))
    o.append(txt(684, 404, "es el bucle del margen", "t-s role-elimina"))
    o.append(txt(684, 418, "de seguridad, hecho import", "t-s role-elimina"))
    o.append(txt(684, 496, "storage/ no tiene flechas:", "t-s"))
    o.append(txt(684, 510, "solo lo importa cli.py, y la", "t-s"))
    o.append(txt(684, 524, "conexión viaja como argumento", "t-s"))
    o.append(txt(246, 470, "y vuelve:", "t-s role-elimina", "end"))
    o.append(txt(246, 484, "utils → ingest", "t-s role-elimina", "end"))

    o.append(band(38, 566, 826, 176, "Las tres tensiones",
                  "derivadas del grafo, no afirmadas", "elimina"))
    for i, (tid, titulo, nota) in enumerate(TENSIONES.values()):
        x = 50 + i * 274
        inner = (f'<rect class="chip-box chip-elimina dimmable" x="{x}" y="604" '
                 f'width="262" height="72" rx="2"/>')
        inner += txt(x + 13, 630, titulo, "t-b")
        for k, ln in enumerate(wrap(nota, 30)):
            inner += txt(x + 13, 648 + k * 14, ln, "t-s")
        o.append(hot(tid, "elimina", x, 604, 262, 72, inner, f"Tensión {titulo}: {nota}"))
    o.append(txt(50, 706, "Dos van contra la dirección esperada y una es entre adapters. "
                "Ninguna es un error: las tres tienen una razón y un costo.", "t-n"))

    o.append(band(38, 770, 826, 340, "Los patrones que se repiten",
                  "nueve, y alcanzan para todo el repo", "selecciona"))
    for i, (pid, titulo, donde, nota) in enumerate(PATRONES):
        x = 50 + (i % 3) * 274
        y = 808 + (i // 3) * 100
        inner = (f'<rect class="chip-box chip-selecciona dimmable" x="{x}" y="{y}" '
                 f'width="262" height="84" rx="2"/>')
        inner += txt(x + 12, y + 24, titulo, "t-b")
        inner += txt(x + 12, y + 44, donde, "t-m")
        for k, ln in enumerate(wrap(nota, 34)[:2]):
            inner += txt(x + 12, y + 64 + k * 13, ln, "t-s")
        o.append(hot(pid, "selecciona", x, y, 262, 84, inner,
                     f"Patrón {titulo}, en {donde}. {nota}"))
    return "".join(o), "0 0 900 1140"


BUILDERS = {"fuentes": plan_f, "capa-a": plan_a, "capa-b": plan_b,
            "capa-c": plan_c, "salida": plan_s, "codigo": plan_codigo}


if __name__ == "__main__":
    for k, fn in BUILDERS.items():
        body, vb = fn()
        print(f"<!--V {k} {vb}-->{body}")
