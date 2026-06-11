# Matriz de capacidades

Trazabilidad capacidad → señal primaria → fallback visual → estado → test.
Complementa el inventario de DOM scraping en `session.py` (que documenta cada
constante JS) con la vista por capacidad. Actualizar en la misma PR que cambie
cualquier señal (regla anti-drift).

**Leyenda estado del fallback:** ✅ implementado · 📋 diseñado (documentado, no codeado) · 🔮 planificado (fase del plan)

## Extracción de contenido

| Capacidad | Señal primaria | Fallback | Estado fallback | Test |
|---|---|---|---|---|
| Detectar burbujas (bbox + sender) | **Visión**: máscaras de color + componentes conexas | — (es el camino primario) | — | `test_vision.py::TestDetectBubbles`, corpus |
| Leer texto de burbuja | **Visión**: OCR Apple Vision por burbuja | — | — | corpus (`text_sim`) |
| Clasificar text/audio/file/media | **Visión**: regex sobre OCR + waveform garbage | triángulo de play por template matching | 🔮 Fase 3 | `test_vision.py::TestClassifyMsgType` |
| Timestamps + fechas | **Visión**: regex OCR + pills de fecha | — | — | `test_vision.py::TestExtractTimestamp`, corpus |
| Burbujas media (foto/video) | ❌ no detectadas | varianza local | 🔮 Fase 3 | corpus (caso desafío) |
| Bytes de audio (.ogg) | **JS**: hook `HTMLMediaElement`/`createObjectURL` + fetch blob | no existe camino visual (límite físico) | — | `test_runner.py` (blob mocks) |
| Transcripción de audio | Groq whisper-large-v3 | pywhispercpp local | ✅ | `test_transcription.py` |

## Dedup e historia

| Capacidad | Señal primaria | Fallback | Estado fallback | Test |
|---|---|---|---|---|
| Dedup entre pantallas | **DOM**: `data-id` | clave OCR (sender+type+text+ts) | ✅ | `test_runner.py` |
| | | dhash perceptual del crop | 🔮 Fase 3 | — |
| Ancla de scroll | **DOM**: dom_id del bubble más viejo | clave OCR del ancla | ✅ | `test_runner.py` |
| Corte por fecha (`--from`) | **Visión**: pills de fecha | — | — | `test_runner.py` |
| Incremental (`--newest`) | claves conocidas de history_bubbles.json | — | — | `test_runner.py` |

## Navegación e interacción

| Capacidad | Señal primaria | Fallback | Estado fallback | Test |
|---|---|---|---|---|
| Abrir chat de contacto | **Coords fijas** (317,80) + teclado | detectar search box visualmente | 🔮 Fase 3 | `test_session.py` |
| Scroll del chat | **DOM**: `scrollTop` | `mouse.wheel` por coordenadas | 🔮 Fase 5 | `test_session.py` |
| Estado de scroll (tope/fondo) | **DOM**: scrollTop/scrollHeight | proxy visual (contenido no cambia) | 📋 | `test_session.py` |
| Botón scroll-to-bottom | **DOM**: heurística posicional en `#main` | botón redondo abajo-derecha por visión | 📋 (`session.py` inventario) | — |
| Compose box | **DOM**: `footer [contenteditable]` → coords | franja inferior por posición | 📋 | `test_session.py` |
| Enviar (botón send) | **DOM**: `span[data-icon="send"]` | ícono flecha por visión | 📋 | `test_session.py` |
| Botón play de audio | **DOM**: `button[aria-label*="Reproducir"]` | triángulo por template matching | 🔮 Fase 3 | `test_runner.py::TestMatchBubbleToButton` |

## Sidebar y contactos

| Capacidad | Señal primaria | Fallback | Estado fallback | Test |
|---|---|---|---|---|
| Filas del sidebar (check-updates) | **DOM**: celdas chat-list → name/last_message/ts | OCR por bandas horizontales | 📋 (`session.py` inventario) | `test_runner.py` (check_updates) |
| Dirección inbound/outbound | **DOM**: íconos `msg-check`/`msg-dbl-check` | ticks por template matching | 🔮 Fase 3 | `test_runner.py` |
| Badge no-leídos | (no usado actualmente) | disco verde con dígitos por color | 📋 | — |
| Abrir/cerrar panel New Chat | **DOM**: `data-icon="new-chat-outline"`/`back-refreshed` | íconos por visión; Escape ya es fallback de cierre | parcial ✅ | `test_runner.py` |
| Lista de contactos completa | **DOM**: `[role="listitem"]` + scroll virtualizado | OCR del panel | 📋 | `test_runner.py` |

## Sesión y ciclo de vida

| Capacidad | Señal primaria | Fallback | Estado fallback | Test |
|---|---|---|---|---|
| Autenticación / QR | **DOM**: selectores `chat-list` / `qrcode` / `data-ref` | — | — | `test_session.py` |
| Daemon Chrome (vida/puerto) | PID + port files, CDP | scan local de sockets (ADR-008) | ✅ | `test_lazy_session.py` |
| Cola por sesión | flock POSIX (`queue.py`) | — | — | `test_lazy_session.py` |
| Viewport estable 1280×1920 DPR=1 | flags de Chrome (ADR-002) | — | — | `test_session.py::TestViewportRegression` |

## Cómo leer esta matriz cuando algo se rompe

1. Identificar la capacidad rota → fila.
2. Si la señal primaria es DOM: revisar el selector en el inventario de `session.py`.
3. Si el fallback está ✅: debería haber degradado solo (si no, es un bug).
   Si está 📋/🔮: el diseño del fallback está descripto aquí y en `session.py`;
   implementarlo es la corrección de fondo (ver fase del plan).
