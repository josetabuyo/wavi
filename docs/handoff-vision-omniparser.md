# Handoff — migración DOM→vision con OmniParser

**Fecha:** 2026-09-18
**Estado:** v0.4.0 publicado (PyPI + git push a `main`, commit `38ed2be`), más
el split de campos de `parse_sidebar_rows()` (commit `4bee0d4`),
`parse_contacts_panel_rows()` (commit `991f286`), un fix de timestamp
encontrado validando contra una sesión real (commit `e6181b4`), y un refactor
de portabilidad (`ChatAppProfile`, ver abajo — sin commitear todavía al cierre
de esta nota). Suite base verde (227 passed, 15 skipped), suite de grounding
verde (10/10 sobre el corpus).

**Sesión real conectada:** `wavi qr default` (22793010001200) escaneado y
autenticado este mismo día — primera vez que este trabajo se validó contra
WhatsApp Web real, no solo el corpus estático. Validación de solo lectura
(`status`/`queue`/`events`/`check-updates`/`get` — nunca `send`, nunca clicks
manuales sobre la tab). Encontró y confirmó:
1. Un bug real en `_split_row_fields()`: el regex de timestamp solo aceptaba
   separador `:`, pero esta sesión renderiza con `.` (`"11.27 a. m."`) y a
   veces sin sufijo am/pm. Arreglado (regex ampliado + fallback posicional
   para formas no enumerables como "Ayer"/fechas). Ver plan-mejoras.md §4.8.
2. `locate_compose_area()` correcto contra un screenshot real de chat abierto
   (`input_box` sobre "Escribe un mensaje", `send_button` sobre el ícono mic).
3. `_OPEN_NEW_CHAT_JS` (DOM) está roto en esta sesión — WA cambió el ícono de
   "nuevo chat". `wavi list-contacts` falla en vivo. Confirma en la práctica
   por qué existe esta migración.

**Sobre el tamaño de `data/` (~17GB, llamó la atención de System@ba-mac):**
esperado, no es basura — `data/sessions/` guarda perfiles de Chrome por sesión
de WA (varios GB cada uno, IndexedDB/caché de WA incluido) más variantes
archivadas nunca borradas por diseño (ver `docs/adr/ADR-009-never-delete-session-profiles.md`
— archivar y renombrar, jamás borrar, porque una sesión perdida cuesta un
nuevo QR scan penalizado por WA). `weights/` son los ~1GB de pesos de
OmniParser. `output/` son screenshots/historiales de pruebas acumulados. Hay
~15 carpetas `_tmp_*` de ~80MB cada una en `data/sessions/` que parecen
perfiles de Chrome de desarrollo/testing viejos — candidatas a revisar en
algún momento, pero **no tocadas** (el usuario pidió explícitamente no borrar
nada en esta sesión).

## Dónde está la sustancia

- **Contexto y decisiones completas:** `docs/plan-mejoras.md` §4.8 — leer eso
  primero, este archivo es solo el mapa de "por dónde seguir".
- **Código:** `wavi/vision_grounding.py` (API pública) + `wavi/_vendor/` (OmniParser
  vendorizado y recortado, con 3 fixes de compatibilidad documentados en el
  docstring de `omniparser_utils.py`).
- **Tests:** `tests/test_vision_grounding.py` (unitarios, sin gate) +
  `tests/test_corpus_grounding.py`, gateado por `WAVI_CORPUS=1` (correr con
  `make corpus-grounding`).

## Qué existe hoy (tres funciones, todas solo detección sobre screenshots estáticos)

1. `locate_compose_area(screenshot_path)` → `{"input_box": {...}, "send_button": {...}}`
   o `None`. Cubre el fallback de `_FIND_COMPOSE_INPUT_JS` / `_CHECK_COMPOSE_EMPTY_JS`
   / `_CLICK_SEND_BTN_JS` (tabla de inventario DOM en `wavi/session.py` líneas ~76-108).
2. `parse_sidebar_rows(screenshot_path)` → lista de filas
   `{"bbox": {...}, "text": str, "name": str, "last_message": str, "timestamp": str,
   "direction": None}` o `None`. Cubre el fallback de `_EXTRACT_SIDEBAR_UPDATES_JS`.
   Ya separa name/last_message/timestamp (helper `_split_row_fields()` en
   `vision_grounding.py`). `direction` queda siempre `None` — ver abajo.
3. `parse_contacts_panel_rows(screenshot_path)` → lista de filas
   `{"bbox": {...}, "name": str, "subtitle": str}` o `None`. Cubre el fallback
   de `_EXTRACT_CONTACTS_JS` / `_EXTRACT_VISIBLE_CONTACTS_JS` (panel "Nuevo
   chat"). Comparte con `parse_sidebar_rows` el crop de columna izquierda y el
   clustering de filas (extraídos a `_ocr_cell_rows()`); solo cambia el split
   por fila (`_split_contact_fields()`: sin timestamp, primera línea = nombre
   completo, resto = subtítulo). **Sin caso de corpus real todavía** —
   validado solo con tests unitarios sintéticos (`tests/test_vision_grounding.py`).
   Ver "Pendiente" abajo.

**Ninguna de las tres está cableada a `session.py`.** Es deliberado — session.py
maneja la sesión de WA autenticada en vivo, y tocarla es mayor riesgo. Ver
`wa-session-guard` skill antes de tocar `session.py`.

**Las tres aceptan un `profile: ChatAppProfile = WHATSAPP_WEB` opcional**
(nuevo, 2026-09-18) — agrupa las constantes específicas de WA Web (ancho de
sidebar, regex de timestamp, umbrales) para que agregar otro chat después sea
escribir un `ChatAppProfile` nuevo, no reescribir la lógica de detección. Hoy
`WHATSAPP_WEB` es el único perfil real; esto es la costura, no la
generalización en sí (ver Fase 5 de plan-mejoras.md).

## Próximo paso recomendado (el más chico, más obvio)

Sembrar un caso de corpus real con el panel "Nuevo chat" abierto (screenshot +
`expected.json`, mismo formato que `tests/corpus/cases/`) y correr
`parse_contacts_panel_rows()` contra él, igual que se hizo para
`parse_sidebar_rows` — hoy esa función solo tiene cobertura sintética, no
validación contra OCR real de WhatsApp Web.

Alternativa igual de chica: `direction` en `parse_sidebar_rows()` — detección
de tick icons (✓/✓✓) vía `predict_yolo()` de
`wavi/_vendor/omniparser_utils.py` (boxes de YOLO sin captioning, para no
perder la ventaja de velocidad de esta función frente a
`locate_compose_area()`), acotado a la región de cada fila ya resuelta.

## Después de eso, en orden sugerido (ver plan-mejoras.md §4.8 para el resto)

1. Cablear `locate_compose_area()` + `parse_sidebar_rows()` +
   `parse_contacts_panel_rows()` a `session.py` como fallback real detrás de
   un flag — con pruebas contra una sesión de staging antes de default-on.
   Primera vez que esto toca código de sesión en vivo.
2. Resto de la tabla de inventario DOM (todos requieren detección de íconos,
   no solo OCR): scroll-bottom button, new-chat/back icons, reacciones —
   mismo patrón: detección sobre corpus estático primero, cableado después,
   por separado.
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
