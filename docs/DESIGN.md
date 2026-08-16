# Design

Sistema visual de las piezas explicativas del bot. Ver `docs/PRODUCT.md` para
registro, audiencia y principios.

## Theme

**Escena física:** una hoja de papel entonado de cuaderno de dibujo, apoyada
sobre un escritorio de kraft, dibujada a mano con lápices de pigmento de tierra.
Se mira de día, de cerca, y uno se acerca para leer una etiqueta.

Esa escena fuerza claro, no oscuro. Pero **claro entonado**, no crema: el papel
de dibujo real es tonal, y el pigmento encima se ve como pigmento. Sobre crema
casi blanco los mismos colores se ven lavados, además de ser el default de IA que
`PRODUCT.md` prohíbe.

**Estrategia de color:** full palette. Cinco roles nombrados, cada uno con un
trabajo semántico en el plano. Está permitido en registro brand y es necesario
acá: el color es notación, no decoración.

## Color

OKLCH en todos lados. Dos superficies, dos tintas, cinco pigmentos con dos
paradas cada uno (`line` para trazo y relleno, `text` para tipografía chica).

### Superficies

| Token | Valor | Uso |
|---|---|---|
| `--desk` | `oklch(0.665 0.048 66)` | Fondo del documento. Kraft de escritorio. |
| `--sheet` | `oklch(0.845 0.035 82)` | La hoja de dibujo. Donde vive el plano. |
| `--sheet-deep` | `oklch(0.795 0.038 80)` | Sombreado dentro de la hoja, zonas agrupadas. |

### Tintas

| Token | Valor | Contraste sobre `--sheet` | Uso |
|---|---|---|---|
| `--ink` | `oklch(0.315 0.045 55)` | ~6.0:1 | Bistre. Todo el texto de cuerpo y el trazo principal. |
| `--ink-soft` | `oklch(0.385 0.040 56)` | ~4.7:1 | Anotaciones, texto secundario. Sigue pasando AA de cuerpo. |

Nunca negro puro: delata el vector.

### Pigmentos (roles semánticos)

Cada rol lleva **pigmento + forma + marca de trazo**. El color nunca codifica
solo.

| Rol | Token `line` | Token `text` | Forma | Marca de trazo |
|---|---|---|---|---|
| **Datos** — fuentes y tablas (Capa A) | `oklch(0.620 0.115 78)` ocre | `oklch(0.400 0.085 72)` | Ficha con esquina doblada | Línea sólida |
| **Elimina** — quality gates, trap detection | `oklch(0.505 0.145 30)` terracota | `oklch(0.385 0.120 30)` | Compuerta con purga lateral | Hatching diagonal |
| **Selecciona** — value indicators, ranking | `oklch(0.545 0.095 135)` oliva | `oklch(0.395 0.075 135)` | Embudo / marca de check | Doble subrayado |
| **Valúa** — story type, DCF, sensitivity (Capa C) | `oklch(0.470 0.115 265)` índigo | `oklch(0.375 0.105 265)` | Círculo concéntrico | Punteado grueso |
| **Vigila** — portfolio monitor, eventos | `oklch(0.505 0.115 350)` ciruela | `oklch(0.385 0.105 350)` | Ojo / campana dibujada | Línea ondulada |

El índigo es deliberado: sin un pigmento frío la paleta de tierra se vuelve una
papilla cálida, y se pierde el contraste que distingue *eliminar* de *valuar*.

## Typography

Tres familias, en el tope permitido, cada una con un trabajo distinto. Todas
embebidas como woff2 en base64: el Artifact corre bajo CSP estricta y bloquea
cualquier CDN.

| Familia | Rol | Por qué |
|---|---|---|
| **Shantell Sans** (variable 300–800) | Títulos y etiquetas del plano | Mano de marcador de Shantell Martin, legible a tamaño chico. Es lo dibujado. |
| **Literata** (variable 7–72 opsz, 300–700, + itálica) | Texto de cuerpo y paneles | Serif de pantalla, cálida. Es lo impreso: la anotación al margen de lo dibujado. |
| **Sometype Mono** (variable 400–700) | Identificadores | Nombres de tabla, reglas, comandos CLI. Mono humanista, no de terminal. |

Manuscrita + serif es un eje de contraste real, y la jerarquía es honesta: lo
dibujado a mano contra lo impreso encima.

**Reflejos rechazados:** Caveat, Architects Daughter y Virgil (la fuente de
Excalidraw) son el pick automático para "dibujado a mano". Inter, DM Sans, IBM
Plex y Fraunces están en la lista de rechazo de `impeccable`.

- Escala modular con ratio ≥1.25, `clamp()` fluido en títulos.
- Techo de display: 6rem. Piso de letter-spacing: -0.04em.
- Cuerpo entre 65 y 75ch.
- `text-wrap: balance` en h1–h3, `pretty` en prosa larga.

## Hand-drawn technique

El temblor es real, no una textura pegada encima. La geometría se traza limpia
en SVG y se deforma con filtro:

```
<filter id="wobble">
  <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="3" seed="N"/>
  <feDisplacementMap in="SourceGraphic" scale="2.5" xChannelSelector="R" yChannelSelector="G"/>
</filter>
```

- `seed` distinto por grupo, para que dos cajas iguales no tiemblen igual.
- `scale` entre 1.5 y 3: más que eso deja de leerse como mano y pasa a temblor.
- `stroke-linecap: round`, `stroke-linejoin: round` en todo trazo.
- Rotación de −0.6° a 0.6° por caja, con `transform`.
- Grano de papel: `feTurbulence` de baja frecuencia en una capa de overlay a
  ~5% de opacidad.

**Costo:** los filtros SVG se rasterizan y son caros en móvil. Aplicar por grupo
grande, nunca por elemento. Si el frame cae, bajar `numOctaves` a 2 antes que
sacar el efecto.

## Layout

- Grid 2D solo cuando hay dos ejes; `flex-wrap` para el resto.
- Espaciado fluido con `clamp()`, variado para ritmo: separaciones generosas
  entre capas, agrupación apretada dentro de una capa.
- Las tarjetas son la respuesta perezosa. Acá el plano no es una grilla de
  tarjetas: es un dibujo continuo con anotaciones ancladas.
- Escala z-index semántica: `dropdown → sticky → modal-backdrop → modal →
  toast → tooltip`. Nunca 9999.

## Motion

- Curvas exponenciales ease-out. Sin bounce, sin elastic.
- El movimiento sirve a la comprensión: al enfocar un nodo, el camino de datos
  se ilumina y el resto se atenúa. Eso es la animación principal y se gana el
  lugar.
- Nada de reveal-on-scroll uniforme por sección.
- El contenido es visible por defecto. Ninguna animación puede ser la condición
  para que algo se vea.
- `prefers-reduced-motion: reduce` → crossfade o cambio instantáneo.
