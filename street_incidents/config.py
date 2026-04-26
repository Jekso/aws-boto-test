"""Configuration loading for the street incidents application."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from street_incidents.exceptions import ConfigError
from street_incidents.models import (
    AppConfig,
    BedrockConfig,
    CameraConfig,
    DetectorConfig,
    IoTConfig,
    S3Config,
    SalesforceConfig,
    SourceType,
)


class ConfigLoader:
    def __init__(self, env_file: str | None = None) -> None:
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

    def load(self) -> AppConfig:
        cameras = self._load_sources()
        if not cameras:
            raise ConfigError(
                "Configure at least one source using SOURCE_{n}_* variables or legacy CAMERA_{n}_* variables."
            )

        aws_region = self._require("AWS_REGION")
        detector = DetectorConfig(
            model_path=self._require("YOLOE_MODEL_PATH"),
            device=os.getenv("YOLO_DEVICE", "cuda"),
            image_size=int(os.getenv("DETECT_IMAGE_SIZE", "960")),
            min_confidence=float(os.getenv("DETECT_MIN_CONFIDENCE", "0.35")),
            min_bbox_area=float(os.getenv("DETECT_MIN_BBOX_AREA", "8000")),
            pet_prompts=self._split_csv(os.getenv("PET_PROMPTS", "pet,dog,cat")),
            floor_garbage_prompts=self._split_csv(os.getenv("FLOOR_GARBAGE_PROMPTS", "garbage,trash,litter,waste on floor")),
            overfilled_bin_prompts=self._split_csv(os.getenv("OVERFILLED_BIN_PROMPTS", "trash bin,garbage bin,overfilled trash bin,overflowing trash can")),
        )
        bedrock = BedrockConfig(
            region_name=aws_region,
            model_id=self._require("BEDROCK_MODEL_ID"),
            temperature=float(os.getenv("QWEN_TEMPERATURE", "0.1")),
            top_p=float(os.getenv("QWEN_TOP_P", "0.9")),
            max_tokens=int(os.getenv("QWEN_MAX_TOKENS", "300")),
        )
        s3 = S3Config(
            bucket_name=self._require("S3_BUCKET"),
            url_expiry_seconds=int(os.getenv("S3_URL_EXPIRY_SECONDS", "86400")),
        )
        salesforce = SalesforceConfig(
            token_url=self._require("SALEFORCE_TOKEN_URL"),
            client_id=self._require("SALEFORCE_CLIENT_ID"),
            client_secret=self._require("SALEFORCE_CLIENT_SECRET"),
            base_url=self._require("SALEFORCE_BASE_URL"),
            api_version=os.getenv("SALEFORCE_API_VERSION", "v62.0"),
            object_api_name=os.getenv("SALEFORCE_OBJECT_API_NAME", "Street_Incident__c"),
        )
        iot = IoTConfig(topic=self._require("IOT_TOPIC"), qos=int(os.getenv("IOT_QOS", "1")))
        return AppConfig(
            aws_region=aws_region,
            frame_sample_seconds=float(os.getenv("FRAME_SAMPLE_SECONDS", "1")),
            pet_cooldown_seconds=int(os.getenv("PET_COOLDOWN_SECONDS", "300")),
            garbage_cooldown_seconds=int(os.getenv("GARBAGE_COOLDOWN_SECONDS", "900")),
            overfilled_bin_cooldown_seconds=int(os.getenv("OVERFILLED_BIN_COOLDOWN_SECONDS", "900")),
            local_output_dir=os.getenv("LOCAL_OUTPUT_DIR", "./data/outputs"),
            log_dir=os.getenv("LOG_DIR", "./logs"),
            cameras=cameras,
            detector=detector,
            bedrock=bedrock,
            s3=s3,
            salesforce=salesforce,
            iot=iot,
        )

    def _load_sources(self) -> list[CameraConfig]:
        sources: list[CameraConfig] = []
        for index in range(1, 100):
            source_id = os.getenv(f"SOURCE_{index}_ID")
            source_name = os.getenv(f"SOURCE_{index}_NAME")
            source_type = os.getenv(f"SOURCE_{index}_TYPE")
            source_uri = os.getenv(f"SOURCE_{index}_URI")
            location = os.getenv(f"SOURCE_{index}_LOCATION")
            loop_video = os.getenv(f"SOURCE_{index}_LOOP_VIDEO", "true").lower() == "true"
            if not any([source_id, source_name, source_type, source_uri, location]):
                continue
            if not source_id or not source_name or not source_type or not source_uri:
                raise ConfigError(f"SOURCE_{index}_ID, SOURCE_{index}_NAME, SOURCE_{index}_TYPE and SOURCE_{index}_URI are required.")
            sources.append(CameraConfig(camera_id=source_id, camera_name=source_name, source_type=SourceType(source_type.lower()), source_uri=source_uri, location=location, loop_video=loop_video))
        if sources:
            return sources

        for index in range(1, 100):
            camera_id = os.getenv(f"CAMERA_{index}_ID")
            camera_name = os.getenv(f"CAMERA_{index}_NAME")
            rtsp_url = os.getenv(f"CAMERA_{index}_RTSP")
            location = os.getenv(f"CAMERA_{index}_LOCATION")
            if not any([camera_id, camera_name, rtsp_url, location]):
                continue
            if not camera_id or not camera_name or not rtsp_url:
                raise ConfigError(f"CAMERA_{index}_ID, CAMERA_{index}_NAME and CAMERA_{index}_RTSP are required.")
            sources.append(CameraConfig(camera_id=camera_id, camera_name=camera_name, source_type=SourceType.RTSP, source_uri=rtsp_url, location=location, loop_video=True))
        return sources

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _require(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ConfigError(f"Missing required environment variable: {name}")
        return value
