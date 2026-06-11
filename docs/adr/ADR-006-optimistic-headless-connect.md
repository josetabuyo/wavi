# ADR-006: Connect headless optimista

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

Una vez autenticada, la sesión vive en el user-data-dir de Chrome y headless la
restaura silenciosamente. Abrir una ventana visible sin necesidad es disruptivo
y más lento.

## Decisión

`wavi connect` siempre intenta headless primero. Solo si hace falta QR, lo
captura igualmente en headless y escribe `data/qr.html` (QR en base64 + countdown
de 60s) para escanear desde el browser del usuario — nunca se abre una ventana
de Chrome visible. La expiración del QR se detecta por cambio del atributo
`data-ref` (fallback: timer de 65s).

## Consecuencias

- Cero ventanas visibles en el flujo completo.
- Tras el escaneo, la carpeta de sesión se renombra al número de teléfono
  detectado y el alias `.default` apunta a ella.
