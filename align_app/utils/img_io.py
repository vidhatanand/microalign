from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np

SUPPORTED_LOWER = {".jpg", ".jpeg", ".png", ".jpe"}

def load_image_bgr(path: str) -> np.ndarray:
    """Load BGR image with EXIF orientation correction when Pillow is present."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        rgb = np.array(im.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Failed to read image: {path}")
        return img

def uniform_preview_scale(width: int, height: int, max_side: int) -> float:
    m = max(width, height)
    return 1.0 if m <= max_side else max_side / float(m)

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def bgr_to_qimage(img_bgr: np.ndarray):
    """Return QImage from BGR ndarray, copying to own buffer."""
    from PyQt5.QtGui import QImage
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
