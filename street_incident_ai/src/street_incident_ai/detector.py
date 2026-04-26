from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import supervision as sv
from loguru import logger
from ultralytics import YOLOE

from street_incident_ai.models import DetectionBox, DetectionResult, ensure_parent


GARBAGE_CLASSES: list[str] = [
    "trash can",
    "trash bin",
    "spray can",
    "bag",
    "toilet paper",
    "beer bottle",
    "beer can",
    "bottle",
    "bottle cap",
    "can",
    "cardboard",
    "cardboard box",
    "carton",
    "cigar",
    "cigarette",
    "coffee cup",
    "cup",
    "debris",
    "diaper",
    "paper cup",
    "garbage",
    "glass bottle",
    "glass jar",
    "grocery bag",
    "leftover",
    "napkin",
    "paper",
    "paper bag",
    "paper plate",
    "paper towel",
    "plastic",
    "rubble",
    "scrap",
    "shopping bag",
    "tin",
    "tinfoil",
    "tissue",
    "waste",
    "wine bottle",
    "wrapping paper",
]
PET_CLASSES: list[str] = ["dog", "cat"]
ALL_CLASSES: list[str] = PET_CLASSES + GARBAGE_CLASSES


class YOLOEObjectDetector:
    """YOLOE detector focused on pets and street-garbage classes."""

    def __init__(self, model_path: str = "yoloe-26x-seg.pt", confidence: float = 0.25) -> None:
        self.model_path = model_path
        self.confidence = confidence
        logger.info("Loading YOLOE model path={} confidence={}", model_path, confidence)
        self.model = YOLOE(model_path)
        self._set_classes(ALL_CLASSES)

    def _set_classes(self, classes: list[str]) -> None:
        """Set text classes while supporting minor Ultralytics API variations."""
        try:
            self.model.set_classes(classes)
        except TypeError:
            logger.debug("YOLOE set_classes requires text embeddings; using get_text_pe fallback.")
            self.model.set_classes(classes, self.model.get_text_pe(classes))
        logger.info("YOLOE configured with {} target classes.", len(classes))

    @staticmethod
    def _names_and_labels(result: Any, detections: sv.Detections) -> tuple[list[str], list[str], list[DetectionBox]]:
        class_names: list[str] = []
        labels: list[str] = []
        boxes: list[DetectionBox] = []

        if detections.class_id is None or detections.confidence is None or detections.xyxy is None:
            return class_names, labels, boxes

        names_map = result.names if hasattr(result, "names") else {}
        for class_id, confidence, xyxy in zip(
            detections.class_id.tolist(),
            detections.confidence.tolist(),
            detections.xyxy.tolist(),
        ):
            class_name = str(names_map.get(int(class_id), int(class_id)))
            confidence_value = float(confidence)
            box_tuple = tuple(float(value) for value in xyxy)
            class_names.append(class_name)
            labels.append(f"{class_name} {confidence_value:.2f}")
            boxes.append(
                DetectionBox(
                    class_name=class_name,
                    confidence=confidence_value,
                    xyxy=box_tuple,  # type: ignore[arg-type]
                )
            )
        return class_names, labels, boxes

    @staticmethod
    def _split_categories(class_names: list[str]) -> tuple[list[str], list[str]]:
        garbage_hits: list[str] = []
        pet_hits: list[str] = []
        for name in class_names:
            if name in GARBAGE_CLASSES and name not in garbage_hits:
                garbage_hits.append(name)
            if name in PET_CLASSES and name not in pet_hits:
                pet_hits.append(name)
        return garbage_hits, pet_hits

    def detect(self, frame_bgr: np.ndarray) -> tuple[DetectionResult, sv.Detections]:
        """Run YOLOE detection on one frame.

        Args:
            frame_bgr: OpenCV BGR image.

        Returns:
            DetectionResult plus raw supervision detections for annotation.
        """
        logger.debug("Running YOLOE prediction on frame shape={}", frame_bgr.shape)
        result = self.model.predict(source=frame_bgr, conf=self.confidence, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(result)
        class_names, labels, boxes = self._names_and_labels(result, detections)
        garbage_hits, pet_hits = self._split_categories(class_names)

        incident_type = "unknown"
        if pet_hits:
            incident_type = "lost_pet"
        elif garbage_hits:
            incident_type = "street_garbage"

        max_conf = max((box.confidence for box in boxes), default=0.0)
        detection_result = DetectionResult(
            has_target=bool(pet_hits or garbage_hits),
            incident_type=incident_type,  # type: ignore[arg-type]
            boxes=boxes,
            labels=labels,
            all_detected_classes=class_names,
            garbage_trigger_classes=garbage_hits,
            pet_trigger_classes=pet_hits,
            max_confidence=max_conf,
        )
        logger.info(
            "Detection complete has_target={} incident_type={} classes={} max_conf={:.3f}",
            detection_result.has_target,
            detection_result.incident_type,
            detection_result.all_detected_classes,
            detection_result.max_confidence,
        )
        return detection_result, detections

    @staticmethod
    def annotate(frame_bgr: np.ndarray, detections: sv.Detections, labels: list[str]) -> np.ndarray:
        """Annotate a frame with boxes and class labels."""
        box_annotator = sv.BoxAnnotator()
        label_annotator = sv.LabelAnnotator()
        annotated = box_annotator.annotate(scene=frame_bgr.copy(), detections=detections)
        return label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

    @staticmethod
    def save_image(frame_bgr: np.ndarray, output_path: str | Path) -> Path:
        """Save a BGR image to disk."""
        path = ensure_parent(output_path)
        ok = cv2.imwrite(str(path), frame_bgr)
        if not ok:
            raise RuntimeError(f"Failed to write image: {path}")
        logger.info("Saved image path={}", path)
        return path

    def detect_image_file(self, image_path: str | Path, output_image_path: str | Path) -> DetectionResult:
        """Solo helper: detect and annotate one local image file."""
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise ValueError(f"Failed to read image: {image_path}")
        detection_result, detections = self.detect(frame)
        annotated = self.annotate(frame, detections, detection_result.labels)
        self.save_image(annotated, output_image_path)
        return detection_result
