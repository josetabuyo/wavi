# wavi — WhatsApp Web Automation via Vision

CLI tool for WhatsApp Web automation. Extracts message history using a vision pipeline (screenshot → OCR → bubbles), and handles navigation and sidebar state via DOM scraping.

## Commands

| Command | What it does | Approach |
|---|---|---|
| `wavi connect [session]` | Start Chrome daemon, authenticate via QR | — |
| `wavi status [session]` | Check if daemon is alive and authenticated | DOM |
| `wavi reload [session]` | **Safe reload** — about:blank flush → WA → verify auth | — |
| `wavi get <contact>` | Extract full message history from a chat (`--grow` to page through in chunks) | **Vision** |
| `wavi send <contact> <message>` | Send a message; in a group `@Name` becomes a real mention of a participant (`--no-mentions` to type `@` literally). `--attach FILE` (repeatable) sends files — PDF, PPT, any document or image — with the message as caption | DOM + keyboard (attachments: paste) |
| `wavi edit <contact> <match> <new>` | Edit one of your own sent messages (WA's 15-min window); `--fragment` replaces only `<match>` | vision (OCR) + keyboard |
| `wavi reply <contact> <match> <text>` | Reply quoting one message (yours or anyone's); `--from` narrows by sender, `--index N` picks among matches | vision (OCR) + keyboard |
| `wavi draft show\|clear <contact>` | Show or empty a chat's compose-box draft (it blocks `send`); `wavi send --discard-draft` does both and sends | DOM + keyboard |
| `wavi media <contact>` | Download a chat's videos and photos (full files) + `media.json` | Media viewer (DOM) |
| `wavi check-updates [session]` | Detect new inbound messages in sidebar | DOM |
| `wavi list-contacts [session]` | List all contacts in the "New chat" panel | DOM |
| `wavi queue [session]` | Show operation queue status | — |
| `wavi stop [session]` | Gracefully shut down the Chrome daemon | — |
| `wavi alias set <name> <session>` | Assign a friendly alias to a session | — |
| `wavi alias list` | List all aliases | — |
| `wavi alias remove <name>` | Remove an alias | — |
| `wavi install-skill` | Install the Claude Code `/wavi` skill to `~/.claude/skills/wavi/` | — |

### Session aliases

All commands accept an alias in place of a phone number. Aliases are stored in `data/sessions/aliases.json`.

```bash
wavi alias set pulpo-bot 5491155612767
wavi alias set mateo 5491122608221
wavi status pulpo-bot       # same as: wavi status 5491155612767
wavi get mateo "Contacto"
```

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

### ⚠️ Session safety — critical rules

**Never call `Page.reload` or `Storage.clearDataForOrigin` on the WhatsApp tab via raw CDP.**

WhatsApp Web holds in-flight IndexedDB write transactions while running. Interrupting the page mid-transaction (via `Page.reload`, `Page.navigate`, or storage wipe) corrupts the LevelDB database and forces a full QR re-scan. `Storage.clearDataForOrigin` is worse — it deletes auth tokens entirely.

**If WA becomes unresponsive or throttled, use the safe cycle:**

```bash
# Option A — soft reload (~15s, Chrome keeps running)
wavi reload pulpo-bot
# → session=restored  ✓
# → session=qr_needed  auth lost, need QR scan

# Option B — full restart (~30s)
wavi stop pulpo-bot && wavi connect pulpo-bot
```

**External agents (Pulpo, scripts, automation):** never send CDP commands directly to the WA tab. Always go through `wavi` CLI or the HTTP API (`wavi serve`). If `wavi reload` returns `qr_needed`, alert a human — do not attempt to recover programmatically.

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
| `--assets DIR` | Override the output directory (default `<wavi output dir>/<session>/<contact>/` — the repo's `output/` on dev installs, `~/.local/share/wavi/output/` otherwise, or `$WAVI_OUTPUT_DIR`; never the caller's cwd). |
| `--json-out` | Print the bubble list as JSON to stdout instead of the summary table. |

### `--grow` workflow for long chats

```bash
wavi get "Contact" --grow --max-iter 10   # run 1: captures first 10 new-content iterations
wavi get "Contact" --grow --max-iter 10   # run 2: fast-forwards to boundary, captures next 10
# repeat — prints "history is now complete" when scrollTop reaches 0
```

State is stored in `<wavi output dir>/<session>/<contact>/grow_checkpoint.json`. Delete it to restart from scratch (also delete `history_bubbles.json`).

## wavi edit

```bash
wavi edit default "DATA LAKE - Técnico" "atías, ya vi" "Matías, ya vi" --fragment
```

Finds — by vision, like `reply` — the one **own** message whose text contains `<match>` (accent/case-insensitive), opens WA's *Edit* dialog and saves the new text. `--fragment` is applied to the editor's prefilled text (the exact message), never to OCR output. Fails without touching anything when there is no match, more than one match (prints them — use a longer fragment), or the message is older than 15 minutes. The editor's content is checked against the intended text before saving; the result is re-read from the chat (`verified`).

## wavi reply

```bash
wavi reply default "DATA LAKE - Técnico" "subí el video" "Gracias, ya lo veo" --from Matias
```

Finds — by vision: OCR of the chat, scrolling up to 4 screens — the one message (own or not) whose body contains `<match>` (text inside a quote doesn't count), right-clicks it and picks *Responder* from the OCR'd menu, checks the quote panel shows that message, and sends `<text>` with the same guards as `wavi send`. Ambiguous matches are listed numbered — narrow with `--from <sender>` or pick with `--index N`. Any failure cancels the quote (Escape) so nothing is left half-done. The sent reply is re-read from the chat (`verified`: body and quote both match).

## wavi media

```bash
wavi media default "DATA LAKE - Técnico" --type video --from 2026-10-08
```

Opens the newest photo/video in the chat's media viewer and walks it with ← (newest → oldest), saving the **full file** (not the bubble thumbnail): photos from the viewer's blob image, videos from WA's `/stream/video` endpoint read range by range. Files land in `<wavi output dir>/<session>/<contact>/media/` as `<date>_<time>_<sender>_<hash>.<ext>`, with `media.json` (sender, timestamp, bytes, sha1). Re-runs skip what's already there.

| Flag | Meaning |
|---|---|
| `--type all\|video\|image` | What to download (default `all`). |
| `--from YYYY-MM-DD` | Stop at the first item older than this date. |
| `--limit N` | At most N new files. |
| `--assets DIR` | Override the output directory. |

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
