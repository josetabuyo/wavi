# wavi — WhatsApp Web Automation via Vision

**Vision-first browser automation for WhatsApp Web.** A CLI tool that extracts messages from WhatsApp Web with minimal DOM interaction.

## Philosophy

- **Vision-first**: Detect and extract messages using image analysis, not DOM parsing
- **Minimal DOM interaction**: Only interact with the browser when necessary (navigation, audio playback)
- **Robust extraction**: Handle complex message layouts, embedded images, and multimedia without brittle selectors
- **Headless-capable**: Run fully automated with screenshot analysis, no manual intervention needed

## Architecture

### Vision Pipeline

```
Screenshot → Crop sidebar → Color-mask detection → Connected components → Bbox extraction
    ↓
    OCR (tiled) → Timestamp extraction → Message classification → Bubble detection
```

**Key components:**
- `element_detector.py`: Detect message bubbles by color (green="me", white="other")
- `vision.py`: Full pipeline—OCR, classification, timestamp extraction, media detection
- `runner.py`: Orchestrate browser + vision pipeline together

### Browser Interaction (Minimal)

| Task | Method | Why |
|------|--------|-----|
| Navigate to chat | DOM click (unavoidable) | No vision-based way to find sidebar contact |
| Scroll to load history | Keyboard events | Triggers virtual scrolling without brittle selectors |
| Take screenshot | CDP screenshot | Only way to get page image |
| Play audio | DOM click on play button | Necessary for audio extraction |

**What we avoid:**
- Parsing message text from DOM
- Relying on class names or data-attributes
- Waiting for dynamic content (vision handles async loading)

## Installation & Usage

### Setup

```bash
git clone <repo>
cd wavi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Launch daemon

```bash
wavi connect default
# Scan QR in WhatsApp Web, leave Chrome open
```

### Extract messages

```bash
wavi full-sync default "Contact Name" --assets ./output/contact
```

**Output:**
- `screenshot.png` — Full page screenshot
- `screenshot_cropped.png` — Chat panel only
- `screenshot_debug.png` — Annotated boxes + click targets
- `screenshot_bubbles.json` — Extracted messages, audio metadata, timestamps

### Analyze a single screenshot

```bash
wavi bubbles /path/to/screenshot.png
```

## Known Limitations

- **Media thumbnails**: Embedded images (links with preview) are detected but not extracted
- **Very long conversations**: Virtual scrolling only loads visible messages; historical data requires scroll-based loading
- **Non-Latin scripts**: OCR may struggle with some character sets
- **Concurrent messages**: Rapid message flood may cause detection drift

## Development

### Testing

```bash
pytest tests/ -v
```

### Key files to understand

- `session.py` — Browser connection via Chrome DevTools Protocol (CDP)
- `element_detector.py` — Color-mask morphology for bubble detection
- `vision.py` — OCR, classification, message split logic
- `runner.py` — Orchestration and audio extraction

### Architecture Decisions

1. **Vision over DOM**: Robust to UI changes; doesn't break if WhatsApp updates selectors
2. **Keyboard events for scroll**: Triggers WhatsApp's lazy loading without worrying about scroll container implementation
3. **Tiled OCR**: Upscaling small text regions improves accuracy before OCR
4. **Color-mask closing**: Morphological closing bridges small gaps within bubbles (text lines) without merging separate messages (gap_px=7)

## Debugging

Enable debug images to see detected boxes and click targets:

```bash
wavi bubbles /path/to/screenshot.png --debug
```

Check `screenshot_debug.png`:
- **Green boxes**: Sent messages ("me")
- **Blue boxes**: Received messages ("other")
- **Red crosses**: Audio play button click targets
- **Labels**: Message ID, sender, type, timestamp

## Contributing

- **Bug reports**: Include screenshot and `screenshot_bubbles.json` output
- **Message format changes**: Add test cases to `test_vision.py`
- **Performance**: Profile with real chats; synthetic test data is minimal

---

**Last updated**: May 2026 | **Status**: Early development (32 messages extracted, 10 audios detected in test data)
