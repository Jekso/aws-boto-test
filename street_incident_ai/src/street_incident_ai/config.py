from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from loguru import logger

from street_incident_ai.models import CameraConfig


@dataclass(slots=True)
class AppConfig:
    """Application configuration loaded from .env and cameras.yaml."""

    aws_region: str
    s3_bucket: str
    s3_prefix: str
    s3_url_mode: str
    s3_presigned_expires_seconds: int
    s3_public_base_url: str | None
    cloudfront_base_url: str | None
    bedrock_model_id: str
    bedrock_max_tokens: int
    bedrock_temperature: float
    iot_endpoint: str | None
    iot_client_id: str
    iot_topic: str
    salesforce_host: str | None
    salesforce_client_id: str | None
    salesforce_client_secret: str | None
    salesforce_token_url: str | None
    salesforce_case_url: str | None
    detector_model_path: str
    detector_confidence: float
    output_dir: Path
    tmp_dir: Path
    log_level: str
    dry_run_iot: bool
    dry_run_salesforce: bool
    dry_run_bedrock: bool


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer. Got: {value}") from exc


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float. Got: {value}") from exc


def load_app_config(env_path: str | Path = ".env") -> AppConfig:
    """Load application config from an env file and environment variables."""
    load_dotenv(env_path)

    aws_region = os.getenv("AWS_REGION", "eu-west-1")
    sf_host = os.getenv("SALESFORCE_HOST")
    sf_token_url = os.getenv("SALESFORCE_TOKEN_URL")
    sf_case_url = os.getenv("SALESFORCE_CASE_URL")

    if sf_host and not sf_token_url:
        sf_token_url = f"https://{sf_host}.my.salesforce.com/services/oauth2/token"
    if sf_host and not sf_case_url:
        sf_case_url = f"https://{sf_host}.my.salesforce.com/services/apexrest/DahuaCreateCaseAPI"

    config = AppConfig(
        aws_region=aws_region,
        s3_bucket=os.getenv("S3_BUCKET", ""),
        s3_prefix=os.getenv("S3_PREFIX", "street-incidents"),
        s3_url_mode=os.getenv("S3_URL_MODE", "presigned").strip().lower(),
        s3_presigned_expires_seconds=_get_int("S3_PRESIGNED_EXPIRES_SECONDS", 604800),
        s3_public_base_url=os.getenv("S3_PUBLIC_BASE_URL"),
        cloudfront_base_url=os.getenv("CLOUDFRONT_BASE_URL"),
        bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0"),
        bedrock_max_tokens=_get_int("BEDROCK_MAX_TOKENS", 800),
        bedrock_temperature=_get_float("BEDROCK_TEMPERATURE", 0.1),
        iot_endpoint=os.getenv("IOT_ENDPOINT"),
        iot_client_id=os.getenv("IOT_CLIENT_ID", "street-incident-ai-local"),
        iot_topic=os.getenv("IOT_TOPIC", "street/incidents/test"),
        salesforce_host=sf_host,
        salesforce_client_id=os.getenv("SALESFORCE_CLIENT_ID"),
        salesforce_client_secret=os.getenv("SALESFORCE_CLIENT_SECRET"),
        salesforce_token_url=sf_token_url,
        salesforce_case_url=sf_case_url,
        detector_model_path=os.getenv("DETECTOR_MODEL_PATH", "yoloe-26x-seg.pt"),
        detector_confidence=_get_float("DETECTOR_CONFIDENCE", 0.25),
        output_dir=Path(os.getenv("OUTPUT_DIR", "data/output")),
        tmp_dir=Path(os.getenv("TMP_DIR", "tmp")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        dry_run_iot=_get_bool("DRY_RUN_IOT", False),
        dry_run_salesforce=_get_bool("DRY_RUN_SALESFORCE", False),
        dry_run_bedrock=_get_bool("DRY_RUN_BEDROCK", False),
    )
    logger.debug("Loaded AppConfig: {}", {k: v for k, v in config.__dict__.items() if "secret" not in k.lower()})
    return config


def load_cameras_config(path: str | Path = "cameras.yaml") -> list[CameraConfig]:
    """Load enabled cameras from cameras.yaml.

    Args:
        path: YAML file with a top-level cameras list.

    Returns:
        List of camera configurations.
    """
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Camera YAML file not found: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    cameras_raw: list[dict[str, Any]] = raw.get("cameras", [])
    cameras: list[CameraConfig] = []
    for item in cameras_raw:
        if "id" in item and "camera_id" not in item:
            item["camera_id"] = item.pop("id")
        camera = CameraConfig(**item)
        cameras.append(camera)

    enabled_cameras = [camera for camera in cameras if camera.enabled]
    logger.info("Loaded {} camera(s), {} enabled.", len(cameras), len(enabled_cameras))
    return enabled_cameras
