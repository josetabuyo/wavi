# Corpus dorado de visión

Screenshots reales de WA Web con salida esperada revisada a mano. Es la base de
evidencia para tocar umbrales del pipeline con confianza (Fase 0 del plan,
`docs/plan-mejoras.md` §1.2).

## Estructura

```
tests/corpus/
  README.md            ← este archivo (trackeado)
  cases/               ← GITIGNORADO — conversaciones reales, nunca commitear
    <nombre_caso>/
      screenshot.png   ← screenshot 1280×1920 del viewport completo
      expected.json    ← burbujas esperadas + thresholds opcionales
```

## Crear un caso

```bash
python scripts/make_corpus_case.py output/<sesión>/<chat>/iter_001/screenshot.png mi_caso
```

El `expected.json` generado es la **salida actual del pipeline** (baseline de
regresión). Para convertirlo en ground truth real: abrir el screenshot al lado
del JSON, corregir sender/type/text/timestamp erróneos y poner `"reviewed": true`.

## Correr la evaluación

```bash
make corpus                                   # o:
WAVI_CORPUS=1 pytest tests/test_corpus.py -v
```

Está gateado con `WAVI_CORPUS=1` porque cada caso corre OCR real (~5–10 s,
solo macOS). No corre en `make test`.

## Métricas (tests/corpus_utils.py)

| Métrica | Qué mide | Mínimo default |
|---|---|---|
| `precision` / `recall` | detección de bboxes, match por IoU ≥ 0.5 | 0.90 |
| `sender_acc` | me/other correcto en pares matcheados | 0.95 |
| `type_acc` | text/audio/file/media correcto | 0.90 |
| `timestamp_acc` | hora del día (HH:MM) correcta — la fecha se ignora porque los pills "Hoy/Ayer" derivan de `date.today()` | 0.80 |
| `text_sim` | similitud media del texto OCR (SequenceMatcher) | 0.85 |

Overrides por caso: `"thresholds": {"recall": 0.8}` en `expected.json`
(útil para casos difíciles conocidos, p. ej. con burbujas media).

## Casos desafío (xfail)

Para screenshots que el pipeline **todavía no resuelve** (tema oscuro, locale
24h, fotos/videos): etiquetar el `expected.json` a mano con lo que *debería*
detectarse y agregar:

```json
"xfail": true,
"xfail_reason": "modo oscuro — pendiente Fase 2 (paleta dinámica)"
```

El caso corre e imprime sus métricas en cada `make corpus` (se ve el progreso),
pero no rompe la suite. Cuando la capacidad se implementa, las métricas suben,
se quita el flag y el caso pasa a ser guardia de regresión. Es TDD a nivel
visión: primero el desafío, después la capacidad.

## Cobertura buscada

Al menos un caso de cada situación: tema claro, **tema oscuro**, locale **24h**,
UI en inglés, chat con audios, chat con archivos, chat con fotos/videos (media),
mensajes de una línea, mensajes largos multilínea, pills de fecha variados.
Hoy el corpus se siembra con tema claro/ES/12h — el resto se agrega al habilitar
cada capacidad (Fases 2–3).
