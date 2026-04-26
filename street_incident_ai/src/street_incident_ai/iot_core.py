from __future__ import annotations

import json
import time
from typing import Any, Callable

from awscrt import auth, io, mqtt
from awsiot import mqtt_connection_builder
from loguru import logger


MessageCallback = Callable[[str, bytes, bool, mqtt.QoS, bool], None]


class IoTCoreError(RuntimeError):
    """Raised when AWS IoT Core MQTT communication fails."""


class IoTCoreMqttPublisher:
    """AWS IoT Core MQTT client using MQTT over WebSockets with SigV4 IAM auth."""

    def __init__(
        self,
        endpoint: str | None,
        region_name: str,
        client_id: str,
        keep_alive_secs: int = 30,
        dry_run: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.region_name = region_name
        self.client_id = client_id
        self.keep_alive_secs = keep_alive_secs
        self.dry_run = dry_run
        self._is_connected = False
        self._connection: mqtt.Connection | None = None

        if dry_run:
            logger.warning("DRY_RUN_IOT=true; IoT Core messages will only be logged.")
            return
        if not endpoint:
            raise ValueError("IOT_ENDPOINT is required unless DRY_RUN_IOT=true.")

        self._event_loop_group = io.EventLoopGroup(1)
        self._host_resolver = io.DefaultHostResolver(self._event_loop_group)
        self._client_bootstrap = io.ClientBootstrap(self._event_loop_group, self._host_resolver)
        self._credentials_provider = auth.AwsCredentialsProvider.new_default_chain(self._client_bootstrap)
        self._connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=endpoint,
            region=region_name,
            credentials_provider=self._credentials_provider,
            client_bootstrap=self._client_bootstrap,
            client_id=client_id,
            clean_session=False,
            keep_alive_secs=keep_alive_secs,
            on_connection_interrupted=self._on_connection_interrupted,
            on_connection_resumed=self._on_connection_resumed,
        )
        logger.info("Initialized IoTCoreMqttPublisher endpoint={} client_id={}", endpoint, client_id)

    @staticmethod
    def _on_connection_interrupted(connection: mqtt.Connection, error: Exception, **kwargs: Any) -> None:
        logger.warning("IoT connection interrupted: {}", error)

    @staticmethod
    def _on_connection_resumed(
        connection: mqtt.Connection,
        return_code: mqtt.ConnectReturnCode,
        session_present: bool,
        **kwargs: Any,
    ) -> None:
        logger.info("IoT connection resumed return_code={} session_present={}", return_code, session_present)

    @staticmethod
    def default_log_callback(topic: str, payload: bytes, dup: bool, qos: mqtt.QoS, retain: bool, **kwargs: Any) -> None:
        try:
            decoded = payload.decode("utf-8")
            logger.info("IoT message received topic={} payload={}", topic, decoded)
        except UnicodeDecodeError:
            logger.info("IoT binary message received topic={} bytes={}", topic, len(payload))

    def connect(self) -> None:
        if self.dry_run:
            return
        if self._is_connected:
            return
        if self._connection is None:
            raise IoTCoreError("MQTT connection is not initialized.")
        try:
            logger.info("Connecting to AWS IoT endpoint={} client_id={}", self.endpoint, self.client_id)
            self._connection.connect().result()
            self._is_connected = True
            logger.info("Connected to AWS IoT Core.")
        except Exception as exc:  # awscrt exposes multiple exception types
            logger.exception("Failed to connect to AWS IoT Core.")
            raise IoTCoreError(f"Failed to connect to AWS IoT Core: {exc}") from exc

    def disconnect(self) -> None:
        if self.dry_run or not self._is_connected or self._connection is None:
            return
        try:
            logger.info("Disconnecting from AWS IoT Core.")
            self._connection.disconnect().result()
            self._is_connected = False
            logger.info("Disconnected from AWS IoT Core.")
        except Exception as exc:
            logger.warning("Failed to disconnect cleanly from AWS IoT Core: {}", exc)

    def publish(self, topic: str, message: dict[str, Any] | list[Any] | str | bytes, retain: bool = False) -> None:
        if isinstance(message, bytes):
            payload = message
        elif isinstance(message, str):
            payload = message.encode("utf-8")
        else:
            payload = json.dumps(message, ensure_ascii=False).encode("utf-8")

        if self.dry_run:
            logger.info("DRY_RUN IoT publish topic={} payload={}", topic, payload.decode("utf-8", errors="ignore"))
            return

        self.connect()
        assert self._connection is not None
        try:
            publish_future, packet_id = self._connection.publish(
                topic=topic,
                payload=payload,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                retain=retain,
            )
            publish_future.result()
            logger.info("Published IoT MQTT message topic={} packet_id={} bytes={}", topic, packet_id, len(payload))
        except Exception as exc:
            logger.exception("Failed to publish IoT MQTT message topic={}", topic)
            raise IoTCoreError(f"Failed to publish IoT MQTT message: {exc}") from exc

    def subscribe_publish_wait(
        self,
        topic: str,
        message: dict[str, Any] | list[Any] | str | bytes,
        wait_seconds: int = 5,
    ) -> None:
        """Solo test helper that subscribes to a topic, publishes once, and waits."""
        if self.dry_run:
            self.publish(topic, message)
            return
        self.connect()
        assert self._connection is not None
        try:
            subscribe_future, packet_id = self._connection.subscribe(
                topic=topic,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self.default_log_callback,
            )
            subscribe_result = subscribe_future.result()
            logger.info("Subscribed topic={} qos={} packet_id={}", topic, subscribe_result["qos"], packet_id)
            self.publish(topic, message)
            time.sleep(wait_seconds)
        finally:
            self.disconnect()
