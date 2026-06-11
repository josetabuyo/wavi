# ADR-003: Chrome como daemon de larga vida

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

WhatsApp guarda su estado de autenticación en IndexedDB dentro del user-data-dir
de Chrome. Matar Chrome en medio de una sesión corrompe IndexedDB y fuerza
re-autenticación por QR.

## Decisión

`wavi connect` inicia Chrome una sola vez como proceso background. Todos los
demás comandos se conectan/desconectan vía CDP sin matar Chrome nunca. El
shutdown se hace solo con `wavi stop`, que navega a `about:blank` primero para
que WA haga flush de IndexedDB, y recién entonces envía SIGTERM (SIGKILL solo
tras 10s de espera).

## Consecuencias

- Conectar/desconectar Playwright es barato; reiniciar Chrome es caro y con
  riesgo de pérdida de sesión.
- Nunca usar `kill -9` directamente sobre un Chrome con sesión WA.
- Los comandos lazy (`_lazy_session`) auto-inician y auto-detienen Chrome solo
  si no había daemon previo.
