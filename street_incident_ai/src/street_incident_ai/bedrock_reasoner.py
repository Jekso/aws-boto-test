from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import boto3
import cv2
import numpy as np
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger

from street_incident_ai.models import DetectionResult, FramePacket, ReasoningResult


class BedrockReasoningError(RuntimeError):
    """Raised when Bedrock reasoning fails."""


class BedrockNovaReasoner:
    """Vision reasoning with Amazon Nova on Amazon Bedrock Converse API."""

    def __init__(
        self,
        region_name: str,
        model_id: str = "eu.amazon.nova-lite-v1:0",
        max_tokens: int = 800,
        temperature: float = 0.1,
        dry_run: bool = False,
    ) -> None:
        self.region_name = region_name
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.dry_run = dry_run
        self.client = boto3.client("bedrock-runtime", region_name=region_name) if not dry_run else None
        logger.info("Initialized BedrockNovaReasoner model_id={} region={} dry_run={}", model_id, region_name, dry_run)

    @staticmethod
    def _frame_to_jpeg_bytes(frame_bgr: np.ndarray) -> bytes:
        ok, buffer = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise BedrockReasoningError("Failed to encode frame to JPEG bytes.")
        return buffer.tobytes()

    @staticmethod
    def _image_bytes_from_file(image_path: str | Path) -> tuple[bytes, str]:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        suffix = path.suffix.lower().replace(".", "")
        image_format = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
        if image_format not in {"jpeg", "png", "gif", "webp"}:
            raise ValueError(f"Unsupported Bedrock image format: {suffix}")
        return path.read_bytes(), image_format

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        content_items = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = [item.get("text", "") for item in content_items if "text" in item]
        return "\n".join(part for part in text_parts if part).strip()

    @staticmethod
    def _parse_json_from_text(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                parsed_again = json.loads(parsed)
                if isinstance(parsed_again, dict):
                    return parsed_again
        except json.JSONDecodeError:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise BedrockReasoningError(f"No JSON object found in Bedrock output: {text}")
        parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise BedrockReasoningError(f"Bedrock output was not a JSON object: {text}")
        return parsed

    @staticmethod
    def _prompt(detection: DetectionResult) -> str:
        trigger_classes = detection.pet_trigger_classes or detection.garbage_trigger_classes
        return f"""
You are an AI incident validation system for street camera frames.
Analyze the WHOLE image, not only the detected box.
YOLOE already detected these possible target classes: {trigger_classes}.
The preliminary incident type is: {detection.incident_type}.

Decide if this frame is a real actionable incident:
- lost_pet: a dog/cat appears unattended or likely lost in a public/street context.
- street_garbage: overflowing garbage, unsafe waste, scattered trash, or unhealthy garbage situation.
- normal: object exists but no actionable incident.

Return ONLY valid JSON with exactly these keys:
{{
  "is_incident": true,
  "incident_type": "lost_pet | street_garbage | unknown",
  "confidence_score": 0.0,
  "risk_level": "low | medium | high | unknown",
  "description": "short practical explanation",
  "recommended_action": "short next action"
}}
""".strip()

    def _call_bedrock(self, image_bytes: bytes, image_format: str, prompt: str) -> dict[str, Any]:
        if self.dry_run:
            logger.warning("DRY_RUN_BEDROCK=true; returning simulated reasoning result.")
            return {
                "is_incident": True,
                "incident_type": "unknown",
                "confidence_score": 0.75,
                "risk_level": "medium",
                "description": "Dry-run reasoning result. Bedrock was not called.",
                "recommended_action": "Review manually.",
            }

        assert self.client is not None
        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
                            {"text": prompt},
                        ],
                    }
                ],
                inferenceConfig={
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            )
            text = self._extract_text(response)
            logger.debug("Raw Bedrock text output: {}", text)
            return self._parse_json_from_text(text)
        except (ClientError, BotoCoreError, json.JSONDecodeError) as exc:
            logger.exception("Bedrock reasoning failed model_id={}", self.model_id)
            raise BedrockReasoningError(f"Bedrock reasoning failed: {exc}") from exc

    def analyze_frame(self, packet: FramePacket, detection: DetectionResult) -> ReasoningResult:
        """Analyze the whole frame when YOLOE detected a target object."""
        prompt = self._prompt(detection)
        image_bytes = self._frame_to_jpeg_bytes(packet.frame_bgr)
        parsed = self._call_bedrock(image_bytes=image_bytes, image_format="jpeg", prompt=prompt)
        return self._to_reasoning_result(parsed, fallback_type=detection.incident_type)

    def analyze_image_file(self, image_path: str | Path, detection: DetectionResult | None = None) -> ReasoningResult:
        """Solo helper: run Bedrock reasoning on one image file."""
        if detection is None:
            detection = DetectionResult(
                has_target=True,
                incident_type="unknown",
                boxes=[],
                labels=[],
                all_detected_classes=[],
                garbage_trigger_classes=[],
                pet_trigger_classes=[],
                max_confidence=0.0,
            )
        image_bytes, image_format = self._image_bytes_from_file(image_path)
        parsed = self._call_bedrock(image_bytes=image_bytes, image_format=image_format, prompt=self._prompt(detection))
        return self._to_reasoning_result(parsed, fallback_type=detection.incident_type)

    @staticmethod
    def _to_reasoning_result(parsed: dict[str, Any], fallback_type: str) -> ReasoningResult:
        confidence = parsed.get("confidence_score", 0.0)
        try:
            confidence_float = float(confidence)
        except (TypeError, ValueError):
            confidence_float = 0.0
        incident_type = str(parsed.get("incident_type") or fallback_type)
        if incident_type not in {"lost_pet", "street_garbage", "unknown"}:
            incident_type = "unknown"
        result = ReasoningResult(
            is_incident=bool(parsed.get("is_incident", False)),
            incident_type=incident_type,  # type: ignore[arg-type]
            confidence_score=max(0.0, min(1.0, confidence_float)),
            description=str(parsed.get("description", "")),
            risk_level=str(parsed.get("risk_level", "unknown")),
            recommended_action=str(parsed.get("recommended_action", "review")),
            raw_response=parsed,
        )
        logger.info(
            "Bedrock reasoning complete is_incident={} incident_type={} confidence={:.3f}",
            result.is_incident,
            result.incident_type,
            result.confidence_score,
        )
        return result
