# wavi — WhatsApp Web automation skill

Use the `wavi` CLI to manage WhatsApp Web sessions, capture message history,
send messages, and monitor chats from the terminal.

---

## ⚠️ READ THIS FIRST — the one rule that matters most

**A WhatsApp session that looks broken is almost never actually broken.**
The single most damaging mistake an agent can make with wavi is treating
"I don't see a connection" as a reason to force a new one, clear data, or
touch the browser directly. That is exactly how real sessions have been
destroyed before — repeatedly — and it is the failure mode this skill
exists to prevent.

**If a session looks disconnected, do this — nothing else:**

```bash
wavi status <session>
```

Then react to what it says:

| `wavi status` says | What it means | What you do |
|---|---|---|
| `daemon_running=True, authenticated=True` (or `wavi connect` prints "ya activa y autenticada") | Everything is fine | Just use it (`wavi get`, `wavi send`, etc.) |
| Daemon not running | Chrome isn't up right now | `wavi connect <session>` — **no flags**. This restarts Chrome on the *existing* profile and tries to restore the *existing* session. It does not touch or discard anything. |
| `qr_needed` after a plain `wavi connect <session>` (no `--new`) | Auth was genuinely lost (rare — see below) | **Stop. Tell the human. Do not try to "fix" it yourself.** Do not retry with `--new`. Do not touch the profile folder. Do not open the tab with a browser tool. Just report it and wait for a human to scan the QR via `wavi qr <session>`. |
| Chrome/WA feels frozen, throttled, or stuck mid-action | Needs a soft kick, not a rebuild | `wavi reload <session>` (see "Session safety" below) |

**Never do any of the following, ever, for any reason, even to "fix" a
session that looks dead:**

- Never pass `--new` to `wavi connect` unless the human explicitly asked
  you to link a **brand-new phone number** that has never used wavi
  before. `--new` is for onboarding a new account, not for recovering an
  existing one. (It no longer deletes the old profile outright — see
  ADR-009 below — but it still burns a fresh QR scan and creates
  confusion. Treat it as a one-way door that needs explicit human intent.)
- Never `rm -rf`, move, or edit anything under `data/sessions/<name>/`
  by hand.
- Never open the WhatsApp tab with a raw browser-automation tool
  (`mcp__claude-in-chrome__*`, Playwright, raw CDP, etc.) — not to look at
  it, not to click something, not to "just check." wavi's own CLI is the
  only supported way to touch that tab. See "Session safety" below for
  exactly why.
- Never call `Storage.clearDataForOrigin` or `Page.reload` against
  `https://web.whatsapp.com` under any circumstance.

**Why this is written so bluntly:** this exact pattern — someone seeing
"not connected" and reaching for a destructive fix instead of a safe
`wavi connect`/`wavi reload` — has broken production sessions multiple
times in the past (see ADR-009). One of those incidents also traced back
to an agent running a **stale pipx install** of wavi that still had the
old destructive `--new` behavior. If a session breaks again after
everything above was followed correctly, the first thing to check is
whether the installed wavi is current:

```bash
pipx list | grep wavi-lib     # compare against pyproject.toml's version in the repo
pipx upgrade wavi-lib         # if stale
```

---

## Which account am I talking to? (read before any `get`/`send`)

wavi can hold multiple WhatsApp accounts side by side, each identified by
a session name or alias (phone number folder, or a friendly alias like
`pulpo-bot`).

- **If the human just says "the conversation", "my messages", "check
  WhatsApp" — with no account named — they mean the `default` session.**
  Do not ask which account; do not guess a different one. Use `default`
  (or simply omit the `[session]` argument — every command defaults to
  `default` on its own).
- **The moment more than one account is in play, be explicit.** Name the
  session/alias in every command and in your own output back to the
  human, so it's never ambiguous which WhatsApp number a message came
  from or was sent to. Don't silently fall back to `default` once the
  conversation has established a specific account.
- Current aliases are not fixed — always check what actually exists
  rather than assuming:

  ```bash
  wavi alias list
  ```

- To add a friendly name for a non-default number:

  ```bash
  wavi alias set pulpo-bot 5491155612767
  wavi alias set mateo 5491122608221
  wavi alias remove pulpo-bot
  ```

  All commands accept an alias wherever a session argument is expected.

---

## Session lifecycle

```bash
wavi connect [session]    # start Chrome daemon, wait for auth (safe — never destroys existing session)
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

## Capture & monitor

```bash
wavi get [session] "Contact Name"             # full message history
wavi get [session] "Contact Name" --newest    # incremental: only new messages
wavi get [session] "Contact Name" --grow --max-iter 20  # page through long chats
wavi check-updates [session]                  # diff sidebar vs last snapshot
wavi list-contacts [session]                  # list all contacts
```

`wavi get`/`check-updates` read text via OCR over screenshots of the chat —
they do not download or extract media (photos/videos) that were sent in the
conversation, only whatever is visible as chat bubbles.

## Send

```bash
wavi send [session] "Contact Name" "message text"
```

There is currently no way to send file attachments (images, PDFs, etc.)
through `wavi send` — text only. `--screenshot-out` only saves a screenshot
*after* sending for confirmation; it does not attach anything to the message.

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

Run this after `pipx upgrade wavi-lib` to pick up any updates. Restart
Claude Code once after installing.

---

## Session safety — the mechanics behind the rules above

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

This is also why raw browser-automation tools are off-limits for the WA tab
(see the rule at the top): they operate at the CDP level and have no
knowledge of wavi's safe lifecycle — a well-intentioned `page.reload()` or
"let me just look at the DOM" from a generic browser tool is indistinguishable,
from WhatsApp's perspective, from the corruption case above.

### The safe cycle

If WA becomes unresponsive, V8-throttled, or stuck:

```bash
# Option A — soft reload (keeps Chrome running, ~15 seconds)
wavi reload <session>
# → session=restored   Chrome is fine
# → session=qr_needed  auth was lost, need QR — tell the human, don't retry with --new
# → session=timeout    WA didn't load — try option B

# Option B — full restart (stops Chrome, starts fresh, ~30 seconds)
wavi stop <session>
wavi connect <session>
```

Neither of these ever deletes or overwrites the existing profile. `--new`
is the only flag that starts a fresh authentication, and even it now
archives (never deletes) whatever was there before — see ADR-009.

### Historical incidents (why the rules exist)

- **2026-07-01** — an external tool (Pulpo) called `Page.reload` directly
  on the WA tab via CDP, which corrupted IndexedDB; the follow-up attempt
  to fix the resulting DB error with `Storage.clearDataForOrigin` wiped
  the auth tokens entirely. Root cause: external tools touching the tab
  directly instead of going through wavi's safe lifecycle.
- **Before 2026-08-18 (ADR-009)** — `wavi connect --new`, when it detected
  the newly-scanned number already had an existing profile, ran
  `shutil.rmtree()` on the old profile before renaming the new one into
  place — an unrecoverable delete, with no backup and no confirmation.
  This happened more than once. Fixed in v0.3.0: the old profile is now
  archived (`<number>_archived_<timestamp>`) instead of deleted.
- **2026-09 (~19-day gap)** — the `default` session went from
  authenticated to `qr_needed` with zero corresponding log entries,
  traced to the pipx-installed `wavi` binary being stuck on **v0.2.6** —
  a version that predates the ADR-009 fix above. Some caller invoked
  `--new` against a session that looked disconnected, and the stale
  binary still had the old destructive delete-then-rename behavior.
  Lesson: an out-of-date local install silently reintroduces fixed bugs.
  Always verify `pipx list | grep wavi-lib` matches the repo's current
  version before trusting that a known issue is actually fixed on this
  machine.

### Contract for external agents (Pulpo, scripts, etc.)

- **Never** send CDP commands directly to the WhatsApp tab.
- **Never** call `Page.reload`, `Page.navigate`, or any Storage API on `https://web.whatsapp.com`.
- **Always** go through the wavi CLI or the wavi HTTP API (`wavi serve`).
- If WA is throttled → call `wavi reload <session>` and wait for `session=restored`.
- If `wavi reload` or `wavi connect` (without `--new`) returns `qr_needed` →
  alert the human; do not attempt to fix it programmatically, and above all
  do not fall back to `--new` as an automatic recovery step.
- Never default a missing/empty session name to `"default"` and then pass
  `new=True`/`--new` — that combination is exactly how a real account has
  been put at risk before. If a session name is required and none was
  given, fail loudly and ask, rather than silently assuming `default` and
  forcing a fresh link.

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
WAVI_SESSIONS_DIR=/path/to/sessions wavi status <session>  # override sessions dir
```

Set `WAVI_SESSIONS_DIR` when running from outside the repo (e.g. pipx installs).
