"""
Thin YOLO wrapper.

Loads a trained model once and turns frames into plain detection tuples,
so no ultralytics types leak into the rest of the app. Knows nothing about
tkinter, cameras, or config.
"""

from ultralytics import YOLO


class Detector:
    def __init__(self, model_path, conf=0.5):
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
