from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
from street_incident_ai.config import load_app_config
from street_incident_ai.logging_config import setup_logging
from street_incident_ai.models import DetectionResult, IncidentEvent, ReasoningResult, S3Artifact
from street_incident_ai.salesforce_client import SalesforceCaseClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Salesforce case creation with a prepared image URL.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--image-url", required=True, help="S3/CloudFront/presigned URL to send in imgList")
    parser.add_argument("--incident-type", choices=["lost_pet", "street_garbage"], default="street_garbage")
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    client = SalesforceCaseClient(
        token_url=config.salesforce_token_url,
        case_url=config.salesforce_case_url,
        client_id=config.salesforce_client_id,
        client_secret=config.salesforce_client_secret,
        dry_run=config.dry_run_salesforce,
    )
    detection = DetectionResult(
        has_target=True,
        incident_type=args.incident_type,
        boxes=[],
        labels=[],
        all_detected_classes=[],
        garbage_trigger_classes=["garbage"] if args.incident_type == "street_garbage" else [],
        pet_trigger_classes=["dog"] if args.incident_type == "lost_pet" else [],
        max_confidence=0.88,
    )
    reasoning = ReasoningResult(
        is_incident=True,
        incident_type=args.incident_type,
        confidence_score=0.87,
        risk_level="medium",
        description="Manual Salesforce case test.",
        recommended_action="Dispatch team for review.",
    )
    event = IncidentEvent(
        incident_id="manual-test",
        incident_type=args.incident_type,
        snapshot_time=datetime.now(timezone.utc),
        camera_id="manual-camera",
        camera_name="Manual Test Camera",
        camera_location="Test Location",
        detection=detection,
        reasoning=reasoning,
        artifacts=S3Artifact(image_s3_uri="s3://manual/test.jpg", image_url=args.image_url, image_object_key="manual/test.jpg"),
    )
    payload = client.build_case_payload(event)
    result = client.create_case(event)
    print(json.dumps({"payload": payload, "result": result.to_dict()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
