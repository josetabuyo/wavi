# ADR-010: Resolución de contacto con desambiguación, nunca adivinar

**Estado:** Aceptado
**Fecha:** 2026-08-26

## Contexto

`navigate_to_contact(contact)` escribía el nombre en el buscador de WA y
abría el primer resultado con `ArrowDown` + `Enter`, sin verificar nunca que
el chat correcto (o siquiera *un* chat) hubiera abierto. Dos problemas
reales, confirmados el mismo día:

1. **Timing:** justo después de vincular un dispositivo nuevo por QR, la
   lista de chats de WA Web todavía está sincronizando desde el teléfono.
   Una búsqueda ejecutada en ese instante puede no devolver resultados
   todavía. `ArrowDown` + `Enter` sobre una lista vacía no abre nada, deja
   la pantalla de bienvenida de WA en pantalla, y el pipeline de visión
   capturó ese banner ("Las llamadas y videollamadas ya están disponibles")
   como si fueran mensajes reales de "Rodolfo Prado".
2. **Ambigüedad real:** el mismo nombre visible puede corresponder a *más
   de una* entrada distinta — un chat existente, un contacto guardado con
   ese nombre, y contactos no guardados con ese mismo nombre pero distinto
   número. Buscar "Rodolfo Prado" mostró 1 chat + 4 contactos diferentes.
   `ArrowDown` una sola vez siempre elegía el primero de la lista, sin que
   nadie confirmara que era el correcto.

Ninguno de los dos casos producía un error — el código seguía adelante en
silencio y devolvía datos basura como si fueran la conversación pedida.

## Decisión

`navigate_to_contact` (usado por `wavi get` y `wavi send`) nunca abre un
chat sin antes:

1. Buscar el nombre y leer **todos** los resultados distintos
   (`WASession.search_contacts`), no solo el primero.
2. Si no hay resultados, refrescar la lista de contactos (abrir y cerrar
   "Nuevo chat" fuerza a WA a sincronizar) y reintentar una vez con una
   espera más larga.
3. Si sigue sin haber resultados, fallar con un error claro (nunca seguir
   con la pantalla de bienvenida).
4. Si hay más de una coincidencia distinta, **preguntarle a un humano**
   cuál es — nunca elegir por orden ni por posición. Sin terminal
   interactiva disponible (scripts, API HTTP), rechazar en vez de adivinar,
   listando las opciones para que quien llama sea más específico.
5. Después de elegir (o resolver sin ambigüedad), hacer clic directo sobre
   la fila resuelta — nunca contar `ArrowDown`s — y **verificar** que un
   chat real quedó abierto (`conversation-panel-messages` presente) antes
   de continuar.

## Consecuencias

- Cualquier acción de la CLI sobre "un contacto" imprime primero
  `Contacto confirmado: <nombre> — <detalle>` — visibilidad total de sobre
  quién se está operando antes de leer o enviar nada.
- Los tests de `wavi/session.py` (`TestSearchContacts`, `TestResolveContact`,
  `TestNavigateToContact`) cubren: cero resultados con refresh, ambigüedad
  con y sin TTY, y que el scroll/captura nunca se ejecuta si el chat no
  abrió de verdad.
- Costo: una búsqueda ambigua sin TTY (uso vía API HTTP o scripts) requiere
  que quien llama pase un identificador más específico en vez de confiar en
  que el primero de la lista sea el correcto.
