"""Annotated evidence generation."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from street_incidents.exceptions import StorageError
from street_incidents.models import DetectionRecord, IncidentRecord


class IncidentAnnotator:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._box_annotator = None
        self._label_annotator = None

    def annotate(self, frame: np.ndarray, incident: IncidentRecord, detection: DetectionRecord) -> Path:
        local_dir = self._output_dir / incident.incident_type.value / incident.camera.camera_id
        local_dir.mkdir(parents=True, exist_ok=True)
        output_path = local_dir / f"{incident.incident_id}.jpg"
        try:
            import supervision as sv
        except Exception as exc:
            raise StorageError(f'Unable to import supervision: {exc}') from exc
        if self._box_annotator is None:
            self._box_annotator = sv.BoxAnnotator()
        if self._label_annotator is None:
            self._label_annotator = sv.LabelAnnotator()
        detections = sv.Detections(xyxy=np.array([[detection.bbox.x1, detection.bbox.y1, detection.bbox.x2, detection.bbox.y2]], dtype=np.float32), confidence=np.array([detection.confidence], dtype=np.float32), class_id=np.array([0], dtype=np.int32))
        labels = [f"{detection.label} {detection.confidence:.2f} | {incident.decision.incident_type.value} {incident.decision.confidence:.2f}"]
        annotated = self._box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated = self._label_annotator.annotate(scene=annotated, detections=detections, labels=labels)
        success = cv2.imwrite(str(output_path), annotated)
        if not success:
            raise StorageError(f'Unable to save annotated image to {output_path}')
        return output_path
