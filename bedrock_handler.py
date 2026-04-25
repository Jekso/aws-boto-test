"""
Amazon Bedrock Qwen VL handling class.

This class uses the Bedrock Runtime Converse API with Qwen3 VL:
    model_id = "qwen.qwen3-vl-235b-a22b"

Authentication:
- On EC2, attach an IAM role with Bedrock invoke permissions.
- Boto3 automatically uses the EC2 role credentials.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


class BedrockQwenVLClient:
    """Client wrapper for Qwen3 VL on Amazon Bedrock Runtime."""

    def __init__(
        self,
        region_name: str,
        model_id: str = "qwen.qwen3-vl-235b-a22b",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> None:
        """
        Args:
            region_name: AWS region where the model is available, for example "eu-west-1".
            model_id: Bedrock model ID.
            max_tokens: Max output tokens.
            temperature: Lower is more deterministic.
            top_p: Nucleus sampling value.
        """
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.client = boto3.client("bedrock-runtime", region_name=region_name)

    @staticmethod
    def _image_format_from_path(image_path: str | Path) -> str:
        """Return Bedrock image format name from local path."""
        suffix = Path(image_path).suffix.lower().replace(".", "")
        if suffix == "jpg":
            return "jpeg"
        allowed = {"jpeg", "png", "gif", "webp"}
        if suffix not in allowed:
            raise ValueError(f"Unsupported image format '{suffix}'. Use one of: {sorted(allowed)}")
        return suffix

    @staticmethod
    def _extract_text(response: Dict[str, Any]) -> str:
        """Extract plain text from a Converse response."""
        content_items = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = [item.get("text", "") for item in content_items if "text" in item]
        return "\n".join(part for part in text_parts if part).strip()

    @staticmethod
    def _parse_json_from_text(text: str) -> Any:
        """Parse JSON even when the model wraps it in markdown fences."""
        cleaned = text.strip()

        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        # Try direct JSON first.
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Fallback: extract first JSON object/array.
        start_positions = [pos for pos in [cleaned.find("{"), cleaned.find("[")] if pos != -1]
        if not start_positions:
            raise ValueError(f"No JSON object or array found in model output: {text}")

        start = min(start_positions)
        end_obj = cleaned.rfind("}")
        end_arr = cleaned.rfind("]")
        end = max(end_obj, end_arr)

        if end <= start:
            raise ValueError(f"Could not identify valid JSON boundaries in model output: {text}")

        return json.loads(cleaned[start : end + 1])

    def ask_text(self, prompt: str) -> str:
        """Send a text-only prompt to Qwen VL and return the text answer."""
        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                inferenceConfig={
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                    "topP": self.top_p,
                },
            )
            return self._extract_text(response)
        except ClientError as exc:
            raise RuntimeError(f"Bedrock text request failed: {exc}") from exc

    def analyze_image(self, image_path: str | Path, prompt: str) -> str:
        """Send an image + text prompt to Qwen VL and return the text answer."""
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        image_format = self._image_format_from_path(image_path)
        image_bytes = image_path.read_bytes()

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": image_format,
                                    "source": {"bytes": image_bytes},
                                }
                            },
                            {"text": prompt},
                        ],
                    }
                ],
                inferenceConfig={
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                    "topP": self.top_p,
                },
            )
            return self._extract_text(response)
        except ClientError as exc:
            raise RuntimeError(f"Bedrock image request failed: {exc}") from exc

    def analyze_image_as_json(
        self,
        image_path: str | Path,
        task_prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Ask Qwen VL to return structured JSON for an image."""
        schema_text = ""
        if output_schema:
            schema_text = f"\nReturn JSON using this schema:\n{json.dumps(output_schema, indent=2)}"

        prompt = f"""
You are an image analysis system.
Analyze the image and answer ONLY with valid JSON.
Do not include markdown, explanation, or extra text.

Task:
{task_prompt}
{schema_text}
""".strip()

        text_output = self.analyze_image(image_path=image_path, prompt=prompt)
        return self._parse_json_from_text(text_output)
