"""Cooldown logic for duplicate suppression."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from street_incidents.models import IncidentType


class CooldownManager:
    """Track per-camera cooldown windows for incident suppression."""

    def __init__(
        self,
        pet_seconds: int,
        garbage_seconds: int,
        overfilled_bin_seconds: int,
    ) -> None:
        """Initialize the cooldown manager.

        Args:
            pet_seconds: Cooldown for lost pet incidents.
            garbage_seconds: Cooldown for floor garbage incidents.
            overfilled_bin_seconds: Cooldown for overfilled bin incidents.
        """
        self._durations = {
            IncidentType.LOST_PET: pet_seconds,
            IncidentType.FLOOR_GARBAGE: garbage_seconds,
            IncidentType.OVERFILLED_BIN: overfilled_bin_seconds,
        }
        self._lock = Lock()
        self._next_allowed: dict[tuple[str, IncidentType], datetime] = {}

    def is_blocked(self, camera_id: str, incident_type: IncidentType) -> bool:
        """Check whether an incident type is currently blocked for a camera.

        Args:
            camera_id: Camera identifier.
            incident_type: Incident type.

        Returns:
            True if the cooldown is still active.
        """
        with self._lock:
            next_allowed = self._next_allowed.get((camera_id, incident_type))
            if next_allowed is None:
                return False
            return datetime.now(UTC) < next_allowed

    def activate(self, camera_id: str, incident_type: IncidentType) -> None:
        """Activate a cooldown after a confirmed incident.

        Args:
            camera_id: Camera identifier.
            incident_type: Incident type.
        """
        with self._lock:
            seconds = self._durations[incident_type]
            self._next_allowed[(camera_id, incident_type)] = datetime.now(UTC) + timedelta(
                seconds=seconds
            )
