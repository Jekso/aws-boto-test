"""Frame source readers for RTSP, images, and local videos."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import cv2
import numpy as np
from loguru import logger

from street_incidents.exceptions import StreamError
from street_incidents.models import CameraConfig, SourceType


class BaseFrameReader(ABC):
    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def read(self) -> np.ndarray:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def __enter__(self) -> "BaseFrameReader":
        self.open()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class RTSPStreamReader(BaseFrameReader):
    def __init__(self, rtsp_url: str, camera_name: str, reconnect_delay_seconds: float = 2.0) -> None:
        self._rtsp_url = rtsp_url
        self._camera_name = camera_name
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        self.close()
        logger.info("Opening RTSP stream for {}", self._camera_name)
        self._capture = cv2.VideoCapture(self._rtsp_url)
        if not self._capture.isOpened():
            raise StreamError(f"Unable to open RTSP stream for camera {self._camera_name}.")

    def read(self) -> np.ndarray:
        if self._capture is None or not self._capture.isOpened():
            self._safe_reconnect()
        assert self._capture is not None
        success, frame = self._capture.read()
        if success and frame is not None:
            return frame
        logger.warning("Failed to read frame for {}. Reconnecting.", self._camera_name)
        self._safe_reconnect()
        assert self._capture is not None
        success, frame = self._capture.read()
        if not success or frame is None:
            raise StreamError(f"Unable to read frame after reconnect for {self._camera_name}.")
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _safe_reconnect(self) -> None:
        self.close()
        time.sleep(self._reconnect_delay_seconds)
        self.open()


class ImageFileReader(BaseFrameReader):
    def __init__(self, image_path: str) -> None:
        self._image_path = image_path
        self._frame: np.ndarray | None = None

    def open(self) -> None:
        self._frame = cv2.imread(self._image_path)
        if self._frame is None:
            raise StreamError(f"Unable to load image source: {self._image_path}")

    def read(self) -> np.ndarray:
        if self._frame is None:
            raise StreamError("Image source is not open.")
        return self._frame.copy()

    def close(self) -> None:
        self._frame = None


class VideoFileReader(BaseFrameReader):
    def __init__(self, video_path: str, loop: bool = True) -> None:
        self._video_path = video_path
        self._loop = loop
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        self.close()
        self._capture = cv2.VideoCapture(self._video_path)
        if not self._capture.isOpened():
            raise StreamError(f"Unable to open video source: {self._video_path}")

    def read(self) -> np.ndarray:
        if self._capture is None or not self._capture.isOpened():
            self.open()
        assert self._capture is not None
        success, frame = self._capture.read()
        if success and frame is not None:
            return frame
        if self._loop:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = self._capture.read()
            if success and frame is not None:
                return frame
        raise StreamError(f"Unable to read frame from video source: {self._video_path}")

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class FrameReaderFactory:
    @staticmethod
    def create(source: CameraConfig) -> BaseFrameReader:
        if source.source_type is SourceType.RTSP:
            return RTSPStreamReader(source.source_uri, source.camera_name)
        if source.source_type is SourceType.IMAGE:
            return ImageFileReader(source.source_uri)
        return VideoFileReader(source.source_uri, loop=source.loop_video)
