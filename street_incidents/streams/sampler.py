"""Frame sampling logic."""

from __future__ import annotations

import time


class FrameSampler:
    """Sample frames at a fixed interval."""

    def __init__(self, sample_seconds: float) -> None:
        """Initialize the sampler.

        Args:
            sample_seconds: Minimum delay between accepted samples.
        """
        self._sample_seconds = sample_seconds
        self._last_sample_monotonic: float = 0.0

    def should_sample(self) -> bool:
        """Determine whether the current frame should be processed.

        Returns:
            True when enough time has elapsed since the last sample.
        """
        now = time.monotonic()
        if now - self._last_sample_monotonic >= self._sample_seconds:
            self._last_sample_monotonic = now
            return True
        return False
