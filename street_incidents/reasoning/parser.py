"""Parse structured JSON output from the reasoning model."""

from __future__ import annotations

import json

from pydantic import ValidationError

from street_incidents.exceptions import ParseError
from street_incidents.models import IncidentType, ReasoningDecision


class ReasoningParser:
    """Convert model output text into typed reasoning decisions."""

    def parse(self, content: str, expected_incident_type: IncidentType) -> ReasoningDecision:
        """Parse a JSON string into a reasoning decision.

        Args:
            content: Raw model text content.
            expected_incident_type: Expected incident type for validation.

        Returns:
            Parsed reasoning decision.

        Raises:
            ParseError: If the content is invalid or mismatched.
        """
        cleaned = self._extract_json(content)
        try:
            payload = json.loads(cleaned)
            decision = ReasoningDecision.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ParseError(f"Unable to parse Qwen response: {exc}") from exc

        if decision.incident_type is not expected_incident_type:
            raise ParseError(
                f"Unexpected incident_type in response. Expected {expected_incident_type.value}, "
                f"got {decision.incident_type.value}."
            )
        return decision

    @staticmethod
    def _extract_json(content: str) -> str:
        """Extract a JSON object from free-form content.

        Args:
            content: Raw model text.

        Returns:
            JSON-like string.

        Raises:
            ParseError: If no JSON object boundaries are found.
        """
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ParseError("No JSON object found in model output.")
        return content[start : end + 1]
