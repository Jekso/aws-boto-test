"""Application runner and dependency wiring."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

from loguru import logger

from street_incidents.detection.yoloe_detector import YOLOEDetector
from street_incidents.incidents.annotator import IncidentAnnotator
from street_incidents.incidents.builder import IncidentBuilder
from street_incidents.incidents.cooldown import CooldownManager
from street_incidents.integrations.iot_publish import IoTPublisher
from street_incidents.integrations.s3_store import S3EvidenceStore
from street_incidents.integrations.salesforce import SalesforceClient
from street_incidents.models import AppConfig
from street_incidents.reasoning.bedrock_qwen import BedrockQwenClient
from street_incidents.streams.worker import CameraWorker


class ApplicationRunner:
    """Create dependencies and run one worker per camera."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the runner.

        Args:
            config: Application configuration.
        """
        self._config = config
        self._detector = YOLOEDetector(config.detector)
        self._reasoner = BedrockQwenClient(config.bedrock)
        self._cooldowns = CooldownManager(
            pet_seconds=config.pet_cooldown_seconds,
            garbage_seconds=config.garbage_cooldown_seconds,
            overfilled_bin_seconds=config.overfilled_bin_cooldown_seconds,
        )
        self._incident_builder = IncidentBuilder()
        self._annotator = IncidentAnnotator(Path(config.local_output_dir))
        self._s3 = S3EvidenceStore(config.s3, region_name=config.aws_region)
        self._salesforce = SalesforceClient(config.salesforce)
        self._iot = IoTPublisher(config.iot, region_name=config.aws_region)

    def run(self) -> None:
        """Run all camera workers forever."""
        workers = [
            CameraWorker(
                camera=camera,
                frame_sample_seconds=self._config.frame_sample_seconds,
                detector=self._detector,
                reasoner=self._reasoner,
                cooldown_manager=self._cooldowns,
                incident_builder=self._incident_builder,
                annotator=self._annotator,
                s3_store=self._s3,
                salesforce_client=self._salesforce,
                iot_publisher=self._iot,
                detector_min_confidence=self._config.detector.min_confidence,
                detector_min_bbox_area=self._config.detector.min_bbox_area,
            )
            for camera in self._config.cameras
        ]
        logger.info("Starting {} camera workers.", len(workers))
        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = [executor.submit(worker.run_forever) for worker in workers]
            wait(futures)
