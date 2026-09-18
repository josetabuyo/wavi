# Handoff — migración DOM→vision con OmniParser

**Fecha:** 2026-09-18
**Estado:** working tree con cambios sin commitear al cierre de esta sesión
(ver "Cómo retomar" para el hash exacto). Suite base verde (241 passed, 26
skipped), suite de grounding verde (15/15 sobre el corpus incluyendo 3 casos
nuevos). ruff limpio.

**Política del proyecto — leer esto antes de tocar cualquier señal DOM rota
(confirmado explícitamente por el usuario, 2026-09-18):** un fix DOM
(selector parcheado, `aria-label` de fallback, lo que sea) **nunca es la
resolución final** de una señal rota, aunque sea correcto y rápido — es, como
mucho, un puente temporal mientras el detector de visión real no existe
todavía. La resolución permanente siempre es un detector de visión en
`vision_grounding.py`, con Playwright/DOM reservados solo para lo
genuinamente genérico: clickear una coordenada, tipear texto. Nunca para
*encontrar* dónde está algo en la pantalla — eso es trabajo de vision,
siempre, no un último recurso. Pasó en la práctica el mismo día: se parchó
`_OPEN_NEW_CHAT_JS` con un fallback `aria-label` primero (rápido, correcto),
el usuario lo rechazó como solución final, y unas horas después se reemplazó
por `locate_new_chat_button()` + cableado real a `session.py` — ver abajo.
Esta es la plantilla a seguir para el resto de señales rotas/pendientes de
la tabla, no una excepción de esta vez.

**Hacia dónde va esto:** sacar a wavi de la dependencia del DOM de WhatsApp
Web por completo, y dejar el núcleo de detección (YOLO + OCR + calibración
de layout) suficientemente separado de WA como para que un chat similar
(Telegram, Slack) se sume escribiendo un `ChatAppProfile` nuevo, no
reescribiendo la lógica. Más robusto a largo plazo que web scraping con
Playwright sobre un DOM que el proveedor cambia sin aviso — pasó tres veces
solo hoy (separador de timestamp, el ícono del botón "nuevo chat", y el
propio botón mudándose de UI entre junio y septiembre 2026, ver evidencia en
"Qué se hizo" abajo). Ver Fase 5 de `docs/plan-mejoras.md` (§6) para el
resto de esa visión; este handoff es el mapa de "por dónde seguir", no el
destino final.

## Qué se hizo esta sesión (2026-09-18), en orden

1. **`direction` en `parse_sidebar_rows()`** — `_detect_row_direction()`
   detecta inbound/outbound buscando un ícono de tick (✓/✓✓) en una banda
   acotada a la izquierda del texto de preview, vía `predict_yolo()` **sin**
   Florence-2. Calibrado contra un screenshot real del sidebar sin filtro de
   búsqueda. Tiene falsos +/- conocidos y documentados en su docstring.
2. **`wavi debug-open <session>`** (ADR-012) — relanza el daemon persistente
   VISIBLE bajo demanda, sin arriesgar dos Chrome sobre el mismo perfil.
   Procedimiento completo en la skill `wa-session-guard`, sección
   "Debugging visibly": `stop` → `debug-open` → trabajo → `stop` → `connect`.
3. **`_OPEN_NEW_CHAT_JS` parcheado con `aria-label`** — puente temporal
   inicial (ver política arriba), **no** la resolución.
4. **Primer caso de corpus real para `parse_contacts_panel_rows()`**
   (`nuevo_chat_panel_000`).
5. **`locate_new_chat_button()`** (la resolución real) — detecta el botón
   "nuevo chat" por visión: el único ícono WA-verde y relleno del header del
   sidebar (logo/wordmark/menú "..." son monocromos). Detecta por presencia
   de ícono (`predict_yolo()`, sin captioning) + color de relleno promedio,
   deliberadamente no por forma/contenido — WA ya cambió el SVG de adentro
   de este botón una vez (lápiz → `+`), el verde de marca es lo que
   sobrevivió. Validado contra 7 casos reales del corpus (positivos y
   negativos) — incluye evidencia real de que el DOM cambia bajo nuestros
   pies: 4 casos de junio 2026 muestran un ícono monocromo de archivo en vez
   del `+` verde (WA rediseñó esto entre junio y septiembre), y la función
   correctamente devuelve `None` para esos, no un falso positivo.
6. **Cableado a `session.py`** — `navigate_to_new_chat()` ahora prueba
   `_click_new_chat_via_vision()` primero (screenshot → `locate_new_chat_button()`
   → `page.mouse.click()` en el centro del box) y solo cae al DOM
   (`_OPEN_NEW_CHAT_JS`) si vision no encuentra nada. Primera vez que vision
   maneja un click real sobre la sesión autenticada en vivo. Validado con
   `wavi debug-open`: `_click_new_chat_via_vision()` devolvió `True`, abrió
   el panel, se cerró bien.

Contexto y decisiones completas de todo esto: `docs/plan-mejoras.md` §4.8.

## Qué existe hoy

**Detección pura (leen screenshots estáticos, no tocan la sesión):**

1. `locate_compose_area(screenshot_path)` → `{"input_box", "send_button"}` o
   `None`. Cubre `_FIND_COMPOSE_INPUT_JS` / `_CHECK_COMPOSE_EMPTY_JS` /
   `_CLICK_SEND_BTN_JS`. **No cableada a session.py todavía.**
2. `parse_sidebar_rows(screenshot_path)` → filas con `name`/`last_message`/
   `timestamp`/`direction`. Cubre `_EXTRACT_SIDEBAR_UPDATES_JS`. **No
   cableada a session.py todavía.**
3. `parse_contacts_panel_rows(screenshot_path)` → filas con `name`/
   `subtitle`. Cubre `_EXTRACT_CONTACTS_JS` / `_EXTRACT_VISIBLE_CONTACTS_JS`.
   **No cableada a session.py todavía.**
4. `locate_new_chat_button(screenshot_path)` → `{"x","y","w","h"}` o `None`.
   Cubre `_OPEN_NEW_CHAT_JS`. **Cableada a `session.py`** —
   `WASession._click_new_chat_via_vision()`, primer caso de uso real.

**Tooling operativo:**

- `wavi debug-open <session>` (ADR-012) — daemon visible bajo demanda.

**Las cuatro funciones de detección aceptan `profile: ChatAppProfile =
WHATSAPP_WEB` opcional** — agrupa las constantes específicas de WA Web
(ancho de sidebar, regex de timestamp, banda de ícono de dirección, banda de
header, umbral de color de acento) para que sumar otro chat después sea
escribir un `ChatAppProfile` nuevo, no reescribir la lógica. Hoy
`WHATSAPP_WEB` es el único perfil real (ver Fase 5 de `docs/plan-mejoras.md`).

## Próximo paso recomendado (el más chico, más obvio)

Mismo patrón que ya funcionó de punta a punta con `_OPEN_NEW_CHAT_JS`,
aplicado a las señales de ícono que quedan: `_CLICK_SCROLL_BOTTOM_BTN_JS`,
`_CLOSE_NEW_CHAT_JS`, `_CLEAR_SIDEBAR_SEARCH_JS` (ver tabla abajo). Orden
correcto (no el que se usó la primera vez con el botón nuevo-chat):

1. `wavi stop` → `wavi debug-open` → inspeccionar la señal en vivo (para
   entender qué la identifica visualmente — color, forma, posición — no
   para buscar un selector DOM que parchear).
2. Detector de visión en `vision_grounding.py`, calibrado contra un
   screenshot real capturado en el paso 1, agregado al corpus con su
   `expected_*.json`.
3. Cablear a `session.py` con el mismo patrón de `_click_new_chat_via_vision()`
   (catch amplio en el paso de detección, fallback DOM temporal solo si hace
   falta desbloquear algo mientras tanto).
4. `wavi stop` → `wavi connect` (vuelve a headless).

Alternativa igual de chica: cablear `locate_compose_area()` y
`parse_sidebar_rows()` a `session.py` (siguen sin cablear, ver tabla
"Qué existe hoy") — mismo patrón ya probado con el botón nuevo-chat.

## Estado completo del inventario DOM (`wavi/session.py` líneas ~76-108)

De las 16 señales documentadas ahí, este es el estado real a 2026-09-18:

| Señal DOM | Estado |
|---|---|
| `_FIND_COMPOSE_INPUT_JS` / `_CHECK_COMPOSE_EMPTY_JS` / `_CLICK_SEND_BTN_JS` | ⚠️ `locate_compose_area()` existe, no cableada |
| `_EXTRACT_SIDEBAR_UPDATES_JS` | ⚠️ `parse_sidebar_rows()` existe (incl. `direction`), no cableada |
| `_EXTRACT_CONTACTS_JS` / `_EXTRACT_VISIBLE_CONTACTS_JS` | ⚠️ `parse_contacts_panel_rows()` existe, no cableada |
| `_FETCH_BLOB_JS` / `_DRAIN_JS` | N/A — API de browser pura, nunca necesita visión |
| `direction` (tick ✓/✓✓ en sidebar) | ✅ `_detect_row_direction()` — falsos +/- conocidos y documentados |
| `_OPEN_NEW_CHAT_JS` | ✅ `locate_new_chat_button()`, **cableada a session.py** — DOM queda solo como fallback |
| `_CLICK_SCROLL_BOTTOM_BTN_JS` | ❌ Pendiente — ícono, sin fallback |
| `_CLOSE_NEW_CHAT_JS` | ❌ Pendiente — ícono |
| `_CLEAR_SIDEBAR_SEARCH_JS` | ❌ Pendiente — ícono (ya tiene fallback no-visual: click + Escape) |
| `_GET_VISIBLE_MSG_IDS_JS` | ⚠️ Ya tiene fallback OCR pre-existente en `runner.get()` (no de esta migración) |
| Scroll state/control (`_CHAT_SCROLL_JS`, `_SCROLL_UP/DOWN_JS`, `_CONTACTS_SCROLL_STATE_JS`, `_SCROLL_CONTACTS_DOWN_JS`) | N/A — solo control de scroll |

**En criollo:** el DOM cambia bajo nuestros pies sin aviso — pasó con el
timestamp, pasó con el botón nuevo-chat (dos veces: cambió el ícono, y antes
de eso probablemente cambió de forma que ni sabemos). Un detector de visión
calibrado por invariantes visuales (color, forma, posición relativa) es más
estable que un selector atado a un atributo o string específico. Eso es la
regla ahora, no una vez que el DOM ya no alcance.

## Después de esto, en orden sugerido (ver `docs/plan-mejoras.md` §4.8 para el resto)

1. Resto de señales de íconos (`_CLICK_SCROLL_BOTTOM_BTN_JS`,
   `_CLOSE_NEW_CHAT_JS`, `_CLEAR_SIDEBAR_SEARCH_JS`) — ver "Próximo paso
   recomendado" arriba, mismo patrón que `locate_new_chat_button()`.
2. Cablear `locate_compose_area()` + `parse_sidebar_rows()` +
   `parse_contacts_panel_rows()` a `session.py` — mismo patrón ya probado.
3. Evaluar sumar un VLM (Qwen-VL u otro) como capa de *razonamiento* sobre lo
   que OmniParser detecta (§4.6 de plan-mejoras.md) — mantiene la filosofía
   de wavi como harness: vision aporta los "ojos", el agente que invoca wavi
   sigue siendo el "cerebro".
4. Generalización real a un segundo chat (Telegram/Slack) — recién tiene
   sentido después de que `session.py` dependa de vision de verdad para la
   mayoría de sus señales, no antes: hoy `ChatAppProfile` es la costura,
   pero generalizar el núcleo de detección sin un segundo caso de uso real
   sería diseñar a ciegas.
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
- **Headless vs. visible cambia el tema (dark/light) de WA Web** — headless
  renderiza claro por defecto (sin contexto real de macOS para
  `prefers-color-scheme`), visible toma el modo real del sistema. No afecta
  la sesión (el tema no vive en el perfil de auth), pero los detectores por
  color (`locate_new_chat_button()`, calibrado con `accent_min_green_delta`)
  están calibrados solo contra modo claro — un screenshot en dark mode
  podría descalibrarlos. Si hace falta generalizar, es un
  `ChatAppProfile`/umbral nuevo, no un rediseño.

## Cómo retomar

```bash
cd /Users/josetabuyo/Development/wavi
git log --oneline -5                 # confirmar el commit de cierre de esta sesión
make corpus-grounding                # confirmar que el corpus sigue verde
uv run wavi status default           # confirmar que la sesión real sigue autenticada
```

Leer `docs/plan-mejoras.md` §4.8 completo antes de tocar nada — tiene el
contexto de negocio (por qué) y la política vision-first explícita del
usuario. Este archivo tiene el mapa (qué sigue).
