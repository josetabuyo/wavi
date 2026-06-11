"""
debug_audio.py — Prueba rápida del flujo click + blob en el daemon activo.

Uso:
    python debug_audio.py                        # usa sesión 'default'
    python debug_audio.py data/sessions/default  # ruta explícita
"""
import asyncio
import sys
from pathlib import Path

PROFILE  = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/sessions/default")
CONTACT  = sys.argv[2] if len(sys.argv) > 2 else "Gregorio tabuyo"


async def main():
    from wavi.session import _BLOB_INIT_SCRIPT, WASession

    s = WASession(PROFILE)
    status = await s.connect()
    print(f"session status: {status}")

    if status == "qr_needed":
        print("[!] Necesitás escanear el QR. Corré 'wavi connect' primero.")
        await s.close()
        return

    print(f"Navegando a '{CONTACT}'...")
    await s.navigate_to_contact(CONTACT)

    # 1. Verificar cuántos botones play hay en pantalla
    buttons = await s.eval("""
    () => {
        const labels = ['Reproducir mensaje de voz', 'Play voice message', 'reproducir'];
        return [...document.querySelectorAll('button[aria-label]')]
            .filter(b => {
                const l = (b.getAttribute('aria-label') || '').toLowerCase();
                return labels.some(lbl => l.includes(lbl.toLowerCase()));
            })
            .map(b => {
                const r = b.getBoundingClientRect();
                return {
                    label: b.getAttribute('aria-label'),
                    vx: Math.round(r.left + r.width / 2),
                    vy: Math.round(r.top + r.height / 2),
                    visible: r.width > 0 && r.height > 0,
                };
            });
    }
    """)
    print(f"\nPlay buttons in DOM: {len(buttons)}")
    for b in buttons:
        print(f"  {b}")

    if not buttons:
        print("\n[!] No play buttons found. ¿Está abierto el chat correcto?")
        await s.close()
        return

    # 1b. Obtener DPR
    dpr = await s.get_dpr()
    print(f"\nDevice pixel ratio: {dpr}")

    # Mostrar qué bubbles coinciden con cada botón
    from wavi.vision import HEADER_PX
    print("\nBotones con coordenadas físicas equivalentes:")
    for b in buttons:
        phys_y = int(b['vy'] * dpr)
        crop_y = phys_y - HEADER_PX
        print(f"  CSS({b['vx']},{b['vy']}) → phys({int(b['vx']*dpr)},{phys_y}) → crop_y={crop_y}")

    # 2. Instalar monitor de blobs lazy
    result = await s._page.evaluate(_BLOB_INIT_SCRIPT)
    print(f"\nBlob monitor: {result!r}  (None = primera instalación, ya instalado no devuelve nada)")

    # Limpiar blobs anteriores
    await s.reset_blobs()

    # 3. Click en el botón más visible (primer vy > 50)
    visible = [b for b in buttons if b['vy'] > 50]
    if not visible:
        print("[!] Todos los botones están fuera del viewport (vy <= 50)")
        await s.close()
        return
    btn = visible[0]
    print(f"\nClickeando botón en CSS ({btn['vx']}, {btn['vy']}) ...")
    await s._page.mouse.click(btn["vx"], btn["vy"])
    await s._page.wait_for_timeout(3000)

    blobs = await s.drain_blobs()
    print(f"Blobs capturados: {len(blobs)}")
    for blob in blobs:
        print(f"  {blob['url'][:80]}  ts={blob['ts']}")

    if not blobs:
        print("\n[!] Sin blobs — posibles causas:")
        print("    - El audio ya estaba cacheado y WA no llama createObjectURL de nuevo")
        print("    - El click no llegó al botón (ver screenshot)")
        shot = await s._page.screenshot(type="png")
        out_dir = Path("output/debug")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "after_click.png").write_bytes(shot)
        print(f"    screenshot guardado en {out_dir / 'after_click.png'}")
    else:
        blob_url = blobs[-1]["url"]
        print(f"\nDescargando blob: {blob_url[:60]}...")
        data = await s.fetch_blob(blob_url)
        if data:
            out_dir = Path("output/debug")
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / "audio.ogg"
            out.write_bytes(data)
            print(f"Audio guardado: {out}  ({len(data)} bytes)")
        else:
            print("[!] fetch_blob devolvió None")

    await s.close()


asyncio.run(main())
