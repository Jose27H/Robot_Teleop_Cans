"""
Thin YOLO wrapper.

Loads a trained model once and turns frames into plain detection tuples,
so no ultralytics types leak into the rest of the app. Knows nothing about
tkinter, cameras, or config.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / ".config" / "ultralytics"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CONFIG_HOME", str(PROJECT_ROOT / ".config"))
os.environ.setdefault("ULTRALYTICS_SETTINGS_DIR", str(CONFIG_DIR))

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    YOLO_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - depends on environment
    YOLO_AVAILABLE = False
    YOLO_IMPORT_ERROR = exc
    YOLO = None


class Detector:
    def __init__(self, model_path, conf=0.5):
        if not YOLO_AVAILABLE:
            raise RuntimeError(f"Ultralytics is unavailable: {YOLO_IMPORT_ERROR}")
        self.model = YOLO(model_path)
        self.conf = conf

    def detect(self, pil_img):
        """Run the model on a PIL image.

        Returns a list of (label, confidence, (x1, y1, x2, y2)) tuples,
        pixel coordinates in the input image's space.
        """
        result = self.model(pil_img, conf=self.conf, verbose=False)[0]
        detections = []
        for box in result.boxes:
            label = self.model.names[int(box.cls)]
            confidence = float(box.conf)
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            detections.append((label, confidence, (x1, y1, x2, y2)))
        return detections
