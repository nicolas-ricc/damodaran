"""Lee src/bot/ y extrae el grafo de dependencias y el índice de símbolos.

Todo sale de parsear los import con ast, así que el plano nunca afirma una
dependencia que el código no tenga. Si un símbolo referenciado por una ficha
no existe, el build falla en vez de dibujar una mentira.
"""
import ast
import json
import pathlib
import sys
from collections import defaultdict

AQUI = pathlib.Path(__file__).resolve().parent
REPO = AQUI.parent.parent
ROOT = REPO / 'src' / 'bot'

# a qué parte de la arquitectura pertenece cada paquete
CAPA = {
    'cli': 'orquestador', 'config': 'compartido', 'storage': 'capa-a',
    'ingest': 'capa-a', 'reference': 'compartido', 'utils': 'compartido',
    'screener': 'capa-b', 'valuator': 'capa-c',
    'portfolio': 'salida', 'reporting': 'salida',
}

# dirección esperada: cada paquete solo debería depender de los de abajo
NIVEL = {'orquestador': 0, 'salida': 1, 'capa-c': 2, 'capa-b': 3,
         'capa-a': 4, 'compartido': 5}

# adapters de proveedor: que uno importe a otro llama la atención;
# que universe componga a fmp, no.
PROVEEDORES = {'bot.ingest.damodaran', 'bot.ingest.sec_edgar',
               'bot.ingest.fmp', 'bot.ingest.ibkr'}


def mod_name(path):
    rel = str(path.relative_to(ROOT))[:-3].replace('/', '.')
    return 'bot' if rel == '__init__' else 'bot.' + rel.replace('.__init__', '')


def paquete(mod):
    partes = mod.split('.')
    return partes[1] if len(partes) > 1 else 'cli'


def firma(n):
    if isinstance(n, ast.ClassDef):
        bases = [ast.unparse(b) for b in n.bases]
        s = f'class {n.name}' + (f'({", ".join(bases)})' if bases else '')
    else:
        ret = f' -> {ast.unparse(n.returns)}' if n.returns else ''
        s = f'def {n.name}({ast.unparse(n.args)}){ret}'
    s = ' '.join(s.split())
    return s if len(s) <= 96 else s[:93] + '…'


def escanear():
    modulos, aristas, simbolos = {}, set(), {}
    for f in sorted(ROOT.rglob('*.py')):
        mod = mod_name(f)
        src = f.read_text(encoding='utf-8')
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            sys.exit(f'no se pudo parsear {f}: {e}')
        rel = str(f.relative_to(REPO))
        modulos[mod] = {'archivo': rel, 'lineas': src.count('\n') + 1}

        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith('bot'):
                if n.module != mod:
                    aristas.add((mod, n.module))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith('bot') and a.name != mod:
                        aristas.add((mod, a.name))

        for n in tree.body:
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                simbolos[f'{rel}:{n.name}'] = {
                    'firma': firma(n), 'archivo': rel, 'linea': n.lineno, 'modulo': mod}
            if isinstance(n, ast.ClassDef):
                for m in n.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        simbolos[f'{rel}:{n.name}.{m.name}'] = {
                            'firma': firma(m), 'archivo': rel,
                            'linea': m.lineno, 'modulo': mod}
    return modulos, sorted(aristas), simbolos


def grafo_paquetes(aristas):
    g = defaultdict(set)
    for a, b in aristas:
        pa, pb = paquete(a), paquete(b)
        if pa != pb:
            g[pa].add(pb)
    return {k: sorted(v) for k, v in sorted(g.items())}


def tensiones(gp, aristas):
    """Aristas que incomodan: contra la dirección esperada, o entre proveedores."""
    out = []
    for a, destinos in gp.items():
        for b in destinos:
            if NIVEL[CAPA[a]] > NIVEL[CAPA[b]]:
                out.append({'de': a, 'a': b, 'tipo': 'contra-corriente',
                            'ciclo': a in gp.get(b, [])})
    for a, b in aristas:
        if a in PROVEEDORES and b in PROVEEDORES:
            out.append({'de': a, 'a': b, 'tipo': 'adapter-adapter', 'ciclo': False})
    return out


def cargar():
    """Devuelve el mapa ya calculado, sin pasar por disco."""
    modulos, aristas, simbolos = escanear()
    gp = grafo_paquetes(aristas)
    return {'modulos': modulos, 'aristas': [list(a) for a in aristas],
            'paquetes': gp, 'capa': CAPA, 'tensiones': tensiones(gp, aristas),
            'simbolos': simbolos}


def main():
    d = cargar()
    (AQUI / 'codemap.json').write_text(
        json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'codemap | {len(d["modulos"])} módulos, {len(d["aristas"])} aristas, '
          f'{len(d["simbolos"])} símbolos, {len(d["tensiones"])} tensiones')
    for t in d['tensiones']:
        print(f'  {t["tipo"]:17s} {t["de"]} -> {t["a"]}')


if __name__ == '__main__':
    main()
