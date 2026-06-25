# Integrating wavi in other projects

wavi exposes three integration surfaces. Pick the one that matches your language and deployment:

| Surface | Best for | Install |
|---|---|---|
| **Python library** | Python projects | `uv add git+https://...wavi` |
| **HTTP JSON API** | Any language (Node.js, Go, Ruby…) | `pip install 'wavi[server]'` + `wavi serve` |
| **CLI** | Humans, AI agents, shell scripts | `pip install wavi` |

---

## 1. Python library (direct)

Use this when your project is Python. Zero overhead — same process, no HTTP.

```python
import asyncio
from pathlib import Path
from wavi import WARunner, run_enhanced, Bubble

SESSION = Path("/path/to/wavi-sessions/5491155612767")

# High-level: get full chat history
async def main():
    result = await run_enhanced(
        profile_dir=SESSION,
        contact="Juan Pérez",
        assets_dir=Path("output/juan"),
        max_iterations=100,
    )
    bubbles: list[Bubble] = result["bubbles"]
    for b in bubbles:
        print(f"[{b.sender}] {b.text}")

asyncio.run(main())
```

```python
# Lower-level: WARunner for fine-grained control
async def send_and_read():
    runner = WARunner(SESSION)
    await runner.connect()
    await runner.open_chat("Juan Pérez")
    await runner.session.send_message("Hola!")
    await runner.close()
```

### Installation

```bash
# From git (private repo)
uv add "wavi @ git+https://github.com/your-org/wavi@v0.2.0"

# Local editable (monorepo / co-located)
uv add --editable ../wavi
```

### Chrome path (non-macOS or custom)

```python
from wavi import WARunner

runner = WARunner(
    profile_dir=SESSION,
    chrome_path="/usr/bin/google-chrome",
)
```

---

## 2. HTTP JSON API (any language)

Use this when your project is **not Python** (Node.js, Go, Ruby…), or when you
want process isolation between wavi and your app.

### Start the server

```bash
# Install server extras
pip install 'wavi[server]'

# Start (default: 127.0.0.1:8900)
wavi serve

# Custom port / sessions dir
wavi serve --port 9000 --sessions-dir /data/wavi-sessions

# Via env var
WAVI_SESSIONS_DIR=/data/wavi-sessions wavi serve
```

Interactive API docs: `http://127.0.0.1:8900/docs`

### Node.js — wavi-client

```bash
npm install wavi-client   # or: pnpm add / yarn add
```

```typescript
import WaviClient from "wavi-client";

const wavi = new WaviClient({ baseUrl: "http://127.0.0.1:8900" });

// Check server is up
await wavi.health();

// Get message history
const { bubbles, count } = await wavi.get({
  contact: "Juan Pérez",
  max_iter: 50,
});
console.log(`${count} messages`);
bubbles.forEach(b => console.log(`[${b.sender}] ${b.text}`));

// Send a message
await wavi.send({ contact: "Juan Pérez", message: "Hola desde Node!" });

// Check for new inbound messages
const updates = await wavi.checkUpdates();
if (updates.status === "updates") {
  updates.new_inbound.forEach(c => console.log(`New from ${c.name}: ${c.last_message}`));
}
```

### Raw HTTP (any language)

```bash
# Health
curl http://127.0.0.1:8900/health

# Status
curl http://127.0.0.1:8900/status/default

# Get messages
curl -X POST http://127.0.0.1:8900/get \
  -H "Content-Type: application/json" \
  -d '{"contact": "Juan Pérez", "max_iter": 50}'

# Send a message
curl -X POST http://127.0.0.1:8900/send \
  -H "Content-Type: application/json" \
  -d '{"contact": "Juan Pérez", "message": "Hola!"}'

# Check updates
curl -X POST http://127.0.0.1:8900/check-updates \
  -H "Content-Type: application/json" \
  -d '{"session": "default"}'
```

### API reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/status/{session}` | Daemon alive + auth status |
| GET | `/queue/{session}` | Current operation or idle |
| POST | `/get` | Capture full message history |
| POST | `/send` | Send a message |
| POST | `/check-updates` | Check sidebar for new inbound |
| POST | `/list-contacts` | List contacts from New Chat |

All POST bodies are JSON. Full schema at `/docs` (Swagger UI).

---

## 3. CLI (humans / AI agents / shell)

Use for one-off operations, scripts, or AI agent tool calls.

```bash
wavi connect                          # authenticate (one-time)
wavi get default "Juan Pérez" --json-out
wavi send default "Juan Pérez" "Hola"
wavi check-updates
wavi status
```

**Never use CLI output parsing in production software.** Use the Python library
or HTTP API instead — they return structured types and don't break on locale changes.

---

## Decision guide

```
Is your project Python?
  YES → Use the Python library directly (import wavi).
  NO  → Use wavi serve + language-specific HTTP client.

Is the operation interactive / one-off / done by a human or AI agent?
  YES → CLI is fine.
  NO  → Never parse CLI stdout in production code.

Do you need process isolation (separate crash domains)?
  YES → HTTP API (even from Python).
  NO  → Python library is simpler.
```

---

## Applying this pattern to other CLI tools

The same three-surface model works for any Python CLI tool:

1. **Separate the library from the CLI at the source.**
   - CLI (`cli.py`) imports and calls the library (`session.py`, `runner.py`).
   - Library has no `click` dependency.
   - `__init__.py` exports the public API.

2. **Add an HTTP server as an optional extra.**
   - `pip install 'mytool[server]'` + `mytool serve`.
   - Use FastAPI for auto-generated docs and Pydantic validation.
   - Use `MYTOOL_DATA_DIR` env var to configure paths.

3. **Publish a typed client per language.**
   - Node.js: thin `fetch` wrapper with TypeScript types.
   - Python: just `import mytool` — no client needed.
   - Others: document the raw HTTP API; one curl example per endpoint.

4. **Never document subprocess as an integration pattern.**
   Parse JSON only from the HTTP API. The CLI output format is a UX contract
   with humans, not a machine contract with software.
