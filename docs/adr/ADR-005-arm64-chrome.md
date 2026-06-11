# ADR-005: Chrome ARM64 nativo en macOS

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

En Apple Silicon, Chrome lanzado sin arch explícito puede correr bajo Rosetta
(emulación x86). El service worker y el IndexedDB de WA Web se comportan de forma
inconsistente bajo Rosetta: la sesión aparece autenticada pero la lista de chats
nunca carga (congelada).

## Decisión

Lanzar Chrome siempre con `arch -arm64` (en `wavi connect` y en el fallback de
`WASession.connect()`).

## Consecuencias

- Sesiones estables; sin cuelgues de chat-list.
- El mismo principio aplica a otros binarios: el OCR Swift también se compila
  arm64 nativo (`make ocr`) — bajo Rosetta, Apple Vision rinde peor y devuelve
  resultados ligeramente distintos.
