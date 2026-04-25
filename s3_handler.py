"""
S3 handling class for reading and writing objects from an EC2-hosted Python app.

Authentication:
- On EC2, do NOT hardcode access keys.
- Attach an IAM role / instance profile to the EC2 instance.
- Boto3 will automatically use the EC2 role credentials.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class S3Handler:
    """Helper class for common Amazon S3 operations."""

    def __init__(self, bucket_name: str, region_name: Optional[str] = None) -> None:
        """
        Args:
            bucket_name: Target S3 bucket name.
            region_name: AWS region, for example "eu-west-1".
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client(
            "s3",
            region_name=region_name,
            config=Config(signature_version="s3v4"),
        )

    def upload_file(
        self,
        local_path: str | Path,
        object_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload any local file to S3 and return its S3 URI."""
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        detected_content_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        extra_args: Dict[str, Any] = {"ContentType": detected_content_type}
        if metadata:
            extra_args["Metadata"] = metadata

        try:
            self.s3_client.upload_file(
                Filename=str(path),
                Bucket=self.bucket_name,
                Key=object_key,
                ExtraArgs=extra_args,
            )
            return f"s3://{self.bucket_name}/{object_key}"
        except ClientError as exc:
            raise RuntimeError(f"Failed to upload file to S3: {exc}") from exc

    def upload_json(self, data: Dict[str, Any] | List[Any], object_key: str) -> str:
        """Serialize a dict/list to JSON and upload it to S3."""
        try:
            body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=body,
                ContentType="application/json; charset=utf-8",
            )
            return f"s3://{self.bucket_name}/{object_key}"
        except ClientError as exc:
            raise RuntimeError(f"Failed to upload JSON to S3: {exc}") from exc

    def upload_image(self, local_image_path: str | Path, object_key: str) -> str:
        """Upload an image file to S3. Content type is inferred from extension."""
        path = Path(local_image_path)
        content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        if not content_type.startswith("image/"):
            raise ValueError(f"File does not look like an image by MIME type: {content_type}")
        return self.upload_file(path, object_key, content_type=content_type)

    def read_object_bytes(self, object_key: str) -> bytes:
        """Read an S3 object as bytes."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_key)
            return response["Body"].read()
        except ClientError as exc:
            raise RuntimeError(f"Failed to read S3 object bytes: {exc}") from exc

    def read_text(self, object_key: str, encoding: str = "utf-8") -> str:
        """Read an S3 object as text."""
        return self.read_object_bytes(object_key).decode(encoding)

    def read_json(self, object_key: str) -> Any:
        """Read an S3 JSON object and deserialize it."""
        return json.loads(self.read_text(object_key))

    def download_file(self, object_key: str, local_path: str | Path) -> Path:
        """Download an S3 object to a local file path."""
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.s3_client.download_file(self.bucket_name, object_key, str(destination))
            return destination
        except ClientError as exc:
            raise RuntimeError(f"Failed to download S3 object: {exc}") from exc

    def list_objects(self, prefix: str = "", max_keys: int = 50) -> List[str]:
        """List object keys under a prefix."""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys,
            )
            return [item["Key"] for item in response.get("Contents", [])]
        except ClientError as exc:
            raise RuntimeError(f"Failed to list S3 objects: {exc}") from exc

    def generate_presigned_get_url(self, object_key: str, expires_in: int = 3600) -> str:
        """Generate a temporary URL to download/view a private S3 object."""
        try:
            return self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expires_in,
            )
        except ClientError as exc:
            raise RuntimeError(f"Failed to generate presigned URL: {exc}") from exc
