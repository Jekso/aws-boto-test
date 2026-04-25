"""
AWS IoT Core MQTT publish/subscribe class for an EC2-hosted Python app.

This implementation uses MQTT over WebSockets with AWS SigV4 signing.
That means the EC2 IAM role is used for authentication, so you do NOT need
to store IoT device certificates on the Windows EC2 instance.

Required IAM actions on the EC2 role:
- iot:Connect
- iot:Publish
- iot:Subscribe
- iot:Receive
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional

from awscrt import auth, io, mqtt
from awsiot import mqtt_connection_builder


MessageCallback = Callable[[str, bytes, bool, mqtt.QoS, bool], None]


class IoTCoreMqttClient:
    """AWS IoT Core MQTT client using MQTT over WebSockets + EC2 IAM role."""

    def __init__(
        self,
        endpoint: str,
        region_name: str,
        client_id: str,
        keep_alive_secs: int = 30,
        clean_session: bool = False,
    ) -> None:
        """
        Args:
            endpoint: AWS IoT data endpoint, for example abc123-ats.iot.eu-west-1.amazonaws.com.
            region_name: AWS region, for example "eu-west-1".
            client_id: Unique MQTT client ID.
            keep_alive_secs: MQTT keep-alive interval.
            clean_session: False keeps subscriptions across reconnects when supported.
        """
        self.endpoint = endpoint
        self.region_name = region_name
        self.client_id = client_id

        self._event_loop_group = io.EventLoopGroup(1)
        self._host_resolver = io.DefaultHostResolver(self._event_loop_group)
        self._client_bootstrap = io.ClientBootstrap(self._event_loop_group, self._host_resolver)
        self._credentials_provider = auth.AwsCredentialsProvider.new_default_chain(self._client_bootstrap)

        self._connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=self.endpoint,
            region=self.region_name,
            credentials_provider=self._credentials_provider,
            client_bootstrap=self._client_bootstrap,
            client_id=self.client_id,
            clean_session=clean_session,
            keep_alive_secs=keep_alive_secs,
            on_connection_interrupted=self._on_connection_interrupted,
            on_connection_resumed=self._on_connection_resumed,
        )

    @staticmethod
    def _on_connection_interrupted(connection: mqtt.Connection, error: Exception, **kwargs: Any) -> None:
        print(f"[IoT] Connection interrupted: {error}")

    @staticmethod
    def _on_connection_resumed(
        connection: mqtt.Connection,
        return_code: mqtt.ConnectReturnCode,
        session_present: bool,
        **kwargs: Any,
    ) -> None:
        print(f"[IoT] Connection resumed. return_code={return_code}, session_present={session_present}")

    @staticmethod
    def default_print_callback(topic: str, payload: bytes, dup: bool, qos: mqtt.QoS, retain: bool, **kwargs: Any) -> None:
        """Default callback that prints received MQTT messages."""
        try:
            decoded = payload.decode("utf-8")
            try:
                decoded_json = json.loads(decoded)
                print(f"[IoT] Received on '{topic}': {json.dumps(decoded_json, indent=2)}")
            except json.JSONDecodeError:
                print(f"[IoT] Received on '{topic}': {decoded}")
        except UnicodeDecodeError:
            print(f"[IoT] Received binary message on '{topic}' with {len(payload)} bytes")

    def connect(self) -> None:
        """Connect to AWS IoT Core."""
        print(f"[IoT] Connecting to {self.endpoint} as client_id={self.client_id} ...")
        self._connection.connect().result()
        print("[IoT] Connected.")

    def disconnect(self) -> None:
        """Disconnect from AWS IoT Core."""
        print("[IoT] Disconnecting ...")
        self._connection.disconnect().result()
        print("[IoT] Disconnected.")

    def subscribe(
        self,
        topic: str,
        callback: Optional[MessageCallback] = None,
        qos: mqtt.QoS = mqtt.QoS.AT_LEAST_ONCE,
    ) -> None:
        """Subscribe to an MQTT topic."""
        final_callback = callback or self.default_print_callback
        subscribe_future, packet_id = self._connection.subscribe(
            topic=topic,
            qos=qos,
            callback=final_callback,
        )
        subscribe_result = subscribe_future.result()
        print(f"[IoT] Subscribed to '{topic}' with QoS={subscribe_result['qos']} packet_id={packet_id}")

    def publish(
        self,
        topic: str,
        message: dict[str, Any] | list[Any] | str | bytes,
        qos: mqtt.QoS = mqtt.QoS.AT_LEAST_ONCE,
        retain: bool = False,
    ) -> None:
        """Publish a dict/list/string/bytes payload to an MQTT topic."""
        if isinstance(message, bytes):
            payload = message
        elif isinstance(message, str):
            payload = message.encode("utf-8")
        else:
            payload = json.dumps(message, ensure_ascii=False).encode("utf-8")

        publish_future, packet_id = self._connection.publish(
            topic=topic,
            payload=payload,
            qos=qos,
            retain=retain,
        )
        publish_future.result()
        print(f"[IoT] Published to '{topic}' packet_id={packet_id}")

    def subscribe_publish_wait(
        self,
        topic: str,
        message: dict[str, Any] | list[Any] | str | bytes,
        wait_seconds: int = 5,
    ) -> None:
        """Convenience helper for testing: subscribe to a topic, publish to it, then wait."""
        self.connect()
        try:
            self.subscribe(topic)
            self.publish(topic, message)
            time.sleep(wait_seconds)
        finally:
            self.disconnect()
