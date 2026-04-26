from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
from street_incident_ai.config import load_app_config
from street_incident_ai.iot_core import IoTCoreMqttPublisher
from street_incident_ai.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Test IoT Core MQTT publish/subscribe.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--topic", default=None)
    parser.add_argument("--wait", type=int, default=5)
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    topic = args.topic or config.iot_topic
    client = IoTCoreMqttPublisher(
        endpoint=config.iot_endpoint,
        region_name=config.aws_region,
        client_id=f"{config.iot_client_id}-test",
        dry_run=config.dry_run_iot,
    )
    payload = {
        "test": True,
        "source": "scripts/test_iot.py",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        client.subscribe_publish_wait(topic, payload, wait_seconds=args.wait)
    finally:
        client.disconnect()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
