from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import cv2
from loguru import logger

import _bootstrap  # noqa: F401
from street_incident_ai.camera_source import make_frame_source
from street_incident_ai.config import load_app_config, load_cameras_config
from street_incident_ai.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Test one camera/video/image source and save sampled frames.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--cameras", default="cameras.yaml")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--frames", type=int, default=5)
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    cameras = [cam for cam in load_cameras_config(args.cameras) if cam.camera_id == args.camera_id]
    if not cameras:
        raise RuntimeError(f"Camera not found or disabled: {args.camera_id}")

    source = make_frame_source(cameras[0], tmp_dir=config.tmp_dir)
    output_dir = config.output_dir / "camera_test" / args.camera_id
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, packet in enumerate(source.iter_frames(), start=1):
        output_path = output_dir / f"frame_{index:03d}.jpg"
        cv2.imwrite(str(output_path), packet.frame_bgr)
        logger.success("Saved sampled frame {}", output_path)
        if index >= args.frames:
            break


if __name__ == "__main__":
    main()
