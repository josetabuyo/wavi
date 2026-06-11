# Checklist de auditoría — valores arcodeados y deuda

Derivado de `docs/plan-mejoras.md` §2–§3 y §5 (2026-06-11). Marcar al resolver;
cada ítem referencia la fase del plan donde se ataca.

## Geometría (Fase 2 salvo indicado)

- [ ] `SIDEBAR_PX = 580` ratio 580/1280 — detectar divisoria por gradiente (`vision.py`, `session.py`)
- [ ] `HEADER_PX = 60` fijo — detectar borde del header (`vision.py`)
- [ ] `footer_px = 70` fijo — detectar compose box (`element_detector.py`)
- [ ] `SEARCH_X=317, SEARCH_Y=80` clic ciego — detectar search box visualmente (Fase 3) (`session.py`)
- [x] `FIRST_RESULT_X/Y` — código muerto, eliminado — 2026-06-11
- [ ] Cruz de play estimada `x+93/x+38, y+h−37` — reemplazar con template matching (Fase 3) (`vision.py`)

## Colores (Fase 2)

- [ ] Máscara verde `G>200, G−R>15, G−B>15` solo tema claro (`element_detector.py`)
- [ ] Máscara blanca `RGB>248` solo tema claro (`element_detector.py`)
- [ ] **Modo oscuro → 0 burbujas sin error** — paleta dinámica por calibración
- [ ] Agregar caso de corpus en tema oscuro al habilitarlo

## Locale (Fase 2)

- [ ] `RE_TIME`/`RE_TIME_END`/`RE_CORE_TIME` requieren "a./p. m." — **formato 24h no extrae ningún timestamp** (`vision.py`)
- [ ] `RE_AUDIO_DUR` matchea horas 24h como duración de audio → texto clasificado audio (`vision.py:38`)
- [ ] `_split_bubbles_by_timestamps` depende de los regex 12h — burbujas fusionadas en 24h
- [ ] `RE_NOISE` "Escribe un mensaje" solo ES (`vision.py:39`)
- [ ] aria-labels play solo ES/EN (`runner.py:28`)
- [ ] `language="es"` fijo en transcripción (`transcription.py:33`)
- [ ] Meses/días solo ES/EN en `_date_from_pill_text`
- [ ] Agregar casos de corpus 24h y EN al habilitarlos

## Umbrales de morfología (Fase 2/3, con evidencia del corpus)

- [ ] `gap_px=7`, min 30×50px, aspect>12, densidad 0.15/0.08, pill h<38 centrada 0.35–0.65, merge 8/120px — re-expresar relativos a line-height medido

## Funcional

- [ ] Burbujas media (foto/video) no detectadas — varianza local (Fase 3)
- [ ] Dedup depende de `data-id` DOM para corrección — agregar dhash (Fase 3)

## Estructura (Fase 1)

- [ ] `cli.py` (~1170 líneas) → extraer `society.py`, `chrome.py`, `qr_pages.py`
- [ ] `capture_full_history` 330 líneas → extraer lógica pura a `history.py`
- [x] Código muerto: `_classify_x`, `detect_day_pills` visual, `FIRST_RESULT_*` eliminados — 2026-06-11
- [ ] Duplicación: `_kill_port` × 2; redraw de debug × 2
- [x] `session_lock` agregado en check-updates y list-contacts — 2026-06-11
- [ ] Ciclo de vida connect/close inconsistente entre comandos del runner
- [ ] Constantes dispersas → `config.py`
- [x] pyproject: dev-deps unificadas; ruff configurado y limpio (E/F/W/I/B/UP); CI en `.github/workflows/test.yml` — 2026-06-11
- [x] `debug_audio.py` movido a `scripts/` — 2026-06-11

## Documentación (Fase 1)

- [x] boarding.html: check-updates reescrito (algoritmo DOM, 2 archivos de salida, diagrama nuevo) — 2026-06-11
- [x] boarding.html: list-contacts actualizado a scroll completo (×3 lugares) — 2026-06-11
- [x] boarding.html: QR corregido a `data/qr.html` — 2026-06-11
- [x] docstring `cli.py check_updates` corregido — 2026-06-11
- [x] docstring `extract_sidebar_updates` corregido — 2026-06-11
- [x] ADR-001…008 extraídos a `docs/adr/` — 2026-06-11
- [x] `docs/capability-matrix.md` creado (rol de RTM) — 2026-06-11

## Fase 0 — estado

- [x] OCR compilado a binario arm64 (`make ocr`, fallback automático al script) — 2026-06-11
- [x] Instrumentación de timing (`WAVI_TIMING=1`) — 2026-06-11
- [x] Harness de corpus + 4 casos locales baseline (`make corpus`) — 2026-06-11
- [ ] Revisar a mano los `expected.json` sembrados (poner `"reviewed": true`)
- [ ] Ampliar corpus: tema oscuro, 24h, EN, media (al habilitar cada uno)

### Baseline de performance medido (2026-06-11, M-series, screenshot 1280×1920, 12 burbujas)

| Métrica | Script interpretado (Rosetta) | Binario arm64 |
|---|---|---|
| Arranque por llamada OCR | ~1.6 s | ~0.27 s |
| 1 llamada OCR pantalla completa | 3.5 s | 1.9 s |
| `analyze()` completo (16 llamadas OCR) | ~30 s estimado | **6.9 s** |
| Desglose binario | — | scan 2.4s · detect 0.07s · OCR burbujas 4.4s (90% del total es OCR) |

Próximo techo de optimización: OCR persistente (daemon/pyobjc), Fase 5.
