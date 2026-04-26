from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from street_incident_ai.config import load_app_config
from street_incident_ai.detector import YOLOEObjectDetector
from street_incident_ai.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Test YOLOE detection and annotation on one image.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", default="data/output/test_detection_annotated.jpg")
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    detector = YOLOEObjectDetector(config.detector_model_path, config.detector_confidence)
    result = detector.detect_image_file(args.image, args.output)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print(f"Annotated image saved to: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
