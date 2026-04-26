from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger

from street_incident_ai.models import IncidentEvent, SalesforceCaseResult


class SalesforceError(RuntimeError):
    """Raised when Salesforce token/case API fails."""


@dataclass(slots=True)
class SalesforceToken:
    """OAuth token response from Salesforce."""

    access_token: str
    token_type: str
    instance_url: str | None
    raw: dict[str, Any]


class SalesforceCaseClient:
    """Salesforce client for token retrieval and DahuaCreateCaseAPI ticket creation."""

    def __init__(
        self,
        token_url: str | None,
        case_url: str | None,
        client_id: str | None,
        client_secret: str | None,
        timeout_seconds: int = 30,
        dry_run: bool = False,
    ) -> None:
        self.token_url = token_url
        self.case_url = case_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds
        self.dry_run = dry_run
        self._cached_token: SalesforceToken | None = None
        logger.info("Initialized SalesforceCaseClient dry_run={} case_url={}", dry_run, case_url)

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "SALESFORCE_TOKEN_URL": self.token_url,
                "SALESFORCE_CASE_URL": self.case_url,
                "SALESFORCE_CLIENT_ID": self.client_id,
                "SALESFORCE_CLIENT_SECRET": self.client_secret,
            }.items()
            if not value
        ]
        if missing:
            raise SalesforceError(f"Missing Salesforce configuration: {', '.join(missing)}")

    def obtain_token(self, force_refresh: bool = False) -> SalesforceToken:
        """Get a client_credentials token from Salesforce."""
        if self.dry_run:
            logger.warning("DRY_RUN_SALESFORCE=true; returning fake token.")
            return SalesforceToken(access_token="dry-run-token", token_type="Bearer", instance_url=None, raw={})

        if self._cached_token and not force_refresh:
            return self._cached_token

        self._validate_config()
        assert self.token_url and self.client_id and self.client_secret
        try:
            logger.info("Requesting Salesforce token url={}", self.token_url)
            response = requests.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            token = SalesforceToken(
                access_token=str(data["access_token"]),
                token_type=str(data.get("token_type", "Bearer")),
                instance_url=data.get("instance_url"),
                raw=data,
            )
            self._cached_token = token
            logger.info("Salesforce token obtained token_type={} scope={}", token.token_type, data.get("scope"))
            return token
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.exception("Failed to obtain Salesforce token.")
            raise SalesforceError(f"Failed to obtain Salesforce token: {exc}") from exc

    @staticmethod
    def build_case_payload(event: IncidentEvent) -> dict[str, Any]:
        """Build the legacy Salesforce car-case payload using incident values.

        Salesforce currently expects vehicle-related keys. Until the endpoint schema is updated,
        the incident information is mapped into the same keys and PlateNo stays empty as requested.
        """
        primary_class = ""
        if event.detection.pet_trigger_classes:
            primary_class = event.detection.pet_trigger_classes[0]
        elif event.detection.garbage_trigger_classes:
            primary_class = event.detection.garbage_trigger_classes[0]

        return {
            "SnapshotTime": event.snapshot_time.isoformat().replace("+00:00", "Z"),
            "ImageType": event.incident_type,
            "PlateNo": "",
            "VehicleColor": event.camera_name,
            "Type": primary_class or event.incident_type,
            "Speed": f"{event.detection.max_confidence:.3f}",
            "Logo": event.reasoning.risk_level,
            "DriverSeatbelt": event.reasoning.recommended_action,
            "imgList": [{"imgUrl": event.artifacts.image_url}],
        }

    @staticmethod
    def parse_case_response(raw_text: str) -> SalesforceCaseResult:
        """Parse Salesforce response text that may contain escaped JSON."""
        parsed: dict[str, Any] = {}
        status: str | None = None
        case_number: str | None = None
        success = False

        try:
            first = json.loads(raw_text)
            if isinstance(first, str):
                first = json.loads(first)
            if isinstance(first, dict):
                parsed = first
                status = str(first.get("status")) if first.get("status") is not None else None
                case_number = str(first.get("caseNumber")) if first.get("caseNumber") is not None else None
                success = status == "success"
        except json.JSONDecodeError:
            logger.warning("Salesforce case response was not JSON. raw_text={}", raw_text)

        return SalesforceCaseResult(
            success=success,
            case_number=case_number,
            status=status,
            raw_text=raw_text,
            parsed_response=parsed,
        )

    def create_case(self, event: IncidentEvent) -> SalesforceCaseResult:
        """Open one Salesforce case for an incident event."""
        payload = self.build_case_payload(event)

        if self.dry_run:
            logger.info("DRY_RUN Salesforce create case payload={}", json.dumps(payload, ensure_ascii=False))
            return SalesforceCaseResult(
                success=True,
                case_number="DRY-RUN",
                status="success",
                raw_text=json.dumps({"caseNumber": "DRY-RUN", "status": "success"}),
                parsed_response={"caseNumber": "DRY-RUN", "status": "success"},
            )

        self._validate_config()
        token = self.obtain_token()
        assert self.case_url
        try:
            logger.info("Creating Salesforce case incident_id={}", event.incident_id)
            response = requests.post(
                self.case_url,
                headers={
                    "Authorization": f"{token.token_type} {token.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            result = self.parse_case_response(response.text)
            logger.info(
                "Salesforce case response success={} status={} case_number={}",
                result.success,
                result.status,
                result.case_number,
            )
            return result
        except requests.RequestException as exc:
            logger.exception("Failed to create Salesforce case incident_id={}", event.incident_id)
            raise SalesforceError(f"Failed to create Salesforce case: {exc}") from exc
