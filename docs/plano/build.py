"""Arma plano.html: un solo archivo autocontenido.

    python3 docs/plano/build.py

Regenera la axonometría, los planos de nivel 2 y el mapa del código, resuelve
cada símbolo citado por las fichas contra el repo, y escribe docs/plano/plano.html.
Si un símbolo dejó de existir, o el grafo de paquetes cambió, esto falla en vez de
publicar una afirmación vieja.
"""
import json
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import codemap  # noqa: E402
import iso      # noqa: E402
import views    # noqa: E402

TEXT_RE = re.compile(r'<text\b[^>]*>.*?</text>', re.S)

FONTS = {'SH': 'shantell.b64', 'LI': 'literata.b64',
         'LII': 'literata-italic.b64', 'SO': 'sometype.b64'}

GRAIN = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E"
         "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' "
         "baseFrequency='0.85' numOctaves='3'/%3E%3C/filter%3E"
         "%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")")

# El tema oscuro es un dibujo a lápiz claro sobre papel entonado oscuro.
# Las caras del volumen van más oscuras que la hoja para que el texto chico
# encima llegue a 4.5:1; la forma la sostiene el contorno de color.
DARK_TOKENS = """
  --desk:oklch(0.190 0.020 58);
  --sheet:oklch(0.345 0.020 68);
  --sheet-deep:oklch(0.300 0.020 66);
  --sheet-edge:oklch(0.455 0.024 70);
  --ink:oklch(0.915 0.018 84);
  --ink-soft:oklch(0.785 0.018 82);
  --ink-faint:oklch(0.700 0.018 78);

  --p-datos:oklch(0.760 0.110 82);      --p-datos-t:oklch(0.845 0.095 84);
  --p-elimina:oklch(0.720 0.130 32);    --p-elimina-t:oklch(0.830 0.105 34);
  --p-selecciona:oklch(0.750 0.105 138);--p-selecciona-t:oklch(0.845 0.090 138);
  --p-valua:oklch(0.745 0.105 262);     --p-valua-t:oklch(0.840 0.090 264);
  --p-vigila:oklch(0.735 0.115 352);    --p-vigila-t:oklch(0.838 0.095 352);

  --t-hi:oklch(0.335 0.016 74);
  --t-md:oklch(0.292 0.018 70);
  --t-lo:oklch(0.250 0.020 66);
  --wash:oklch(0.315 0.016 72);

  --ok:oklch(0.750 0.105 138);
  --warn:oklch(0.790 0.120 78);
  --bad:oklch(0.720 0.130 32);

  --grain:0.09;
  --shadow:0 2px 0 oklch(0.145 0.016 56/.7), 0 16px 38px oklch(0.09 0.01 60/.55);
"""

DARKBLOCKS = ('@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){'
              + DARK_TOKENS + '}}\n:root[data-theme="dark"]{' + DARK_TOKENS + '}')

DEFS = """<svg width="0" height="0" aria-hidden="true" focusable="false"
 style="position:absolute;pointer-events:none"><defs>
<filter id="wob" x="-3%" y="-2%" width="106%" height="104%">
 <feTurbulence type="fractalNoise" baseFrequency="0.016" numOctaves="2" seed="5" result="n"/>
 <feDisplacementMap in="SourceGraphic" in2="n" scale="1.7" xChannelSelector="R" yChannelSelector="G"/>
</filter>
<filter id="wob2" x="-2%" y="-1%" width="104%" height="102%">
 <feTurbulence type="fractalNoise" baseFrequency="0.014" numOctaves="2" seed="11" result="n"/>
 <feDisplacementMap in="SourceGraphic" in2="n" scale="1.5" xChannelSelector="R" yChannelSelector="G"/>
</filter>
<marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6"
 orient="auto-start-reverse"><path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke"
 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></marker>
<marker id="ar2" viewBox="0 0 10 10" refX="8.4" refY="5" markerWidth="6.4" markerHeight="6.4"
 orient="auto-start-reverse"><path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke"
 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></marker>
</defs></svg>"""

CABEZAS = {
    "fuentes": ("Fuentes", "cuatro proveedores, cuatro trabajos distintos",
                "Dos son gratis y dos se pagan, pero la diferencia que importa es otra: "
                "Damodaran no aporta ni una empresa. Aporta la vara contra la que se miden "
                "todas. Los otros tres traen los hechos de cada compañía y de tu cartera.",
                "Tocá un proveedor para ver qué aporta y qué cuesta."),
    "capa-a": ("Capa A · datos crudos", "hechos, sin opinión",
               "Esta capa no decide nada. Baja, normaliza y guarda, con una sola regla de "
               "fondo: nunca volver a pedir un dato que sigue vigente. Todo lo demás de "
               "esta página depende de que acá no haya basura.",
               "Tocá una etapa para ver cómo funciona."),
    "capa-b": ("Capa B · el screener mecánico", "dieciséis reglas, cero subjetividad",
               "El embudo abierto. La primera etapa y la tercera eliminan; la segunda y la "
               "cuarta seleccionan. Y las dos del medio son fuerzas opuestas a propósito: "
               "una busca lo que está barato, la otra pregunta por qué lo está.",
               "Tocá cualquier regla para ver qué pregunta y por qué."),
    "capa-c": ("Capa C · análisis profundo", "acá vive la filosofía y lo subjetivo",
               "Cinco estaciones en cadena sobre cada candidato. La fórmula del DCF es una "
               "sola; lo que cambia es cómo se proyectan sus insumos, y eso depende del "
               "arquetipo. Cada supuesto declara de dónde salió.",
               "Tocá un arquetipo, un supuesto o una bandera para abrir su ficha."),
    "salida": ("Salida", "reportes diarios y vigilancia de la cartera",
               "Doce tipos de evento, seis del broker y seis de cruzar la cartera contra el "
               "análisis. Y una lista corta de cosas que se decidió no detectar, que es tan "
               "parte del diseño como la otra.",
               "Tocá el monitor o los eventos para el detalle."),
    "codigo": ("El código", "cómo está construido esto hoy",
               "El grafo sale de parsear los import de src/bot/ con ast, así que no afirma "
               "ninguna dependencia que el código no tenga. Abajo, los nueve patrones que "
               "alcanzan para todo el repo, y las tres aristas que incomodan: dos van contra "
               "la dirección esperada y una es entre adapters.",
               "Tocá un paquete, un patrón o una tensión."),
}


def read(p):
    return (AQUI / p).read_text(encoding='utf-8')


def split_text(frag):
    """Saca los <text>: el filtro de temblor deformaría los glifos."""
    return TEXT_RE.sub('', frag), ''.join(TEXT_RE.findall(frag))


def resolver_simbolos(cm, meta_js):
    ids = re.findall(r'sym:"([^"]+)"', meta_js)
    faltan = sorted({s for s in ids if s not in cm['simbolos']})
    if faltan:
        sys.exit('símbolos que ya no existen en el repo:\n  ' + '\n  '.join(faltan))
    pkgs = cm['paquetes']
    usan = {}
    for a, destinos in pkgs.items():
        for b in destinos:
            usan.setdefault(b, []).append(a)
    tabla = {}
    for s in sorted(set(ids)):
        info = cm['simbolos'][s]
        pkg = info['modulo'].split('.')[1] if info['modulo'].count('.') else 'cli'
        tabla[s] = {'firma': info['firma'],
                    'donde': f"{info['archivo']}:{info['linea']}",
                    'paquete': pkg,
                    'depende': pkgs.get(pkg, []),
                    'usan': sorted(usan.get(pkg, []))}
    return tabla


def main():
    head = read('part-head.html')
    body = read('part-body.html')
    data = read('part-data.js')
    meta = read('part-meta.js')
    js = read('part-js.js')

    for k, v in FONTS.items():
        head = head.replace('__' + k + '__', read('fonts/' + v).strip())
    head = head.replace('__DARKBLOCKS__', DARKBLOCKS).replace('__GRAIN__', GRAIN)

    cm = codemap.cargar()
    simb = resolver_simbolos(cm, meta)

    formas, rotulos = iso.build()
    nivel1 = ('<svg class="plan" id="svg-sistema" viewBox="0 0 1056 1180" '
              'aria-label="Axonometría explotada de las cinco capas del bot.">'
              '<g transform="translate(346,30)">'
              f'<g class="lines" filter="url(#wob)">{formas}</g>'
              f'<g class="labels">{rotulos}</g></g></svg>')

    vistas = []
    for vid, fn in views.BUILDERS.items():
        frag, vb = fn()
        t, sub, p, hint = CABEZAS[vid]
        f_formas, f_textos = split_text(frag)
        vistas.append(
            f'<section class="view" id="v-{vid}" hidden>'
            f'<div class="view-head"><h2>{t}</h2><p class="sub">{sub}</p>'
            f'<p>{p}</p><p class="hint">{hint}</p></div>'
            f'<div class="scroll"><svg class="plan plan-{vid}" viewBox="{vb}" '
            f'aria-label="{t}">'
            f'<g class="lines" filter="url(#wob2)">{f_formas}</g>'
            f'<g class="labels">{f_textos}</g></svg></div></section>')

    body = body.replace('__ISO__', nivel1).replace('__VIEWS__', ''.join(vistas))
    out = (head + DEFS + body + '<script>' + data + '\n' + meta + '\n'
           + 'const SIMB = ' + json.dumps(simb, ensure_ascii=False) + ';\n'
           + js + '</script>\n')
    dest = AQUI / 'plano.html'
    dest.write_text(out, encoding='utf-8')
    print(f'{dest.name} · {round(len(out) / 1024)} KB · {len(vistas) + 1} vistas · '
          f'{len(simb)} símbolos · {len(cm["tensiones"])} tensiones')


if __name__ == '__main__':
    main()
