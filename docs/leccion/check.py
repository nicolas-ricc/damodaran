"""Verifica que cada símbolo citado por la lección exista en src/bot/.

    python3 docs/leccion/check.py [ruta/a/index.html]

Recorre cada <code data-symbol="bot.modulo.Nombre"> y lo busca en el índice que
arma docs/plano/codemap.py con ast. Si falta, o si la ubicación citada al lado
apunta a otro archivo, sale con 1 y los lista: la lección no puede quedar
citando código que ya no existe. Una línea corrida es solo un aviso.
"""
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'plano'))

import codemap  # noqa: E402

CITA_RE = re.compile(
    r'<code\b[^>]*\bdata-symbol="([^"]+)"[^>]*>.*?</code>'
    r'(?:\s*(?:·|&middot;)?\s*<code class="at">(src/bot/[^<:]+\.py):(\d+)</code>)?',
    re.S)
AT_RE = re.compile(r'<code\b[^>]*\bclass="at"')


def indice():
    modulos, _, simbolos = codemap.escanear()
    idx = {mod: (m['archivo'], 1) for mod, m in modulos.items()}
    for clave, s in simbolos.items():
        nombre = clave.split(':', 1)[1]
        idx[f"{s['modulo']}.{nombre}"] = (s['archivo'], s['linea'])
    return idx


def citas(html):
    return [(m[1], m[2], int(m[3]) if m[3] else None) for m in CITA_RE.finditer(html)]


def revisar(html, idx):
    errores, avisos = [], []
    for simbolo, archivo, linea in citas(html):
        if simbolo not in idx:
            errores.append(f'falta: {simbolo}')
            continue
        real_archivo, real_linea = idx[simbolo]
        if archivo is None:
            continue
        if archivo != real_archivo:
            errores.append(f'archivo: {simbolo} citado en {archivo}, vive en {real_archivo}')
        elif linea != real_linea:
            avisos.append(f'línea movida: {simbolo} citado en {archivo}:{linea}, '
                          f'ahora {real_archivo}:{real_linea}')
    # una ubicación que el regex no empareja se saltearía en silencio
    sueltas = len(AT_RE.findall(html)) - sum(1 for _, archivo, _ in citas(html) if archivo)
    if sueltas:
        errores.append(f'ubicación ilegible: {sueltas} <code class="at"> sin símbolo y archivo:línea')
    return errores, avisos


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    ruta = pathlib.Path(args[0]) if args else AQUI / 'index.html'
    html = ruta.read_text(encoding='utf-8')
    errores, avisos = revisar(html, indice())
    for a in avisos:
        print(f'aviso  {a}')
    for e in errores:
        print(f'error  {e}')
    print(f'check | {len(citas(html))} citas, {len(errores)} errores, {len(avisos)} avisos')
    return 1 if errores else 0


if __name__ == '__main__':
    sys.exit(main())
