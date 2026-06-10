from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from layout_extraction.generate_html import TextBox, generate_html, write_layout_json
from layout_extraction.inpainting import inpaint_text_regions

logger = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def bbox_from_points(points: Iterable[Iterable[float]]) -> tuple[int, int, int, int]:
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        x, y = point
        xs.append(float(x))
        ys.append(float(y))
    left = max(0, int(min(xs)))
    top = max(0, int(min(ys)))
    right = max(left + 1, int(max(xs)))
    bottom = max(top + 1, int(max(ys)))
    return left, top, right - left, bottom - top


def estimate_font_size(height: int) -> int:
    return max(8, int(round(height * 0.72)))


def estimate_text_color(image: Image.Image, box: tuple[int, int, int, int]) -> str:
    left, top, width, height = box
    crop = image.crop((left, top, left + width, top + height)).convert("RGB")
    pixels = np.asarray(crop).reshape(-1, 3).astype(np.float32)
    if pixels.size == 0:
        return "rgb(0, 0, 0)"

    crop_array = np.asarray(crop).astype(np.float32)
    borders = np.concatenate(
        [
            crop_array[0, :, :],
            crop_array[-1, :, :],
            crop_array[:, 0, :],
            crop_array[:, -1, :],
        ],
        axis=0,
    )
    background = np.median(borders, axis=0)
    distance = np.linalg.norm(pixels - background, axis=1)
    foreground = pixels[distance > max(35.0, np.percentile(distance, 70))]

    if len(foreground) < 8:
        luminance = pixels @ np.array([0.2126, 0.7152, 0.0722])
        foreground = pixels[luminance <= np.percentile(luminance, 35)]

    if len(foreground) == 0:
        color = np.median(pixels, axis=0)
    else:
        quantized = (foreground // 16) * 16
        colors, counts = np.unique(quantized.astype(np.uint8), axis=0, return_counts=True)
        color = colors[int(np.argmax(counts))]

    r, g, b = [int(max(0, min(255, value))) for value in color]
    return f"rgb({r}, {g}, {b})"


def run_easyocr(image_path: Path, languages: list[str]) -> list[tuple[str, float, tuple[int, int, int, int]]]:
    import easyocr
    import torch

    gpu_available = torch.cuda.is_available()
    logger.info("EasyOCR GPU enabled: %s", gpu_available)
    reader = easyocr.Reader(languages, gpu=gpu_available)
    results = reader.readtext(str(image_path), detail=1, paragraph=False)
    parsed = []
    for points, text, confidence in results:
        parsed.append((str(text), float(confidence), bbox_from_points(points)))
    return parsed


def run_paddleocr(image_path: Path, languages: list[str]) -> list[tuple[str, float, tuple[int, int, int, int]]]:
    from paddleocr import PaddleOCR
    import torch

    gpu_available = torch.cuda.is_available()
    logger.info("PaddleOCR GPU enabled: %s", gpu_available)
    lang = "en" if "en" in languages else languages[0]
    ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False, use_gpu=gpu_available)
    raw_results = ocr.ocr(str(image_path), cls=True)
    parsed = []
    for page in raw_results or []:
        for item in page or []:
            points = item[0]
            text, confidence = item[1]
            parsed.append((str(text), float(confidence), bbox_from_points(points)))
    return parsed


def run_tesseract(image_path: Path, languages: list[str]) -> list[tuple[str, float, tuple[int, int, int, int]]]:
    import pytesseract
    from pytesseract import Output

    lang = "+".join(languages)
    data = pytesseract.image_to_data(
        Image.open(image_path), lang=lang, output_type=Output.DICT
    )
    parsed = []
    for index, text in enumerate(data.get("text", [])):
        text = str(text).strip()
        if not text:
            continue
        confidence = float(data["conf"][index]) / 100.0
        if confidence < 0:
            confidence = 0.0
        box = (
            int(data["left"][index]),
            int(data["top"][index]),
            int(data["width"][index]),
            int(data["height"][index]),
        )
        parsed.append((text, confidence, box))
    return parsed


def run_ocr(
    image_path: Path, engine: str = "auto", languages: list[str] | None = None
) -> list[tuple[str, float, tuple[int, int, int, int]]]:
    selected_languages = languages or ["en"]
    engines = [engine] if engine != "auto" else ["easyocr", "paddleocr", "tesseract"]
    errors: list[str] = []

    for candidate in engines:
        try:
            if candidate == "easyocr":
                return run_easyocr(image_path, selected_languages)
            if candidate == "paddleocr":
                return run_paddleocr(image_path, selected_languages)
            if candidate == "tesseract":
                return run_tesseract(image_path, selected_languages)
        except ImportError as exc:
            errors.append(f"{candidate}: {exc}")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    raise RuntimeError(
        "No OCR engine succeeded. Install easyocr, paddleocr, or pytesseract "
        "with the Tesseract binary. Errors: " + " | ".join(errors)
    )


def merge_text_boxes(boxes: list[TextBox]) -> list[TextBox]:
    if not boxes:
        return []

    # Sort boxes: top first, then left
    sorted_boxes = sorted(boxes, key=lambda b: (b.top, b.left))
    groups: list[list[TextBox]] = []

    for box in sorted_boxes:
        merged = False
        for group in groups:
            # Get group bounding box
            g_left = min(b.left for b in group)
            g_top = min(b.top for b in group)
            g_right = max(b.left + b.width for b in group)
            g_bottom = max(b.top + b.height for b in group)
            
            # Average height of boxes in group
            avg_height = sum(b.height for b in group) / len(group)
            
            # Check if box is on the same line or consecutive line
            # Same line: large vertical overlap
            vert_overlap = min(box.top + box.height, g_bottom) - max(box.top, g_top)
            is_same_line = vert_overlap > (avg_height * 0.4)
            
            # Consecutive line: top of box is close to bottom of group (can be slightly negative overlap)
            is_next_line = (box.top - g_bottom <= avg_height * 1.5) and (box.top >= g_top - avg_height)
            
            # Horizontal relationship
            horiz_overlap = min(box.left + box.width, g_right) - max(box.left, g_left)
            min_width = min(box.width, g_right - g_left)
            
            # 1. If same line, they should be horizontally close (within the same column)
            if is_same_line:
                # Gap between box and group
                gap = max(box.left - g_right, g_left - (box.left + box.width))
                if gap <= avg_height * 1.2: # close words on the same line
                    group.append(box)
                    merged = True
                    break
                    
            # 2. If next line, they must overlap horizontally (same column)
            elif is_next_line:
                # Overlap must be at least 30% of the narrower width to ensure they belong to same column
                if horiz_overlap > (min_width * 0.30):
                    group.append(box)
                    merged = True
                    break

        if not merged:
            groups.append([box])

    # Now construct the merged TextBoxes
    merged_boxes = []
    for group in groups:
        # Sort elements in the group top-to-bottom, left-to-right
        group_sorted = sorted(group, key=lambda b: (b.top, b.left))
        
        # Build merged text
        lines: list[list[TextBox]] = []
        for b in group_sorted:
            # Find if there's an existing line this box belongs to
            placed = False
            for line in lines:
                # Check vertical overlap with line
                l_top = min(x.top for x in line)
                l_bottom = max(x.top + x.height for x in line)
                l_height = l_bottom - l_top
                overlap = min(b.top + b.height, l_bottom) - max(b.top, l_top)
                if overlap > l_height * 0.4:
                    line.append(b)
                    placed = True
                    break
            if not placed:
                lines.append([b])
                
        # Sort each line horizontally and join words with space
        line_texts = []
        for line in lines:
            line_sorted = sorted(line, key=lambda x: x.left)
            line_texts.append(" ".join(x.text for x in line_sorted))
            
        merged_text = "\n".join(line_texts)
        
        # Bounding box
        left = min(b.left for b in group)
        top = min(b.top for b in group)
        right = max(b.left + b.width for b in group)
        bottom = max(b.top + b.height for b in group)
        
        # Metrics
        avg_font_size = int(sum(b.font_size for b in group) / len(group))
        avg_confidence = sum(b.confidence for b in group) / len(group)
        color = group[0].color # use color from the first box
        
        merged_boxes.append(
            TextBox(
                text=merged_text,
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
                font_size=avg_font_size,
                color=color,
                confidence=avg_confidence,
            )
        )
        
    return merged_boxes


def extract_image_layout(
    image_path: Path,
    output_dir: Path,
    engine: str = "auto",
    languages: list[str] | None = None,
    enable_inpainting: bool = True,
) -> tuple[Path, Path]:
    """Extract text layout from an image and generate an editable HTML overlay.

    When ``enable_inpainting`` is True, the original text is removed from the
    background using OpenCV inpainting so that the HTML overlay doesn't show
    double text.  Only the OCR bounding-box regions are inpainted — the rest
    of the image (graphics, icons, photos) is preserved intact.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    raw_boxes = run_ocr(image_path, engine=engine, languages=languages)

    boxes = []
    for text, confidence, bbox in raw_boxes:
        left, top, box_width, box_height = bbox
        if box_width <= 0 or box_height <= 0:
            continue
        boxes.append(
            TextBox(
                text=text,
                left=left,
                top=top,
                width=box_width,
                height=box_height,
                font_size=estimate_font_size(box_height),
                color=estimate_text_color(image, bbox),
                confidence=confidence,
            )
        )

    # Merge individual text boxes into single unified paragraph areas
    boxes = merge_text_boxes(boxes)

    # Determine background image
    background_path = image_path
    if enable_inpainting and boxes:
        inpainted_path = output_dir / f"{image_path.stem}_clean.png"
        try:
            inpaint_text_regions(
                image_path=image_path,
                boxes=boxes,
                output_path=inpainted_path,
                padding=4,
                inpaint_radius=7,
                method="telea",
            )
            background_path = inpainted_path
            logger.info("Using inpainted background: %s", inpainted_path.name)
        except Exception as exc:
            logger.warning("Inpainting failed, using original image: %s", exc)

    stem = image_path.stem
    json_path = output_dir / f"{stem}.layout.json"
    html_path = output_dir / f"{stem}.html"
    write_layout_json(json_path, image_path, width, height, boxes)
    generate_html(html_path, background_path, width, height, boxes)
    return json_path, html_path


def iter_input_images(input_path: Path | None, input_dir: Path | None) -> list[Path]:
    if input_path is not None:
        return [input_path]
    if input_dir is None:
        raise ValueError("Either --input or --input-dir is required.")
    return sorted(
        path for path in input_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract slide text layout and generate editable HTML overlays."
    )
    parser.add_argument("--input", type=Path, help="Single image path.")
    parser.add_argument("--input-dir", type=Path, help="Directory of slide images.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("layout_extraction/outputs")
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "easyocr", "paddleocr", "tesseract"],
        default="auto",
    )
    parser.add_argument(
        "--languages",
        default="en",
        help="Comma-separated OCR language codes. Example: en,id",
    )
    parser.add_argument(
        "--no-inpainting",
        action="store_true",
        help="Disable text inpainting (keep original image as background).",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    languages = [item.strip() for item in args.languages.split(",") if item.strip()]

    for image_path in iter_input_images(args.input, args.input_dir):
        logger.info("Processing %s", image_path)
        json_path, html_path = extract_image_layout(
            image_path=image_path,
            output_dir=args.output_dir,
            engine=args.engine,
            languages=languages,
            enable_inpainting=not args.no_inpainting,
        )
        logger.info("Wrote %s and %s", json_path, html_path)


if __name__ == "__main__":
    main()
