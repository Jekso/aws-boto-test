"""Source worker implementation."""

from __future__ import annotations

import time

import cv2
import numpy as np
from loguru import logger

from street_incidents.detection.filters import DetectionFilter
from street_incidents.detection.yoloe_detector import YOLOEDetector
from street_incidents.exceptions import DetectionError, IntegrationError, ReasoningError, StorageError
from street_incidents.incidents.annotator import IncidentAnnotator
from street_incidents.incidents.builder import IncidentBuilder
from street_incidents.incidents.cooldown import CooldownManager
from street_incidents.integrations.iot_publish import IoTPublisher
from street_incidents.integrations.s3_store import S3EvidenceStore
from street_incidents.integrations.salesforce import SalesforceClient
from street_incidents.models import CameraConfig, DetectionRecord, IncidentRecord, IncidentType
from street_incidents.reasoning.bedrock_qwen import BedrockQwenClient
from street_incidents.streams.reader import FrameReaderFactory
from street_incidents.streams.sampler import FrameSampler


class CameraWorker:
    def __init__(self, camera: CameraConfig, frame_sample_seconds: float, detector: YOLOEDetector, reasoner: BedrockQwenClient, cooldown_manager: CooldownManager, incident_builder: IncidentBuilder, annotator: IncidentAnnotator, s3_store: S3EvidenceStore, salesforce_client: SalesforceClient, iot_publisher: IoTPublisher, detector_min_confidence: float, detector_min_bbox_area: float, sleep_seconds: float = 0.05) -> None:
        self._camera = camera
        self._sampler = FrameSampler(frame_sample_seconds)
        self._detector = detector
        self._reasoner = reasoner
        self._cooldowns = cooldown_manager
        self._incident_builder = incident_builder
        self._annotator = annotator
        self._s3_store = s3_store
        self._salesforce = salesforce_client
        self._iot = iot_publisher
        self._detector_min_confidence = detector_min_confidence
        self._detector_min_bbox_area = detector_min_bbox_area
        self._sleep_seconds = sleep_seconds

    def run_forever(self) -> None:
        logger.info("Starting worker for {} ({})", self._camera.camera_name, self._camera.source_type.value)
        with FrameReaderFactory.create(self._camera) as reader:
            while True:
                frame = reader.read()
                if not self._sampler.should_sample():
                    time.sleep(self._sleep_seconds)
                    continue
                try:
                    self._process_frame(frame)
                except (DetectionError, ReasoningError, StorageError) as exc:
                    logger.exception("Processing failure for source {}: {}", self._camera.camera_name, exc)
                except Exception as exc:  # pragma: no cover
                    logger.exception("Unexpected worker failure for source {}: {}", self._camera.camera_name, exc)
                finally:
                    time.sleep(self._sleep_seconds)

    def _process_frame(self, frame: np.ndarray) -> None:
        detections = self._detector.predict(frame)
        if not detections:
            return
        for incident_type in (IncidentType.LOST_PET, IncidentType.FLOOR_GARBAGE, IncidentType.OVERFILLED_BIN):
            if self._cooldowns.is_blocked(self._camera.camera_id, incident_type):
                continue
            candidate = DetectionFilter.pick_best_candidate(detections=detections, incident_type=incident_type, min_confidence=self._detector_min_confidence, min_bbox_area=self._detector_min_bbox_area)
            if candidate is None:
                continue
            self._handle_candidate(frame=frame, incident_type=incident_type, detection=candidate)

    def _handle_candidate(self, frame: np.ndarray, incident_type: IncidentType, detection: DetectionRecord) -> None:
        image_bytes = self._encode_frame_to_jpeg(frame)
        decision = self._reasoner.classify_image(image_bytes=image_bytes, incident_type=incident_type, camera=self._camera)
        if not decision.is_incident:
            logger.info("Candidate rejected by reasoner for source={} type={}", self._camera.camera_name, incident_type.value)
            return
        incident = self._incident_builder.build(camera=self._camera, detection=detection, decision=decision, model_id=self._reasoner.model_id)
        local_image_path = self._annotator.annotate(frame=frame, incident=incident, detection=detection)
        evidence = self._s3_store.upload_artifacts(incident=incident, local_image_path=local_image_path)
        incident.evidence = evidence
        self._cooldowns.activate(self._camera.camera_id, incident_type)
        self._send_downstream(incident)
        logger.info("Confirmed incident {} for source {}", incident.incident_id, self._camera.camera_name)

    @staticmethod
    def _encode_frame_to_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
        success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not success:
            raise StorageError('Failed to encode frame as JPEG.')
        return bytes(buffer.tobytes())

    def _send_downstream(self, incident: IncidentRecord) -> None:
        try:
            self._salesforce.create_incident(incident)
        except IntegrationError as exc:
            logger.exception('Salesforce integration failed for {}: {}', incident.incident_id, exc)
        try:
            self._iot.publish_incident(incident)
        except IntegrationError as exc:
            logger.exception('IoT publish failed for {}: {}', incident.incident_id, exc)
