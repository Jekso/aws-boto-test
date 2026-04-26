from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loguru import logger

from street_incident_ai.camera_source import make_frame_source
from street_incident_ai.config import load_app_config, load_cameras_config
from street_incident_ai.incident_service import build_incident_service
from street_incident_ai.logging_config import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Street incident AI camera pipeline")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    parser.add_argument("--cameras", default="cameras.yaml", help="Path to cameras.yaml")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N sampled frames per camera. 0 means unlimited.")
    parser.add_argument("--camera-id", default=None, help="Optional camera_id filter")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_config = load_app_config(args.env)
    setup_logging(level=app_config.log_level)
    logger.info("Starting street incident AI pipeline")

    cameras = load_cameras_config(args.cameras)
    if args.camera_id:
        cameras = [camera for camera in cameras if camera.camera_id == args.camera_id]
    if not cameras:
        raise RuntimeError("No enabled cameras matched the provided configuration.")

    service = build_incident_service(app_config)
    try:
        for camera in cameras:
            frame_source = make_frame_source(camera, tmp_dir=app_config.tmp_dir)
            processed = 0
            logger.info("Starting camera loop camera_id={} name={}", camera.camera_id, camera.name)
            for packet in frame_source.iter_frames():
                try:
                    service.process_frame(packet)
                except Exception:
                    logger.exception("Failed processing frame camera_id={} frame_number={}", camera.camera_id, packet.frame_number)

                processed += 1
                if args.max_frames and processed >= args.max_frames:
                    logger.info("Reached max_frames={} for camera_id={}", args.max_frames, camera.camera_id)
                    break
    finally:
        service.iot.disconnect()
        logger.info("Pipeline stopped.")


if __name__ == "__main__":
    main()
