# Handoff — media, edit y blindaje de send (pedido de DataLake)

**Fecha:** 2026-10-08
**Versión:** v0.6.0 (PyPI `wavi-lib`). Suite verde (283 passed, 26 skipped), ruff limpio.
**Origen:** reporte de bugs y pedido de DataLake (agente LAS que usa wavi sobre la sesión
`default` para el cliente Data Lake), 2026-10-04 → 2026-10-08.

---

## Qué se hizo

### Features nuevas

| Comando | Qué hace | Commit |
|---|---|---|
| `wavi media [session] <chat> [--type all\|video\|image] [--from AAAA-MM-DD] [--limit N]` | Baja fotos y videos **completos** (no miniaturas) a `<output>/<session>/<chat>/media/` + `media.json` | `9cbf28f` |
| `wavi edit [session] <chat> <fragmento> <texto nuevo> [--fragment]` | Edita un mensaje propio dentro de la ventana de 15 min de WA | `fb3a602` |

**Cómo funciona `media`:** abre el visor de medios de WA sobre la burbuja de media más nueva
(`image-thumb` / `video-content`) y lo recorre con ← (más nuevo → más viejo). Fotos: el
`<img src="blob:">` más ancho del visor. Videos: el `<video>` apunta a
`/stream/video?key=…` del service worker de WA, que responde 206 en tramos de ~1.5 MB;
`_fetch_stream` lo lee entero con `Range`. El header del visor da remitente y
"Hoy a la(s) 11:26 a. m." → `parse_viewer_when`. Corta en `--from`, en `--limit` o cuando
← ya no cambia de ítem (espera 15 s para confirmar el final). Re-correr saltea lo ya bajado
(key del video o sha1 de la foto). Validado en vivo: video de 0:37 de Matias Becerro en
"DATA LAKE - Técnico" → h264 1920x1080 + aac, 37.8 MB.

**Cómo funciona `edit`:** mensajes propios = filas de `#main [data-id]` con la etiqueta oculta
`Tú:`/`You:`. Hora de envío desde `data-pre-plain-text` (`[5:35 p. m., 8/10/2026] …`).
Exige exactamente un match (sin tildes/mayúsculas); falla antes de tocar nada si hay 0, ≥2 o
pasaron 15 min. Menú del mensaje → *Editar* → diálogo con editor prellenado → reemplaza,
verifica el texto del editor, guarda ("Enviar mensaje editado") y relee el chat
(`verified`, exit 2 si no lo puede confirmar). Validado en vivo en el chat propio.

### Bugs corregidos (reporte de DataLake)

| # | Bug | Fix | Commit |
|---|---|---|---|
| 1 | La búsqueda tipeó el nombre en la caja de mensaje del chat abierto (quedó borrador en "DATA LAKE - Gerencia") | `search_contacts` verifica que el foco no siga en `#main`; reintenta 1 click, si no aborta sin tipear | `032933b` |
| 2 | `open_search_result` abrió el chat equivocado | No era bug: la verificación de header lo detectó y reintentó | — |
| 3 | `--newest` asignó 2026-10-03 a una respuesta del 04 | `_fill_missing_dates` no rompe la cronología (hora < ancla vieja → día +1) | `d9bfc11` |
| 4 | Listas numeradas salían `2. 2.` | WA autocontinúa la lista tras Shift+Enter; `_absorb_list_autoprefix` lo absorbe o borra | `e76f9a9` |
| 5 | `history_bubbles.json` (con credenciales) se escribía en el cwd del llamador | Output central: `$WAVI_OUTPUT_DIR` › `output/` del repo › `~/.local/share/wavi/output` | `1932186` |
| 6 | `send` se comió la "M" de "Matías" | `send_message`: rechaza si hay borrador, espera foco, compara el texto antes de Enter (1 reintento, si no aborta) | `0f9840b` |
| — | El chat propio ("José Tabuyo (Tú)") no aparecía en la búsqueda | Es `message-yourself-row`, no `cell-frame-container` | `e76f9a9` |

El 6 no se pudo reproducir; la causa más probable es tipeo antes de que la caja tome foco.
El blindaje lo cubre aunque la causa fuera otra: nunca se envía un texto distinto al pedido.

### Otros
- El daemon de `default` murió el 2026-10-05: segfault de Chrome a las 11:44 (stack overflow)
  después de que Chrome se auto-actualizara a 154 con el proceso corriendo desde el 24/09.
  No es bug de wavi; un daemon de varios días puede volver a caer tras un update de Chrome.
- `.las-agent.json`: `short_description`/`long_description` completados.
- Skill `resume-editor` (fuera del repo) apunta a la carpeta de output central.

---

## Pendiente

1. **Política vision-first:** `media` y `edit` usan DOM (testids `image-thumb`,
   `video-content`, `media-viewer-modal`, `data-pre-plain-text`, `aria-label` "Tú:" y del menú).
   Son puente: para *bajar bytes* no hay alternativa a la página, pero *encontrar* la burbuja de
   media y el mensaje propio debería migrar a `vision_grounding.py` como el resto.
2. **Locale:** fechas de `data-pre-plain-text` y del visor se leen día-primero (WA en español).
   Una sesión en inglés-US (mes-primero) leería mal fechas ambiguas como 5/10.
3. **`media` solo ve el chat cargado** para encontrar la primera burbuja (sube hasta 40 scrolls);
   después el visor recorre todo el chat. Documentos/PDF no se bajan (no aparecen en el visor).
4. **Remitente en `media`** es el nombre corto del header del visor ("Matias"), no el de la
   burbuja ("Matias Becerro").
5. `edit` solo busca entre los mensajes cargados al abrir el chat (los recientes); alcanza para
   la ventana de 15 min.

## Cómo retomar

```bash
cd ~/Development/wavi
uv run pytest -q                        # 283 passed esperado
uv run wavi media default "<chat>" --type video --limit 1
uv run wavi edit default "<chat>" "<fragmento>" "<nuevo>" --fragment
```

Para probar `edit`/`send` sin molestar a nadie: el chat propio ("José Tabuyo"). Los scripts de
exploración que se usaron (abrir visor, recorrer con ←, abrir el diálogo de edición y cancelar)
siguen el patrón de `WASession(P).connect()` + `session_lock`, sin tocar el daemon.
Antes de cualquier cosa con la sesión: skill `wa-session-guard`.
