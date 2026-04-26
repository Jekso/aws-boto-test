from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np


CameraSourceType = Literal["rtsp", "video", "image"]
ReaderType = Literal["vlc", "opencv"]
IncidentType = Literal["lost_pet", "street_garbage", "unknown"]


@dataclass(slots=True)
class CameraConfig:
    """Runtime camera/video configuration loaded from cameras.yaml."""

    camera_id: str
    name: str
    enabled: bool
    source_type: CameraSourceType
    url: str
    reader: ReaderType = "opencv"
    username: str | None = None
    password: str | None = None
    location: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sample_fps: float = 1.0
    resize_width: int = 650
    resize_height: int = 280
    cooldown_seconds_pet: int = 300
    cooldown_seconds_garbage: int = 900
    loop_video: bool = False


@dataclass(slots=True)
class FramePacket:
    """Single sampled frame and the related camera metadata."""

    camera: CameraConfig
    frame_bgr: np.ndarray
    captured_at: datetime
    frame_number: int
    source_position_ms: float | None = None


@dataclass(slots=True)
class DetectionBox:
    """Single YOLOE detection."""

    class_name: str
    confidence: float
    xyxy: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DetectionResult:
    """YOLOE detection result for one frame."""

    has_target: bool
    incident_type: IncidentType
    boxes: list[DetectionBox]
    labels: list[str]
    all_detected_classes: list[str]
    garbage_trigger_classes: list[str]
    pet_trigger_classes: list[str]
    max_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_target": self.has_target,
            "incident_type": self.incident_type,
            "boxes": [box.to_dict() for box in self.boxes],
            "labels": self.labels,
            "all_detected_classes": self.all_detected_classes,
            "garbage_trigger_classes": self.garbage_trigger_classes,
            "pet_trigger_classes": self.pet_trigger_classes,
            "max_confidence": self.max_confidence,
        }


@dataclass(slots=True)
class ReasoningResult:
    """Structured vision-language reasoning result from Bedrock."""

    is_incident: bool
    incident_type: IncidentType
    confidence_score: float
    description: str
    risk_level: str = "unknown"
    recommended_action: str = "review"
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class S3Artifact:
    """S3 uploaded object references."""

    image_s3_uri: str
    image_url: str
    image_object_key: str
    metadata_s3_uri: str | None = None
    metadata_object_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SalesforceCaseResult:
    """Salesforce case/ticket creation result."""

    success: bool
    case_number: str | None
    status: str | None
    raw_text: str
    parsed_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IncidentEvent:
    """Final incident event sent to AWS IoT Core and Salesforce."""

    incident_id: str
    incident_type: IncidentType
    snapshot_time: datetime
    camera_id: str
    camera_name: str
    camera_location: str | None
    detection: DetectionResult
    reasoning: ReasoningResult
    artifacts: S3Artifact
    salesforce_case: SalesforceCaseResult | None = None
    camera_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "snapshot_time": self.snapshot_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "camera_location": self.camera_location,
            "detection": self.detection.to_dict(),
            "reasoning": self.reasoning.to_dict(),
            "artifacts": self.artifacts.to_dict(),
            "salesforce_case": self.salesforce_case.to_dict() if self.salesforce_case else None,
            "camera_metadata": self.camera_metadata,
        }
        return payload


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def safe_filename(value: str) -> str:
    """Make a simple filesystem/S3-key safe name."""
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_")


def ensure_parent(path: str | Path) -> Path:
    """Create parent folder and return normalized path."""
    normalized = Path(path)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return normalized
