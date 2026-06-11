# ADR-004: Dedup por ancla DOM con fallback OCR

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

Las regiones de scroll se solapan ~15%: un mensaje visible al fondo del frame N
reaparece arriba del frame N+1. El texto OCR del mismo mensaje puede variar entre
capturas (ruido, puntuación), así que una clave de contenido sola no alcanza.

## Decisión

Clave primaria de dedup = `dom_id` (atributo `data-id` de WA, inmutable por
mensaje). Fallback cuando no se pudo asignar dom_id (elemento fuera de pantalla):
clave OCR = `(sender, msg_type, text[:80], timestamp)`.

## Consecuencias

- Cero duplicados aun con OCR imperfecto.
- Dependencia residual del DOM para corrección — el plan (Fase 3) agrega una
  tercera clave por hash perceptual (dhash) del crop para eliminar esa dependencia.
