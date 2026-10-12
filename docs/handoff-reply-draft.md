# Handoff — reply, borradores y orden de fechas

**Fecha:** 2026-10-09
**Versión:** v0.7.0. Suite verde (309 passed, 26 skipped), ruff limpio.
**Antes:** [handoff-media-edit-send.md](handoff-media-edit-send.md) (v0.6.0).

---

## Qué se hizo

| Commit | Qué |
|---|---|
| `004ef56` | `wavi reply [session] <chat> <fragmento> <texto> [--from REMITENTE] [--index N]` — responde citando un mensaje (propio o ajeno) |
| `9d006bc` | Fechas numéricas en el orden de la sesión (día-primero / mes-primero) |
| `3df150f` | `connect()` no abre ni mata nada si la carpeta de la sesión no existe |
| `3df5a30` | `wavi draft show\|clear [session] <chat>` y `wavi send --discard-draft` (pedido de DataLake) |
| `9788011` | La búsqueda de contacto solo tipea con el foco en el buscador (bug de DataLake) |

**reply:** `_locate_message()` elige un mensaje entre las filas de `_CHAT_MESSAGES_JS` (lo comparte
con `edit`). Hover → menú del mensaje → *Responder* → el panel de cita sobre la caja tiene que
mostrar ese mensaje o no se envía nada (Escape, sin cita colgada) → `send_message`. Después relee:
el último mensaje propio tiene que tener ese cuerpo y esa cita (`verified`, exit 2 si no).
Validado en vivo en el chat propio. Respondiendo a un mensaje ajeno: solo con tests (falta un chat
de prueba con un tercero, José lo va a indicar).

Descubierto en vivo y corregido de paso:
- La etiqueta oculta `Tú:` está solo en algunos mensajes propios (no en todos los de una racha):
  `edit` no veía esos mensajes. Ahora "propio" = tiene ticks de entrega (`Leído`, `Entregado`, …).
- En una respuesta, el primer `selectable-text` es la cita; el cuerpo es el otro
  (`[data-testid="quoted-message"]` separa la cita).

**Fechas:** `vision.infer_day_first(wa_lang, muestras)`: una fecha que solo se lee de una forma
(25/10) manda; si no, el idioma de WA (`<html lang>`): `en`/`en-US` → mes-primero, el resto →
día-primero. **No usar `navigator.language`:** dice `en-US` con WA en español (visto en vivo).
`WASession.detect_date_order()` corre al abrir cada chat y fija el orden para el proceso
(`vision.set_date_order`); lo usan las píldoras de día, `data-pre-plain-text` y el visor de `media`.

**Sesión inexistente:** sin carpeta no hay `.cdp_port` → `CDP_PORT` (9222), que puede ser el
daemon de otra sesión; el fallback de `connect()` lo mataba (`_kill_port`) y abría un perfil vacío.
Pasó de verdad el 2026-10-08 con un path relativo equivocado. Ahora falla con un error claro.
Se borraron los alias `mateo` y `pulpo-bot`: apuntaban a sesiones que ya no existen en esta Mac.

**Borradores:** `send` se niega si la caja tiene texto, y con Chrome headless nadie lo podía borrar.
`draft clear` = click en la caja, foco confirmado, Cmd+A + Delete, verifica vacío; sin reload ni
storage. El error de `send` ahora muestra el borrador y cómo salir.

**Búsqueda que tipeaba en el chat abierto:** la guarda del 03/10 solo chequeaba que el foco *no*
estuviera en `#main`. Con un Chrome recién arrancado (daemon caído → fallback por comando), WA
movía el foco a la caja del chat abierto entre el click y el tipeo: "DATA LAKE - Técnico" quedó en
Gerencia (09/10 ~14:40). Ahora el foco tiene que estar *en* el input del buscador (dos chequeos) y
después se compara la caja del chat abierto: si se filtró y estaba vacía se limpia, si había un
borrador no se toca; en ambos casos falla.

### Incidentes de sesión de esta tanda
- 2026-10-08: un script con path relativo equivocado mató el daemon de `default` (→ fix `3df150f`).
- 2026-10-09: el daemon de la noche anterior ya no estaba; uno arrancado por fallback quedó
  colgado en el splash de WA (progreso 0 por 5+ min, Chrome arm64, sin QR). `wavi stop` +
  `wavi connect default` lo restauró sin QR (daemon headless en 9200).

---

## Migración a visión de edit/reply (2026-10-12, v0.8.0)

`edit` y `reply` ya no eligen el mensaje por DOM:

- `vision.read_message_bubbles(screenshot)` → por burbuja: propio/ajeno, remitente, cuerpo, cita,
  hora y punto de click. La **cita** se separa por su barra vertical de color a la izquierda
  (2–8 px de ancho, saturada, con fondo liso al costado; medida en vivo: `(27,135,85)`). El
  **remitente** en grupos es la primera línea con tinta de color (WA pinta los nombres; el texto
  es casi negro `#111b21`, que tiene saturación nominal alta: solo cuentan píxeles no oscuros) y
  se hereda a lo largo de la racha de burbujas del mismo remitente.
- `WASession._find_message()` busca en pantalla y sube hasta `MESSAGE_SCREENS` (4) pantallas.
- El menú se abre con **click derecho** sobre el cuerpo y la opción se encuentra por **OCR**
  (`vision.find_menu_item`).
- `edit --fragment` reemplaza sobre el texto **prellenado del editor** (el mensaje exacto), nunca
  sobre el OCR; si el editor no contiene MATCH, se abrió otro mensaje → Escape, nada cambia.
- La cita y la relectura final se comparan con `_roughly_contains` (tolera errores de OCR).
- Fallback DOM temporal solo si no hay helper OCR (`vision.vision_available()`).
- El wheel ahora incluye `swift/ocr_vision.swift` (`wavi/_ocr/`): antes una instalación desde
  PyPI no tenía OCR en absoluto (tampoco `wavi get`). Necesita `swift` (Xcode CLT) en el PATH.

Validado en vivo (chat propio): `reply` citó el mensaje correcto aunque el texto aparecía también
como cita en otras dos respuestas; `edit --fragment` cambió solo el fragmento; un mensaje dos
pantallas arriba se encontró subiendo 2 pantallas. Costo: ~20–40 s por comando (OCR ~9 s/pantalla).

Observado: el primer click en un resultado de búsqueda a veces no abre el chat ("header shows
'DATA LAKE - Tecnico'") y el reintento existente lo resuelve; pasó 2 veces en esta tanda.

## Pendiente

1. **Vision-first, lo que queda:** `media` (encontrar la burbuja de media y el visor), y las
   relecturas de verificación por DOM de `edit`/`reply` (hoy son un chequeo cruzado independiente).
2. **`media` no baja documentos/PDF** (no pasan por el visor; hace falta el botón de descarga de la
   burbuja + `expect_download`/`Browser.setDownloadBehavior`, explorar en vivo primero).
3. **Remitente en `media`** = nombre corto del visor ("Matias"); ahora se puede mapear con el
   remitente que da `read_message_bubbles` (nombre completo coloreado).
4. **`reply` a un mensaje ajeno** sin validar en vivo (falta chat de prueba).
5. `server.py` no expone `reply`/`draft`, y `_resolve` lee el `.default` viejo en vez de `aliases.json`.
