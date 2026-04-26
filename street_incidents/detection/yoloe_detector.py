"""Ultralytics YOLOE detector wrapper."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np
from loguru import logger

from street_incidents.exceptions import DetectionError
from street_incidents.models import BoundingBox, DetectionRecord, DetectorConfig


class YOLOEDetector:
    def __init__(self, config: DetectorConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._model = self._load_model()

    def predict(self, frame: np.ndarray) -> list[DetectionRecord]:
        try:
            with self._lock:
                results = self._model.predict(source=frame, conf=self._config.min_confidence, imgsz=self._config.image_size, device=self._config.device, verbose=False)
            if not results:
                return []
            result = results[0]
            boxes: Any = getattr(result, 'boxes', None)
            names: dict[int, str] = getattr(result, 'names', {})
            if boxes is None:
                return []
            parsed: list[DetectionRecord] = []
            for index in range(len(boxes)):
                box = boxes[index]
                xyxy = box.xyxy[0].tolist()
                confidence = float(box.conf[0].item())
                class_idx = int(box.cls[0].item())
                label = str(names.get(class_idx, class_idx)).lower()
                parsed.append(DetectionRecord(label=label, confidence=confidence, bbox=BoundingBox(x1=float(xyxy[0]), y1=float(xyxy[1]), x2=float(xyxy[2]), y2=float(xyxy[3]))))
            return parsed
        except Exception as exc:
            raise DetectionError(f'YOLOE inference failed: {exc}') from exc

    def _load_model(self):
        try:
            from ultralytics import YOLO
            logger.info('Loading YOLOE model from {}', self._config.model_path)
            model = YOLO(self._config.model_path)
            prompts = self._config.pet_prompts + self._config.floor_garbage_prompts + self._config.overfilled_bin_prompts
            if prompts and hasattr(model, 'set_classes'):
                model.set_classes(prompts)  # type: ignore[attr-defined]
                logger.info('Applied open-vocabulary prompts: {}', prompts)
            else:
                logger.warning('Model does not expose set_classes(). Continuing without prompt injection.')
            return model
        except Exception as exc:
            raise DetectionError(f'Unable to load YOLOE model: {exc}') from exc
