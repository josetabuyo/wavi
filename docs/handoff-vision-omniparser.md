# Handoff — migración DOM→vision con OmniParser

**Fecha:** 2026-09-18
**Estado:** commit `6277f0e`, `main` al día, working tree limpio. Suite base
verde (233 passed, 19 skipped), suite de grounding verde (14/14 sobre el
corpus). ruff limpio.

**Hacia dónde va esto (para no perder el hilo entre sesiones):** el objetivo
no es solo reemplazar selectores DOM rotos uno por uno — es sacar a wavi de
la dependencia del DOM de WhatsApp Web por completo, y dejar el núcleo de
detección (YOLO + OCR + calibración de layout) suficientemente separado de
WA como para que un chat similar (Telegram, Slack) se sume escribiendo un
`ChatAppProfile` nuevo, no reescribiendo la lógica. `ChatAppProfile` (ver
abajo) ya es la costura para eso, aunque hoy solo tiene un perfil real. Esto
es más robusto a largo plazo que web scraping con Playwright sobre un DOM
que el proveedor puede cambiar sin aviso (pasó dos veces esta sesión: el
timestamp separator y el botón de "nuevo chat", ver más abajo) — vision no
le pide permiso al DOM. Ver Fase 5 de `docs/plan-mejoras.md` (§6) para el
resto de esa visión; este handoff es solo el mapa de "por dónde seguir" paso
a paso, no el destino final.

## Qué se hizo esta sesión (2026-09-18), en orden

1. **`direction` en `parse_sidebar_rows()`** — `_detect_row_direction()`
   (nuevo) detecta inbound/outbound buscando un ícono de tick (✓/✓✓) en una
   banda acotada a la izquierda del texto de preview, vía `predict_yolo()`
   **sin** Florence-2 (mantiene la ventaja de velocidad de esta función).
   Calibrado contra un screenshot real del sidebar sin filtro de búsqueda
   (primera vez que el corpus tuvo uno — los 5 casos previos eran todos
   resultados de búsqueda a 1 contacto). Tiene falsos +/- conocidos y
   documentados en su docstring (detalle en "Próximo paso recomendado").
2. **`wavi debug-open <session>`** (ADR-012, nuevo comando) — relanza el
   daemon persistente VISIBLE bajo demanda, sin arriesgar dos Chrome sobre
   el mismo perfil (se niega si el daemon ya está vivo o el perfil no está
   autenticado). Procedimiento completo en la skill `wa-session-guard`,
   sección "Debugging visibly": `stop` → `debug-open` → trabajo → `stop` →
   `connect`. Existía código muerto (`_VISIBLE_CHROME_ARGS`) anticipando
   este hueco desde antes.
3. **`_OPEN_NEW_CHAT_JS` arreglado** — con el daemon visible se inspeccionó
   el DOM real: WA reemplazó el ícono lápiz por un botón `+` sin
   `data-icon`. Fix: fallback a `aria-label="Nuevo chat"` (mismo patrón que
   `_CLICK_SEND_BTN_JS` ya usaba). `wavi list-contacts default` corre
   end-to-end de nuevo.
4. **Primer caso de corpus real para `parse_contacts_panel_rows()`**
   (`nuevo_chat_panel_000`, capturado con `debug-open` + `list-contacts`) —
   antes solo tenía cobertura sintética.

Contexto y decisiones completas de todo esto: `docs/plan-mejoras.md` §4.8.

## Qué existe hoy

**Detección (todas leen screenshots estáticos, ninguna toca la sesión en
vivo — ver "Por qué no está cableado a session.py" abajo):**

1. `locate_compose_area(screenshot_path)` → `{"input_box": {...},
   "send_button": {...}}` o `None`. Cubre `_FIND_COMPOSE_INPUT_JS` /
   `_CHECK_COMPOSE_EMPTY_JS` / `_CLICK_SEND_BTN_JS`.
2. `parse_sidebar_rows(screenshot_path)` → lista de
   `{"bbox", "text", "name", "last_message", "timestamp", "direction"}` o
   `None`. Cubre `_EXTRACT_SIDEBAR_UPDATES_JS`. `direction` vía
   `_detect_row_direction()` — best-effort, no verdad de referencia (ver
   docstring).
3. `parse_contacts_panel_rows(screenshot_path)` → lista de `{"bbox",
   "name", "subtitle"}` o `None`. Cubre `_EXTRACT_CONTACTS_JS` /
   `_EXTRACT_VISIBLE_CONTACTS_JS`. Comparte crop + clustering de filas con
   `parse_sidebar_rows` (`_ocr_cell_rows()`), solo cambia el split por fila.

**Tooling operativo:**

- `wavi debug-open <session>` (ADR-012) — daemon visible bajo demanda para
  DOM/vision debugging, ver arriba.

**Por qué no está cableado a `session.py`:** session.py maneja la sesión de
WA autenticada en vivo — tocar sus rutas de click/type real es mayor riesgo
y deliberadamente el último paso (#4 de "Después de esto" abajo), no algo a
hacer de pasada. Ver skill `wa-session-guard` antes de tocar `session.py`.

**Las tres funciones de detección aceptan `profile: ChatAppProfile =
WHATSAPP_WEB` opcional** — agrupa las constantes específicas de WA Web
(ancho de sidebar, regex de timestamp, umbrales, banda de ícono de
dirección) para que sumar otro chat después sea escribir un `ChatAppProfile`
nuevo, no reescribir la lógica de detección. Hoy `WHATSAPP_WEB` es el único
perfil real — es la costura, no la generalización en sí (ver Fase 5 de
`docs/plan-mejoras.md`).

## Próximo paso recomendado (el más chico, más obvio)

Mismo patrón que ya funcionó dos veces esta sesión, aplicado al resto de
señales de íconos rotas/pendientes: `_CLICK_SCROLL_BOTTOM_BTN_JS`,
`_CLOSE_NEW_CHAT_JS`, `_CLEAR_SIDEBAR_SEARCH_JS` (ver tabla abajo).
Procedimiento: `wavi stop` → `wavi debug-open` → inspeccionar el DOM en vivo
para encontrar/confirmar el selector real → arreglarlo (o, si no hay más
anclaje textual/DOM disponible, ahí es donde empieza a justificarse una
detección de ícono vision-first en vez de un fix DOM) → capturar screenshot
para corpus si aplica → `wavi stop` → `wavi connect` (vuelve a headless).

Alternativa igual de chica: mejorar la precisión de `_detect_row_direction()`
— tiene falsos positivos (ícono de adjunto antes de "Foto" en mensajes
entrantes, indistinguible de un tick sin captioning; filtrar por
tamaño/aspect-ratio del box detectado ayudaría) y un falso negativo conocido
(EasyOCR a veces lee el tick como texto suelto dentro de la línea de
preview, ej. `"✓✓ Jll18 DE 21"` → `"V/ JII18 DE 21"`; buscar ese patrón
además de la detección de ícono ayudaría). No bloqueante hoy — nada consume
`direction` todavía.

## Estado completo del inventario DOM (`wavi/session.py` líneas ~76-108)

De las 16 señales documentadas ahí, este es el estado real a 2026-09-18:

| Señal DOM | Estado |
|---|---|
| `_FIND_COMPOSE_INPUT_JS` / `_CHECK_COMPOSE_EMPTY_JS` / `_CLICK_SEND_BTN_JS` | ✅ `locate_compose_area()` |
| `_EXTRACT_SIDEBAR_UPDATES_JS` | ✅ `parse_sidebar_rows()`, incluido `direction` |
| `_EXTRACT_CONTACTS_JS` / `_EXTRACT_VISIBLE_CONTACTS_JS` | ✅ `parse_contacts_panel_rows()`, validado contra corpus real |
| `_FETCH_BLOB_JS` / `_DRAIN_JS` | N/A — API de browser pura, nunca necesita visión |
| `direction` (tick ✓/✓✓ en sidebar) | ✅ `_detect_row_direction()` (YOLO sin captioning) — falsos +/- conocidos y documentados |
| `_OPEN_NEW_CHAT_JS` | ✅ Arreglado (fallback `aria-label`, vía `wavi debug-open`) |
| `_CLICK_SCROLL_BOTTOM_BTN_JS` | ❌ Pendiente — ícono, sin fallback |
| `_CLOSE_NEW_CHAT_JS` | ❌ Pendiente — ícono |
| `_CLEAR_SIDEBAR_SEARCH_JS` | ❌ Pendiente — ícono (ya tiene fallback no-visual: click + Escape) |
| `_GET_VISIBLE_MSG_IDS_JS` | ⚠️ Ya tiene fallback OCR pre-existente en `runner.get()` (no de esta migración) |
| Scroll state/control (`_CHAT_SCROLL_JS`, `_SCROLL_UP/DOWN_JS`, `_CONTACTS_SCROLL_STATE_JS`, `_SCROLL_CONTACTS_DOWN_JS`) | N/A — solo control de scroll |

**En criollo:** lo que queda son señales de **íconos** sin texto que las
identifique — antes de asumir que hace falta detección vision (YOLO), probar
primero si `wavi debug-open` revela un anclaje DOM más simple (como pasó con
`_OPEN_NEW_CHAT_JS`, que terminó siendo un `aria-label`, no vision). Vision
es para cuando **no** hay ningún anclaje textual/DOM que confiar — no el
primer recurso.

## Después de esto, en orden sugerido (ver `docs/plan-mejoras.md` §4.8 para el resto)

1. Resto de señales de íconos (`_CLICK_SCROLL_BOTTOM_BTN_JS`,
   `_CLOSE_NEW_CHAT_JS`, `_CLEAR_SIDEBAR_SEARCH_JS`) — ver "Próximo paso
   recomendado" arriba.
2. Cablear `locate_compose_area()` + `parse_sidebar_rows()` +
   `parse_contacts_panel_rows()` a `session.py` como fallback real detrás de
   un flag — con pruebas contra una sesión de staging antes de default-on.
   Primera vez que esto toca código de sesión en vivo.
3. Evaluar sumar un VLM (Qwen-VL u otro) como capa de *razonamiento* sobre lo
   que OmniParser detecta (§4.6 de plan-mejoras.md) — mantiene la filosofía
   de wavi como harness: vision aporta los "ojos", el agente que invoca wavi
   sigue siendo el "cerebro".
4. Generalización real a un segundo chat (Telegram/Slack) — recién tiene
   sentido después de que `session.py` dependa de vision de verdad (paso 2),
   no antes: hoy `ChatAppProfile` es la costura, pero generalizar el núcleo
   de detección sin un segundo caso de uso real sería diseñar a ciegas.
5. Optimización pendiente, no bloqueante: `parse_screen()` (usado por
   `locate_compose_area`) sigue corriendo YOLO en CPU — solo el captioning de
   Florence-2 se movió a MPS. Si el detector de íconos se vuelve el cuello de
   botella, ahí hay margen.

## Gotchas para no repetir investigación

Todo esto ya está documentado en los docstrings de
`wavi/_vendor/omniparser_utils.py` y `wavi/vision_grounding.py`, pero el
resumen rápido:

- `transformers` debe ser **exactamente** `4.49.0` — versiones ≥5 rompen el
  código custom de Florence-2.
- La carpeta de pesos del captioner debe llamarse literalmente
  `icon_caption_florence` (no `icon_caption`) — el código de OmniParser
  elige la rama de generación correcta buscando el string "florence" en el
  path.
- El bug de MPS (`RuntimeError` de dtype float16/float32) es un bug real de
  upstream (nunca casteaban los inputs a float16 fuera de
  `device.type=='cuda'`), ya arreglado acá — no hace falta forzar CPU.
- Pesos: `make omniparser-weights` (~1.5GB, gitignorados). Extra opcional:
  `uv sync --extra vision-omniparser`.
- **Licencia:** el detector de íconos (YOLO) es AGPLv3 con cláusula de uso
  en red. Bien para wavi como CLI local. Revisar de nuevo antes de exponer
  esto vía `wavi/server.py` o `wavi/qr_server.py` como servicio a terceros.
- `wavi status <session>` **no es garantizado de solo lectura** — si no hay
  daemon corriendo, lanza Chrome headless como fallback. Para un dato
  puramente informativo (qué sesiones existen), leer
  `data/sessions/aliases.json` en vez de correr `status`.
- Para ver la sesión en vivo (DOM roto, debug, capturar un screenshot que
  ningún comando de solo lectura da hoy): `wavi debug-open`, nunca abrir
  Chrome visible a mano por fuera de ese comando. Ver ADR-012 y la sección
  "Debugging visibly" de la skill `wa-session-guard`.

## Cómo retomar

```bash
cd /Users/josetabuyo/Development/wavi
git log --oneline -5                 # confirmar que seguís en 6277f0e o más nuevo
make corpus-grounding                # confirmar que el corpus sigue verde
uv run wavi status default           # confirmar que la sesión real sigue autenticada
```

Leer `docs/plan-mejoras.md` §4.8 completo antes de tocar nada — tiene el
contexto de negocio (por qué), este archivo tiene el mapa (qué sigue).
