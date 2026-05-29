"""
element_detector.py — Detecta bubbles de WhatsApp Web por color de imagen.

Estrategia:
  - Bubble "me" (enviado):    verde ~(217,253,211) → G domina: G−R>15 y G−B>15 y G>200
  - Bubble "other" (recibido): blanco ~(255,255,255) → min(R,G,B) > 248
  - Fondo del chat:           beige ~(243,238,231) → todo lo demás

El tipo se determina por color dominante, NO por posición x.
Se usa scipy.ndimage.label() para encontrar componentes conectadas de cada máscara
y find_objects() para obtener sus bounding boxes.

LIMITACIÓN CONOCIDA: bubbles de media (foto/video thumbnail) NO son color uniforme
→ la detección los pierde. Bubbles de archivo adjunto (xlsx, mov) son blancos/rectangulares
→ se detectan como "other" o se fusionan con el bubble contenedor. No se intenta
resolver esto en este POC.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage


# ─── Umbrales de color ───────────────────────────────────────────────────────

def _build_masks(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Construye máscaras booleanas para pixels de bubble verde y blanco."""
    R = arr[:, :, 0].astype(np.int16)
    G = arr[:, :, 1].astype(np.int16)
    B = arr[:, :, 2].astype(np.int16)

    # Bubble "me": verde claro, G domina sobre R y B
    mask_me = (
        (G - R > 15) &
        (G - B > 15) &
        (G > 200)
    )

    # Bubble "other": blanco puro (near-white), todos los canales >248
    mask_other = (
        (R > 248) &
        (G > 248) &
        (B > 248)
    )

    return mask_me.astype(np.uint8), mask_other.astype(np.uint8)


# ─── Morfología para rellenar gaps internos de los bubbles ───────────────────

def _close_mask(mask: np.ndarray, gap_px: int = 7) -> np.ndarray:
    """
    Closing morfológico: dilata → erosiona.
    Rellena gaps pequeños dentro del mismo bubble (ej: texto oscuro sobre fondo claro).
    gap_px controla cuántos pixels de gap se cierran verticalmente.
    Reducido a 7 para evitar puentear gaps inter-mensaje (~8-12px) que fusionan bubbles distintos.
    """
    struct_v = ndimage.generate_binary_structure(2, 1)
    # Kernel vertical para cerrar gaps entre líneas de texto dentro del bubble (no inter-mensaje)
    kernel = np.ones((gap_px, 1), dtype=np.uint8)
    closed = ndimage.binary_closing(mask, structure=kernel).astype(np.uint8)
    return closed


# ─── Detección principal ─────────────────────────────────────────────────────

def detect_bubbles(img: Image.Image, footer_px: int = 70) -> list[dict]:
    """
    Detecta bubbles de WhatsApp Web en una imagen de chat (ya croppeada sin sidebar).

    Args:
        img:        Imagen PIL del panel de chat.
        footer_px:  Pixels al fondo a ignorar (input bar de WA).

    Returns:
        Lista de dicts ordenada por y: [{"x", "y", "w", "h", "type"}, ...]
        donde type es "me" | "other".

    Tamaños mínimos: 30px alto × 50px ancho (descarta timestamps sueltos e íconos).
    """
    img_rgb = img.convert("RGB")
    arr = np.array(img_rgb)
    img_h, img_w = arr.shape[:2]

    # Ignorar el footer (input bar de WA)
    work_arr = arr[: img_h - footer_px, :]

    mask_me_raw, mask_other_raw = _build_masks(work_arr)

    results: list[dict] = []

    for mask_raw, bubble_type in [(mask_me_raw, "me"), (mask_other_raw, "other")]:
        # Cerrar gaps internos del bubble (texto oscuro sobre fondo claro)
        # gap_px=7 evita fusionar bubbles distintos del mismo emisor
        mask_closed = _close_mask(mask_raw, gap_px=7)

        # Connected components
        labeled, n_labels = ndimage.label(mask_closed)
        if n_labels == 0:
            continue

        slices = ndimage.find_objects(labeled)
        for sl in slices:
            if sl is None:
                continue
            row_sl, col_sl = sl
            y0 = row_sl.start
            y1 = row_sl.stop
            x0 = col_sl.start
            x1 = col_sl.stop

            bh = y1 - y0
            bw = x1 - x0

            # Permitir footers pequeños coloreados (contienen timestamp bajo imágenes).
            # Footers son muy finos (bh ~28px) pero anchos (bw >= bubble width).
            # Otros elementos pequeños (timestamps sueltos, íconos) se filtran por densidad.
            is_thin_footer = bh < 30 and bw >= 50
            if (bh < 30 or bw < 50) and not is_thin_footer:
                continue

            # Filtrar separadores de fecha de WA ("18/5/2026" en píldora centrada).
            # Son near-white, muy bajos (h < 38px) y centrados horizontalmente.
            # Los mensajes reales de una línea tienen h ~34px pero están alineados
            # al borde izquierdo o derecho, no al centro.
            if bubble_type == "other" and bh < 38:
                center_frac = (x0 + bw / 2) / img_w
                if 0.35 < center_frac < 0.65:
                    continue  # es un separador de fecha, no un bubble real

            # Verificar que la región tiene suficiente densidad del color esperado
            # (evita cajas muy grandes con pocos pixels de ese color)
            region_mask = mask_raw[y0:y1, x0:x1]
            density = region_mask.sum() / (bh * bw)
            if density < 0.08:
                continue

            results.append({
                "x": int(x0),
                "y": int(y0),
                "w": int(bw),
                "h": int(bh),
                "type": bubble_type,
            })

    # Ordenar por y (posición vertical, top primero)
    results.sort(key=lambda d: d["y"])

    # Post-proceso: fusionar bubbles del mismo tipo que se solapan en Y
    # (puede ocurrir si un bubble tiene texto largo que fragmenta la máscara)
    results = _merge_overlapping(results)

    return results


def _merge_overlapping(bubbles: list[dict]) -> list[dict]:
    """
    Fusiona bubbles del mismo tipo que se solapan o tienen gap pequeño en Y.
    - Gap normal (8px): para text/audio/file
    - Gap grande (120px): solo si UNO es un footer fino (bh < 30)
    Recibe la lista ya ordenada por y.
    """
    if not bubbles:
        return bubbles

    merged = [bubbles[0].copy()]
    for b in bubbles[1:]:
        last = merged[-1]
        last_y1 = last["y"] + last["h"]
        b_y0 = b["y"]
        gap = b_y0 - last_y1

        # Determinar si alguno es un footer fino (muy pequeño en altura)
        last_is_footer = last["h"] < 30
        b_is_footer = b["h"] < 30

        # Elegir overlap_gap basado en los tipos
        if last_is_footer or b_is_footer:
            # Si alguno es footer fino, permitir gap hasta 120px
            overlap_gap = 120
        else:
            # Si ambos son normales, usar gap pequeño (original)
            overlap_gap = 8

        # Fusionar si mismo tipo y gap dentro del límite
        if b["type"] == last["type"] and gap <= overlap_gap:
            # Expandir el bounding box del último para incluir b
            new_x0 = min(last["x"], b["x"])
            new_y0 = min(last["y"], b["y"])
            new_x1 = max(last["x"] + last["w"], b["x"] + b["w"])
            new_y1 = max(last["y"] + last["h"], b["y"] + b["h"])
            last["x"] = new_x0
            last["y"] = new_y0
            last["w"] = new_x1 - new_x0
            last["h"] = new_y1 - new_y0
        else:
            merged.append(b.copy())

    return merged
