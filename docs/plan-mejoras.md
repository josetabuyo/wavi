# wavi — Análisis integral y plan de mejoras

**Fecha:** 2026-06-11 · **Estado del repo analizado:** main @ e95f033 (145 tests verdes)

Este documento responde cuatro preguntas: (1) ¿hasta dónde se puede llevar la visión?,
(2) ¿dónde hay valores arcodeados que comprometen la robustez?, (3) ¿cómo ordenar mejor
el proyecto?, (4) ¿qué oportunidades de visión de última generación aplican aquí?
Cierra con un plan en 6 fases ejecutable gradualmente.

---

## 1. Estudio: hasta dónde se puede llevar la visión

### 1.1 Techo teórico

Clasificando cada capacidad actual por su naturaleza física:

| Capacidad | ¿Visión pura posible? | Notas |
|---|---|---|
| Detectar/leer burbujas | ✅ Ya es visión | Núcleo actual |
| Clasificar tipo (text/audio/file/media) | ✅ Ya es visión | Media aún no detectado (§2.4) |
| Timestamps y fechas | ✅ Ya es visión | Frágil ante locale 24h (§2.3) |
| Ubicar botón play | ✅ Template matching del triángulo | Hoy DOM (aria-label) |
| Dirección inbound/outbound (ticks ✓✓) | ✅ Template matching | Hoy DOM (msg-check icons) |
| Botón send, new-chat, back | ✅ Iconos visualmente estables | Hoy DOM |
| Compose box | ✅ Franja inferior del panel | Hoy DOM (contenteditable) |
| Sidebar: nombre + preview + hora por fila | ✅ OCR por bandas horizontales | Hoy DOM |
| Badge de no-leídos | ✅ Disco verde con dígitos — trivial por color | Hoy DOM |
| Lista de contactos | ✅ OCR del panel | Hoy DOM |
| Scroll (acción) | ✅ `mouse.wheel(x, y, dy)` — evento de input, no DOM | Hoy `el.scrollTop` |
| Estado de scroll (¿llegué al tope/fondo?) | ⚠️ Proxy visual: contenido no cambia tras scroll / botón flotante visible | Hoy DOM, más preciso |
| Dedup entre pantallas | ⚠️ Posible sin DOM con hash perceptual del crop (dhash) + clave OCR | Hoy `data-id` es superior |
| **Bytes del audio (.ogg)** | ❌ Imposible por visión | Único insustituible: blob capture vía JS |
| Teclado/mouse | — | Son eventos de input, no DOM; ya compatibles |

**Conclusión del estudio:** el techo de la visión es ~95% del sistema. Lo único
físicamente insustituible es la captura de blobs de audio (JS hook sobre
`HTMLMediaElement` / `URL.createObjectURL`), que de todos modos usa APIs del browser
estándar, no el DOM de WA. El `data-id` para dedup y el `scrollTop` para precisión
conviene mantenerlos como **aceleradores opcionales**, no como dependencias: si WA
los rompe, el sistema debe degradar automáticamente a la vía visual (hash perceptual +
clave de contenido; proxy visual de scroll). Esa es la arquitectura objetivo:
**visión como camino primario o fallback garantizado en todo, DOM solo como acelerador
con detección de salud** (§5, Fase 4).

### 1.2 Cómo hacer el estudio "confiable": harness de evaluación

Hoy la afirmación "la visión funciona" se apoya en tests sintéticos (Pillow + numpy) y
en uso real no medido. Para sostener afirmaciones confiables hace falta un **corpus
dorado**: screenshots reales (anonimizables) etiquetados a mano, con métricas por
elemento:

- *Detección de burbujas:* precision/recall de bboxes (IoU ≥ 0.5).
- *OCR:* CER/WER contra texto de referencia.
- *Clasificación:* matriz de confusión text/audio/file/media.
- *Timestamps:* exactitud de fecha-hora.

Con eso, cada cambio de WA o de umbral se evalúa en segundos (`pytest -m corpus`) y el
"score de visión" queda versionado. Es la pieza que convierte la estrategia en ciencia
y es prerequisito para tocar umbrales con confianza (Fase 0).

---

## 2. Auditoría de valores arcodeados

### 2.1 Geometría (posiciones estrictas)

| Valor | Dónde | Riesgo | Mitigación propuesta |
|---|---|---|---|
| `SIDEBAR_PX = 580` (ratio 580/1280) | `vision.py:41`, `session.py` | **Alto** — el ancho del sidebar de WA no es proporcional al viewport en todos los anchos; un rediseño lo rompe silenciosamente | Detectar la divisoria vertical sidebar/chat por gradiente de color (una línea vertical de contraste constante); calibrar por sesión |
| `HEADER_PX = 60` | `vision.py:42` | Medio | Detectar el borde inferior del header (banda de color uniforme full-width) |
| `footer_px = 70` | `element_detector.py:70` | Medio | Detectar la caja de composición (banda clara inferior) |
| `SEARCH_X=317, SEARCH_Y=80` | `session.py:495` | **Alto** — clic ciego a coordenadas fijas | OCR del placeholder "Buscar" / detección del rect del search box; coordenadas fijas como fallback |
| `FIRST_RESULT_X/Y = 317/200` | `session.py:497` | — | **Código muerto** (la navegación usa ArrowDown+Enter) — eliminar |
| Cruz de play estimada `x+93 / x+38, y+h−37` | `vision.py:552` | Bajo (solo debug) | Reemplazar al implementar template matching del triángulo |
| `WINDOW 1280×1920, DPR=1` | ADR-002 | Aceptado y testeado | OK como base calibrada; todo lo derivado debe medir el screenshot real, no asumir |

### 2.2 Colores (la fragilidad más grande)

`element_detector.py` asume **tema claro**: verde `G>200, G−R>15, G−B>15`, blanco
`RGB>248`, fondo beige. **El modo oscuro de WA (burbujas ~#005c4b y ~#202c33) hace
que la detección devuelva cero burbujas sin error.** También un simple ajuste de
paleta de WA rompería los umbrales.

Mitigación (Fase 2): **calibración automática de paleta** — muestrear el fondo del
panel, extraer los 2-3 colores dominantes de regiones redondeadas alineadas a
izquierda/derecha (k-means liviano sobre el histograma), y construir las máscaras
dinámicamente. El principio actual ("tipo por color, no por posición x") se conserva,
pero el color se *mide* en runtime en vez de estar fijado. La posición x queda como
segundo voto (ya existe `_classify_x`, hoy sin uso productivo).

### 2.3 Locale e idioma

| Supuesto | Dónde | Efecto si cambia |
|---|---|---|
| Formato 12h con "a. m./p. m." | `RE_TIME`, `RE_TIME_END`, `RE_CORE_TIME` (`vision.py:25-27`) | **Con WA en formato 24h no se extrae NINGÚN timestamp** y `_split_bubbles_by_timestamps` deja de cortar burbujas fusionadas |
| `RE_AUDIO_DUR = \d:\d{2}` sin a/p | `vision.py:38` | En locale 24h, la hora "14:23" matchea como duración → texto clasificado como audio |
| "Escribe un mensaje" | `RE_NOISE` (`vision.py:39`) | Solo es ruido en ES |
| aria-labels 'Reproducir mensaje de voz'/'Play voice message' | `runner.py:28` | Otros idiomas de UI no encuentran botones play |
| `language="es"` | `transcription.py:33` | Transcripción forzada a español |
| Meses/días ES+EN | `_date_from_pill_text` | Otros idiomas no parsean pills |

Mitigación: soportar 24h (regex alternativo `\b([01]?\d|2[0-3]):\d{2}\b` con
desambiguación por posición: el timestamp está en la esquina inferior derecha de la
burbuja, la duración de audio junto al waveform), y un mini-módulo `locale.py` con los
patrones por idioma, detectando el locale una vez por sesión.

### 2.4 Umbrales de morfología

`gap_px=7`, alto mínimo 30px, ancho 50px, aspect ratio >12, densidad 0.15/0.08,
pill h<38 centrada 0.35–0.65, merge gap 8px/120px… Todos en píxeles absolutos
calibrados a 1280×DPR=1. Funcionan, están comentados (muy bien), y el ADR-002 los
protege — pero deberían expresarse **relativos a una unidad medida** (la altura de
línea detectada por OCR, ~34px hoy) para sobrevivir a cambios de densidad de UI.
Prioridad media: con el corpus de Fase 0 se pueden re-derivar con evidencia.

### 2.5 Limitación funcional conocida

Las burbujas de **media (foto/video)** no se detectan (color no uniforme). Está
documentado, pero es el hueco funcional más visible del pipeline: un historial con
fotos pierde esos mensajes por completo. Solución factible y liviana en §4.3.

---

## 3. Orden y arquitectura del código

Lo bueno (preservar): separación limpia visión-pura / sesión / orquestación; el
**inventario de DOM scraping con fallback visual documentado por constante** en
`session.py` es excelente práctica; comentarios con el *porqué*; 145 tests offline;
conftest que alimenta boarding.html; ADRs.

Problemas concretos:

1. **`cli.py` (1159 líneas) mezcla 4 responsabilidades:** comandos Click, cliente del
   registry de puertos (Society), lanzamiento/limpieza de Chrome, y ~130 líneas de
   plantillas HTML del QR inline. → dividir en `society.py`, `chrome.py`,
   `qr_pages.py` (o `templates/`), dejando `cli.py` solo con comandos.
2. **`capture_full_history` (330 líneas)** concentra scroll, anclaje, dedup, modo
   `--newest`, filtro `--from`, descarga de audio y renumeración. La lógica pura
   (acumulador de historia: claves, anclas, merge, renumeración) puede extraerse a un
   `history.py` sin Playwright → testeable directo y reutilizable.
3. **Código muerto:** `FIRST_RESULT_X/Y`, `_classify_x` (solo lo usan tests),
   `element_detector.detect_day_pills` (versión visual nunca llamada; se usa la OCR),
   `debug_audio.py` en la raíz (mover a `scripts/` o borrar).
4. **Duplicación:** `_kill_port` (session.py) ≈ `_kill_port_processes` (cli.py);
   redibujado de debug duplicado en `_redraw_debug_with_dom_positions` y
   `capture_audio_bubbles`.
5. **Lock de sesión inconsistente:** `get` y `send` toman `session_lock`, pero
   `check-updates` y `list-contacts` no — dos comandos concurrentes pueden pisarse
   el mismo Chrome.
6. **Ciclo de vida inconsistente:** `check_updates`/`list_contacts` hacen
   connect/close internamente; `get`/`send` lo hacen afuera. Unificar (el runner
   siempre administra, o nunca).
7. **Constantes dispersas:** SIDEBAR/HEADER en vision.py, WINDOW en session.py,
   footer en element_detector, umbrales inline. → módulo `geometry.py`/`config.py`
   único, preparado para recibir la calibración de Fase 2.
8. **`pyproject.toml`:** dev-deps duplicadas entre `[project.optional-dependencies]`
   (pytest) y `[dependency-groups]` (pytest-asyncio); unificar. Falta config de ruff
   (el Makefile lo invoca "si existe") y no hay CI.

---

## 4. Oportunidades de visión de última generación (livianas)

Orden por relación impacto/esfuerzo:

### 4.1 OCR: eliminar el cuello de botella del subproceso Swift
Cada `_run_ocr` ejecuta `swift ocr_vision.swift` → el intérprete recompila el script
en cada llamada (~0.5–1.5s de arranque). Un screenshot dispara 1 scan estructural
(≥4 tiles) + 1 OCR por burbuja (~10) ≈ **15 procesos Swift por pantalla**; en un
historial de 30 iteraciones son ~450 arranques. Opciones:
- **Mínimo (1 hora):** `swiftc -O ocr_vision.swift -o bin/ocr_vision` en el Makefile
  → ~10× menos latencia de arranque. Sin cambiar nada más.
- **Óptimo:** modo daemon (lee rutas por stdin, responde JSON por stdout, proceso
  persistente por corrida) o llamar Vision in-process vía `pyobjc-framework-Vision`.
- Además: el Swift ya devuelve `confidence` y Python lo descarta — usarlo para
  filtrar ruido en lugar de heurísticas regex adicionales.

### 4.2 Banco de templates de iconos (la apuesta de tu tesis)
Tu intuición es correcta: el triángulo de play, los ticks ✓/✓✓, el micrófono, la
flecha de send son **invariantes perceptuales**. Implementación liviana sin
dependencias nuevas: normalized cross-correlation con `scipy.signal.fftconvolve`
(o `cv2.matchTemplate` si se acepta opencv) sobre el **mapa de bordes** (gradiente),
no sobre color crudo → inmune a temas claro/oscuro. Templates de ~20×20px, match
multi-escala (0.8×–1.2×). Habilita: play button sin DOM, dirección inbound/outbound
sin DOM, y clasificación de audio por presencia de triángulo (más robusto que el
regex de duración).

### 4.3 Detección de burbujas media (cerrar el hueco funcional)
Fotos/videos = regiones rectangulares de **alta varianza local** sobre fondo
uniforme. Máscara: varianza local (filtro de ventana con scipy) > umbral, mismas
componentes conexas que hoy. Con el corner del bubble redondeado y la alineación
izquierda/derecha se obtiene sender. El bubble se reporta como `msg_type="media"`
con bbox (texto vacío) — deja de perderse el mensaje.

### 4.4 Dedup por hash perceptual
Tercera clave de dedup (tras `dom_id` y clave OCR): **dhash de 64 bits del crop del
bubble** (Pillow puro, 10 líneas). Es estable entre screenshots de overlap, no
depende ni del DOM ni de la varianza del OCR. Reduce la dependencia de `data-id`
a cero para corrección (queda como acelerador).

### 4.5 Calibración automática (`wavi calibrate`)
El antídoto general contra los arcodeos de §2: comando que abre la sesión, mide y
persiste `calibration.json` por sesión: ancho real del sidebar (gradiente vertical),
altura de header/footer, paleta de burbujas (k-means), formato horario detectado
(12h/24h), idioma de UI. Todos los módulos leen calibración con los valores actuales
como default. Re-ejecutable tras cualquier update de WA.

### 4.6 Escalación opcional a VLM (mantenerlo liviano)
Para mantener el sistema "de última generación" sin volverlo pesado: un nivel de
escalación **solo ante fallo** — si una región no se pudo clasificar o el OCR da
confianza baja, enviar ese crop (no la pantalla) a un VLM (Claude Haiku o un modelo
local tipo moondream). Apagado por default, activable con flag. El 99% del trabajo
sigue siendo CV clásico de milisegundos; el VLM es el paracaídas semántico.

### 4.7 Scroll por input en vez de DOM
`page.mouse.wheel(x, y, delta)` sobre el panel de chat reproduce el scroll humano sin
tocar `scrollTop`. Menos preciso (se compensa con el ancla, que ya existe), pero
elimina otra dependencia del DOM y es indistinguible de un usuario real.

---

## 5. Documentación

1. **Drift en boarding.html** (es estático por diseño — se corrige contenido, no se
   dinamiza):
   - *check-updates:* describe pixel-diff del sidebar + badges `icon-unread-count` +
     rotación `snapshot_prev.png`. El código real es 100% DOM
     (`extract_sidebar_updates`), compara last_message+direction, y **nunca escribe
     snapshot_prev.png** (el docstring de `cli.py:1076` también lo promete). README sí
     está correcto.
   - *list-contacts:* dice "scroll not yet implemented (~30 contactos)" pero
     `_scroll_all_contacts` existe y se usa (aparece dos veces, en Quick start §6 y
     en la sección de comando).
   - *QR:* dice `/tmp/wavi_qr.html`; el código escribe `data/qr.html`.
   - El docstring de `WASession.extract_sidebar_updates` describe el retorno viejo
     (`{name, unread_count}`) — hoy devuelve `{name, last_message, timestamp, direction}`.
2. **ADRs:** existen ADR-001…008 inline en boarding pero solo ADR-002 como archivo.
   Extraer los 8 a `docs/adr/` (fuente de verdad) y que boarding los resuma.
3. **Matriz de capacidades (rol de RTM):** elevar el inventario de `session.py` a
   `docs/capability-matrix.md`: capacidad → señal primaria → fallback → estado
   (implementado/diseñado/pendiente) → test que la cubre. Es la trazabilidad
   requisito→implementación→test que hoy vive fragmentada.
4. **README:** agregar `wavi boarding`, `bubbles` y la fila de `send --screenshot-out`
   ya está; documentar GROQ_API_KEY (hoy solo en boarding).

---

## 6. Plan por fases

### Fase 0 — Medir antes de tocar (fundación del estudio confiable) ✅ 2026-06-11
1. ~~Compilar el OCR a binario~~ → `make ocr` → `bin/ocr_vision` (arm64 nativo;
   `vision.py` lo usa automáticamente con fallback al script). `analyze()` pasó de
   ~30s a **6.9s** por pantalla.
2. ~~Harness de corpus~~ → `tests/test_corpus.py` + `tests/corpus_utils.py` +
   `scripts/make_corpus_case.py`; 4 casos locales sembrados (gitignorados por
   privacidad). Correr con `make corpus`. **Pendiente:** revisar a mano los
   `expected.json` y ampliar cobertura (oscuro/24h/EN/media) en Fases 2–3.
3. ~~Timing por etapa~~ → `WAVI_TIMING=1` imprime desglose
   (crop/scan/detect/ocr) por `analyze()`. Baseline documentado en
   `docs/audit-checklist.md`.
4. ~~Checklist de auditoría~~ → `docs/audit-checklist.md`.

### Fase 1 — Higiene y estructura (riesgo bajo, todo verde siempre) — parcial 2026-06-11
1. ~~Borrar código muerto~~ ✅ (`FIRST_RESULT_*`, `detect_day_pills` visual,
   `_classify_x` + sus tests; `debug_audio.py` → `scripts/`).
2. Dividir `cli.py` → `society.py`, `chrome.py`, `qr_pages.py`; unificar `_kill_port`. ⏳
3. Extraer lógica pura de `capture_full_history` → `history.py` + tests directos. ⏳
4. ~~`session_lock` en check-updates y list-contacts~~ ✅; unificar ciclo de vida
   connect/close. ⏳
5. `config.py` con todas las constantes de geometría/umbral (preparado para Fase 2). ⏳
6. ~~pyproject + ruff + CI~~ ✅ (dev-deps unificadas, ruff E/F/W/I/B/UP limpio,
   `.github/workflows/test.yml` con lint+test en ubuntu).
7. ~~Documentación~~ ✅ (drift de boarding corregido, ADR-001…008 en `docs/adr/`,
   `docs/capability-matrix.md` creado).

### Fase 2 — Calibración sobre constantes (núcleo de robustez)
1. `wavi calibrate` + `calibration.json` por sesión (§4.5).
2. Detección de la divisoria del sidebar y header por gradiente (reemplaza 580/60).
3. Paleta dinámica de burbujas → **soporte de modo oscuro** (validado con corpus).
4. Locale: timestamps 24h, patrones de ruido por idioma, `language` configurable en
   transcripción.

### Fase 3 — Profundizar visión (reemplazar señales frágiles)
1. Banco de templates de iconos sobre mapa de bordes (§4.2): play, ticks, send.
2. Detección de burbujas media por varianza local (§4.3).
3. Dedup por dhash (§4.4) como tercera clave.
4. Parser visual del sidebar (bandas + badge verde + tick) — fallback completo de
   check-updates.
5. Búsqueda de contacto sin coordenadas fijas: detectar search box (reemplaza 317,80).

### Fase 4 — Auto-fallback y resiliencia (la tesis hecha sistema)
1. Cada señal DOM del inventario se envuelve en un "signal" con fallback visual
   automático: si el selector devuelve vacío/lanza, se usa visión y se loguea.
2. `wavi doctor`: ejecuta todas las señales contra la sesión viva y reporta qué
   selectores DOM siguen vivos y qué fallbacks están listos — el radar de cambios
   de WA.
3. Telemetría local simple (qué camino se usó por operación) para decidir cuándo
   jubilar una señal DOM.

### Fase 5 — Última generación opcional
1. Escalación VLM ante baja confianza (flag, apagado por default) (§4.6).
2. Scroll por `mouse.wheel` como modo alternativo (§4.7).
3. OCR in-process (pyobjc) o daemon persistente si el binario compilado no alcanza.
4. Generalización: extraer el núcleo visual (detector + OCR + templates + calibración)
   a un paquete agnóstico de WA — la "gramática visual de chats" aplicable a
   Telegram/Slack que postula la Philosophy del boarding.

✱ = puede hacerse hoy mismo sin riesgo.

**Criterio transversal:** ninguna fase rompe la suite; cada cambio de visión se valida
contra el corpus de Fase 0 antes de mergear; boarding.html se actualiza en la misma PR
que cambia el comportamiento que describe (regla anti-drift).
