from __future__ import annotations

from street_incident_ai.models import DetectionResult


WASTE_PROMPT = """Analyze the provided full street-camera image and decide whether the visible public trash can / waste area is Safe/Healthy or Unsafe/Unhealthy.

Important context:
- Analyze the whole image, not only the YOLO bounding box.
- Base the answer only on visible evidence in the frame.
- If the image does not clearly show a trash can or waste area, return status "safe" with a low confidence_score and explain that there is not enough visible waste evidence.

Use the following criteria:
1. Containment: Is all waste inside the bin, or is there overflow and litter on the ground within approximately a 2-meter radius?
2. Structural Integrity: Is the bin upright, properly secured, and free of significant physical damage?
3. Hygiene & Hazards: Are there signs of liquid leaks, animal scavenging, sharps, chemicals, or other hazardous material?
4. Accessibility: Is the area around the bin clear for pedestrians and maintenance workers?

Return JSON only in exactly this structure:
{
  "status": "safe" | "unsafe",
  "confidence_score": 0,
  "key_observations": [
    "specific visual cue 1",
    "specific visual cue 2"
  ],
  "containment": "clear short assessment",
  "structural_integrity": "clear short assessment",
  "hygiene_hazards": "clear short assessment",
  "accessibility": "clear short assessment",
  "reason": "one short overall explanation"
}

If the bin appears normal, clean, upright, and the surrounding area is clear, return this style of answer:
{
  "status": "safe",
  "confidence_score": 90,
  "key_observations": ["clear perimeter", "waste contained inside bin"],
  "containment": "Waste appears properly contained.",
  "structural_integrity": "The bin appears upright and undamaged.",
  "hygiene_hazards": "No clear hygiene or hazard issue is visible.",
  "accessibility": "The area around the bin appears clear.",
  "reason": "The trash can appears healthy and safe based on visible evidence."
}

Rules:
- status must be either "safe" or "unsafe".
- confidence_score must be an integer from 0 to 100.
- key_observations must be a list of short visual observations only.
- containment, structural_integrity, hygiene_hazards, and accessibility must each contain a short assessment based only on visible evidence.
- reason must be one short summary sentence.
- Do not use markdown formatting like ```.
- Return JSON only with no extra text before or after it."""


PET_PROMPT = """Analyze the provided full street-camera image and determine whether the visible pet appears likely lost, unattended, or safely accompanied.

Important context:
- Analyze the whole image, not only the YOLO bounding box.
- Base the answer only on visible evidence in the frame.
- Do not assume a pet is lost only because a dog/cat is visible.
- If evidence is unclear, return status "uncertain" instead of guessing.

Use the following criteria:
1. Owner Presence: Is there a clearly visible owner, handler, leash, or direct supervision nearby?
2. Animal Context: Does the pet appear dirty, tired, hungry, isolated, or as if it may have been unattended for some time?
3. Behavior and Position: Does the pet appear to be wandering, sleeping alone, waiting alone, roaming near traffic, or otherwise unattended?
4. Safety Context: Is the pet in a potentially unsafe situation such as near vehicles, in the road, or in a confusing public environment?

Return JSON only in exactly this structure:
{
  "status": "likely_lost" | "not_lost" | "uncertain",
  "confidence_score": 0,
  "key_observations": [
    "specific visual cue 1",
    "specific visual cue 2"
  ],
  "owner_presence": "clear short assessment",
  "animal_context": "clear short assessment",
  "safety_context": "clear short assessment",
  "reason": "one short overall explanation",
  "leash_found": true,
  "direct_supervision": 0
}

If the pet appears clearly accompanied, supervised, leashed, or not in a risky unattended context, return this style of answer:
{
  "status": "not_lost",
  "confidence_score": 90,
  "key_observations": ["owner visible nearby", "pet appears supervised"],
  "owner_presence": "A likely owner or direct supervision is visible.",
  "animal_context": "The pet does not appear isolated.",
  "safety_context": "No clear unattended street risk is visible.",
  "reason": "The pet does not appear lost based on visible evidence.",
  "leash_found": true,
  "direct_supervision": 90
}

Rules:
- status must be one of "likely_lost", "not_lost", or "uncertain".
- confidence_score must be an integer from 0 to 100.
- key_observations must be a list of short visual observations only.
- owner_presence, animal_context, and safety_context must each contain a short assessment based only on visible evidence.
- leash_found must be a JSON boolean: true or false.
- direct_supervision must be an integer from 0 to 100.
- reason must be one short summary sentence.
- Do not use markdown formatting like ```.
- Return JSON only with no extra text before or after it."""


GENERIC_INCIDENT_PROMPT = """You are an AI incident validation system for street camera frames.
Analyze the whole image, not only the detected box.

Decide if this frame is a real actionable incident:
- lost_pet: a dog/cat appears unattended or likely lost in a public/street context.
- street_garbage: overflowing garbage, unsafe waste, scattered trash, or unhealthy garbage situation.
- normal: object exists but no actionable incident.

Return ONLY valid JSON with exactly these keys:
{
  "is_incident": true,
  "incident_type": "lost_pet | street_garbage | unknown",
  "confidence_score": 0.0,
  "risk_level": "low | medium | high | unknown",
  "description": "short practical explanation",
  "recommended_action": "short next action"
}"""


def build_reasoning_prompt(detection: DetectionResult) -> str:
    """Build the Bedrock prompt based on the preliminary YOLOE incident type."""
    trigger_classes = detection.pet_trigger_classes or detection.garbage_trigger_classes or detection.all_detected_classes
    context = f"""
YOLOE preliminary context:
- preliminary_incident_type: {detection.incident_type}
- detected_target_classes: {trigger_classes}
- max_detection_confidence: {detection.max_confidence:.3f}
""".strip()

    if detection.incident_type == "street_garbage":
        return f"{context}\n\n{WASTE_PROMPT}"
    if detection.incident_type == "lost_pet":
        return f"{context}\n\n{PET_PROMPT}"
    return f"{context}\n\n{GENERIC_INCIDENT_PROMPT}"
