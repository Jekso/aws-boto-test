"""Post-processing helpers for detections."""

from __future__ import annotations

from street_incidents.models import DetectionRecord, IncidentType


class DetectionFilter:
    """Filter and classify raw detections into incident candidates."""

    PET_LABELS = {"pet", "dog", "cat"}
    FLOOR_GARBAGE_LABELS = {"garbage", "trash", "litter", "waste on floor", "waste"}
    OVERFILLED_BIN_LABELS = {
        "trash bin",
        "garbage bin",
        "overfilled trash bin",
        "overflowing trash can",
        "trash can",
    }

    @classmethod
    def pick_best_candidate(
        cls,
        detections: list[DetectionRecord],
        incident_type: IncidentType,
        min_confidence: float,
        min_bbox_area: float,
    ) -> DetectionRecord | None:
        """Pick the best detection candidate for a given incident type.

        Args:
            detections: All raw detections.
            incident_type: Target incident type.
            min_confidence: Minimum accepted detection confidence.
            min_bbox_area: Minimum accepted bounding-box area.

        Returns:
            Best matching detection or None.
        """
        label_set = cls._labels_for_incident(incident_type)
        filtered = [
            item
            for item in detections
            if item.label.lower() in label_set
            and item.confidence >= min_confidence
            and item.bbox.area() >= min_bbox_area
        ]
        if not filtered:
            return None
        return sorted(filtered, key=lambda item: item.confidence, reverse=True)[0]

    @classmethod
    def _labels_for_incident(cls, incident_type: IncidentType) -> set[str]:
        """Get label vocabulary for an incident type.

        Args:
            incident_type: Incident type.

        Returns:
            Accepted labels.
        """
        if incident_type is IncidentType.LOST_PET:
            return cls.PET_LABELS
        if incident_type is IncidentType.FLOOR_GARBAGE:
            return cls.FLOOR_GARBAGE_LABELS
        return cls.OVERFILLED_BIN_LABELS
