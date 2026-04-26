from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from loguru import logger

from street_incident_ai.models import CameraConfig, FramePacket, utc_now


class CameraSourceError(RuntimeError):
    """Raised when a camera/video source cannot provide frames."""


class BaseFrameSource(ABC):
    """Abstract frame source for RTSP, local videos, and images."""

    def __init__(self, camera: CameraConfig) -> None:
        self.camera = camera
        self._frame_number = 0

    def _resize(self, frame_bgr: np.ndarray) -> np.ndarray:
        return cv2.resize(
            frame_bgr,
            (self.camera.resize_width, self.camera.resize_height),
            interpolation=cv2.INTER_AREA,
        )

    def _packet(self, frame_bgr: np.ndarray, source_position_ms: float | None = None) -> FramePacket:
        self._frame_number += 1
        return FramePacket(
            camera=self.camera,
            frame_bgr=self._resize(frame_bgr),
            captured_at=utc_now(),
            frame_number=self._frame_number,
            source_position_ms=source_position_ms,
        )

    @abstractmethod
    def iter_frames(self) -> Iterator[FramePacket]:
        """Yield sampled frame packets."""


class ImageFrameSource(BaseFrameSource):
    """One-frame source for testing with a local image."""

    def iter_frames(self) -> Iterator[FramePacket]:
        image_path = Path(self.camera.url)
        logger.info("Reading test image for camera_id={} path={}", self.camera.camera_id, image_path)
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise CameraSourceError(f"Failed to read image: {image_path}")
        yield self._packet(frame)


class OpenCVFrameSource(BaseFrameSource):
    """OpenCV-based frame source, best for local videos and simple RTSP streams."""

    def iter_frames(self) -> Iterator[FramePacket]:
        logger.info("Opening OpenCV source camera_id={} url={}", self.camera.camera_id, self.camera.url)
        cap = cv2.VideoCapture(self.camera.url)
        if not cap.isOpened():
            raise CameraSourceError(f"OpenCV failed to open source: {self.camera.url}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0 or fps > 240:
                fps = 25.0
            frame_step = max(1, int(round(fps / max(self.camera.sample_fps, 0.1))))
            logger.info(
                "OpenCV source opened camera_id={} source_fps={} sample_fps={} frame_step={}",
                self.camera.camera_id,
                fps,
                self.camera.sample_fps,
                frame_step,
            )

            raw_index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    if self.camera.source_type == "video" and self.camera.loop_video:
                        logger.info("Looping local video for camera_id={}", self.camera.camera_id)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        raw_index = 0
                        continue
                    logger.info("OpenCV source ended camera_id={}", self.camera.camera_id)
                    break

                if raw_index % frame_step == 0:
                    pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                    logger.debug("Yielding sampled OpenCV frame camera_id={} raw_index={}", self.camera.camera_id, raw_index)
                    yield self._packet(frame, source_position_ms=pos_ms)

                raw_index += 1
        finally:
            cap.release()
            logger.info("Released OpenCV source camera_id={}", self.camera.camera_id)


class VLCFrameSource(BaseFrameSource):
    """VLC-based RTSP snapshot source.

    Use this when OpenCV/FFmpeg fail with authentication headers but VLC succeeds.
    VLC receives the RTSP stream and saves snapshots at the requested sample rate.
    """

    def __init__(self, camera: CameraConfig, snapshot_dir: str | Path = "tmp/vlc_snapshots") -> None:
        super().__init__(camera)
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def iter_frames(self) -> Iterator[FramePacket]:
        try:
            import vlc  # type: ignore
        except ImportError as exc:
            raise CameraSourceError("python-vlc is not installed. Install requirements and VLC desktop app.") from exc

        logger.info("Opening VLC RTSP source camera_id={} url={}", self.camera.camera_id, self.camera.url)
        instance = vlc.Instance("--rtsp-tcp", "--network-caching=500", "--no-audio")
        media = instance.media_new(self.camera.url)

        if self.camera.username:
            media.add_option(f":rtsp-user={self.camera.username}")
        if self.camera.password:
            media.add_option(f":rtsp-pwd={self.camera.password}")

        player = instance.media_player_new()
        player.set_media(media)
        player.play()
        logger.info("Waiting for VLC stream warm-up camera_id={}", self.camera.camera_id)
        time.sleep(5)

        interval = 1.0 / max(self.camera.sample_fps, 0.1)
        snapshot_index = 0
        try:
            while True:
                snapshot_path = self.snapshot_dir / f"{self.camera.camera_id}_{snapshot_index:08d}.jpg"
                result = player.video_take_snapshot(
                    0,
                    str(snapshot_path),
                    self.camera.resize_width,
                    self.camera.resize_height,
                )
                if result != 0:
                    logger.warning("VLC snapshot failed camera_id={} index={}", self.camera.camera_id, snapshot_index)
                    time.sleep(interval)
                    snapshot_index += 1
                    continue

                frame = cv2.imread(str(snapshot_path))
                if frame is None:
                    logger.warning("OpenCV failed reading VLC snapshot camera_id={} path={}", self.camera.camera_id, snapshot_path)
                    time.sleep(interval)
                    snapshot_index += 1
                    continue

                logger.debug("Yielding sampled VLC frame camera_id={} snapshot={}", self.camera.camera_id, snapshot_path)
                yield self._packet(frame)
                snapshot_index += 1
                time.sleep(interval)
        finally:
            player.stop()
            logger.info("Stopped VLC source camera_id={}", self.camera.camera_id)


def make_frame_source(camera: CameraConfig, tmp_dir: str | Path = "tmp") -> BaseFrameSource:
    """Factory for the configured frame source."""
    if camera.source_type == "image":
        return ImageFrameSource(camera)
    if camera.reader == "vlc":
        return VLCFrameSource(camera, snapshot_dir=Path(tmp_dir) / "vlc_snapshots")
    return OpenCVFrameSource(camera)
