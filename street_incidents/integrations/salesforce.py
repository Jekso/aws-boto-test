"""Salesforce REST API integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import requests
from loguru import logger
from street_incidents.utils.retry_compat import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from street_incidents.exceptions import IntegrationError
from street_incidents.models import IncidentRecord, SalesforceConfig


class SalesforceClient:
    """Create incident records in Salesforce."""

    def __init__(self, config: SalesforceConfig) -> None:
        """Initialize the client.

        Args:
            config: Salesforce API configuration.
        """
        self._config = config
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(IntegrationError),
    )
    def create_incident(self, incident: IncidentRecord) -> dict:
        """Create a Salesforce record for an incident.

        Args:
            incident: Final incident record.

        Returns:
            Response JSON from Salesforce.

        Raises:
            IntegrationError: If auth or record creation fails.
        """
        token = self._get_access_token()
        url = (
            f"{self._config.base_url}/services/data/{self._config.api_version}/sobjects/"
            f"{self._config.object_api_name}/"
        )
        payload = {
            "Incident_Id__c": incident.incident_id,
            "Incident_Type__c": incident.incident_type.value,
            "Camera_Id__c": incident.camera.camera_id,
            "Camera_Name__c": incident.camera.camera_name,
            "Timestamp_UTC__c": incident.timestamp_utc.isoformat(),
            "Confidence__c": incident.decision.confidence,
            "Caption__c": incident.decision.caption,
            "Reason__c": incident.decision.reason,
            "Evidence_URL__c": incident.evidence.evidence_url if incident.evidence else None,
            "Raw_JSON__c": incident.model_dump_json(),
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code >= 400:
            raise IntegrationError(
                f"Salesforce create failed ({response.status_code}): {response.text}"
            )
        logger.info("Created Salesforce incident record for {}", incident.incident_id)
        return response.json()

    def _get_access_token(self) -> str:
        """Get or refresh an OAuth access token.

        Returns:
            OAuth access token.

        Raises:
            IntegrationError: If token retrieval fails.
        """
        if self._access_token and self._token_expiry and datetime.now(UTC) < self._token_expiry:
            return self._access_token

        response = requests.post(
            self._config.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise IntegrationError(
                f"Salesforce token request failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise IntegrationError("Salesforce token response did not contain access_token.")
        expires_in = int(payload.get("expires_in", 1800))
        self._access_token = token
        self._token_expiry = datetime.now(UTC) + timedelta(seconds=max(60, expires_in - 60))
        return token
