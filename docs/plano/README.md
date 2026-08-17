# Los dos planos

Dos páginas autocontenidas que se leen juntas y contestan preguntas distintas.

| Página | Contesta | Envejece |
|---|---|---|
| `plano.html` | **Cómo está pensado el sistema.** Tres niveles: la axonometría, cada capa con sus reglas, y una ficha por pieza con la lógica de Damodaran al lado de su implementación. | Ruidosamente: el build falla. |
| `estado.html` | **Cuánto de eso existe hoy.** El mismo dibujo teñido por estado real, más el inventario de los 76 componentes con su evidencia. | En silencio: hay que re-auditar. |

Esa asimetría es la que manda todo lo demás de este documento.

## No son decorado: son la guía de trabajo

Los dos planos existen para usarse mientras el proyecto avanza, no para mirarse
una vez. En concreto:

- **Antes de empezar una etapa**, `estado.html` dice qué hay de verdad en la
  zona que vas a tocar. La columna que importa es la de los `muertos`: código
  terminado, tipado y a veces con tests, que nadie llama. Casi siempre es más
  barato cablear uno que escribir algo nuevo al lado.
- **Mientras la escribís**, `plano.html` dice dónde va la pieza, qué patrón usa
  la vecindad y de qué depende. La vista «El código» muestra las tres tensiones
  vivas, así que si tu cambio agrega una cuarta, se va a ver.
- **Al cerrar la etapa**, los dos se actualizan. Eso no es opcional: un plano de
  estado desactualizado es peor que no tenerlo, porque se le cree.

## Qué hacer al terminar cada etapa

1. **Regenerar el plano de arquitectura.**

   ```bash
   python3 docs/plano/build.py
   ```

   Si falla, no es un problema del generador: te está diciendo que la página
   dejó de describir el código. Ver *Por qué falla el build a propósito*.

2. **Re-auditar el estado.** Es el paso que no se puede automatizar. Un símbolo
   existe o no existe, y eso lo verifica el build; pero que un detector *pueda
   dispararse*, que un supuesto tenga de dónde salir o que un test cubra la
   rama que importa, hay que ir a mirarlo. La forma que funcionó fue repartir el
   trabajo en auditorías paralelas por capa (Capa A, Capa B, Capa C, salida, y
   una transversal de hitos, ADRs y tests), con una regla única: **manda el
   código, no el spec**. Ahí aparecieron las cosas que ningún grep encuentra.

3. **Actualizar `estado.py`** con lo que la auditoría encontró:
   - los estados que cambiaron en `INVENTARIO`, con su evidencia nueva;
   - `BLOQUES`, que tiñe la axonometría con el peor estado de cada bloque;
   - `BRECHAS`, si se cerró o se abrió alguna;
   - y `AUDITADO_EN` / `AUDITADO_EL` con el commit y la fecha reales.

4. **Regenerar el plano de estado y republicar los dos.**

   ```bash
   python3 docs/plano/build_estado.py
   ```

5. **Cerrar la ADR si la etapa la implementó.** Es el error que este proyecto ya
   cometió dos veces: las ADR 0005 y 0006 dicen «Accepted» a secas y su decisión
   nunca se implementó, así que quien lee `docs/adr/` cree que el código las
   cumple. Si una etapa implementa una ADR, decilo en la ADR. Si la deja
   pendiente, decilo también.

## El aviso de foto vieja

`build_estado.py` compara `AUDITADO_EN` contra HEAD y avisa si hay commits que
tocaron `src/` desde entonces, en la consola y con un cartel arriba de la propia
página. Se filtra por `src/` a propósito: un commit de documentación no invalida
una auditoría del código, y contarlo solo enseñaría a ignorar el aviso.

El aviso no rompe el build. Una foto puede ser legítimamente más vieja que HEAD;
lo que no puede es fingir que no lo es.

## Construir

```bash
python3 docs/plano/build.py            # escribe docs/plano/plano.html
python3 docs/plano/build_estado.py     # escribe docs/plano/estado.html
```

Ninguno necesita red ni dependencias: las tipografías están embebidas en
`fonts/` como base64 y todo lo demás es la librería estándar. Las dos salidas
están gitignoreadas por ser generadas; lo que se versiona son los fuentes.

## Por qué falla el build a propósito

El plano hace afirmaciones verificables sobre el código, así que se genera desde
el código y no desde el spec. `build.py` corta con un mensaje cuando:

- una ficha cita un símbolo que ya no existe en `src/bot/`;
- aparece una tensión en el grafo de dependencias que no tiene ficha;
- hay una ficha de tensión que ya no corresponde a ninguna arista real.

Ese último es el importante: si arreglás una de las tres tensiones, el build
falla y te obliga a sacar su ficha. La página no puede quedar diciendo que hay
una deuda de diseño que ya pagaste.

## Los archivos

| Archivo | Qué hace |
|---|---|
| `build.py` | Junta todo y escribe `plano.html`. |
| `build_estado.py` | Junta todo y escribe `estado.html`. Reutiliza fuentes, filtros y geometría del otro. |
| `codemap.py` | Parsea `src/bot/` con `ast`: grafo de módulos, grafo de paquetes, tensiones e índice de símbolos con firma y línea. |
| `iso.py` | La axonometría. La comparten los dos planos: uno la tiñe por rol y el otro por estado. |
| `views.py` | Los seis planos de nivel 2. El de «El código» deriva su grafo de `codemap`. |
| `estado.py` | El inventario de estado: los 76 componentes, la tinción de la axonometría y las ocho brechas. **Es lo que se actualiza después de cada etapa.** |
| `part-head.html` | Tokens de color y todo el CSS del plano de arquitectura. |
| `part-body.html` | El armazón: hero, los cuatro principios, la navegación y el diálogo. |
| `part-data.js` | El contenido de las fichas de dominio. |
| `part-meta.js` | Qué símbolo implementa cada ficha, qué patrones usa, y las fichas de patrón, tensión y paquete. |
| `part-js.js` | Navegación entre vistas, ficha modal, resaltado y teclado. |
| `fonts/*.b64` | Shantell Sans, Literata y Sometype Mono, subconjunto latino. |

## Decisiones que conviene no deshacer sin pensarlo

- **El texto va fuera del filtro de temblor.** `feDisplacementMap` deforma los
  glifos; por eso el build separa los `<text>` a una capa aparte con
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
- **En `estado.html` el color codifica estado y nada más.** El rol se fue a
  propósito: dos codificaciones de color en el mismo dibujo no se leen. El rol
  sigue disponible en el plano hermano.

Ver `docs/PRODUCT.md` y `docs/DESIGN.md` para el registro, la audiencia y el
sistema visual.
