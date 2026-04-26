"""Amazon Bedrock Qwen3-VL client wrapper."""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from street_incidents.utils.retry_compat import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from street_incidents.exceptions import ReasoningError
from street_incidents.models import BedrockConfig, CameraConfig, IncidentType, ReasoningDecision
from street_incidents.reasoning.parser import ReasoningParser
from street_incidents.reasoning.prompts import PromptFactory


class BedrockQwenClient:
    """Call Amazon Bedrock Converse API for structured incident reasoning."""

    def __init__(self, config: BedrockConfig) -> None:
        """Initialize the client.

        Args:
            config: Bedrock runtime configuration.
        """
        self._config = config
        self._client: BaseClient = boto3.client(
            "bedrock-runtime",
            region_name=config.region_name,
        )
        self._parser = ReasoningParser()

    @property
    def model_id(self) -> str:
        """Return the configured Bedrock model ID.

        Returns:
            Bedrock model identifier.
        """
        return self._config.model_id

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(ReasoningError),
    )
    def classify_image(
        self,
        image_bytes: bytes,
        incident_type: IncidentType,
        camera: CameraConfig,
    ) -> ReasoningDecision:
        """Classify an image for a target incident type.

        Args:
            image_bytes: Raw image bytes.
            incident_type: Target incident type.
            camera: Camera metadata for prompt context.

        Returns:
            Structured reasoning decision.

        Raises:
            ReasoningError: If the API call fails or the response is malformed.
        """
        try:
            response = self._client.converse(
                modelId=self._config.model_id,
                system=[{"text": PromptFactory.system_prompt()}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": PromptFactory.user_prompt(
                                    incident_type=incident_type,
                                    camera_name=camera.camera_name,
                                )
                            },
                            {
                                "image": {
                                    "format": "jpeg",
                                    "source": {"bytes": image_bytes},
                                }
                            },
                        ],
                    }
                ],
                inferenceConfig={
                    "temperature": self._config.temperature,
                    "topP": self._config.top_p,
                    "maxTokens": self._config.max_tokens,
                },
            )
            text = self._extract_text(response)
            return self._parser.parse(text, expected_incident_type=incident_type)
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - runtime integration
            raise ReasoningError(f"Bedrock request failed: {exc}") from exc
        except Exception as exc:
            raise ReasoningError(f"Reasoning pipeline failed: {exc}") from exc

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        """Extract text from a Converse API response.

        Args:
            response: Converse API response payload.

        Returns:
            Concatenated text content.

        Raises:
            ReasoningError: If no textual content is found.
        """
        content = response.get("output", {}).get("message", {}).get("content", [])
        parts: list[str] = []
        for item in content:
            if "text" in item:
                parts.append(item["text"])
        if not parts:
            raise ReasoningError(f"No text content found in Bedrock response: {json.dumps(response)}")
        return "\n".join(parts)
