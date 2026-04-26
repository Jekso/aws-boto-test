from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401
from street_incident_ai.bedrock_reasoner import BedrockNovaReasoner
from street_incident_ai.config import load_app_config
from street_incident_ai.logging_config import setup_logging
from street_incident_ai.models import DetectionResult


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Bedrock/Nova image reasoning on one image.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--image", required=True)
    parser.add_argument("--incident-type", default="unknown", choices=["lost_pet", "street_garbage", "unknown"])
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    reasoner = BedrockNovaReasoner(
        region_name=config.aws_region,
        model_id=config.bedrock_model_id,
        max_tokens=config.bedrock_max_tokens,
        temperature=config.bedrock_temperature,
        dry_run=config.dry_run_bedrock,
    )
    detection = DetectionResult(
        has_target=True,
        incident_type=args.incident_type,
        boxes=[],
        labels=[],
        all_detected_classes=[],
        garbage_trigger_classes=["garbage"] if args.incident_type == "street_garbage" else [],
        pet_trigger_classes=["dog"] if args.incident_type == "lost_pet" else [],
        max_confidence=0.9,
    )
    result = reasoner.analyze_image_file(args.image, detection)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
