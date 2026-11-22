import logging
import threading

from PIL import Image

from config import settings
from core.canvas_engine import create_combined_sheet
from core.face_detector import FaceDetector
from core.crop_engine import crop_passport
from core.background import make_white_background
from core.enhancer import auto_enhance
from core.pipeline import pil_to_cv

# A passport photo prints at roughly 366 x 449 px (31 x 38 mm @ 300 DPI), so
# full 12 MP+ phone photos are far more than needed. Working on smaller copies
# keeps face detection and background removal fast and memory-friendly.
MAX_SOURCE_SIDE = 2000   # cap right after opening the file
MAX_WORKING_SIDE = 1000  # cap after cropping, before the heavy steps

_detector = None
_detector_lock = threading.Lock()


def _limit_size(image, max_side):
    """Shrink image so its longest side is at most max_side (never enlarges)."""
    w, h = image.size
    longest = max(w, h)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                        Image.Resampling.LANCZOS)


def _detect_face(image):
    """Run face detection; the lock keeps a single detector safe to share."""
    global _detector
    with _detector_lock:
        if _detector is None:
            _detector = FaceDetector()
        return _detector.detect(pil_to_cv(image))


def _process_photo(image_path, smart_crop, white_background, enhance, rotation=0):
    """Run one photo through the full passport pipeline and return a PIL image."""
    image = Image.open(image_path).convert("RGB")
    image = _limit_size(image, MAX_SOURCE_SIDE)

    # rotation is stored in degrees clockwise (multiples of 90)
    if rotation % 360:
        image = image.rotate(-rotation, expand=True)

    if smart_crop:
        face = _detect_face(image)
        if face is not None:
            image = crop_passport(image, face)

    image = _limit_size(image, MAX_WORKING_SIDE)

    if white_background:
        image = make_white_background(image)

    if enhance:
        image = auto_enhance(image)

    return image


def generate_batch(customers, progress_cb=None, cancel_event=None):
    """
    Process every customer and place them one after another on a single A4.

    progress_cb(done, total, label) is called before each customer starts.
    cancel_event (threading.Event) stops the job between customers.

    Returns:
        {
            "combined_sheet": PIL.Image or None,
            "errors": [{"label": str, "error": str}, ...],
            "cancelled": bool,
        }
    """
    customers_data = []
    errors = []
    total = len(customers)

    for idx, c in enumerate(customers):
        if cancel_event is not None and cancel_event.is_set():
            return {"combined_sheet": None, "errors": errors, "cancelled": True}

        label = c.get("label") or f"Customer {idx + 1}"
        if progress_cb:
            progress_cb(idx, total, label)

        try:
            photo = _process_photo(
                image_path=c["image_path"],
                smart_crop=c.get("smart_crop", True),
                white_background=c.get("white_background", False),
                enhance=c.get("enhance", True),
                rotation=c.get("rotation", 0),
            )
            customers_data.append({
                "photo":  photo,
                "copies": c.get("copies", 12),
                "label":  label,
            })
        except Exception as exc:
            logging.exception("Failed processing %s", label)
            errors.append({"label": label,
                           "error": str(exc) or type(exc).__name__})

    if cancel_event is not None and cancel_event.is_set():
        return {"combined_sheet": None, "errors": errors, "cancelled": True}

    combined_sheet = None
    if customers_data:
        try:
            combined_sheet = create_combined_sheet(customers_data, settings)
        except Exception as exc:
            logging.exception("Failed building combined sheet")
            errors.append({"label": "Sheet layout",
                           "error": str(exc) or type(exc).__name__})

    return {"combined_sheet": combined_sheet,
            "errors": errors,
            "cancelled": False}