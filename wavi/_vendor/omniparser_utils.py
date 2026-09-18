"""
Vendored + trimmed from microsoft/OmniParser (util/utils.py), commit as of
2026-09, https://github.com/microsoft/OmniParser — licensed CC-BY-4.0.
This file is a derivative excerpt kept under the same license; it is NOT
MIT like the rest of wavi (see wavi/vision_grounding.py for the full
licensing breakdown of the OmniParser stack, including the AGPLv3 icon
detector weights this code loads at runtime).

Trimmed from the original: dropped BLIP2/phi3v caption branches, the
GroundingDINO `predict()` path, the legacy `remove_overlap()` (superseded
by `remove_overlap_new()`), the YOLOv9Detector fallback (we always load
plain ultralytics YOLO), and the `display_img=True` branch of
`check_ocr_box()` (matplotlib preview, unused headless) — none of these
are reachable from wavi's usage. paddleocr and azure-openai imports the
original had at module level were removed; wavi only ever calls this with
easyocr.

Two runtime fixes vs. upstream, found empirically (see plan-mejoras.md):
  1. `get_caption_model_processor` forces device='cpu' for florence2 — the
     torch.float16 + MPS (Apple Silicon) branch throws
     `RuntimeError: Input type (float) and bias type (c10::Half) should be
     the same`. CPU/float32 is slower but correct on every platform.
  2. The captioning weights directory MUST be named containing the string
     "florence" (e.g. `icon_caption_florence`) — `get_parsed_content_icon`
     below branches on `'florence' in model.config.name_or_path` to pick
     num_beams=1 (works) vs. num_beams=5 (crashes on this transformers
     version with a beam-search attention-mask shape mismatch).
"""
from __future__ import annotations

import base64
import io
import time

import cv2
import easyocr
import numpy as np
import supervision as sv
import torch
from PIL import Image
from torchvision.ops import box_convert
from torchvision.transforms import ToPILImage

from .box_annotator import BoxAnnotator

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["en", "es"])
    return _reader


def get_caption_model_processor(model_name_or_path: str, device: str | None = None):
    """Loads the Florence-2 icon-captioning model.

    Upstream OmniParser only casts inputs to float16 when `device.type ==
    'cuda'` (see get_parsed_content_icon) — on MPS (Apple Silicon) it still
    loads the model in float16 but leaves the processor's output in
    float32, which is the actual root cause of the historical
    `RuntimeError: Input type (float) and bias type (c10::Half) should be
    the same` crash. It was never a CPU-vs-MPS issue, just a missed branch
    upstream. Fixed here by casting inputs to the model's own dtype for
    *any* accelerator (see get_parsed_content_icon), so MPS now gets real
    GPU (Metal) acceleration instead of always falling back to CPU.
    """
    from transformers import AutoModelForCausalLM, AutoProcessor

    if device is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"

    processor = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
    dtype = torch.float16 if device != "cpu" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_name_or_path, torch_dtype=dtype, trust_remote_code=True
    )
    return {"model": model.to(device), "processor": processor}


def get_yolo_model(model_path: str):
    from ultralytics import YOLO

    return YOLO(model_path)


@torch.inference_mode()
def get_parsed_content_icon(filtered_boxes, starting_idx, image_source, caption_model_processor, batch_size=1):
    to_pil = ToPILImage()
    non_ocr_boxes = filtered_boxes[starting_idx:] if starting_idx else filtered_boxes
    croped_pil_image = []
    for coord in non_ocr_boxes:
        try:
            xmin, xmax = int(coord[0] * image_source.shape[1]), int(coord[2] * image_source.shape[1])
            ymin, ymax = int(coord[1] * image_source.shape[0]), int(coord[3] * image_source.shape[0])
            cropped_image = image_source[ymin:ymax, xmin:xmax, :]
            cropped_image = cv2.resize(cropped_image, (64, 64))
            croped_pil_image.append(to_pil(cropped_image))
        except Exception:
            continue

    model, processor = caption_model_processor["model"], caption_model_processor["processor"]
    prompt = "<CAPTION>"
    device = model.device
    model_dtype = next(model.parameters()).dtype

    generated_texts = []
    for i in range(0, len(croped_pil_image), batch_size):
        batch = croped_pil_image[i : i + batch_size]
        # Cast to the model's own dtype (not just on cuda — see
        # get_caption_model_processor docstring for why this must also
        # cover mps, which is the fix that lets this run on Metal/GPU).
        inputs = processor(images=batch, text=[prompt] * len(batch), return_tensors="pt").to(
            device=device, dtype=model_dtype
        )
        # num_beams=1 is required — see module docstring fix #2.
        generated_ids = model.generate(
            input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
            max_new_tokens=20, num_beams=1, do_sample=False,
        )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)
        generated_texts.extend(gen.strip() for gen in generated_text)

    return generated_texts


def remove_overlap_new(boxes, iou_threshold, ocr_bbox=None):
    """ocr_bbox: [{'type':'text','bbox':[x,y,x,y],'interactivity':False,'content':str}, ...]
    boxes:      [{'type':'icon','bbox':[x,y,x,y],'interactivity':True,'content':None}, ...]"""
    assert ocr_bbox is None or isinstance(ocr_bbox, list)

    def box_area(box):
        return (box[2] - box[0]) * (box[3] - box[1])

    def intersection_area(box1, box2):
        x1, y1 = max(box1[0], box2[0]), max(box1[1], box2[1])
        x2, y2 = min(box1[2], box2[2]), min(box1[3], box2[3])
        return max(0, x2 - x1) * max(0, y2 - y1)

    def iou(box1, box2):
        intersection = intersection_area(box1, box2)
        union = box_area(box1) + box_area(box2) - intersection + 1e-6
        if box_area(box1) > 0 and box_area(box2) > 0:
            return max(intersection / union, intersection / box_area(box1), intersection / box_area(box2))
        return 0

    def is_inside(box1, box2):
        return intersection_area(box1, box2) / box_area(box1) > 0.80

    filtered_boxes = list(ocr_bbox) if ocr_bbox else []
    for i, box1_elem in enumerate(boxes):
        box1 = box1_elem["bbox"]
        is_valid_box = True
        for j, box2_elem in enumerate(boxes):
            box2 = box2_elem["bbox"]
            if i != j and iou(box1, box2) > iou_threshold and box_area(box1) > box_area(box2):
                is_valid_box = False
                break
        if not is_valid_box:
            continue
        if not ocr_bbox:
            filtered_boxes.append(box1)
            continue
        box_added = False
        ocr_labels = ""
        for box3_elem in list(ocr_bbox):
            box3 = box3_elem["bbox"]
            if is_inside(box3, box1):  # ocr inside icon
                try:
                    ocr_labels += box3_elem["content"] + " "
                    filtered_boxes.remove(box3_elem)
                except ValueError:
                    continue
            elif is_inside(box1, box3):  # icon inside ocr — icon is redundant, skip it
                box_added = True
                break
        if not box_added:
            content = ocr_labels if ocr_labels else None
            source = "box_yolo_content_ocr" if ocr_labels else "box_yolo_content_yolo"
            filtered_boxes.append({"type": "icon", "bbox": box1, "interactivity": True, "content": content, "source": source})
    return filtered_boxes


def annotate(image_source: np.ndarray, boxes: torch.Tensor, text_scale: float,
             text_padding=5, text_thickness=2, thickness=3):
    """boxes: cxcywh format, ratio scale."""
    h, w, _ = image_source.shape
    boxes = boxes * torch.Tensor([w, h, w, h])
    xyxy = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xyxy").numpy()
    xywh = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xywh").numpy()
    detections = sv.Detections(xyxy=xyxy)
    labels = [str(i) for i in range(boxes.shape[0])]

    box_annotator = BoxAnnotator(text_scale=text_scale, text_padding=text_padding,
                                  text_thickness=text_thickness, thickness=thickness)
    annotated_frame = box_annotator.annotate(scene=image_source.copy(), detections=detections,
                                               labels=labels, image_size=(w, h))
    label_coordinates = {str(i): v for i, v in enumerate(xywh)}
    return annotated_frame, label_coordinates


def predict_yolo(model, image, box_threshold, imgsz, iou_threshold=0.7):
    result = model.predict(source=image, conf=box_threshold, imgsz=imgsz, iou=iou_threshold)
    boxes = result[0].boxes.xyxy
    conf = result[0].boxes.conf
    return boxes, conf


def int_box_area(box, w, h):
    x1, y1, x2, y2 = box
    int_box = [int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)]
    return (int_box[2] - int_box[0]) * (int_box[3] - int_box[1])


def get_som_labeled_img(image_source: str | Image.Image, model, BOX_TRESHOLD=0.05,
                         ocr_bbox=None, text_scale=0.4, text_padding=5, draw_bbox_config=None,
                         caption_model_processor=None, ocr_text=None, iou_threshold=0.7, imgsz=640):
    """Returns (annotated_png_b64, label_coordinates_ratio, parsed_content_list)."""
    if isinstance(image_source, str):
        image_source = Image.open(image_source)
    image_source = image_source.convert("RGB")
    w, h = image_source.size

    xyxy, _conf = predict_yolo(model=model, image=image_source, box_threshold=BOX_TRESHOLD, imgsz=imgsz, iou_threshold=0.1)
    xyxy = xyxy / torch.Tensor([w, h, w, h]).to(xyxy.device)
    image_source = np.asarray(image_source)

    if ocr_bbox:
        ocr_bbox = (torch.tensor(ocr_bbox) / torch.Tensor([w, h, w, h])).tolist()
    else:
        ocr_bbox = None

    ocr_text = ocr_text or []
    ocr_bbox_elem = [
        {"type": "text", "bbox": box, "interactivity": False, "content": txt, "source": "box_ocr_content_ocr"}
        for box, txt in zip(ocr_bbox or [], ocr_text, strict=False) if int_box_area(box, w, h) > 0
    ]
    xyxy_elem = [{"type": "icon", "bbox": box, "interactivity": True, "content": None} for box in xyxy.tolist() if int_box_area(box, w, h) > 0]
    filtered_boxes_elem = remove_overlap_new(boxes=xyxy_elem, iou_threshold=iou_threshold, ocr_bbox=ocr_bbox_elem)

    filtered_boxes_elem = sorted(filtered_boxes_elem, key=lambda x: x["content"] is None)
    starting_idx = next((i for i, box in enumerate(filtered_boxes_elem) if box["content"] is None), -1)
    filtered_boxes = torch.tensor([box["bbox"] for box in filtered_boxes_elem])

    if caption_model_processor is not None:
        t0 = time.time()
        parsed_content_icon = get_parsed_content_icon(filtered_boxes, starting_idx, image_source, caption_model_processor)
        for box in filtered_boxes_elem:
            if box["content"] is None:
                box["content"] = parsed_content_icon.pop(0)
        _ = time.time() - t0  # captioning wall time, not surfaced (kept for parity w/ upstream)

    filtered_boxes_cxcywh = box_convert(boxes=filtered_boxes, in_fmt="xyxy", out_fmt="cxcywh")

    draw_bbox_config = draw_bbox_config or {"text_scale": text_scale, "text_padding": text_padding}
    annotated_frame, _label_coordinates = annotate(image_source=image_source, boxes=filtered_boxes_cxcywh, **draw_bbox_config)

    pil_img = Image.fromarray(annotated_frame)
    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    encoded_image = base64.b64encode(buffered.getvalue()).decode("ascii")

    return encoded_image, filtered_boxes_elem


def _get_xywh(item):
    x, y, w, h = item[0][0], item[0][1], item[2][0] - item[0][0], item[2][1] - item[0][1]
    return int(x), int(y), int(w), int(h)


def _get_xyxy(item):
    x, y, xp, yp = item[0][0], item[0][1], item[2][0], item[2][1]
    return int(x), int(y), int(xp), int(yp)


def check_ocr_box(image_source: str | Image.Image, output_bb_format="xyxy", easyocr_args=None):
    """EasyOCR-only (paddleocr branch dropped — wavi never sets it)."""
    if isinstance(image_source, str):
        image_source = Image.open(image_source)
    if image_source.mode == "RGBA":
        image_source = image_source.convert("RGB")
    image_np = np.array(image_source)

    result = _get_reader().readtext(image_np, **(easyocr_args or {}))
    coord = [item[0] for item in result]
    text = [item[1] for item in result]

    getter = _get_xywh if output_bb_format == "xywh" else _get_xyxy
    bb = [getter(item) for item in coord]
    return text, bb
