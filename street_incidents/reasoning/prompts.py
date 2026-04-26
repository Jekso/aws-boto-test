"""Prompt templates for Bedrock Qwen3-VL reasoning."""

from __future__ import annotations

from street_incidents.models import IncidentType


class PromptFactory:
    """Build system and user prompts for incident reasoning."""

    @staticmethod
    def system_prompt() -> str:
        """Return the shared system prompt.

        Returns:
            System prompt text.
        """
        return (
            "You are an incident classification model for street camera monitoring. "
            "Return valid JSON only. Do not wrap the output in markdown. "
            "Do not add any explanatory text outside the JSON."
        )

    @staticmethod
    def user_prompt(incident_type: IncidentType, camera_name: str) -> str:
        """Create a user prompt for a target incident.

        Args:
            incident_type: Incident type to evaluate.
            camera_name: Camera name for context.

        Returns:
            User prompt text with explicit JSON schema.
        """
        if incident_type is IncidentType.LOST_PET:
            return (
                f"Camera: {camera_name}. Determine whether the image shows a likely lost pet. "
                "Respond with JSON only using this schema: "
                '{"incident_type":"lost_pet","is_incident":true,"confidence":0.0,'
                '"reason":"","caption":"","visible_pet_type":"","visible_owner_present":false,'
                '"recommended_action":"ignore|monitor|report","extra":{}}'
            )
        if incident_type is IncidentType.FLOOR_GARBAGE:
            return (
                f"Camera: {camera_name}. Determine whether the image shows garbage or litter on the floor "
                "that should be reported. Respond with JSON only using this schema: "
                '{"incident_type":"floor_garbage","is_incident":true,"confidence":0.0,'
                '"reason":"","caption":"","recommended_action":"ignore|monitor|report","extra":{}}'
            )
        return (
            f"Camera: {camera_name}. Determine whether the image shows an overfilled trash bin "
            "that should be reported. Respond with JSON only using this schema: "
            '{"incident_type":"overfilled_bin","is_incident":true,"confidence":0.0,'
            '"reason":"","caption":"","recommended_action":"ignore|monitor|report","extra":{}}'
        )
