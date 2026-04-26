import json
from pathlib import Path
from typing import Any

import cv2
import supervision as sv
from ultralytics import YOLOE

YOLO_MODEL = "yoloe-26x-seg.pt"
GARBAGE_CLASSES = [
    "trash can",
    "trash bin",
    "spray can",
    "bag",
    "toilet paper",
    "beer bottle",
    "beer can",
    "bottle",
    "bottle cap",
    "can",
    "cardboard",
    "cardboard box",
    "carton",
    "cigar",
    "cigarette",
    "coffee cup",
    "cup",
    "debris",
    "diaper",
    "paper cup",
    "garbage",
    "glass bottle",
    "glass jar",
    "grocery bag",
    "leftover",
    "napkin",
    "paper",
    "paper bag",
    "paper plate",
    "paper towel",
    "plastic",
    "rubble",
    "scrap",
    "shopping bag",
    "tin",
    "tinfoil",
    "tissue",
    "waste",
    "wine bottle",
    "wrapping paper",
]
PET_CLASSES = ["dog", "cat"]
ALL_CLASSES = PET_CLASSES + GARBAGE_CLASSES



def get_detection_names_and_labels(results: Any, detections: sv.Detections) -> tuple[list[str], list[str]]:
    """Build class names and labels from YOLOE detections.

    Args:
        results: Raw Ultralytics result object.
        detections: Supervision detections object.

    Returns:
        Tuple of class names and display labels.
    """
    class_names: list[str] = []
    labels: list[str] = []

    if detections.class_id is None or detections.confidence is None:
        return class_names, labels

    names_map = results.names if hasattr(results, "names") else {}

    for class_id, confidence in zip(detections.class_id.tolist(), detections.confidence.tolist()):
        class_name = str(names_map.get(int(class_id), int(class_id)))
        class_names.append(class_name)
        labels.append(f"[{class_id}] {class_name} {confidence:.2f}")

    return class_names, labels


def annotate_image(
    image: Any,
    detections: sv.Detections,
    labels: list[str],
) -> Any:
    """Annotate the image with detections and labels.

    Args:
        image: Input OpenCV image.
        detections: Supervision detections.
        labels: Label strings.

    Returns:
        Annotated image.
    """
    box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    annotated = box_annotator.annotate(scene=image.copy(), detections=detections)
    annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)
    return annotated


def split_detected_categories(class_names: list[str]) -> tuple[list[str], list[str]]:
    """Split detected class names into garbage and pet hits.

    Args:
        class_names: Detected class names.

    Returns:
        Tuple of unique garbage hits and pet hits.
    """
    garbage_hits: list[str] = []
    pet_hits: list[str] = []

    for name in class_names:
        if name in GARBAGE_CLASSES and name not in garbage_hits:
            garbage_hits.append(name)
        if name in PET_CLASSES and name not in pet_hits:
            pet_hits.append(name)

    return garbage_hits, pet_hits


def process_image(
    image_path: str,
    output_image_path: str,
    detector_model: str,
    conf: float,
) -> dict[str, Any]:
    """Run the full image pipeline: YOLOE detection.

    Args:
        image_path: Path to the input image.
        output_image_path: Path to save the annotated image.
        detector_model: Path to YOLOE weights.
        conf: YOLOE confidence threshold.

    Returns:
        Final combined result dictionary.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to read image: {image_path}")

    yolo_model = YOLOE(detector_model)
    yolo_model.set_classes(ALL_CLASSES)

    results = yolo_model.predict(source=image, conf=conf, verbose=False)[0]
    detections = sv.Detections.from_ultralytics(results)

    class_names, labels = get_detection_names_and_labels(results, detections)
    annotated_image = annotate_image(image=image, detections=detections, labels=labels)

    output_path = Path(output_image_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), annotated_image)

    garbage_hits, pet_hits = split_detected_categories(class_names)

    if garbage_hits:
        analyses["garbage"] = {
            "trigger_classes": garbage_hits,
        }

    if pet_hits:
        analyses["pet"] = {
            "trigger_classes": pet_hits,
        }

    return {
        "image_path": image_path,
        "annotated_image_path": str(output_path),
        "all_detected_classes": class_names,
        "garbage_trigger_classes": garbage_hits,
        "pet_trigger_classes": pet_hits,
    }


image_path = "../data/images/waste/20.jpg"
output_image = "./outputs/annotated_image.jpg"

result = process_image(
    image_path=image_path,
    output_image_path=output_image,
    detector_model=YOLO_MODEL,
    conf=CONFIDENCE,
)
print(json.dumps(result, indent=2, ensure_ascii=False))


