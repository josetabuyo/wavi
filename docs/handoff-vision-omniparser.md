# Handoff — migración DOM→vision con OmniParser

**Fecha:** 2026-09-18
**Estado:** v0.4.0 publicado (PyPI + git push a `main`, commit `38ed2be`). Suite
base verde (207 passed, 15 skipped), suite de grounding verde (10/10 sobre el
corpus).

## Dónde está la sustancia

- **Contexto y decisiones completas:** `docs/plan-mejoras.md` §4.8 — leer eso
  primero, este archivo es solo el mapa de "por dónde seguir".
- **Código:** `wavi/vision_grounding.py` (API pública) + `wavi/_vendor/` (OmniParser
  vendorizado y recortado, con 3 fixes de compatibilidad documentados en el
  docstring de `omniparser_utils.py`).
- **Tests:** `tests/test_corpus_grounding.py`, gateado por `WAVI_CORPUS=1` (correr
  con `make corpus-grounding`).

## Qué existe hoy (dos funciones, ambas solo detección sobre screenshots estáticos)

1. `locate_compose_area(screenshot_path)` → `{"input_box": {...}, "send_button": {...}}`
   o `None`. Cubre el fallback de `_FIND_COMPOSE_INPUT_JS` / `_CHECK_COMPOSE_EMPTY_JS`
   / `_CLICK_SEND_BTN_JS` (tabla de inventario DOM en `wavi/session.py` líneas ~76-108).
2. `parse_sidebar_rows(screenshot_path)` → lista de filas `{"bbox": {...}, "text": str}`
   o `None`. Cubre el fallback de `_EXTRACT_SIDEBAR_UPDATES_JS`. Solo separa **filas**,
   no todavía name/last_message/timestamp/direction dentro de cada una.

**Ninguna de las dos está cableada a `session.py`.** Es deliberado — session.py
maneja la sesión de WA autenticada en vivo, y tocarla es mayor riesgo. Ver
`wa-session-guard` skill antes de tocar `session.py`.

## Próximo paso recomendado (el más chico, más obvio)

Separar campos dentro de cada fila de `parse_sidebar_rows()`: name (primera
línea, izquierda) / last_message (línea de abajo) / timestamp (texto alineado a
la derecha en la primera línea, matchea `RE_TIME` o fecha — reusar regexes de
`wavi/vision.py`) / direction (requiere detectar el tick icon ✓/✓✓ — esto sí
necesita YOLO, no alcanza con el EasyOCR-only que usa `parse_sidebar_rows` hoy,
así que hay que llamar a `parse_screen()` en vez de OCR directo, o hacer una
pasada de icon-detection acotada al sidebar).

Es un corte bajo-riesgo porque los límites de fila (la parte difícil) ya están
resueltos — esto es post-procesamiento puro de Python sobre algo que ya
funciona, sin tocar el pipeline de OmniParser.

## Después de eso, en orden sugerido (ver plan-mejoras.md §4.8 para el resto)

1. Cablear `locate_compose_area()` + `parse_sidebar_rows()` a `session.py` como
   fallback real detrás de un flag — con pruebas contra una sesión de staging
   antes de default-on. Primera vez que esto toca código de sesión en vivo.
2. Resto de la tabla de inventario DOM: scroll-bottom button, new-chat/back
   icons, reacciones, lista de contactos del panel "Nuevo chat" — mismo patrón:
   detección sobre corpus estático primero, cableado después, por separado.
3. Evaluar sumar un VLM (Qwen-VL u otro) como capa de *razonamiento* sobre lo
   que OmniParser detecta (§4.6 de plan-mejoras.md) — mantiene la filosofía de
   wavi como harness: vision aporta los "ojos", el agente que invoca wavi sigue
   siendo el "cerebro".
4. Optimización pendiente, no bloqueante: `parse_screen()` (usado por
   `locate_compose_area`) sigue corriendo YOLO en CPU — solo el captioning de
   Florence-2 se movió a MPS. Si el detector de íconos se vuelve el cuello de
   botella, ahí hay margen.

## Gotchas para no repetir investigación

Todo esto ya está documentado en los docstrings de `wavi/_vendor/omniparser_utils.py`
y `wavi/vision_grounding.py`, pero el resumen rápido:

- `transformers` debe ser **exactamente** `4.49.0` — versiones ≥5 rompen el código
  custom de Florence-2.
- La carpeta de pesos del captioner debe llamarse literalmente
  `icon_caption_florence` (no `icon_caption`) — el código de OmniParser elige la
  rama de generación correcta buscando el string "florence" en el path.
- El bug de MPS (`RuntimeError` de dtype float16/float32) es un bug real de
  upstream (nunca casteaban los inputs a float16 fuera de `device.type=='cuda'`),
  ya arreglado acá — no hace falta forzar CPU.
- Pesos: `make omniparser-weights` (~1.5GB, gitignorados). Extra opcional:
  `uv sync --extra vision-omniparser`.
- **Licencia:** el detector de íconos (YOLO) es AGPLv3 con cláusula de uso en
  red. Bien para wavi como CLI local. Revisar de nuevo antes de exponer esto
  vía `wavi/server.py` o `wavi/qr_server.py` como servicio a terceros.

## Cómo retomar

```bash
cd /Users/josetabuyo/Development/wavi
git log --oneline -5                 # confirmar que seguís en 38ed2be o más nuevo
make corpus-grounding                # confirmar que el corpus sigue verde
```

Leer `docs/plan-mejoras.md` §4.8 completo antes de tocar nada — tiene el
contexto de negocio (por qué), este archivo tiene el mapa (qué sigue).
