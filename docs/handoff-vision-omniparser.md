# Handoff — migración DOM→vision con OmniParser

**Fecha:** 2026-09-18
**Estado:** **v0.5.0 publicado en PyPI** (commit `b848e7f`, `main` al día).
Desde v0.4.0 (`38ed2be`) se sumaron, en orden: split de campos de
`parse_sidebar_rows()` (`4bee0d4`), `parse_contacts_panel_rows()` (`991f286`),
fix de timestamp validado contra sesión real (`e6181b4`), refactor de
portabilidad `ChatAppProfile` (`9dab6c8`), bump a v0.5.0 (`b848e7f`). Suite
base verde (227 passed, 15 skipped), suite de grounding verde (10/10 sobre el
corpus). Todo commiteado, pusheado y publicado — nada pendiente en el working
tree al cierre de esta sesión.

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

**Sobre el tamaño de `data/` (llamó la atención de System@ba-mac):** llegó a
~17GB por perfiles de Chrome viejos/rotos (pulpo-bot en 4 variantes, mateo
desconectada, ~16 carpetas `_tmp_*` de testing) — **limpiado el mismo día**,
con confirmación explícita del usuario ítem por ítem (`wa-session-guard`).
Quedó solo `data/sessions/22793010001200` (`default`, ~940MB). `weights/`
(~1GB, pesos de OmniParser) y `output/` (screenshots/historiales de pruebas)
sin tocar. Política del proyecto (`docs/adr/ADR-009-never-delete-session-profiles.md`):
wavi mismo nunca borra un perfil automáticamente (solo archiva); borrar a
mano, con confirmación explícita, sigue siendo decisión del usuario — eso es
lo que pasó acá. Si se reconectan `pulpo-bot` o `mateo` más adelante, piden
QR nuevo (perfil desde cero, esperado).

**Gotcha nuevo:** `wavi status <session>` **no es garantizado de solo
lectura** — si no hay daemon corriendo para esa sesión, lanza Chrome headless
como fallback para poder chequear el auth. Confirmado en vivo: correr `status`
sobre dos sesiones inactivas las encendió sin querer. Si solo hace falta un
dato informativo (qué sesiones existen), leer `data/sessions/aliases.json` en
vez de correr `status` sobre sesiones que no se van a usar.

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

## Estado completo del inventario DOM (`wavi/session.py` líneas ~76-108)

De las 16 señales documentadas ahí, este es el estado real a 2026-09-18:

| Señal DOM | Estado |
|---|---|
| `_FIND_COMPOSE_INPUT_JS` / `_CHECK_COMPOSE_EMPTY_JS` / `_CLICK_SEND_BTN_JS` | ✅ `locate_compose_area()` |
| `_EXTRACT_SIDEBAR_UPDATES_JS` | ✅ `parse_sidebar_rows()` — salvo `direction` |
| `_EXTRACT_CONTACTS_JS` / `_EXTRACT_VISIBLE_CONTACTS_JS` | ✅ `parse_contacts_panel_rows()` — sin caso de corpus real |
| `_FETCH_BLOB_JS` / `_DRAIN_JS` | N/A — API de browser pura, nunca necesita visión |
| `direction` (tick ✓/✓✓ en sidebar) | ❌ Pendiente — necesita detección de íconos (YOLO sin captioning) |
| `_CLICK_SCROLL_BOTTOM_BTN_JS` | ❌ Pendiente — ícono, sin fallback |
| `_OPEN_NEW_CHAT_JS` | ❌ Pendiente — **confirmado roto en la sesión real** (WA cambió el ícono) |
| `_CLOSE_NEW_CHAT_JS` | ❌ Pendiente — ícono |
| `_CLEAR_SIDEBAR_SEARCH_JS` | ❌ Pendiente — ícono (ya tiene fallback no-visual: click + Escape) |
| `_GET_VISIBLE_MSG_IDS_JS` | ⚠️ Ya tiene fallback OCR pre-existente en `runner.get()` (no de esta migración) |
| Scroll state/control (`_CHAT_SCROLL_JS`, `_SCROLL_UP/DOWN_JS`, `_CONTACTS_SCROLL_STATE_JS`, `_SCROLL_CONTACTS_DOWN_JS`) | N/A — solo control de scroll |

**En criollo:** todo lo que queda son señales de **íconos**, ninguna es
texto — no alcanza con el OCR usado hasta ahora, necesitan detección de
íconos vía YOLO (sin el captioning de Florence-2, para no perder la ventaja
de velocidad). Ese es el próximo bloque de trabajo real, no una simple
continuación del patrón OCR-only usado hasta acá.

## Después de eso, en orden sugerido (ver plan-mejoras.md §4.8 para el resto)

1. `direction` vía detección de íconos — el corte más chico de los que
   quedan (la fila ya está resuelta, solo falta el tick).
2. Sembrar un caso de corpus real con el panel "Nuevo chat" abierto.
3. Resto de señales de íconos (`_CLICK_SCROLL_BOTTOM_BTN_JS`,
   `_OPEN_NEW_CHAT_JS` — priorizar, ya confirmado roto —, `_CLOSE_NEW_CHAT_JS`,
   `_CLEAR_SIDEBAR_SEARCH_JS`) — mismo patrón: detección sobre corpus estático
   primero, cableado después, por separado.
4. Cablear `locate_compose_area()` + `parse_sidebar_rows()` +
   `parse_contacts_panel_rows()` a `session.py` como fallback real detrás de
   un flag — con pruebas contra una sesión de staging antes de default-on.
   Primera vez que esto toca código de sesión en vivo.
5. Evaluar sumar un VLM (Qwen-VL u otro) como capa de *razonamiento* sobre lo
   que OmniParser detecta (§4.6 de plan-mejoras.md) — mantiene la filosofía de
   wavi como harness: vision aporta los "ojos", el agente que invoca wavi sigue
   siendo el "cerebro".
6. Optimización pendiente, no bloqueante: `parse_screen()` (usado por
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
git log --oneline -5                 # confirmar que seguís en b848e7f o más nuevo
make corpus-grounding                # confirmar que el corpus sigue verde
uv run wavi status default           # confirmar que la sesión real sigue autenticada
```

Leer `docs/plan-mejoras.md` §4.8 completo antes de tocar nada — tiene el
contexto de negocio (por qué), este archivo tiene el mapa (qué sigue).
