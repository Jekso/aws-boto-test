"""Typed data models used across the project."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Supported input source types."""

    RTSP = "rtsp"
    IMAGE = "image"
    VIDEO = "video"


class IncidentType(str, Enum):
    """Supported incident types."""

    LOST_PET = "lost_pet"
    FLOOR_GARBAGE = "floor_garbage"
    OVERFILLED_BIN = "overfilled_bin"


class CameraConfig(BaseModel):
    """Configuration for a single input source.

    The project keeps the historical `CameraConfig` name even when the input is
    a file-based image or video, to reduce refactoring across the codebase.
    """

    camera_id: str
    camera_name: str
    source_type: SourceType = SourceType.RTSP
    source_uri: str
    location: str | None = None
    loop_video: bool = True


class DetectorConfig(BaseModel):
    """Local detector configuration."""

    model_path: str
    device: str = "cuda"
    image_size: int = 960
    min_confidence: float = 0.35
    min_bbox_area: float = 8000.0
    pet_prompts: list[str] = Field(default_factory=lambda: ["pet", "dog", "cat"])
    floor_garbage_prompts: list[str] = Field(default_factory=list)
    overfilled_bin_prompts: list[str] = Field(default_factory=list)


class BedrockConfig(BaseModel):
    """Amazon Bedrock reasoning configuration."""

    region_name: str
    model_id: str
    temperature: float = 0.1
    top_p: float = 0.9
    max_tokens: int = 300


class S3Config(BaseModel):
    """S3 evidence storage configuration."""

    bucket_name: str
    url_expiry_seconds: int = 86400


class SalesforceConfig(BaseModel):
    """Salesforce integration configuration."""

    token_url: str
    client_id: str
    client_secret: str
    base_url: str
    api_version: str = "v62.0"
    object_api_name: str = "Street_Incident__c"


class IoTConfig(BaseModel):
    """AWS IoT Core publish configuration."""

    topic: str
    qos: int = 1


class AppConfig(BaseModel):
    """Top-level application configuration."""

    aws_region: str
    frame_sample_seconds: float
    pet_cooldown_seconds: int
    garbage_cooldown_seconds: int
    overfilled_bin_cooldown_seconds: int
    local_output_dir: str
    log_dir: str
    cameras: list[CameraConfig]
    detector: DetectorConfig
    bedrock: BedrockConfig
    s3: S3Config
    salesforce: SalesforceConfig
    iot: IoTConfig


class BoundingBox(BaseModel):
    """Single bounding box prediction."""

    x1: float
    y1: float
    x2: float
    y2: float

    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


class DetectionRecord(BaseModel):
    label: str
    confidence: float
    bbox: BoundingBox


class ReasoningDecision(BaseModel):
    incident_type: IncidentType
    is_incident: bool
    confidence: float
    reason: str
    caption: str
    visible_pet_type: str | None = None
    visible_owner_present: bool | None = None
    recommended_action: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class IncidentEvidence(BaseModel):
    local_image_path: str
    s3_key_image: str
    s3_key_json: str
    evidence_url: str


class IncidentRecord(BaseModel):
    incident_id: str
    incident_type: IncidentType
    camera: CameraConfig
    timestamp_utc: datetime
    detector_name: str
    detector_confidence: float
    detector_bbox: BoundingBox
    classifier_provider: str
    classifier_model_id: str
    decision: ReasoningDecision
    evidence: IncidentEvidence | None = None

    def compact_payload(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type.value,
            "camera_id": self.camera.camera_id,
            "camera_name": self.camera.camera_name,
            "source_type": self.camera.source_type.value,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "confidence_score": self.decision.confidence,
            "caption": self.decision.caption,
            "reason": self.decision.reason,
            "evidence_url": self.evidence.evidence_url if self.evidence else None,
        }
