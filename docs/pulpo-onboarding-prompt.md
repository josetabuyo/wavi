# Prompt para onboarding de Pulpo con wavi

Copia y pégale esto a Pulpo (o a cualquier proyecto que quiera integrar wavi):

---

## PROMPT

Necesitamos integrar **wavi** para leer y enviar mensajes de WhatsApp desde este proyecto.

wavi es una herramienta de automatización de WhatsApp Web. Expone tres superficies:
- **Librería Python** (`import wavi`) — para proyectos Python
- **HTTP JSON API** (`wavi serve`) — para cualquier lenguaje (Node.js, etc.)
- **CLI** (`wavi get`, `wavi send`) — solo para uso humano, nunca para integración de software

### Contexto de wavi

Repo: `https://github.com/[org]/wavi` (o ruta local: `../wavi`)
Versión: 0.2.0
Docs de integración: `../wavi/docs/library-integration.md`

### Paso 1 — Setup único (ya lo hizo el operador humano)

El operador corrió `wavi connect` en la máquina donde correrá Pulpo y autenticó WhatsApp.
La sesión autenticada vive en `/path/to/wavi-sessions/<phone_number>/`.
El daemon de Chrome está corriendo (o se levanta solo en el primer uso).

### Paso 2 — Cómo integrarlo en este proyecto

#### Si Pulpo es Python:

```bash
uv add "wavi @ git+https://github.com/[org]/wavi@v0.2.0"
# o editable local:
uv add --editable ../wavi
```

```python
import asyncio
from pathlib import Path
from wavi import WARunner, run_enhanced, Bubble

SESSION = Path(os.environ["WAVI_SESSION_DIR"])  # e.g. /data/wavi-sessions/5491155612767

# Leer historial de un chat
async def get_messages(contact: str) -> list[Bubble]:
    result = await run_enhanced(
        profile_dir=SESSION,
        contact=contact,
        max_iterations=50,
        newest=True,  # solo mensajes nuevos desde la última vez
    )
    return result["bubbles"]

# Enviar un mensaje
async def send_message(contact: str, text: str) -> None:
    runner = WARunner(SESSION)
    await runner.connect()
    await runner.open_chat(contact)
    await runner.session.send_message(text)
    await runner.close()
```

#### Si Pulpo es Node.js / TypeScript:

1. Instalar el servidor en la máquina donde está la sesión de WA:
```bash
pip install 'wavi[server]'
wavi serve --port 8900   # dejar corriendo (systemd, pm2, etc.)
```

2. Instalar el cliente en Pulpo:
```bash
npm install wavi-client
```

3. Usar:
```typescript
import WaviClient, { Bubble } from "wavi-client";

const wavi = new WaviClient({ baseUrl: process.env.WAVI_API_URL ?? "http://127.0.0.1:8900" });

// Verificar que el servidor esté up
await wavi.health();

// Leer mensajes nuevos
const { bubbles } = await wavi.get({ contact: "Juan Pérez", newest: true });

// Enviar mensaje
await wavi.send({ contact: "Juan Pérez", message: "Hola desde Pulpo!" });

// Chequear si hay mensajes entrantes nuevos en el sidebar
const updates = await wavi.checkUpdates();
if (updates.status === "updates") {
  for (const chat of updates.new_inbound) {
    console.log(`Nuevo de ${chat.name}: ${chat.last_message}`);
  }
}
```

### Variables de entorno a configurar en Pulpo

| Variable | Descripción | Ejemplo |
|---|---|---|
| `WAVI_SESSION_DIR` | Ruta al directorio de sesión autenticada (solo Python) | `/data/wavi-sessions/5491155612767` |
| `WAVI_API_URL` | URL del servidor wavi (solo Node.js) | `http://127.0.0.1:8900` |
| `WAVI_SESSIONS_DIR` | Dir raíz de sesiones para `wavi serve` | `/data/wavi-sessions` |

### Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `QR scan required` | La sesión no está autenticada | Correr `wavi connect` y escanear el QR |
| `Session not found` | El path de sesión no existe | Verificar `WAVI_SESSION_DIR` |
| `Session is busy (409)` | Otra operación corre sobre esa sesión | Esperar o revisar `/queue/default` |
| `Connection timed out` | Chrome daemon no responde | `wavi status` para diagnosticar |

### Cosas que NO hay que hacer

- ❌ Parsear el stdout de `wavi get ...` con `subprocess` — usa la librería o la API HTTP
- ❌ Correr múltiples `get` concurrentes sobre la misma sesión — la sesión tiene lock, el segundo espera en cola
- ❌ Llamar `wavi connect` desde código — es una operación interactiva con QR para humanos

### Próximos pasos

1. Implementar la integración según el lenguaje de Pulpo (Python lib o HTTP client)
2. Hacer una prueba de `get` y `send` con un contacto de prueba
3. Reportar cualquier error o comportamiento inesperado para iterar
