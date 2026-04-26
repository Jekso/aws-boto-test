"""Custom exception types for the project."""


class StreetIncidentsError(Exception):
    """Base exception for the project."""


class ConfigError(StreetIncidentsError):
    """Raised when configuration is invalid."""


class StreamError(StreetIncidentsError):
    """Raised when RTSP stream operations fail."""


class DetectionError(StreetIncidentsError):
    """Raised when local object detection fails."""


class ReasoningError(StreetIncidentsError):
    """Raised when remote reasoning fails."""


class ParseError(StreetIncidentsError):
    """Raised when model output cannot be parsed."""


class StorageError(StreetIncidentsError):
    """Raised when artifact storage fails."""


class IntegrationError(StreetIncidentsError):
    """Raised when a downstream integration fails."""
