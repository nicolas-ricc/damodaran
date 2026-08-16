# El plano

Página autocontenida que explica el bot en tres niveles: el sistema en
axonometría, cada capa abierta con sus reglas, y una ficha por pieza con la
lógica de Damodaran de un lado y la implementación del otro.

## Construir

```bash
python3 docs/plano/build.py     # escribe docs/plano/plano.html
```

No necesita red ni dependencias: las tipografías están embebidas en `fonts/`
como base64 y todo lo demás es la librería estándar.

## Por qué falla el build a propósito

El plano hace afirmaciones verificables sobre el código, así que se genera
desde el código y no desde el spec. `build.py` corta con un mensaje cuando:

- una ficha cita un símbolo que ya no existe en `src/bot/`;
- aparece una tensión en el grafo de dependencias que no tiene ficha;
- hay una ficha de tensión que ya no corresponde a ninguna arista real.

Eso último es lo importante: si arreglás una de las tres tensiones, el build
falla y te obliga a sacar su ficha. La página no puede quedar diciendo que hay
una deuda de diseño que ya pagaste.

## Los archivos

| Archivo | Qué hace |
|---|---|
| `build.py` | Junta todo y escribe `plano.html`. Es el único que se corre. |
| `codemap.py` | Parsea `src/bot/` con `ast`: grafo de módulos, grafo de paquetes, tensiones e índice de símbolos con firma y línea. |
| `iso.py` | La axonometría del nivel 1. Proyección isométrica calculada, no dibujada a mano. |
| `views.py` | Los seis planos de nivel 2. El de «El código» deriva su grafo de `codemap`. |
| `part-head.html` | Tokens de color y todo el CSS. |
| `part-body.html` | El armazón: hero, los cuatro principios, la navegación y el diálogo. |
| `part-data.js` | El contenido de las fichas de dominio. |
| `part-meta.js` | Qué símbolo implementa cada ficha, qué patrones usa, y las fichas de patrón, tensión y paquete. |
| `part-js.js` | Navegación entre vistas, ficha modal, resaltado y teclado. |
| `fonts/*.b64` | Shantell Sans, Literata y Sometype Mono, subconjunto latino. |

## Decisiones que conviene no deshacer sin pensarlo

- **El texto va fuera del filtro de temblor.** `feDisplacementMap` deforma los
  glifos; por eso `build.py` separa los `<text>` a una capa aparte con
  `pointer-events:none`, y los clics llegan al rectángulo invisible de abajo.
- **Al seleccionar una pieza se atenúa solo el trazo, no los rótulos.** Atenuar
  el texto lo dejaba por debajo del contraste mínimo y no había opacidad que lo
  arreglara.
- **Cada pigmento tiene dos paradas**: `--p-*` para trazo (necesita 3:1) y
  `--p-*-t` para texto chico (necesita 4.5:1). Colapsarlas en una rompe el
  contraste en tema claro.
- **En tema oscuro las caras del volumen son más oscuras que la hoja.** Es al
  revés de lo intuitivo, y es lo que permite que el texto claro encima llegue a
  4.5:1; la forma la sostiene el contorno de color, no el relleno.

Ver `docs/PRODUCT.md` y `docs/DESIGN.md` para el registro, la audiencia y el
sistema visual.
