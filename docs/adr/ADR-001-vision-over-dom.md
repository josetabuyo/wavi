# ADR-001: Visión sobre DOM para extracción de contenido

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

El DOM de WhatsApp Web está minificado y ofuscado, y cambia con cada deploy. Los
selectores CSS y APIs JS que funcionan hoy se rompen silenciosamente mañana. El
rendering visual, en cambio, está anclado a la percepción humana: las burbujas se
ven como burbujas, los timestamps como timestamps — eso casi no cambia entre
versiones de WA.

## Decisión

Extraer el contenido de mensajes vía screenshots + OCR (pipeline de visión), no
vía selectores DOM. La interacción usa coordenadas físicas y eventos de teclado,
no `page.locator()`.

El DOM se usa solo como **acelerador** donde no hay alternativa razonable hoy:
coordenadas de elementos dinámicos (compose box), estado de scroll, `data-id`
para dedup, y captura de blobs de audio vía JS. Cada señal DOM tiene su fallback
visual documentado en el inventario de `session.py`.

## Consecuencias

- Más lento que parsear DOM, pero resiliente a cualquier cambio no-visual de WA.
- Requiere calibración de geometría/colores (ver ADR-002 y plan-mejoras Fase 2).
- La captura de audio (bytes .ogg) es la única capacidad sin camino visual posible.
