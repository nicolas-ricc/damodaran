"""Arma estado.html: qué está hecho de verdad y qué no.

    python3 docs/plano/build_estado.py

Reutiliza las tipografías, los filtros y la geometría axonométrica del plano
hermano; lo único propio es la paleta, que acá codifica ESTADO y no rol.
"""
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import build as plano  # noqa: E402
import estado  # noqa: E402
import iso  # noqa: E402

# Cuatro estados. El color solo significa estado; el rol se fue a propósito.
CLARO = """
  --desk:oklch(0.620 0.050 64);
  --sheet:oklch(0.805 0.045 78);
  --sheet-deep:oklch(0.848 0.034 82);
  --sheet-edge:oklch(0.640 0.045 76);
  --ink:oklch(0.300 0.045 55);
  --ink-soft:oklch(0.360 0.040 56);
  --ink-faint:oklch(0.450 0.032 58);

  --e-hecho:oklch(0.455 0.095 140);    --e-hecho-t:oklch(0.355 0.078 140);
  --e-hecho-hi:oklch(0.878 0.034 140); --e-hecho-md:oklch(0.782 0.038 140);
  --e-hecho-lo:oklch(0.688 0.042 140);

  --e-a-medias:oklch(0.470 0.110 75);    --e-a-medias-t:oklch(0.370 0.092 72);
  --e-a-medias-hi:oklch(0.876 0.042 78); --e-a-medias-md:oklch(0.780 0.048 78);
  --e-a-medias-lo:oklch(0.686 0.052 78);

  --e-muerto:oklch(0.455 0.140 30);    --e-muerto-t:oklch(0.355 0.120 30);
  --e-muerto-hi:oklch(0.874 0.040 30); --e-muerto-md:oklch(0.778 0.046 30);
  --e-muerto-lo:oklch(0.684 0.052 30);

  --e-falta:oklch(0.470 0.010 70);     --e-falta-t:oklch(0.370 0.010 70);
  --e-falta-hi:oklch(0.812 0.012 76);  --e-falta-md:oklch(0.760 0.014 76);
  --e-falta-lo:oklch(0.700 0.016 76);

  --t-hi:oklch(0.888 0.014 82);
  --t-md:oklch(0.786 0.020 78);
  --t-lo:oklch(0.686 0.024 74);
  --grain:0.055;
  --shadow:0 2px 0 oklch(0.520 0.050 60/.45), 0 12px 32px oklch(0.30 0.04 60/.26);
"""

OSCURO = """
  --desk:oklch(0.190 0.020 58);
  --sheet:oklch(0.345 0.020 68);
  --sheet-deep:oklch(0.300 0.020 66);
  --sheet-edge:oklch(0.455 0.024 70);
  --ink:oklch(0.915 0.018 84);
  --ink-soft:oklch(0.785 0.018 82);
  --ink-faint:oklch(0.700 0.018 78);

  --e-hecho:oklch(0.750 0.105 138);    --e-hecho-t:oklch(0.845 0.090 138);
  --e-hecho-hi:oklch(0.352 0.030 138); --e-hecho-md:oklch(0.305 0.028 138);
  --e-hecho-lo:oklch(0.262 0.026 138);

  --e-a-medias:oklch(0.790 0.115 78);    --e-a-medias-t:oklch(0.862 0.098 80);
  --e-a-medias-hi:oklch(0.356 0.034 78); --e-a-medias-md:oklch(0.308 0.032 78);
  --e-a-medias-lo:oklch(0.264 0.030 78);

  --e-muerto:oklch(0.720 0.130 32);    --e-muerto-t:oklch(0.830 0.105 34);
  --e-muerto-hi:oklch(0.352 0.036 32); --e-muerto-md:oklch(0.304 0.034 32);
  --e-muerto-lo:oklch(0.262 0.032 32);

  --e-falta:oklch(0.700 0.008 76);     --e-falta-t:oklch(0.800 0.008 76);
  --e-falta-hi:oklch(0.318 0.008 72);  --e-falta-md:oklch(0.286 0.008 72);
  --e-falta-lo:oklch(0.252 0.008 72);

  --t-hi:oklch(0.335 0.016 74);
  --t-md:oklch(0.292 0.018 70);
  --t-lo:oklch(0.250 0.020 66);
  --grain:0.09;
  --shadow:0 2px 0 oklch(0.145 0.016 56/.7), 0 16px 38px oklch(0.09 0.01 60/.55);
"""

CSS = """
@font-face{font-family:'Shantell';src:url(data:font/woff2;base64,__SH__) format('woff2');font-weight:300 800;font-display:swap}
@font-face{font-family:'Literata';src:url(data:font/woff2;base64,__LI__) format('woff2');font-weight:300 700;font-style:normal;font-display:swap}
@font-face{font-family:'Literata';src:url(data:font/woff2;base64,__LII__) format('woff2');font-weight:300 700;font-style:italic;font-display:swap}
@font-face{font-family:'Sometype';src:url(data:font/woff2;base64,__SO__) format('woff2');font-weight:400 700;font-display:swap}
:root{__CLARO__--ease:cubic-bezier(.16,1,.3,1)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){__OSCURO__}}
:root[data-theme="dark"]{__OSCURO__}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--desk);color:var(--ink);
 font-family:'Literata',Georgia,serif;font-size:16px;line-height:1.62;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:clamp(14px,3vw,38px) clamp(10px,3vw,28px) 70px}
.sheet{background:var(--sheet);border:1px solid var(--sheet-edge);border-radius:3px;
 padding:clamp(18px,4vw,52px);position:relative;overflow:hidden;box-shadow:var(--shadow)}
.sheet::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:var(--grain);
 mix-blend-mode:multiply;background-image:__GRAIN__}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .sheet::after{mix-blend-mode:screen}}
:root[data-theme="dark"] .sheet::after{mix-blend-mode:screen}
.sheet>*{position:relative;z-index:1}
h1{font-family:'Shantell',system-ui,sans-serif;font-weight:700;
 font-size:clamp(2.1rem,5.4vw,3.4rem);line-height:.98;letter-spacing:-0.032em;margin:0 0 .22em;text-wrap:balance}
.deck{font-family:'Shantell',system-ui,sans-serif;font-weight:500;color:var(--ink-soft);
 font-size:clamp(1rem,2vw,1.14rem);margin:0 0 .7rem}
.sello{font-family:'Sometype',monospace;font-size:.8rem;color:var(--ink-faint);margin:0 0 1.6rem}
p{margin:0 0 1rem;text-wrap:pretty}
.lede{max-width:64ch}
code{font-family:'Sometype',monospace;font-size:.87em}

.marcador{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
 gap:14px;margin:2.4rem 0 .6rem;border-top:1.5px solid var(--sheet-edge);padding-top:1.8rem}
.tarjeta{border:1.5px solid currentColor;border-radius:2px;padding:14px 16px}
.tarjeta .n{font-family:'Shantell',system-ui,sans-serif;font-weight:700;font-size:2.1rem;line-height:1}
.tarjeta .q{font-family:'Shantell',system-ui,sans-serif;font-weight:700;font-size:.95rem;margin-top:.15rem}
.tarjeta .d{font-size:.86rem;color:var(--ink-soft);margin-top:.35rem;line-height:1.45}
.t-hecho{color:var(--e-hecho-t)}.t-a-medias{color:var(--e-a-medias-t)}
.t-muerto{color:var(--e-muerto-t)}.t-falta{color:var(--e-falta-t)}

.nav{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:2.6rem 0 1.1rem;
 padding-bottom:.9rem;border-bottom:1.5px solid var(--sheet-edge)}
.crumb{font-family:'Shantell',system-ui,sans-serif;font-size:.9rem;font-weight:600;
 background:none;border:1.5px solid var(--ink-faint);border-radius:2px;color:var(--ink-soft);
 padding:6px 13px;cursor:pointer;transition:border-color .2s var(--ease),color .2s var(--ease)}
.crumb:hover{border-color:var(--ink);color:var(--ink)}
.crumb:focus-visible{outline:2.5px solid var(--ink);outline-offset:2px}
.crumb[aria-current="true"]{border-color:var(--ink);color:var(--ink);box-shadow:inset 0 -3px 0 var(--ink)}
@media (prefers-reduced-motion:reduce){.crumb{transition:none}}

.view[hidden]{display:none}
.view-head{max-width:66ch;margin-bottom:1.3rem}
.view-head h2{font-family:'Shantell',system-ui,sans-serif;font-weight:700;
 font-size:clamp(1.5rem,3.2vw,2.1rem);line-height:1.06;letter-spacing:-0.025em;margin:0 0 .3em}
.scroll{overflow-x:auto;overflow-y:hidden;padding-bottom:10px}
svg.plan{display:block;width:100%;height:auto}
#svg-sistema{min-width:900px}
.plan-inv{min-width:820px}
figcaption{font-size:.92rem;color:var(--ink-soft);font-style:italic;max-width:70ch;margin-top:1rem}

.lines{stroke-linejoin:round;stroke-linecap:round}
.labels{pointer-events:none}
.face-top{fill:var(--t-hi);stroke:var(--ink);stroke-width:1.6}
.face-right{fill:var(--t-md);stroke:var(--ink);stroke-width:1.6}
.face-left{fill:var(--t-lo);stroke:var(--ink);stroke-width:1.6}
.blk-top,.blk-right,.blk-left{stroke-width:1.8}
.aperture{fill:var(--sheet);stroke:var(--ink);stroke-width:1.3;opacity:.8}
.flow-left{fill:var(--t-lo);stroke:var(--ink-faint);stroke-width:1.5}
.flow-right{fill:var(--t-md);stroke:var(--ink-faint);stroke-width:1.5}
.flow-cap{fill:var(--t-hi);stroke:var(--ink-faint);stroke-width:1.5}
.leader{stroke:var(--ink-soft);stroke-width:1.1;fill:none}
.loop-path{fill:none;stroke:var(--ink-faint);stroke-width:1.6;stroke-dasharray:1 5.5}
__BLOQUES__
/* lo que falta se dibuja hueco: sin relleno y con el contorno cortado */
#svg-sistema [data-node="story"] polygon{stroke-dasharray:6 4}

.band{fill:var(--sheet-deep);stroke:var(--ink-faint);stroke-width:1.3;stroke-dasharray:6 5}
.chip{fill:var(--sheet-deep);stroke-width:1.5}
.chip.e-hecho{stroke:var(--e-hecho)}.chip.e-a-medias{stroke:var(--e-a-medias)}
.chip.e-muerto{stroke:var(--e-muerto)}.chip.e-falta{stroke:var(--e-falta);stroke-dasharray:6 4}
.tick{stroke:none}
.tick.e-hecho{fill:var(--e-hecho)}.tick.e-a-medias{fill:var(--e-a-medias)}
.tick.e-muerto{fill:var(--e-muerto)}.tick.e-falta{fill:var(--e-falta);opacity:.45}

svg text{fill:var(--ink);font-family:'Shantell',system-ui,sans-serif}
.t-h{font-size:15px;font-weight:700}
.t-b{font-size:13px;font-weight:600}
.t-s{font-size:11.5px;fill:var(--ink-soft);font-weight:500}
.t-e{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.t-m{font-size:10.5px;fill:var(--ink-faint);font-family:'Sometype',monospace}
.e-hecho-t{fill:var(--e-hecho-t)}.e-a-medias-t{fill:var(--e-a-medias-t)}
.e-muerto-t{fill:var(--e-muerto-t)}.e-falta-t{fill:var(--e-falta-t)}
.lbl-lyr{font-size:22px;font-weight:700;letter-spacing:-0.02em}
.lbl-sub{font-size:12px;fill:var(--ink-soft);font-weight:500}
.lbl-blk{font-size:12.5px;font-weight:600}
.lbl-flow{font-size:12px;fill:var(--ink-soft);font-family:'Literata',serif;font-style:italic}
.lbl-loop{font-size:11.5px;fill:var(--ink-faint);font-weight:600}
.slab,.blk,.lyr-lbl{pointer-events:none}

.brechas{margin-top:3rem;border-top:1.5px solid var(--sheet-edge);padding-top:1.8rem}
.brechas h2{font-family:'Shantell',system-ui,sans-serif;font-weight:700;font-size:1.55rem;
 letter-spacing:-0.02em;margin:0 0 .3rem}
.brechas>p{max-width:68ch;color:var(--ink-soft)}
.brechas ol{padding-left:0;list-style:none;margin:1.6rem 0 0;
 display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.brechas li{border-left:0;border-top:2px solid var(--e-muerto);padding-top:.8rem}
.brechas b{font-family:'Shantell',system-ui,sans-serif;font-weight:700;font-size:1rem;
 display:block;margin-bottom:.3rem}
.brechas span{font-size:.93rem;color:var(--ink-soft)}
.cierre{margin-top:2.6rem;border-top:1.5px dashed var(--sheet-edge);padding-top:1.4rem;
 font-style:italic;color:var(--ink-soft);max-width:68ch}
"""

HEAD = """<meta charset="utf-8">
<title>Qué está hecho</title>
<style>__CSS__</style>"""


def marcador():
    c = estado.contar()
    total = sum(c.values())
    out = ['<div class="marcador">']
    for k, nombre, desc in estado.ESTADOS:
        out.append(f'<div class="tarjeta t-{k}"><div class="n">{c[k]}</div>'
                   f'<div class="q">{nombre}</div><div class="d">{desc}</div></div>')
    out.append('</div>')
    return "".join(out), total


def main():
    css = CSS
    for k, v in plano.FONTS.items():
        css = css.replace('__' + k + '__', plano.read('fonts/' + v).strip())
    css = (css.replace('__CLARO__', CLARO).replace('__OSCURO__', OSCURO)
              .replace('__GRAIN__', plano.GRAIN)
              .replace('__BLOQUES__', estado.css_bloques()))

    formas, rotulos = iso.build()
    axo = ('<svg class="plan" id="svg-sistema" viewBox="0 0 1056 1180" '
           'aria-label="Las cinco capas del bot, teñidas según su estado real.">'
           '<g transform="translate(346,30)">'
           f'<g class="lines" filter="url(#wob)">{formas}</g>'
           f'<g class="labels">{rotulos}</g></g></svg>')

    tarjetas, total = marcador()
    crumbs = [("resumen", "El resumen")] + [
        (k, estado.INVENTARIO[k][0]) for k in estado.INVENTARIO]
    nav = ['<nav class="nav" aria-label="Capas">']
    for i, (k, nombre) in enumerate(crumbs):
        act = ' aria-current="true"' if i == 0 else ''
        nav.append(f'<button class="crumb" data-goto="{k}"{act}>{nombre}</button>')
        if i == 0:
            nav.append('<span class="crumb-sep" aria-hidden="true">·</span>')
    nav.append('</nav>')

    vistas = [
        '<section class="view" id="v-resumen">'
        '<div class="view-head"><h2>Dónde están los huecos</h2>'
        '<p>La misma axonometría del plano hermano, pintada por estado en vez de por rol. '
        'Cada bloque toma el color del peor problema que tiene adentro, así que un bloque '
        'verde es verde de verdad y uno ámbar esconde al menos una cosa a medias.</p></div>'
        f'<figure style="margin:0"><div class="scroll">{axo}</div>'
        '<figcaption>La Capa C es la que peor sale: el story type se clasifica bien y '
        'después no cambia ningún supuesto, así que todo el aparato de arquetipos del '
        'spec no llega a la valuación. La Capa B es la que mejor: dieciséis reglas reales '
        'con tests, y lo que falla está en los bordes.</figcaption></figure></section>']

    for k in estado.INVENTARIO:
        titulo, sub, _ = estado.INVENTARIO[k]
        cuerpo, vb = estado.plan_inventario(k)
        formas_i, textos_i = plano.split_text(cuerpo)
        vistas.append(
            f'<section class="view" id="v-{k}" hidden>'
            f'<div class="view-head"><h2>{titulo}</h2><p>{sub}.</p></div>'
            f'<div class="scroll"><svg class="plan plan-inv" viewBox="{vb}" '
            f'aria-label="Inventario de estado de {titulo}">'
            f'<g class="lines" filter="url(#wob2)">{formas_i}</g>'
            f'<g class="labels">{textos_i}</g></svg></div></section>')

    brechas = ['<section class="brechas"><h2>Lo que el proyecto cree que tiene y no tiene</h2>',
               '<p>Ocho brechas entre lo que los documentos afirman y lo que el código hace. '
               'Ninguna es un descuido: todas están escritas en algún lado. El problema es '
               'que están escritas en el lugar que se olvida y borradas del que se consulta.</p><ol>']
    for titulo, cuerpo in estado.BRECHAS:
        brechas.append(f'<li><b>{titulo}</b><span>{cuerpo}</span></li>')
    brechas.append('</ol><p class="cierre">Dos cosas que esta foto no dice y conviene tener '
                   'presentes. La primera: 676 tests pasan, mypy en modo estricto está limpio '
                   'sobre 47 archivos, y de los seis ítems que el spec dejó fuera de alcance no '
                   'empezó ni uno. La calidad interna es alta; lo que falta es superficie de '
                   'operación. La segunda: el proyecto se auditó a sí mismo hace dos días, '
                   'encontró los dos problemas más graves y escribió dos ADR excelentes. '
                   'Después no implementó ninguna de las dos.</p></section>')

    js = """
const VISTAS = __VISTAS__;
function mostrar(v){
  VISTAS.forEach(k => {const s=document.getElementById('v-'+k); if(s) s.hidden = (k!==v);});
  document.querySelectorAll('.crumb').forEach(b =>
    b.setAttribute('aria-current', String(b.dataset.goto===v)));
  const n=document.querySelector('.nav');
  if(n) n.scrollIntoView({block:'start',
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto':'smooth'});
}
document.querySelectorAll('.crumb').forEach(b =>
  b.addEventListener('click', () => mostrar(b.dataset.goto)));
""".replace('__VISTAS__', repr([k for k, _ in crumbs]).replace("'", '"'))

    cuerpo = (
        '<div class="wrap"><div class="sheet">'
        '<h1>Qué está hecho</h1>'
        '<p class="deck">El mismo bot, pintado por estado real en vez de por diseño</p>'
        f'<p class="sello">auditado sobre {estado.AUDITADO_EN} · {estado.AUDITADO_EL} · '
        f'{total} componentes</p>'
        '<p class="lede">Este es el plano hermano de «Cómo el bot elige». Aquel explica '
        'cómo está pensado el sistema; este dice cuánto de eso existe. Cinco auditorías '
        'independientes recorrieron el código, y la regla fue siempre la misma: manda el '
        'código, no el spec.</p>'
        '<p class="lede">El estado que más importa es el tercero. Un componente '
        '<em>muerto</em> no está sin terminar: está terminado, tipado, a veces con tests, '
        'y nadie lo llama. Se ve verde desde cualquier ángulo excepto el del grep, y es la '
        'clase de hueco que un plano de arquitectura no puede mostrar.</p>'
        + tarjetas + "".join(nav) + "".join(vistas) + "".join(brechas)
        + '</div></div>')

    out = (HEAD.replace('__CSS__', css) + plano.DEFS + cuerpo
           + '<script>' + js + '</script>\n')
    dest = AQUI / 'estado.html'
    dest.write_text(out, encoding='utf-8')
    c = estado.contar()
    print(f'{dest.name} · {round(len(out)/1024)} KB · {total} componentes · '
          f'hecho {c["hecho"]} · a medias {c["a-medias"]} · '
          f'muerto {c["muerto"]} · falta {c["falta"]}')


if __name__ == '__main__':
    main()
