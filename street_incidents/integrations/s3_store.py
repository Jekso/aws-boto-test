"""S3 artifact storage helpers."""

from __future__ import annotations

import json
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from street_incidents.exceptions import StorageError
from street_incidents.models import IncidentEvidence, IncidentRecord, S3Config


class S3EvidenceStore:
    """Upload evidence artifacts to S3 and generate evidence URLs."""

    def __init__(self, config: S3Config, region_name: str) -> None:
        """Initialize the S3 store.

        Args:
            config: S3 storage configuration.
            region_name: AWS region.
        """
        self._config = config
        self._client: BaseClient = boto3.client("s3", region_name=region_name)

    def upload_artifacts(self, incident: IncidentRecord, local_image_path: Path) -> IncidentEvidence:
        """Upload image and JSON metadata to S3.

        Args:
            incident: Incident record.
            local_image_path: Local JPEG file path.

        Returns:
            Evidence metadata after upload.

        Raises:
            StorageError: If any upload step fails.
        """
        date_path = incident.timestamp_utc.strftime("%Y/%m/%d")
        image_key = (
            f"incidents/{incident.incident_type.value}/{incident.camera.camera_id}/"
            f"{date_path}/{incident.incident_id}.jpg"
        )
        json_key = (
            f"incidents/json/{incident.incident_type.value}/{incident.camera.camera_id}/"
            f"{date_path}/{incident.incident_id}.json"
        )
        try:
            self._client.upload_file(
                Filename=str(local_image_path),
                Bucket=self._config.bucket_name,
                Key=image_key,
                ExtraArgs={"ContentType": "image/jpeg"},
            )
            self._client.put_object(
                Bucket=self._config.bucket_name,
                Key=json_key,
                Body=json.dumps(incident.model_dump(mode="json"), default=str).encode("utf-8"),
                ContentType="application/json",
            )
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket_name, "Key": image_key},
                ExpiresIn=self._config.url_expiry_seconds,
            )
            return IncidentEvidence(
                local_image_path=str(local_image_path),
                s3_key_image=image_key,
                s3_key_json=json_key,
                evidence_url=url,
            )
        except (BotoCoreError, ClientError, OSError) as exc:  # pragma: no cover - runtime integration
            raise StorageError(f"Failed to upload artifacts to S3: {exc}") from exc
