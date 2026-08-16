"""Axonometría del nivel 1: cinco planos apilados en cascada.

Proyección isométrica. Un desplazamiento de (+d, -d) en planta es un corrimiento
puramente horizontal en pantalla, así que la cascada se arma moviendo cada capa
(+OD, -OD) en planta y bajándola DZ en elevación.

El caudal se dibuja solo en el aire entre losa y losa: sale por debajo de una y
aterriza sobre el objeto central de la siguiente. Así queda siempre visible, y
se lo ve angostarse al atravesar la Capa B.
"""
import math

K = math.cos(math.radians(30))

W, H, T = 300.0, 170.0, 13.0
DZ, OD = 215.0, 26.0
CX, CY = 150.0, 85.0            # centro de planta: por ahí baja el caudal


def iso(x, y, z):
    return ((x - y) * K, (x + y) * 0.5 - z)


def poly(pts, cls):
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return f'<polygon class="{cls}" points="{d}"/>'


def prism(ox, oy, z, w, h, t, top, left, right):
    """Prisma recto: cara superior más las dos caras frontales visibles."""
    x0, y0, x1, y1 = ox, oy, ox + w, oy + h
    f_top = [iso(x0, y0, z), iso(x1, y0, z), iso(x1, y1, z), iso(x0, y1, z)]
    f_left = [iso(x0, y1, z), iso(x1, y1, z), iso(x1, y1, z - t), iso(x0, y1, z - t)]
    f_right = [iso(x1, y0, z), iso(x1, y1, z), iso(x1, y1, z - t), iso(x1, y0, z - t)]
    return poly(f_left, left) + poly(f_right, right) + poly(f_top, top)


LAYERS = [
    dict(id="fuentes", title="Fuentes", sub="los hechos, sin opinión",
         role="datos", entry=0.0),
    dict(id="capa-a", title="Capa A", sub="datos crudos", role="datos", entry=0.0),
    dict(id="capa-b", title="Capa B", sub="screener mecánico",
         role="selecciona", entry=56.0),
    dict(id="capa-c", title="Capa C", sub="análisis profundo",
         role="valua", entry=26.0),
    dict(id="salida", title="Salida", sub="reportes y vigilancia",
         role="vigila", entry=0.0),
]

# (id, x, y, ancho, profundidad, altura, rótulo, rol, dx_rótulo, dy_rótulo)
BLOCKS = {
    "fuentes": [
        ("damodaran", 10, 6, 128, 56, 15, "Damodaran", "datos", 0, 0),
        ("sec", 168, 6, 122, 56, 15, "SEC EDGAR", "datos", 0, 0),
        ("fmp", 10, 108, 128, 56, 15, "FMP", "datos", 0, 0),
        ("ibkr", 168, 108, 122, 56, 15, "IBKR", "vigila", 0, 0),
    ],
    "capa-a": [
        ("adapters", 10, 10, 116, 150, 16, "Adapters", "datos", 0, 0),
        ("duckdb", 172, 10, 118, 150, 30, "DuckDB", "datos", 0, 0),
    ],
    "capa-c": [
        ("story", 8, 52, 46, 66, 16, "Story type", "valua", -6, -4),
        ("assumptions", 66, 52, 46, 66, 16, "Supuestos", "valua", -6, -4),
        ("dcf", 124, 52, 52, 66, 26, "DCF", "valua", 26, -2),
        ("sensitivity", 188, 52, 46, 66, 16, "Sensitivity", "valua", 6, -4),
        ("flags", 246, 52, 46, 66, 16, "Flags", "valua", 6, -4),
    ],
    "salida": [
        ("monitor", 10, 8, 128, 60, 16, "Monitor", "vigila", 0, 0),
        ("events", 168, 8, 122, 60, 16, "Eventos", "vigila", 0, 0),
        ("reports", 10, 104, 280, 56, 12, "Reportes", "vigila", 0, 0),
    ],
}

# zigurat de la Capa B: cuatro escalones que se angostan
ZIG = [
    (24, 14, 252, 142, 14, "gates", "elimina"),
    (54, 32, 192, 106, 14, "value", "selecciona"),
    (84, 50, 132, 70, 14, "traps", "elimina"),
    (114, 68, 72, 34, 14, "ranking", "selecciona"),
]

# semiancho del caudal que aterriza en cada capa
FLOW_W = [30.0, 30.0, 30.0, 9.0, 9.0]
# el tramo ancho es el que entra a la Capa B; el angosto, el que sale
FLOW_LABEL = {1: "todo el universo", 2: "20 a 30 candidatos"}

ARIA = {
    "fuentes": "Fuentes: los cuatro proveedores externos",
    "capa-a": "Capa A: datos crudos",
    "capa-b": "Capa B: el screener mecánico",
    "capa-c": "Capa C: análisis profundo",
    "salida": "Salida: reportes y vigilancia de la cartera",
}


def origin(i):
    return i * OD, -i * OD, -i * DZ


def rhombus(cx, cy, z, s):
    return [iso(cx - s, cy, z), iso(cx, cy - s, z),
            iso(cx + s, cy, z), iso(cx, cy + s, z)]


def slab(i, L):
    ox, oy, z = origin(i)
    body = prism(ox, oy, z, W, H, T, "face-top", "face-left", "face-right")
    if i < len(LAYERS) - 1:
        body += poly(rhombus(ox + CX, oy + CY, z + 0.4, FLOW_W[i] * 0.72), "aperture")
    return (f'<g class="slab" data-layer="{L["id"]}" data-role="{L["role"]}" '
            f'tabindex="0" role="button" aria-label="{ARIA[L["id"]]}. '
            f'Abre el plano de esta capa.">{body}</g>')


def blocks(i, L, near=None):
    """near=None todos; False solo los lejanos; True solo los cercanos."""
    ox, oy, z = origin(i)
    if L["id"] == "capa-b":
        if near is True:
            return ""
        out = []
        for k, (bx, by, bw, bh, bz, bid, role) in enumerate(ZIG):
            out.append(
                f'<g class="blk" data-node="{bid}" data-layer="capa-b" '
                f'data-role="{role}" tabindex="0" role="button" '
                f'aria-label="Escalón {k + 1} del embudo. Abre el plano de la Capa B.">'
                + prism(ox + bx, oy + by, z + (k + 1) * bz, bw, bh, bz,
                        f"blk-top r-{role}", f"blk-left r-{role}",
                        f"blk-right r-{role}") + "</g>")
        return "".join(out)
    out = []
    for b in sorted(BLOCKS[L["id"]], key=lambda b: b[1] + b[2]):
        bid, bx, by, bw, bh, bz, label, role, _, _ = b
        cerca = (bx + bw / 2) + (by + bh / 2) > CX + CY
        if near is not None and cerca != near:
            continue
        out.append(
            f'<g class="blk" data-node="{bid}" data-layer="{L["id"]}" '
            f'data-role="{role}" tabindex="0" role="button" '
            f'aria-label="{label}. Abre su ficha.">'
            + prism(ox + bx, oy + by, z + bz, bw, bh, bz,
                    f"blk-top r-{role}", f"blk-left r-{role}",
                    f"blk-right r-{role}") + "</g>")
    return "".join(out)


def block_labels(i, L):
    ox, oy, z = origin(i)
    if L["id"] == "capa-b":
        bx, by, bw, bh, bz, _, _ = ZIG[-1]
        px, py = iso(ox + bx + bw / 2, oy + by + bh / 2, z + 4 * bz)
        tx, ty = px + 108, py - 44
        return (f'<g class="callout">'
                f'<path class="leader" d="M{px + 6:.1f},{py - 4:.1f} '
                f'L{tx - 8:.1f},{ty + 4:.1f}"/>'
                f'<text class="lbl-blk" x="{tx:.1f}" y="{ty:.1f}">4 etapas</text>'
                f'<text class="lbl-sub" x="{tx:.1f}" y="{ty + 14:.1f}">16 reglas</text>'
                "</g>")
    out = []
    for bid, bx, by, bw, bh, bz, label, role, dx, dy in BLOCKS[L["id"]]:
        px, py = iso(ox + bx + bw / 2, oy + by + bh / 2, z + bz)
        out.append(f'<text class="lbl-blk" x="{px + dx:.1f}" y="{py + dy + 4:.1f}" '
                   f'text-anchor="middle">{label}</text>')
    return "".join(out)


def flow(i):
    """Caudal en el aire entre la losa i y la losa i+1."""
    ox0, oy0, z0 = origin(i)
    ox1, oy1, z1 = origin(i + 1)
    a = rhombus(ox0 + CX, oy0 + CY, z0 - T, FLOW_W[i])
    b = rhombus(ox1 + CX, oy1 + CY, z1 + LAYERS[i + 1]["entry"], FLOW_W[i + 1])
    cuerpo = (poly([a[2], a[3], b[3], b[2]], "flow-right")
              + poly([a[3], a[0], b[0], b[3]], "flow-left") + poly(b, "flow-cap"))
    lab = ""
    if i in FLOW_LABEL:
        mx, my = (a[2][0] + b[2][0]) / 2, (a[2][1] + b[2][1]) / 2
        lab = (f'<path class="leader" d="M{mx + 6:.1f},{my:.1f} '
               f'L{mx + 96:.1f},{my - 30:.1f}"/>'
               f'<text class="lbl-flow" x="{mx + 102:.1f}" y="{my - 27:.1f}">'
               f'{FLOW_LABEL[i]}</text>')
    return f'<g class="flow">{cuerpo}</g>', lab


def layer_label(i, L):
    ox, oy, z = origin(i)
    corner = iso(ox, oy + H, z)
    tx, ty = corner[0] - 30, corner[1] - 10
    return (f'<g class="lyr-lbl" data-layer="{L["id"]}" data-role="{L["role"]}" '
            f'tabindex="0" role="button" aria-label="{ARIA[L["id"]]}. '
            f'Abre el plano de esta capa.">'
            f'<path class="leader" d="M{tx + 8:.1f},{ty - 5:.1f} '
            f'L{corner[0] - 5:.1f},{corner[1] - 3:.1f}"/>'
            f'<text class="lbl-lyr" x="{tx:.1f}" y="{ty:.1f}" text-anchor="end">'
            f'{L["title"]}</text>'
            f'<text class="lbl-sub" x="{tx:.1f}" y="{ty + 16:.1f}" text-anchor="end">'
            f'{L["sub"]}</text></g>')


def loops():
    def borde(i):
        ox, oy, z = origin(i)
        return iso(ox + W, oy, z)

    out = []
    specs = [("mos", 3, 2, "el margen de seguridad vuelve al ranking"),
             ("filing", 4, 3, "un filing nuevo vuelve a disparar el análisis")]
    for k, (lid, src, dst, label) in enumerate(specs):
        p0, p1 = borde(src), borde(dst)
        bx = max(p0[0], p1[0]) + 78 + k * 46
        d = (f"M{p0[0] + 6:.1f},{p0[1]:.1f} C{bx:.1f},{p0[1]:.1f} "
             f"{bx:.1f},{p1[1]:.1f} {p1[0] + 6:.1f},{p1[1]:.1f}")
        my = (p0[1] + p1[1]) / 2
        out.append(f'<g class="loop"><path class="loop-path" d="{d}" '
                   f'marker-end="url(#ar)"/></g>')
        out.append(f'<text class="lbl-loop" transform="rotate(-90 {bx + 12:.1f} {my:.1f})" '
                   f'x="{bx + 12:.1f}" y="{my:.1f}" text-anchor="middle">{label}</text>')
    return out


def build():
    formas, rotulos = [], []
    for i in range(len(LAYERS) - 1, -1, -1):
        L = LAYERS[i]
        formas.append(f'<g class="layer" data-layer="{L["id"]}">')
        formas.append(slab(i, L))
        if i > 0:
            formas.append(blocks(i, L, near=False))
            cuerpo, lab = flow(i - 1)
            formas.append(cuerpo)
            rotulos.append(lab)
            formas.append(blocks(i, L, near=True))
        else:
            formas.append(blocks(i, L))
        formas.append("</g>")
    loop_partes = loops()
    formas.extend(p for p in loop_partes if p.startswith('<g class="loop"'))
    rotulos.extend(p for p in loop_partes if p.startswith('<text'))
    for i, L in enumerate(LAYERS):
        rotulos.append(layer_label(i, L))
        rotulos.append(block_labels(i, L))
    return "".join(formas), "".join(rotulos)


if __name__ == "__main__":
    s, l = build()
    print(f"<!--S-->{s}<!--L-->{l}")
