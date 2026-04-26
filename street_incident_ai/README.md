# Street Incident AI Pipeline

This project integrates your working draft files into one clean Python project.
It reads camera/video/image configuration from `cameras.yaml`, samples frames at 1 FPS, resizes frames to a low CPU-friendly size, runs YOLOE detection for pets and street garbage, validates incidents with Amazon Bedrock Nova, annotates the full frame with `supervision`, uploads image + metadata to S3, publishes the incident to AWS IoT Core MQTT, opens a Salesforce case, and applies cooldown so the system does not open a ticket for every detection.

## Important security note

Do not commit real `.env` values. The Salesforce `client_secret` that was shared in the request should be rotated if it is a real credential. This project keeps all credentials in `.env` placeholders only.

## Project structure

```text
street_incident_ai/
  .env
  .env.example
  cameras.yaml
  requirements.txt
  pyproject.toml
  main.py
  src/street_incident_ai/
    models.py
    config.py
    logging_config.py
    camera_source.py
    detector.py
    bedrock_reasoner.py
    s3_storage.py
    iot_core.py
    salesforce_client.py
    incident_service.py
  scripts/
    test_camera_stream.py
    test_detection.py
    test_reasoning.py
    test_s3_upload.py
    test_iot.py
    test_salesforce_token.py
    test_salesforce_case.py
    test_incident_artifacts.py
    test_full_pipeline_once.py
  data/input/
  data/output/
  logs/
  tmp/
```

## Setup on Windows

```powershell
cd street_incident_ai
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For RTSP streams that only work in VLC, install VLC Desktop first, then keep `reader: vlc` in `cameras.yaml`.

## Required AWS/Salesforce preparation

1. Configure AWS credentials on the machine or attach an EC2 IAM role with access to:
   - `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`
   - `bedrock:InvokeModel`, `bedrock:Converse`
   - `iot:Connect`, `iot:Publish`, `iot:Subscribe`, `iot:Receive`
2. Enable the Nova model/inference profile in Amazon Bedrock for your region.
3. Create or choose an S3 bucket.
4. Create an IoT Core thing/policy or allow IAM SigV4 WebSocket access from the EC2 role/user.
5. Fill Salesforce host, client ID, and client secret in `.env`.

## URL mode for images

The user requirement says “presigned url no expired”. A normal S3 presigned URL is temporary. For a stable URL, use one of these:

```env
S3_URL_MODE=cloudfront
CLOUDFRONT_BASE_URL=https://your-distribution.cloudfront.net
```

or a public bucket/base URL:

```env
S3_URL_MODE=public
S3_PUBLIC_BASE_URL=https://your-domain-or-bucket-url
```

For private temporary URLs, keep:

```env
S3_URL_MODE=presigned
S3_PRESIGNED_EXPIRES_SECONDS=604800
```

## Configure cameras

For local video testing:

```yaml
- camera_id: local_video_001
  enabled: true
  source_type: video
  reader: opencv
  url: data/input/sample_video.mp4
```

For RTSP testing with VLC authentication:

```yaml
- camera_id: rtsp_camera_001
  enabled: true
  source_type: rtsp
  reader: vlc
  url: rtsp://camera-ip-or-server/path
  username: your-rtsp-username
  password: your-rtsp-password
```

## Solo tests

Run from the project root.

### 1) Test camera/RTSP/video sampling

```powershell
python scripts/test_camera_stream.py --camera-id local_video_001 --frames 5
```

For RTSP, enable the RTSP camera in `cameras.yaml`, then:

```powershell
python scripts/test_camera_stream.py --camera-id rtsp_camera_001 --frames 5
```

### 2) Test YOLOE detection + annotation

```powershell
python scripts/test_detection.py --image data/input/sample_image.jpg --output data/output/test_detection_annotated.jpg
```

### 3) Test Bedrock Nova reasoning only

```powershell
python scripts/test_reasoning.py --image data/input/sample_image.jpg --incident-type street_garbage
```

Use dry run without calling Bedrock:

```env
DRY_RUN_BEDROCK=true
```

### 4) Test S3 image + JSON upload

```powershell
python scripts/test_s3_upload.py --image data/input/sample_image.jpg
```

### 5) Test AWS IoT Core MQTT

```powershell
python scripts/test_iot.py
```

Use dry run without sending IoT message:

```env
DRY_RUN_IOT=true
```

### 6) Test Salesforce token

```powershell
python scripts/test_salesforce_token.py
```

### 7) Test Salesforce case creation

```powershell
python scripts/test_salesforce_case.py --image-url "https://example.com/test.jpg" --incident-type street_garbage
```

Use dry run without opening a real case:

```env
DRY_RUN_SALESFORCE=true
```

### 8) Test detection annotation + S3 incident artifact upload

```powershell
python scripts/test_incident_artifacts.py --image data/input/sample_image.jpg
```

### 9) Test the full pipeline once

```powershell
python scripts/test_full_pipeline_once.py --camera-id local_image_001
```

## Run the full pipeline

```powershell
python main.py --camera-id local_video_001 --max-frames 100
```

For continuous run, omit `--max-frames`:

```powershell
python main.py --camera-id rtsp_camera_001
```

## Salesforce payload mapping

The current Salesforce API still expects vehicle-related keys. The project keeps the same keys and maps incident values like this:

- `SnapshotTime`: current UTC detection time
- `ImageType`: `lost_pet` or `street_garbage`
- `PlateNo`: empty string
- `VehicleColor`: camera name
- `Type`: detected class, such as `dog`, `cat`, or `garbage`
- `Speed`: YOLOE confidence as string
- `Logo`: Bedrock risk level
- `DriverSeatbelt`: Bedrock recommended action
- `imgList`: annotated image URL

The response parser supports the returned text form:

```json
"{\"caseNumber\":\"02187950\",\"status\":\"success\"}"
```

## Cooldown behavior

Cooldown is tracked in memory by `(camera_id, incident_type)`.
Defaults:

- pets: 5 minutes
- garbage: 15 minutes

Adjust per camera in `cameras.yaml`.

## Type checking and linting

```powershell
mypy src scripts
ruff check src scripts
```
