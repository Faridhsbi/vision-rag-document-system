"""Text inpainting: remove original text from slide background using OCR bounding boxes.

Creates a clean background image where only the text regions are inpainted,
so the HTML overlay does not produce a "double text" effect.

Two strategies are provided:
  1. OpenCV inpainting  — uses cv2.inpaint() with a tight text mask.
  2. CSS background-color — a fallback that adds a matching bg-color on each
     text span to visually cover the original text (no image modification).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from layout_extraction.generate_html import TextBox

logger = logging.getLogger(__name__)


def create_text_mask(
    image_shape: tuple[int, int, int],
    boxes: list[TextBox],
    padding: int = 2,
) -> np.ndarray:
    """Create a binary mask where text regions are white (255).

    Only the bounding-box areas of detected text are marked — surrounding
    graphics, icons, and images are untouched.
    """
    height, width = image_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    for box in boxes:
        x1 = max(0, box.left - padding)
        y1 = max(0, box.top - padding)
        x2 = min(width, box.left + box.width + padding)
        y2 = min(height, box.top + box.height + padding)
        mask[y1:y2, x1:x2] = 255

    return mask


def inpaint_text_regions(
    image_path: Path,
    boxes: list[TextBox],
    output_path: Path,
    padding: int = 3,
    inpaint_radius: int = 5,
    method: str = "telea",
) -> Path:
    """Remove text from the image by inpainting only the bounding-box areas.

    Args:
        image_path: Original slide image.
        boxes: OCR-detected text boxes (only these areas will be inpainted).
        output_path: Where to save the cleaned background.
        padding: Extra pixels around each bbox to catch anti-aliased edges.
        inpaint_radius: Radius for cv2.inpaint (larger = smoother but slower).
        method: 'telea' (Telea algorithm) or 'ns' (Navier-Stokes).

    Returns:
        Path to the inpainted image.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    mask = create_text_mask(image.shape, boxes, padding=padding)

    # Choose inpainting algorithm
    flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    inpainted = cv2.inpaint(image, mask, inpaint_radius, flag)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), inpainted)
    logger.info(
        "Inpainted %d text regions → %s",
        len(boxes),
        output_path,
    )
    return output_path


def estimate_background_color(
    image: Image.Image,
    box: TextBox,
    border_fraction: float = 0.15,
) -> str:
    """Estimate the background color around a text box for CSS masking.

    Samples pixels from the border region of the bounding box to estimate
    the local background color. This is used as a CSS fallback when
    inpainting is not desired.
    """
    left, top = box.left, box.top
    right, bottom = left + box.width, top + box.height

    # Clamp to image bounds
    img_w, img_h = image.size
    left = max(0, left)
    top = max(0, top)
    right = min(img_w, right)
    bottom = min(img_h, bottom)

    crop = image.crop((left, top, right, bottom)).convert("RGB")
    arr = np.asarray(crop, dtype=np.float32)

    if arr.size == 0:
        return "rgba(255, 255, 255, 0.9)"

    # Sample border pixels
    h, w = arr.shape[:2]
    bh = max(1, int(h * border_fraction))
    bw = max(1, int(w * border_fraction))

    border_pixels = np.concatenate([
        arr[:bh, :, :].reshape(-1, 3),      # top border
        arr[-bh:, :, :].reshape(-1, 3),     # bottom border
        arr[:, :bw, :].reshape(-1, 3),      # left border
        arr[:, -bw:, :].reshape(-1, 3),     # right border
    ], axis=0)

    median_color = np.median(border_pixels, axis=0)
    r, g, b = [int(max(0, min(255, v))) for v in median_color]
    return f"rgb({r}, {g}, {b})"
