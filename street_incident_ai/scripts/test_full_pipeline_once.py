from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401
from street_incident_ai.camera_source import make_frame_source
from street_incident_ai.config import load_app_config, load_cameras_config
from street_incident_ai.incident_service import build_incident_service
from street_incident_ai.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full pipeline for one sampled frame from one configured camera.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--cameras", default="cameras.yaml")
    parser.add_argument("--camera-id", required=True)
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    cameras = [cam for cam in load_cameras_config(args.cameras) if cam.camera_id == args.camera_id]
    if not cameras:
        raise RuntimeError(f"Camera not found or disabled: {args.camera_id}")

    service = build_incident_service(config)
    source = make_frame_source(cameras[0], tmp_dir=config.tmp_dir)
    try:
        for packet in source.iter_frames():
            event = service.process_frame(packet)
            if event:
                print(json.dumps(event.to_dict(), indent=2, ensure_ascii=False))
            else:
                print(json.dumps({"created_incident": False, "camera_id": packet.camera.camera_id}, indent=2))
            break
    finally:
        service.iot.disconnect()


if __name__ == "__main__":
    main()
