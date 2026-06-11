# ADR-007: Transcripción después de cerrar el browser

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

Las llamadas a la API de Groq tardan 1–3s cada una. Ejecutarlas dentro del event
loop de Playwright con Chrome abierto arriesga timeouts e intercala operaciones
async de forma difícil de predecir.

## Decisión

`transcribe_history_audios()` corre como segunda pasada después de
`runner.close()`: lee `history_bubbles.json`, transcribe los `.ogg` ya
descargados en serie, y reescribe el JSON con los transcripts.

## Consecuencias

- Scroll y captura deterministas, sin bloqueos de Playwright.
- La transcripción es re-ejecutable (reintentos de fallos, o si faltaba
  `GROQ_API_KEY` durante el scraping).
- Fallback local: pywhispercpp si Groq falla o no hay API key.
