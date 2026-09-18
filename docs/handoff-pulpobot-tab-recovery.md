# Handoff: pulpo-bot tab recovery

**Fecha:** 2026-07-01  
**Estado al cerrar:** tab throttleado, session=timeout después de Page.reload  
**Propietario siguiente:** Wavi (nueva sesión)

---

## Contexto

pulpo-bot es la sesión de WhatsApp de +54 9 11 5561-2767.  
Chrome daemon lleva corriendo desde el lunes sin interacción real → V8 throttleado → WA React no procesa mensajes entrantes aunque el WebSocket TCP está vivo.

---

## Estado actual del sistema

| Elemento | Valor |
|---|---|
| PID del daemon | 70650 |
| CDP port | 9216 |
| Tab ID | `0A4F05B33EC71180A81AC383D8F080AE` |
| Profile path | `/Users/josetabuyo/Development/wavi/data/sessions/5491155612767` |
| PID file | `/Users/josetabuyo/Development/wavi/data/sessions/5491155612767/chrome_daemon.pid` → `70650` |
| Port file | `/Users/josetabuyo/Development/wavi/data/sessions/5491155612767/chrome_daemon.port` → `9216` |
| Último status wavi | `session=timeout` (después de que Pulpo hizo Page.reload vía CDP) |

**Verificar primero:**
```bash
# ¿Sigue vivo el PID?
ps aux | grep 70650 | grep -v grep

# ¿CDP responde?
curl -s http://localhost:9216/json/version

# ¿Qué tab ID está activo ahora?
curl -s http://localhost:9216/json | python3 -c "import json,sys; [print(t['id'], t.get('url',''), t.get('title','')) for t in json.load(sys.stdin)]"
```

---

## Lo que se sabe del DOM de WA Web (versión actual)

WA Web **cambió su estructura DOM** — esto afecta a wavi:

| Antes | Ahora |
|---|---|
| `#main` | **no existe** |
| `[data-testid="conversation-panel-messages"]` | probablemente obsoleto |
| Layout plano | `drawer-left` / `drawer-middle` / `drawer-right` |

**Selectores que SÍ siguen funcionando** (confirmado via CDP directo):
- `[data-testid="chat-list"]` ✅ (sidebar)
- `[data-testid="cell-frame-container"]` ✅ (filas del sidebar)
- `[data-testid="cell-frame-title"]` ✅ (nombre del contacto)
- `.copyable-text` → **0 resultados** en el chat abierto (puede ser obsoleto)
- `[data-id]` → **0 resultados** (puede ser obsoleto para message rows)

**`_AUTHED_SEL` en session.py probablemente obsoleto** — causó `session=timeout` después del reload porque wavi no encontró el selector de autenticación en el nuevo DOM. Hay que actualizarlo.

---

## Zombies a matar (si no se hizo ya)

```bash
kill 19855 21373 65082
```
- 19855: Chrome con profile path incorrecto (pipx venv), port 9222
- 21373: Chrome con profile path incorrecto (pipx venv), port 9233  
- 65082: Chrome duplicado con profile correcto pero port 9218

**NO matar 70650.**

---

## Variable de entorno requerida

```bash
export WAVI_SESSIONS_DIR=/Users/josetabuyo/Development/wavi/data/sessions
```

Sin esto, el CLI de wavi (instalado via pipx) resuelve al path del venv.

---

## Plan de acción para la nueva sesión

### Paso 1 — Diagnóstico del tab
```python
# Tomar screenshot vía CDP para ver estado visual actual
import asyncio, json, websockets, base64, pathlib

WS = "ws://localhost:9216/devtools/page/<TAB_ID_ACTUAL>"  # verificar con /json

async def screenshot():
    async with websockets.connect(WS, max_size=50_000_000) as ws:
        await ws.send(json.dumps({"id":1,"method":"Page.captureScreenshot","params":{"format":"png"}}))
        r = json.loads(await ws.recv())
        pathlib.Path("/tmp/wa_state.png").write_bytes(base64.b64decode(r["result"]["data"]))

asyncio.run(screenshot())
```

### Paso 2 — Si WA está cargado pero `_AUTHED_SEL` falló
Actualizar `_AUTHED_SEL` en `session.py` para matchear el nuevo DOM:
```python
# Buscar cuál selector corresponde al estado autenticado en el nuevo WA Web
# Candidatos:
# '[data-testid="drawer-left"]'  (siempre presente cuando autenticado)
# '[data-testid="chat-list"]'    (ya usado en ensure_chat_list)
# '[data-testid="chatlist-header"]'
```

### Paso 3 — Reconectar con wavi
```bash
WAVI_SESSIONS_DIR=/Users/josetabuyo/Development/wavi/data/sessions wavi status pulpo-bot
WAVI_SESSIONS_DIR=/Users/josetabuyo/Development/wavi/data/sessions wavi connect pulpo-bot
```

### Paso 4 — Auditar selectores obsoletos en session.py
Los selectores de conversation panel necesitan ser actualizados para la nueva estructura `drawer-*`. Especialmente:
- `_CHAT_SCROLL_JS` → buscar el panel scrollable dentro de `drawer-middle`
- `_SCROLL_UP_JS` / `_SCROLL_DOWN_JS` → ídem
- `_GET_VISIBLE_MSG_IDS_JS` → `[data-id]` puede estar obsoleto
- `_CLICK_SCROLL_BOTTOM_BTN_JS` → el botón puede estar en diferente contenedor

### Paso 5 — Confirmar recepción de mensajes
Una vez que session=restored:
```bash
WAVI_SESSIONS_DIR=/Users/josetabuyo/Development/wavi/data/sessions wavi check-updates pulpo-bot
```
Pulpo mandará mensaje de prueba "WA → flow → TG" para confirmar el pipeline completo.

---

## Fixes ya despachados (NO re-hacer)

| Versión | Fix | Estado |
|---|---|---|
| v0.2.3 | `ensure_chat_list()` limpia búsqueda del sidebar via JS (no Escape×3) | ✅ PyPI |
| v0.2.3 | `_CHAT_SCROLL_JS` no reporta false negative en chats cortos | ✅ PyPI |
| v0.2.4 | `DEFAULT_SESSIONS_DIR` resuelve correctamente en pipx/PyPI installs | ✅ PyPI |

---

## Contactos LAS relevantes

```bash
las agent inject Pulpo "..." --from Wavi   # notificar progreso
las agent inject Teli "..." --from Wavi    # si se necesita algo de otras sesiones
```

---

## Token PyPI (ya guardado, no volver a pedir)

```bash
UV_PUBLISH_TOKEN="$(grep password ~/.pypirc | cut -d= -f2 | tr -d ' ')" uv publish dist/*.whl dist/*.tar.gz
```
