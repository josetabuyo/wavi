# ADR-011: Detección de reacciones por color, no por identidad de emoji

**Estado:** Aceptado
**Fecha:** 2026-08-26

## Contexto

Las reacciones a mensajes (❤️, 👍, etc.) se muestran en WhatsApp Web como una
pequeña insignia siempre visible, pegada a la esquina inferior del bubble
(derecha para mensajes salientes, izquierda para entrantes) — no hace falta
hacer hover para verla. El pipeline de visión no la capturaba en absoluto.

Investigando el bug de ADR-anterior (tooltip de tooltip de tooltip
contaminando capturas), se confirmó además que el tooltip de hover ("N
reacciones" + quién reaccionó) es un elemento *distinto* de esta insignia
persistente — uno es texto flotante que solo aparece con el mouse encima
(y que `runner.get_bubbles()` ahora evita activamente), el otro es un ícono
pequeño siempre presente.

## Decisión

No se intenta reconocer QUÉ emoji es ni CUÁNTAS reacciones hay — solo que
*existe* una. Detección genérica por color:

1. Buscar en una ventana chica (110×22px) pegada a la esquina inferior
   externa del bubble (derecha si `sender=me`, izquierda si `sender=other`),
   empezando **estrictamente después** del borde inferior del bubble, nunca
   superpuesta con él.
2. Convertir a HSV y buscar un blob compacto (≤40×40px) de saturación alta
   (>90/255) — los emojis de reacción son vívidos; el wallpaper y el
   relleno de los bubbles no lo son.
3. Excluir explícitamente el azul de acento propio de WhatsApp (tilde de
   "leído" ✓✓, punto de progreso de reproducción de audio) por rango de hue
   — es color de UI, no de reacción, y por estar tan cerca del borde caía
   dentro de la ventana de búsqueda antes de que se ajustara el margen.
4. Si se encuentra, se recorta esa región (con padding) y se guarda como
   `<screenshot>_reaction_<id>.png` junto a los demás assets — la "mini
   imagen" queda disponible para quien quiera mirarla, sin que el pipeline
   tenga que clasificarla.
5. El bubble queda marcado `has_reaction: true` en el JSON.

## Por qué no clasificar el emoji

Reconocer específicamente qué emoji es (además de solo detectar que hay
uno) requeriría un clasificador entrenado o comparación contra un set de
íconos de referencia — mucho más trabajo para un beneficio que el usuario
explícitamente no pidió ("por ahora no vamos a distinguir entre emojis ni
cuántos son"). La mini imagen guardada ya le permite a un humano (o un
paso posterior) ver de qué reacción se trata sin que el pipeline tenga que
resolverlo.

## Iteración de calibración

La primera versión tenía falsos positivos reales, todos por buscar
demasiado cerca o demasiado lejos del borde del bubble:

- Ventana empezando 8px *antes* del borde → capturaba el tilde ✓✓ y el
  punto de progreso de audio (ambos dentro del bubble). Corregido:
  empezar 2px *después* del borde, nunca antes.
- Ventana de 40px de alto → en bubbles apilados con poco espacio, la
  ventana del bubble de arriba alcanzaba la insignia real del bubble de
  abajo. Corregido: 22px, suficiente para la insignia real (que empieza
  ~2px después del borde) sin alcanzar el siguiente bubble.

Dos casos de corpus preexistentes (`lurgo_000`, `lurgo_002`, con
contaminación de tooltip de antes de esta sesión) resultaron tener
reacciones reales no anotadas — se corrigió su `expected.json` en vez de
suprimir la detección.

## Consecuencias

- `corpus_utils.evaluate_case` ahora también mide `has_reaction_acc`
  (umbral 0.90 por defecto, overrideable por caso).
- `scripts/make_corpus_case.py` serializa `has_reaction` al crear un caso
  nuevo.
- Ver también ADR-009 (nunca borrar sesiones) y el fix de
  `runner.get_bubbles()` que estaciona el mouse antes de cada captura —
  ambos previenen que el tooltip de hover vuelva a contaminar una captura.
