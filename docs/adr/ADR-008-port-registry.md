# ADR-008: Registry de puertos vía Local Agent Society

**Estado:** Aceptado
**Fecha:** 2026-05 (formalizado como archivo 2026-06-11)

## Contexto

Múltiples sesiones wavi (y otros agentes locales) comparten el rango de puertos
CDP 9200–9249. Dos sesiones iniciando a la vez pueden colisionar en el mismo
puerto.

## Decisión

Reclamar puertos del registry de la Local Agent Society (`http://localhost:8700`)
con fallback en tres niveles:

1. `POST /ports/claim` — atómico (preferido).
2. `GET /ports/free` + `POST /ports` — dos pasos.
3. Scan local de sockets — sin registry, sin society.

El puerto se libera (`DELETE /ports/<port>`) en `wavi stop`.

## Consecuencias

- Sin carreras de puerto entre sesiones concurrentes.
- La herramienta funciona igual sin el daemon de la society (nivel 3).
- El puerto de cada sesión persiste en `chrome_daemon.port` dentro del profile.
