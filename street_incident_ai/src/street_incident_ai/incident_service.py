from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from street_incident_ai.bedrock_reasoner import BedrockNovaReasoner
from street_incident_ai.config import AppConfig
from street_incident_ai.detector import YOLOEObjectDetector
from street_incident_ai.iot_core import IoTCoreMqttPublisher
from street_incident_ai.models import FramePacket, IncidentEvent, ReasoningResult, S3Artifact, safe_filename
from street_incident_ai.s3_storage import S3Storage
from street_incident_ai.salesforce_client import SalesforceCaseClient


class CooldownManager:
    """In-memory cooldown by camera and incident type."""

    def __init__(self) -> None:
        self._last_event_epoch: dict[tuple[str, str], float] = {}

    def is_active(self, camera_id: str, incident_type: str, cooldown_seconds: int, now_epoch: float) -> bool:
        key = (camera_id, incident_type)
        last_epoch = self._last_event_epoch.get(key)
        if last_epoch is None:
            return False
        elapsed = now_epoch - last_epoch
        if elapsed < cooldown_seconds:
            logger.info(
                "Cooldown active camera_id={} incident_type={} remaining={:.1f}s",
                camera_id,
                incident_type,
                cooldown_seconds - elapsed,
            )
            return True
        return False

    def mark(self, camera_id: str, incident_type: str, now_epoch: float) -> None:
        self._last_event_epoch[(camera_id, incident_type)] = now_epoch
        logger.info("Cooldown started camera_id={} incident_type={} at_epoch={}", camera_id, incident_type, now_epoch)


class IncidentService:
    """Coordinates detection, Bedrock reasoning, S3 artifacts, IoT publish, Salesforce case, and cooldown."""

    def __init__(
        self,
        app_config: AppConfig,
        detector: YOLOEObjectDetector,
        reasoner: BedrockNovaReasoner,
        s3_storage: S3Storage,
        iot_publisher: IoTCoreMqttPublisher,
        salesforce_client: SalesforceCaseClient,
        cooldown_manager: CooldownManager | None = None,
    ) -> None:
        self.config = app_config
        self.detector = detector
        self.reasoner = reasoner
        self.s3 = s3_storage
        self.iot = iot_publisher
        self.salesforce = salesforce_client
        self.cooldown = cooldown_manager or CooldownManager()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _cooldown_seconds(packet: FramePacket, incident_type: str) -> int:
        if incident_type == "lost_pet":
            return packet.camera.cooldown_seconds_pet
        if incident_type == "street_garbage":
            return packet.camera.cooldown_seconds_garbage
        return 60

    @staticmethod
    def _external_send_allowed(reasoning: ReasoningResult) -> bool:
        """Return True only for incidents that should be sent to Salesforce and IoT.

        Business rule:
            - Garbage is sent only when Bedrock classifies it as unsafe.
            - Pet is sent only when Bedrock classifies it as likely_lost.
            - Safe garbage, not_lost pets, uncertain pets, unknown types, or malformed
              responses are logged only and are not sent to external integrations.
        """
        status = str(reasoning.raw_response.get("status", "")).lower().strip()

        if reasoning.incident_type == "street_garbage":
            return reasoning.is_incident and status == "unsafe"

        if reasoning.incident_type == "lost_pet":
            return reasoning.is_incident and status == "likely_lost"

        return False

    def _build_keys(self, packet: FramePacket, incident_id: str, incident_type: str) -> tuple[str, str, Path]:
        """Build organized local and S3 paths for incident artifacts.

        S3 layout:
            {prefix}/date=YYYY-MM-DD/incident_type=TYPE/camera_id=CAMERA/incident_id=UUID/annotated.jpg
            {prefix}/date=YYYY-MM-DD/incident_type=TYPE/camera_id=CAMERA/incident_id=UUID/metadata.json
        """
        captured_utc = packet.captured_at.astimezone(timezone.utc)
        date_part = captured_utc.strftime("%Y-%m-%d")
        camera_id = safe_filename(packet.camera.camera_id)
        incident_type_safe = safe_filename(incident_type or "unknown")
        prefix = self.config.s3_prefix.strip("/")
        base_key = (
            f"{prefix}/date={date_part}/incident_type={incident_type_safe}/"
            f"camera_id={camera_id}/incident_id={incident_id}"
        )
        image_key = f"{base_key}/annotated.jpg"
        metadata_key = f"{base_key}/metadata.json"
        local_image_path = self.config.output_dir / date_part / incident_type_safe / camera_id / incident_id / "annotated.jpg"
        return image_key, metadata_key, local_image_path

    def process_frame(self, packet: FramePacket) -> IncidentEvent | None:
        """Process a sampled frame and create an incident event when all checks pass."""
        logger.debug("Processing frame camera_id={} frame_number={}", packet.camera.camera_id, packet.frame_number)
        detection, raw_detections = self.detector.detect(packet.frame_bgr)
        if not detection.has_target:
            logger.debug("No target detection camera_id={} frame_number={}", packet.camera.camera_id, packet.frame_number)
            return None

        now_epoch = packet.captured_at.timestamp()
        cooldown_seconds = self._cooldown_seconds(packet, detection.incident_type)
        if self.cooldown.is_active(packet.camera.camera_id, detection.incident_type, cooldown_seconds, now_epoch):
            return None

        reasoning = self.reasoner.analyze_frame(packet, detection)
        if not reasoning.is_incident:
            logger.info(
                "Bedrock classified detection as non-actionable. External integrations skipped. "
                "camera_id={} preliminary_type={} bedrock_type={} status={} description={}",
                packet.camera.camera_id,
                detection.incident_type,
                reasoning.incident_type,
                reasoning.raw_response.get("status"),
                reasoning.description,
            )
            return None

        incident_id = str(uuid.uuid4())
        image_key, metadata_key, local_image_path = self._build_keys(packet, incident_id, reasoning.incident_type)
        annotated = self.detector.annotate(packet.frame_bgr, raw_detections, detection.labels)
        self.detector.save_image(annotated, local_image_path)

        image_s3_uri, image_url = self.s3.upload_incident_image(
            local_image_path=local_image_path,
            object_key=image_key,
            metadata={
                "incident_id": incident_id,
                "camera_id": packet.camera.camera_id,
                "incident_type": reasoning.incident_type,
            },
        )
        artifacts = S3Artifact(image_s3_uri=image_s3_uri, image_url=image_url, image_object_key=image_key)
        event = IncidentEvent(
            incident_id=incident_id,
            incident_type=reasoning.incident_type,
            snapshot_time=packet.captured_at,
            camera_id=packet.camera.camera_id,
            camera_name=packet.camera.name,
            camera_location=packet.camera.location,
            detection=detection,
            reasoning=reasoning,
            artifacts=artifacts,
            camera_metadata=packet.camera.metadata,
        )

        external_send_allowed = self._external_send_allowed(reasoning)
        if external_send_allowed:
            # Salesforce first, then include the case number in the metadata and IoT message.
            salesforce_result = self.salesforce.create_case(event)
            event.salesforce_case = salesforce_result

            metadata_s3_uri = self.s3.upload_json(event.to_dict(), metadata_key)
            event.artifacts.metadata_s3_uri = metadata_s3_uri
            event.artifacts.metadata_object_key = metadata_key

            self.iot.publish(self.config.iot_topic, event.to_dict())
            self.cooldown.mark(packet.camera.camera_id, reasoning.incident_type, now_epoch)
            logger.success(
                "Incident handled and external integrations notified incident_id={} camera_id={} "
                "type={} status={} image_url={} case_number={}",
                incident_id,
                packet.camera.camera_id,
                reasoning.incident_type,
                reasoning.raw_response.get("status"),
                image_url,
                salesforce_result.case_number,
            )
            return event

        # Defensive guard: this should rarely run because safe/not_lost/uncertain
        # normally produce reasoning.is_incident=False and return earlier. It protects
        # Salesforce and IoT from malformed or unexpected Bedrock responses.
        metadata_s3_uri = self.s3.upload_json(event.to_dict(), metadata_key)
        event.artifacts.metadata_s3_uri = metadata_s3_uri
        event.artifacts.metadata_object_key = metadata_key
        self.cooldown.mark(packet.camera.camera_id, reasoning.incident_type, now_epoch)
        logger.warning(
            "Incident artifact saved, but Salesforce and IoT skipped by business rule. "
            "incident_id={} camera_id={} type={} status={} metadata_s3_uri={}",
            incident_id,
            packet.camera.camera_id,
            reasoning.incident_type,
            reasoning.raw_response.get("status"),
            metadata_s3_uri,
        )
        return event


def build_incident_service(app_config: AppConfig) -> IncidentService:
    """Create the complete incident service from AppConfig."""
    detector = YOLOEObjectDetector(app_config.detector_model_path, app_config.detector_confidence)
    reasoner = BedrockNovaReasoner(
        region_name=app_config.aws_region,
        model_id=app_config.bedrock_model_id,
        max_tokens=app_config.bedrock_max_tokens,
        temperature=app_config.bedrock_temperature,
        dry_run=app_config.dry_run_bedrock,
    )
    s3_storage = S3Storage(
        bucket_name=app_config.s3_bucket,
        region_name=app_config.aws_region,
        url_mode=app_config.s3_url_mode,
        presigned_expires_seconds=app_config.s3_presigned_expires_seconds,
        public_base_url=app_config.s3_public_base_url,
        cloudfront_base_url=app_config.cloudfront_base_url,
    )
    iot = IoTCoreMqttPublisher(
        endpoint=app_config.iot_endpoint,
        region_name=app_config.aws_region,
        client_id=app_config.iot_client_id,
        dry_run=app_config.dry_run_iot,
    )
    salesforce = SalesforceCaseClient(
        token_url=app_config.salesforce_token_url,
        case_url=app_config.salesforce_case_url,
        client_id=app_config.salesforce_client_id,
        client_secret=app_config.salesforce_client_secret,
        dry_run=app_config.dry_run_salesforce,
    )
    return IncidentService(app_config, detector, reasoner, s3_storage, iot, salesforce)
