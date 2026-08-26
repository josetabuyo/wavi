# wavi — WhatsApp Web automation skill

Use the `wavi` CLI to manage WhatsApp Web sessions, capture message history,
send messages, and monitor chats from the terminal.

## Session lifecycle

```bash
wavi connect [session]    # start Chrome daemon, wait for auth
wavi qr      [session]    # self-contained: opens a local web page, "Buscar QR"
                           # button starts the daemon if needed and shows a
                           # QR that never goes stale (never a separate step)
wavi status  [session]    # check: daemon alive? session authenticated?
wavi reload  [session]    # safely reload WA when throttled or unresponsive
wavi stop    [session]    # graceful shutdown (about:blank flush → SIGTERM)
wavi events  [session]    # session lifecycle log — connects, QR, archives
```

QR scanning is never done inline by `connect` — run `wavi qr <session>` (or
pass `--open` to `connect` to launch it automatically). It never shows a
stale screenshot: press the button again anytime for a fresh QR.

### Session aliases

```bash
wavi alias set pulpo-bot 5491155612767   # friendly name → phone folder
wavi alias set mateo 5491122608221
wavi alias list
wavi alias remove pulpo-bot
```

All commands accept an alias wherever a session argument is expected.

## Capture & monitor

```bash
wavi get [session] "Contact Name"             # full message history
wavi get [session] "Contact Name" --newest    # incremental: only new messages
wavi get [session] "Contact Name" --grow --max-iter 20  # page through long chats
wavi check-updates [session]                  # diff sidebar vs last snapshot
wavi list-contacts [session]                  # list all contacts
```

## Send

```bash
wavi send [session] "Contact Name" "message text"
```

## Contact resolution — never guesses when a name is ambiguous

`wavi get` and `wavi send` resolve CONTACT through WhatsApp's own search
before doing anything else:

1. Search for the name. If nothing matches, refresh the contact list (opens
   "New chat" once to force WA to sync) and search again — covers a
   freshly-linked session whose chat list is still syncing from the phone.
2. If still nothing matches, fail loudly with an error (never silently
   proceeds against the wrong screen).
3. If more than one distinct match exists (same display name can belong to
   an existing chat AND unrelated saved/unsaved contacts), it prints every
   candidate with whatever distinguishes them (last message preview, phone
   number, status text) and prompts interactively for a choice.
4. Without a TTY to ask (scripts, the HTTP API), it refuses instead of
   guessing — the error lists the candidates so you can be more specific
   (e.g. include the phone number).
5. Once resolved, it prints "Contacto confirmado: <name> — <detail>" and
   *verifies* the chat actually opened before capturing/sending anything.

See docs/adr/ADR-010-contact-disambiguation.md.

## Skill install / update

```bash
wavi install-skill   # copies SKILL.md to ~/.claude/skills/wavi/SKILL.md
```

Run this after `pip install --upgrade wavi-lib` to pick up any updates.
Restart Claude Code once after installing.

---

## SESSION SAFETY — read this before touching Chrome directly

> **NEVER call `Page.reload` or `Storage.clearDataForOrigin` on a WhatsApp tab via raw CDP.**
> Both operations destroy the session and force a full QR re-scan.

### Why

WhatsApp Web keeps its auth state in IndexedDB (LevelDB on disk). When Chrome
is running, WA has in-flight write transactions open at all times. Interrupting
the page mid-transaction corrupts the database — Chrome will report
"error en la base de datos de tu navegador" and show the QR screen.

`Storage.clearDataForOrigin` is even worse: it deletes the auth tokens entirely,
making the session irrecoverable without a new QR scan, and risks triggering
WA's device-linking rate limiter if attempted multiple times.

### The safe cycle

If WA becomes unresponsive, V8-throttled, or stuck:

```bash
# Option A — soft reload (keeps Chrome running, ~15 seconds)
wavi reload pulpo-bot
# → session=restored   Chrome is fine
# → session=qr_needed  auth was lost, need QR
# → session=timeout    WA didn't load — try option B

# Option B — full restart (stops Chrome, starts fresh, ~30 seconds)
wavi stop pulpo-bot
wavi connect pulpo-bot
```

### Contract for external agents (Pulpo, scripts, etc.)

- **Never** send CDP commands directly to the WhatsApp tab.
- **Never** call `Page.reload`, `Page.navigate`, or any Storage API on `https://web.whatsapp.com`.
- **Always** go through the wavi CLI or the wavi HTTP API (`wavi serve`).
- If WA is throttled → call `wavi reload <session>` and wait for `session=restored`.
- If `wavi reload` returns `qr_needed` → alert the human; do not attempt to fix it programmatically.

---

## HTTP API (optional)

```bash
wavi serve                  # start JSON API on 127.0.0.1:8900
# docs at http://127.0.0.1:8900/docs
```

All CLI operations are available as HTTP endpoints. The API is the correct
interface for external agents — it enforces the safe session lifecycle
automatically.

---

## Debugging

```bash
wavi bubbles /path/to/screenshot.png --debug   # run vision pipeline locally
WAVI_SESSIONS_DIR=/path/to/sessions wavi status pulpo-bot  # override sessions dir
```

Set `WAVI_SESSIONS_DIR` when running from outside the repo (e.g. pipx installs).
