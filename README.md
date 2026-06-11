# wavi — WhatsApp Web Automation via Vision

CLI tool for WhatsApp Web automation. Extracts message history using a vision pipeline (screenshot → OCR → bubbles), and handles navigation and sidebar state via DOM scraping.

## Commands

| Command | What it does | Approach |
|---|---|---|
| `wavi connect [session]` | Start Chrome daemon, authenticate via QR | — |
| `wavi status [session]` | Check if daemon is alive and authenticated | DOM |
| `wavi get <contact>` | Extract full message history from a chat | **Vision** |
| `wavi send <contact> <message>` | Send a message | DOM + keyboard |
| `wavi check-updates [session]` | Detect new inbound messages in sidebar | DOM |
| `wavi list-contacts [session]` | List all contacts in the "New chat" panel | DOM |
| `wavi queue [session]` | Show operation queue status | — |
| `wavi stop [session]` | Gracefully shut down the Chrome daemon | — |

## Architecture

### Vision pipeline (`wavi get`)

```
Screenshot → Crop chat panel → Color-mask detection → Bbox extraction
    ↓
    OCR (tiled) → Timestamp extraction → Message classification → Bubble list
```

Used for message content because WhatsApp Web obfuscates the message DOM in ways that make direct scraping unreliable.

Key files: `element_detector.py`, `vision.py`, `runner.py`

### DOM scraping

Navigation and sidebar state use JavaScript evaluated directly on the page. Each JS constant in `session.py` has a comment documenting its key selector and the vision-based fallback to implement if the selector breaks after a WA update. When a DOM-scraped feature stops working, check `session.py` → "DOM scraping inventory" block at the top.

### Chrome daemon

Chrome runs as a long-lived background process (started by `wavi connect`). Playwright connects and disconnects for each operation without ever killing Chrome. Killing Chrome mid-session corrupts WA's IndexedDB and invalidates the session. Shutdown is done only via `wavi stop`, which navigates to `about:blank` first so WA can flush state.

## Setup

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <repo> && cd wavi
uv sync
```

## Quick start

```bash
# 1. Start daemon and scan QR
wavi connect

# 2. Extract message history
wavi get "Contact Name"

# 3. Poll for new messages
wavi check-updates           # first run: saves baseline
wavi check-updates           # subsequent: no_updates or updates + contact list
```

## check-updates behavior

Compares the sidebar snapshot (last message + timestamp per chat) against the previous saved state. Reports a contact as updated only when:
- its `last_message` changed, **and**
- `direction == "inbound"` (outbound messages and re-reads are ignored)

Direction is inferred from tick icons (`msg-check`, `msg-dbl-check`, etc.) — present → outbound; absent → inbound.

**Limitation**: only the last visible message per chat is tracked. If multiple messages arrive between two checks, only the most recent is reported per contact. Use `wavi get <contact>` to retrieve the full history after detection.

## Development

```bash
make ocr                  # compile the OCR helper to bin/ocr_vision (arm64, ~4x faster pipeline)
make hooks                # git hooks: ruff on commit, ruff+pytest on push (bypass: --no-verify)
uv run pytest tests/ -v   # unit tests (offline, mocked browser)
make corpus               # vision eval on golden screenshots (real OCR, see tests/corpus/README.md)
```

`WAVI_TIMING=1` prints a per-stage timing breakdown of each `analyze()` run.
Roadmap and audit: `docs/plan-mejoras.md`, `docs/audit-checklist.md`.

Key files:
- `session.py` — Chrome CDP connection + all DOM scraping JS (see inventory block)
- `runner.py` — Orchestration: vision pipeline, `check_updates`, `list_contacts`
- `element_detector.py` — Color-mask morphology for bubble detection
- `vision.py` — OCR, classification, timestamp extraction

## Debugging

```bash
wavi bubbles /path/to/screenshot.png --debug
```

Produces `screenshot_debug.png` with annotated boxes:
- Green: sent messages
- Blue: received messages
- Red crosses: audio play button targets
