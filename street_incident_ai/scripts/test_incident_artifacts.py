from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

import cv2

import _bootstrap  # noqa: F401
from street_incident_ai.config import load_app_config
from street_incident_ai.detector import YOLOEObjectDetector
from street_incident_ai.logging_config import setup_logging
from street_incident_ai.s3_storage import S3Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Test detection annotation + S3 image/metadata artifact upload.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    detector = YOLOEObjectDetector(config.detector_model_path, config.detector_confidence)
    s3 = S3Storage(
        bucket_name=config.s3_bucket,
        region_name=config.aws_region,
        url_mode=config.s3_url_mode,
        presigned_expires_seconds=config.s3_presigned_expires_seconds,
        public_base_url=config.s3_public_base_url,
        cloudfront_base_url=config.cloudfront_base_url,
    )

    frame = cv2.imread(args.image)
    if frame is None:
        raise RuntimeError(f"Failed to read image: {args.image}")
    detection, raw_detections = detector.detect(frame)
    annotated = detector.annotate(frame, raw_detections, detection.labels)

    incident_id = str(uuid4())
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y-%m-%d")
    incident_type = detection.incident_type
    camera_id = "artifact_test"
    local_output = config.output_dir / date_part / incident_type / camera_id / incident_id / "annotated.jpg"
    detector.save_image(annotated, local_output)
    base_key = f"{config.s3_prefix}/date={date_part}/incident_type={incident_type}/camera_id={camera_id}/incident_id={incident_id}"
    image_key = f"{base_key}/annotated.jpg"
    metadata_key = f"{base_key}/metadata.json"
    image_s3_uri, image_url = s3.upload_incident_image(local_output, image_key, metadata={"test": "incident_artifacts"})
    metadata = {
        "incident_id": incident_id,
        "detection": detection.to_dict(),
        "image_s3_uri": image_s3_uri,
        "image_url": image_url,
    }
    metadata_s3_uri = s3.upload_json(metadata, metadata_key)
    print(json.dumps({**metadata, "metadata_s3_uri": metadata_s3_uri}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
