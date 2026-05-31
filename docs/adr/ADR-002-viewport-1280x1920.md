# ADR-002: Viewport 1280×1920 con DPR=1 forzado

**Estado:** Aceptado  
**Fecha:** 2026-05-30  
**Relacionado:** ADR-001 (navigate_to_contact sin locators)

## Contexto

El pipeline de visión captura screenshots de WhatsApp Web y los analiza para detectar
burbujas. Cuantos más mensajes quepan en un screenshot, menos iteraciones de scroll
necesita `full-sync-enhanced` para capturar el historial completo. La resolución del
screenshot determina directamente la cantidad de mensajes capturados por pantalla.

En macOS con pantalla Retina (DPR=2), Chrome headless sin configuración explícita
produce screenshots de ~876px de alto (limitado por la altura física de la pantalla
dividida por DPR), en lugar de los 1920px que necesitamos.

## Decisión

1. **WINDOW_W = 1280, WINDOW_H = 1920** — constantes en `session.py`, fuente de verdad
   para todo el sistema.

2. **`--force-device-scale-factor=1`** en los args de Chrome (tanto `wavi connect`
   como el fallback en `WASession.connect()`). Fuerza DPR=1 para que
   `--window-size=1280,1920` mapee directamente a 1280×1920 píxeles CSS. Sin este
   flag, en Mac Retina el viewport efectivo es ~640×960 CSS (DPR=2 divide el window-size).

3. **`set_viewport_size(WINDOW_W, WINDOW_H)` solo antes de la primera carga de WA**
   (cuando la página está en `about:blank`). NO se llama en reconexiones porque
   provoca pantalla blanca en WA Web ya cargado (confirmado, commit a092e41).
   Con `--force-device-scale-factor=1`, el viewport de Chrome es el correcto
   sin necesitar emulación de Playwright en reconexiones.

4. **WINDOW_W = 1280 es la base calibrada de la fórmula del sidebar** en `vision.py`:
   `sidebar_x = screenshot_w * (SIDEBAR_PX / WINDOW_W)`. Esta fórmula escala
   correctamente con DPR (screenshot_w = WINDOW_W * DPR). No cambiar WINDOW_W
   sin recalibrar SIDEBAR_PX.

## Consecuencias

- Screenshots de 1280×1920 px consistentes entre ejecuciones y reconexiones.
- ~10–12 burbujas visibles por screenshot (vs ~4 con viewport pequeño).
- El sidebar cropping formula en vision.py sigue siendo válida para DPR=1 y DPR=2.
- `--force-device-scale-factor=1` debe estar en TODOS los puntos de lanzamiento
  de Chrome (CLI `connect` y fallback de `WASession.connect()`). Un punto que lo
  omita produce imágenes "enanas" sin error visible — regresión silenciosa.

## Tests de regresión

`tests/test_session.py::TestViewportRegression` cubre:
- WINDOW_W == 1280, WINDOW_H == 1920
- `--force-device-scale-factor=1` presente en args de launch (CLI y fallback)
- `--window-size=1280,1920` presente en args de launch
- Screenshot dimensions verificados contra WINDOW_W × WINDOW_H

Si alguno de estos tests falla, la imagen de debug tendrá menos mensajes de lo
esperado y la captura de historial necesitará más iteraciones de scroll.
