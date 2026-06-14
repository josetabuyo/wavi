# wavi — WhatsApp Web Automation via Vision

CLI tool for WhatsApp Web automation. Extracts message history using a vision pipeline (screenshot → OCR → bubbles), and handles navigation and sidebar state via DOM scraping.

## Commands

| Command | What it does | Approach |
|---|---|---|
| `wavi connect [session]` | Start Chrome daemon, authenticate via QR | — |
| `wavi status [session]` | Check if daemon is alive and authenticated | DOM |
| `wavi get <contact>` | Extract full message history from a chat (`--grow` to page through in chunks) | **Vision** |
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

# 2b. Long chat — page through in blocks of 10 iterations
wavi get "Contact Name" --grow --max-iter 10   # block 1
wavi get "Contact Name" --grow --max-iter 10   # block 2 (continues where block 1 stopped)
# repeat until "history is now complete" or no more messages

# 3. Poll for new messages
wavi check-updates           # first run: saves baseline
wavi check-updates           # subsequent: no_updates or updates + contact list
```

## wavi get flags

| Flag | Behavior |
|---|---|
| `--max-iter N` | Stop after N scroll iterations (default 300). In `--grow` mode, N counts only **new-content** iterations per run. |
| `--from YYYY-MM-DD` | Stop scrolling when the oldest visible day pill is before this date. Drop bubbles older than the date. |
| `--newest` | Load existing `history_bubbles.json` and stop the moment a known message is found. Prepends new messages. Goes toward the **present**. |
| `--grow` | Load existing history, fast-forward past known content, then capture N more iterations toward the **past**. Saves a `grow_checkpoint.json` so each run continues where the last one stopped. Incompatible with `--newest`. |
| `--assets DIR` | Override the output directory (default `output/<session>/<contact>/`). |
| `--json-out` | Print the bubble list as JSON to stdout instead of the summary table. |

### `--grow` workflow for long chats

```bash
wavi get "Contact" --grow --max-iter 10   # run 1: captures first 10 new-content iterations
wavi get "Contact" --grow --max-iter 10   # run 2: fast-forwards to boundary, captures next 10
# repeat — prints "history is now complete" when scrollTop reaches 0
```

State is stored in `output/<session>/<contact>/grow_checkpoint.json`. Delete it to restart from scratch (also delete `history_bubbles.json`).

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
