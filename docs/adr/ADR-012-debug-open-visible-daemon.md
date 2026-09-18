# ADR-012: `wavi debug-open` — daemon visible bajo demanda para debug

**Estado:** Aceptado
**Fecha:** 2026-09-18

## Contexto

ADR-006 fija headless como el único modo del daemon persistente — correcto
para uso normal, pero deja un hueco real: cuando WA cambia su DOM (confirmado
2026-09-18, `_OPEN_NEW_CHAT_JS` roto — WA reemplazó el ícono lápiz por un
botón `+` sin `data-icon`) o hace falta inspeccionar visualmente algo que
está fallando, no hay forma de *ver* la sesión sin arriesgar dos Chrome
sobre el mismo perfil (la advertencia central de `wa-session-guard`:
"Never connect the same number twice simultaneously").

Antes de esta ADR, `_VISIBLE_CHROME_ARGS` existía en `cli.py` como código
muerto — alguien ya había anticipado esta necesidad sin resolverla.

## Decisión

`wavi debug-open <session>` lanza el daemon SIN `--headless=new`, mismo
perfil, mismo mecanismo de claim de puerto que `connect` (registry de la
Local Agent Society). Deliberadamente angosto para que dé confianza usarlo
seguido:

- Rechaza correr si el daemon ya está vivo (`wavi stop` primero, siempre).
- Rechaza correr si el perfil no está autenticado (no maneja QR — es para
  una sesión ya autenticada, no para el alta inicial).
- Una vez arriba, es un daemon normal: todos los comandos `wavi` existentes
  (`get`, `list-contacts`, `check-updates`, ...) se conectan igual, vía CDP.

El procedimiento completo, siempre en este orden:

```bash
wavi stop <session>          # cierre correcto del daemon headless
wavi debug-open <session>    # daemon visible, mismo perfil
# ... inspección / debug / captura de screenshots ...
wavi stop <session>          # cierre correcto del daemon visible
wavi connect <session>       # vuelve a headless (default, el único modo
                              # que debe quedar corriendo sin supervisión)
```

Ver la sección "Debuggear con el daemon visible" en la skill
`wa-session-guard` para el detalle operativo.

## Consecuencias

- Nunca dos Chrome sobre el mismo perfil: `debug-open` se niega a correr con
  el daemon vivo, igual que `connect`.
- El modo visible es siempre una excepción explícita y temporal, nunca el
  estado de reposo — `debug-open` no cambia el comportamiento default de
  `connect` (sigue siendo 100% headless-first, ADR-006 intacto).
- Habilitó, el mismo día, encontrar el selector roto real
  (`button[aria-label="Nuevo chat"]`, ver fix en `_OPEN_NEW_CHAT_JS`) y
  capturar el primer caso de corpus real para
  `parse_contacts_panel_rows()` (`tests/corpus/cases/nuevo_chat_panel_000/`)
  sin necesitar devtools ni acceso de otro tipo a la sesión headless.
