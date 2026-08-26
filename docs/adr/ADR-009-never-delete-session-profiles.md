# ADR-009: Nunca borrar un directorio de perfil de sesión

**Estado:** Aceptado
**Fecha:** 2026-08-18

## Contexto

`wavi connect --new` detecta el teléfono recién autenticado y renombra el
perfil temporal al número. Cuando ya existía un perfil con ese nombre (el
caso normal de re-autenticar un número existente), el código hacía:

```python
shutil.rmtree(phone_profile, ignore_errors=True)
profile.rename(phone_profile)
```

Es decir: **borraba sin posibilidad de recuperación** el directorio de
perfil de Chrome/Playwright de la sesión anterior — incluyendo el
`IndexedDB` con los tokens de autenticación de WhatsApp — antes de mover el
nuevo perfil en su lugar. No había paso intermedio, ni backup, ni
confirmación.

Esto pasó en la práctica más de una vez: cualquier corrida de `--new`
(intencional, o por una detección de teléfono equivocada que forzaba el
fallback) destruía la sesión previa. Sumado al incidente separado del
2026-07-01 (`clearDataForOrigin` + `Page.reload` externo, ver
`.claude/skills/wa-session-guard/SKILL.md`), esto convirtió la pérdida de
sesión en un riesgo recurrente en vez de un accidente aislado — inaceptable
para una herramienta cuyo propósito es *no* arriesgar la cuenta de
WhatsApp del usuario.

## Decisión

**Ningún comando de wavi puede borrar (`rmtree`/`unlink` de directorio
completo) un directorio de perfil de sesión, bajo ninguna circunstancia,
nunca — ni siquiera con `--new` o `--force`.**

En su lugar:

- `wavi connect --new` **archiva** (`Path.rename`) el perfil existente a
  `<numero>_archived_<timestamp>` antes de mover el nuevo en su lugar. El
  dato viejo queda en disco, íntegro, para siempre (o hasta que el usuario
  decida borrarlo a mano).
- Ningún flag, ninguna ruta de código, puede requerir borrado destructivo
  de un perfil para funcionar. Si hace falta "limpiar", se archiva.
- La única excepción son archivos de recuperación de crash de Chrome
  (`Last Session`, `Sessions/`, etc. dentro de `Default/`) en
  `_cleanup_crash_files()` — eso es metadata de restauración de pestañas,
  no autenticación, y no toca `IndexedDB`.

## Consecuencias

- Los directorios `data/sessions/` acumulan perfiles archivados con el
  tiempo. Es intencional: preferimos disco ocupado a una sesión
  irrecuperable. La limpieza manual de archivos viejos (`*_archived_*`,
  `*_bak`) es responsabilidad explícita del usuario, nunca automática.
- `wavi/tests/test_session.py::test_connect_never_deletes_session_profile_dir`
  hace un chequeo estático del source de `connect()` — si alguien
  reintroduce `shutil.rmtree` sobre un perfil ahí, el test falla en CI
  antes de que llegue a producción.
- Cualquier PR futura que toque `connect()`, `_cleanup_crash_files()`, o
  cualquier función con acceso a `DEFAULT_SESSIONS_DIR` debe releer este
  ADR antes de tocar código de borrado.
