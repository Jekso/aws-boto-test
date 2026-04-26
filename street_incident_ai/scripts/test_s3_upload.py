from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from street_incident_ai.config import load_app_config
from street_incident_ai.logging_config import setup_logging
from street_incident_ai.s3_storage import S3Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Test S3 image and JSON upload.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--image", required=True)
    parser.add_argument("--key-prefix", default="manual-tests")
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    s3 = S3Storage(
        bucket_name=config.s3_bucket,
        region_name=config.aws_region,
        url_mode=config.s3_url_mode,
        presigned_expires_seconds=config.s3_presigned_expires_seconds,
        public_base_url=config.s3_public_base_url,
        cloudfront_base_url=config.cloudfront_base_url,
    )
    image_path = Path(args.image)
    image_key = f"{config.s3_prefix}/{args.key_prefix}/{image_path.name}"
    metadata_key = f"{config.s3_prefix}/{args.key_prefix}/{image_path.stem}.json"
    image_s3_uri, image_url = s3.upload_incident_image(image_path, image_key, metadata={"test": "true"})
    metadata = {"image_s3_uri": image_s3_uri, "image_url": image_url, "local_image": str(image_path)}
    metadata_s3_uri = s3.upload_json(metadata, metadata_key)
    print(json.dumps({"image_s3_uri": image_s3_uri, "image_url": image_url, "metadata_s3_uri": metadata_s3_uri}, indent=2))


if __name__ == "__main__":
    main()
