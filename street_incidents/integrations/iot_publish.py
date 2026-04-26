"""AWS IoT Core publishing client."""

from __future__ import annotations

import json

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from street_incidents.utils.retry_compat import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from street_incidents.exceptions import IntegrationError
from street_incidents.models import IncidentRecord, IoTConfig


class IoTPublisher:
    """Publish confirmed incidents to AWS IoT Core."""

    def __init__(self, config: IoTConfig, region_name: str) -> None:
        """Initialize the publisher.

        Args:
            config: IoT publish configuration.
            region_name: AWS region.
        """
        self._config = config
        control_client: BaseClient = boto3.client("iot", region_name=region_name)
        endpoint = control_client.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
        self._data_client: BaseClient = boto3.client(
            "iot-data",
            region_name=region_name,
            endpoint_url=f"https://{endpoint}",
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(IntegrationError),
    )
    def publish_incident(self, incident: IncidentRecord) -> None:
        """Publish a compact incident payload.

        Args:
            incident: Incident record.

        Raises:
            IntegrationError: If publishing fails.
        """
        try:
            self._data_client.publish(
                topic=self._config.topic,
                qos=self._config.qos,
                payload=json.dumps(incident.compact_payload()).encode("utf-8"),
            )
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - runtime integration
            raise IntegrationError(f"Failed to publish to IoT Core: {exc}") from exc
