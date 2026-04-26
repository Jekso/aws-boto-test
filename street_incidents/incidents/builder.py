"""Incident record builder."""

from __future__ import annotations

from datetime import UTC, datetime

from street_incidents.models import CameraConfig, DetectionRecord, IncidentRecord, ReasoningDecision


class IncidentBuilder:
    """Build consistent incident records from pipeline outputs."""

    def build(
        self,
        camera: CameraConfig,
        detection: DetectionRecord,
        decision: ReasoningDecision,
        model_id: str,
    ) -> IncidentRecord:
        """Build an incident record.

        Args:
            camera: Camera metadata.
            detection: Detection result from YOLOE.
            decision: Reasoning decision from Qwen3-VL.
            model_id: Bedrock model identifier.

        Returns:
            Complete incident record without evidence attached yet.
        """
        timestamp = datetime.now(UTC)
        incident_id = (
            f"{decision.incident_type.value}-{camera.camera_id}-"
            f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}"
        )
        return IncidentRecord(
            incident_id=incident_id,
            incident_type=decision.incident_type,
            camera=camera,
            timestamp_utc=timestamp,
            detector_name="yoloe",
            detector_confidence=detection.confidence,
            detector_bbox=detection.bbox,
            classifier_provider="bedrock",
            classifier_model_id=model_id,
            decision=decision,
            evidence=None,
        )
