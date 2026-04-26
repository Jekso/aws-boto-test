from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger


class S3StorageError(RuntimeError):
    """Raised when S3 upload/read/presign fails."""


class S3Storage:
    """S3 helper for incident images, JSON metadata, and URLs."""

    MAX_PRESIGNED_SECONDS = 604800  # 7 days for SigV4 generated with IAM user credentials.

    def __init__(
        self,
        bucket_name: str,
        region_name: str,
        url_mode: str = "presigned",
        presigned_expires_seconds: int = 604800,
        public_base_url: str | None = None,
        cloudfront_base_url: str | None = None,
    ) -> None:
        if not bucket_name:
            raise ValueError("S3 bucket name is required.")
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.url_mode = url_mode.lower().strip()
        self.presigned_expires_seconds = min(presigned_expires_seconds, self.MAX_PRESIGNED_SECONDS)
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.cloudfront_base_url = cloudfront_base_url.rstrip("/") if cloudfront_base_url else None
        self.client = boto3.client("s3", region_name=region_name, config=Config(signature_version="s3v4"))
        logger.info("Initialized S3Storage bucket={} url_mode={}", bucket_name, self.url_mode)

    def upload_file(
        self,
        local_path: str | Path,
        object_key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        detected_content_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        extra_args: dict[str, Any] = {"ContentType": detected_content_type}
        if metadata:
            extra_args["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

        try:
            self.client.upload_file(str(path), self.bucket_name, object_key, ExtraArgs=extra_args)
            s3_uri = f"s3://{self.bucket_name}/{object_key}"
            logger.info("Uploaded file to S3 local={} s3_uri={}", path, s3_uri)
            return s3_uri
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to upload file to S3 local={} key={}", path, object_key)
            raise S3StorageError(f"Failed to upload file to S3: {exc}") from exc

    def upload_json(self, data: dict[str, Any] | list[Any], object_key: str) -> str:
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
            s3_uri = f"s3://{self.bucket_name}/{object_key}"
            logger.info("Uploaded JSON to S3 s3_uri={}", s3_uri)
            return s3_uri
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to upload JSON to S3 key={}", object_key)
            raise S3StorageError(f"Failed to upload JSON to S3: {exc}") from exc

    def read_json(self, object_key: str) -> Any:
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=object_key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except (ClientError, BotoCoreError, json.JSONDecodeError) as exc:
            logger.exception("Failed to read JSON from S3 key={}", object_key)
            raise S3StorageError(f"Failed to read JSON from S3: {exc}") from exc

    def generate_presigned_get_url(self, object_key: str, expires_in: int | None = None) -> str:
        seconds = min(expires_in or self.presigned_expires_seconds, self.MAX_PRESIGNED_SECONDS)
        if seconds < (expires_in or seconds):
            logger.warning("Requested S3 presigned URL expiration exceeds max; capped to {} seconds.", seconds)
        try:
            url = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=seconds,
            )
            logger.debug("Generated presigned URL key={} expires_in={}", object_key, seconds)
            return url
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to generate presigned URL key={}", object_key)
            raise S3StorageError(f"Failed to generate presigned URL: {exc}") from exc

    def public_url_for_key(self, object_key: str) -> str:
        encoded_key = quote(object_key)
        if self.url_mode == "cloudfront":
            if not self.cloudfront_base_url:
                raise S3StorageError("S3_URL_MODE=cloudfront requires CLOUDFRONT_BASE_URL.")
            return f"{self.cloudfront_base_url}/{encoded_key}"
        if self.url_mode == "public":
            if self.public_base_url:
                return f"{self.public_base_url}/{encoded_key}"
            return f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{encoded_key}"
        return self.generate_presigned_get_url(object_key)

    def upload_incident_image(self, local_image_path: str | Path, object_key: str, metadata: dict[str, str]) -> tuple[str, str]:
        s3_uri = self.upload_file(local_image_path, object_key, content_type="image/jpeg", metadata=metadata)
        url = self.public_url_for_key(object_key)
        return s3_uri, url
