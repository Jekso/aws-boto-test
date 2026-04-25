"""
Example usage for:
1. S3 JSON/image upload + object read + presigned URL
2. Amazon Bedrock Qwen VL text/image inference
3. AWS IoT Core MQTT publish/subscribe

Before running on Windows EC2:
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt

Required environment variables:
    AWS_REGION=eu-west-1
    S3_BUCKET=your-bucket-name
    IOT_ENDPOINT=your-iot-endpoint-ats.iot.eu-west-1.amazonaws.com
    IOT_CLIENT_ID=ec2-python-demo-01
    IOT_TOPIC=street/incidents/test
    BEDROCK_MODEL_ID=qwen.qwen3-vl-235b-a22b

Optional:
    SAMPLE_IMAGE_PATH=C:\path\to\sample.jpg
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

from bedrock_handler import BedrockQwenVLClient
from iot_core_handler import IoTCoreMqttClient
from s3_handler import S3Handler


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def demo_s3(region: str, bucket: str, sample_image_path: str | None) -> None:
    print("\n=== S3 DEMO ===")
    s3 = S3Handler(bucket_name=bucket, region_name=region)

    timestamp = int(time.time())
    json_key = f"demo/results/result-{timestamp}.json"

    sample_result = {
        "incident_id": f"incident-{timestamp}",
        "incident_type": "test",
        "status": "created_from_ec2_python",
        "confidence_score": 0.99,
    }

    s3_uri = s3.upload_json(sample_result, json_key)
    print(f"Uploaded JSON: {s3_uri}")

    loaded = s3.read_json(json_key)
    print(f"Read JSON from S3: {loaded}")

    presigned_url = s3.generate_presigned_get_url(json_key, expires_in=3600)
    print(f"Temporary presigned GET URL: {presigned_url}")

    if sample_image_path and Path(sample_image_path).exists():
        image_key = f"demo/images/{Path(sample_image_path).name}"
        image_s3_uri = s3.upload_image(sample_image_path, image_key)
        print(f"Uploaded image: {image_s3_uri}")
    else:
        print("No valid SAMPLE_IMAGE_PATH provided; skipping image upload.")


def demo_bedrock(region: str, model_id: str, sample_image_path: str | None) -> None:
    print("\n=== BEDROCK QWEN VL DEMO ===")
    bedrock = BedrockQwenVLClient(region_name=region, model_id=model_id)

    text_answer = bedrock.ask_text("Return a short JSON object with keys service and status about Amazon Bedrock.")
    print(f"Text answer:\n{text_answer}")

    if sample_image_path and Path(sample_image_path).exists():
        schema = {
            "is_relevant_incident": "boolean",
            "incident_type": "lost_pet | garbage_bin_status | unknown",
            "description": "string",
            "confidence_score": "number from 0 to 1",
        }

        task_prompt = """
Classify whether this image shows one of these:
1. lost pet incident
2. overflowing/unsafe garbage bin
3. normal/healthy scene
"""

        result_json = bedrock.analyze_image_as_json(
            image_path=sample_image_path,
            task_prompt=task_prompt,
            output_schema=schema,
        )
        print(f"Image structured JSON:\n{result_json}")
    else:
        print("No valid SAMPLE_IMAGE_PATH provided; skipping Bedrock image analysis.")


def demo_iot(region: str, endpoint: str, client_id: str, topic: str) -> None:
    print("\n=== AWS IOT CORE MQTT DEMO ===")
    iot_client = IoTCoreMqttClient(
        endpoint=endpoint,
        region_name=region,
        client_id=client_id,
    )

    message = {
        "source": "windows-ec2-python",
        "message_type": "test_event",
        "timestamp_epoch": int(time.time()),
        "status": "hello_from_ec2",
    }

    iot_client.subscribe_publish_wait(
        topic=topic,
        message=message,
        wait_seconds=5,
    )


def main() -> None:
    load_dotenv()

    region = env_required("AWS_REGION")
    bucket = env_required("S3_BUCKET")
    # iot_endpoint = env_required("IOT_ENDPOINT")
    # iot_client_id = os.getenv("IOT_CLIENT_ID", "ec2-python-demo-01")
    # iot_topic = os.getenv("IOT_TOPIC", "street/incidents/test")
    # bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "qwen.qwen3-vl-235b-a22b")
    # sample_image_path = os.getenv("SAMPLE_IMAGE_PATH")

    demo_s3(region, bucket, sample_image_path)
    # demo_bedrock(region, bedrock_model_id, sample_image_path)
    # demo_iot(region, iot_endpoint, iot_client_id, iot_topic)


if __name__ == "__main__":
    main()
