# Product

## Register

brand

## Users

Nicolás (autor del bot) y gente técnica que no conoce el proyecto: devs, cuants,
alguien a quien le muestra en qué anda. Entienden arquitectura de software. No
necesariamente entienden por qué un DCF necesita un *story type*, ni por qué una
empresa barata puede ser una mala compra.

El trabajo que vienen a hacer: entender cómo un pipeline convierte 50.000
empresas en una shortlist de 20, y por qué cada etapa descarta lo que descarta.
No vienen a operar nada. Vienen a entender.

## Product Purpose

Las superficies visuales de este repo explican el bot; no lo operan. El bot es
CLI y así se queda (spec §15 deja fuera de alcance el dashboard web). Lo que se
diseña acá son piezas explicativas: planos, mapas, documentos que hacen legible
un sistema de cuatro capas que de otro modo solo vive en el spec y en el código.

Éxito = alguien que no conoce el proyecto mira el plano dos minutos y puede
explicar con sus palabras por qué el screener tiene *trap detection* separado de
los *quality gates*.

## Brand Personality

Paciente, artesanal, curioso.

La voz es la de alguien que dibuja para pensar, no para impresionar. Explica sin
condescender: asume que el lector es inteligente pero no sabe de valuación.
Nombra lo que no sabe (el DCF es garbage-in/garbage-out y el spec lo dice en
§16.4; el plano también debería decirlo).

Contra-voz: el tono de producto financiero. Nada de "decisiones más
inteligentes", nada de promesas de rendimiento. El bot sugiere candidatos para
que un humano investigue, y la pieza tiene que sonar así.

## Anti-references

- **Dashboard de fintech.** Azul marino y dorado, tarjetas de métrica grande,
  líneas verdes. Bloomberg-para-retail.
- **Landing de SaaS.** Gradientes, ilustración isométrica, grilla de tarjetas
  idénticas con ícono + título + párrafo.
- **Diagrama de Confluence.** Cajas grises, flechas rectas, tipografía de
  sistema, cero jerarquía.
- **Editorial-tipográfico.** Serif display en itálica + etiquetas mono +
  filetes + monocromo. Carril saturado por IA; prohibido aunque el registro sea
  editorial.
- **Crema / arena / papel casi blanco** como fondo. El default de IA de 2026.

## Design Principles

1. **El dibujo es el argumento.** Si algo se puede mostrar en el plano, no se
   escribe en un párrafo al lado. El texto anota; no narra en paralelo.
2. **La forma sigue a la mecánica.** El screener se estrecha porque descarta;
   el valuador no se estrecha porque profundiza. La geometría tiene que ser
   verdad sobre el sistema, no decoración.
3. **Barato ≠ buena compra.** Es la tesis del bot y tiene que ser visible: lo
   que busca valor y lo que detecta trampas son fuerzas opuestas, y se dibujan
   opuestas.
4. **Honestidad sobre los límites.** El spec admite en §6.7 y §16 lo que el bot
   no puede hacer. La pieza lo hereda: donde hay un supuesto frágil, se dice.
5. **Dibujado, no renderizado.** El temblor de la línea es parte del mensaje:
   esto es un modelo de alguien, no una verdad de máquina.

## Accessibility & Inclusion

- WCAG 2.2 AA en todo el texto. Cuerpo ≥4.5:1, texto grande y grafismo ≥3:1.
- **El color nunca codifica solo.** Los cinco roles semánticos (datos, elimina,
  selecciona, valúa, vigila) llevan además del pigmento una forma y una marca de
  trazo propias, legibles en escala de grises y con daltonismo.
- `prefers-reduced-motion: reduce` reemplaza todo movimiento por transición
  instantánea o crossfade.
- Navegable por teclado: cada nodo del plano es un control enfocable con foco
  visible, y el panel de detalle anuncia sus cambios.
