# La lección

Una página para quien sabe invertir pero no matemática financiera avanzada: explica el pipeline de Damodaran capítulo por capítulo y señala dónde vive cada pieza en el código.

- **Abrirla**: doble clic en `index.html`. Es autocontenida, no necesita servidor ni red.
- **Verificarla**: `python3 docs/leccion/check.py`. Sale con 1 y lista los símbolos que ya no existen; avisa si una línea citada se movió.
- **Tests**: `uv run pytest tests/unit/test_leccion.py` también chequea umbrales, pesos y el ejemplo del DCF contra el código.
- **Publicarla** como Artifact de claude.ai: subí `index.html` tal cual.

Si cambiás `src/`, corré el check antes de commitear y arreglá los avisos.
