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

## Pendiente

1. **Vision-first:** `media`, `edit` y `reply` encuentran mensajes por DOM (inventario en la tabla
   de `session.py`). `edit`/`reply` comparten `_locate_message()`: migrar esa entrada a burbujas de
   OCR de `vision.py` cubre los dos.
2. **`media` no baja documentos/PDF** (no pasan por el visor; hace falta el botón de descarga de la
   burbuja + `expect_download`/`Browser.setDownloadBehavior`, explorar en vivo primero).
3. **Remitente en `media`** = nombre corto del visor ("Matias"); se podría mapear al completo con los
   remitentes de `data-pre-plain-text` del chat (match único por primer nombre).
4. **`reply` a un mensaje ajeno** sin validar en vivo (falta chat de prueba).
5. `server.py` no expone `reply`/`draft`, y `_resolve` lee el `.default` viejo en vez de `aliases.json`.
