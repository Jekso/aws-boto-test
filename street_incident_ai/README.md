# Street Incident AI Pipeline

A Python production-ready pipeline for street incident detection using camera streams or local media.

The system reads cameras from `cameras.yaml`, samples frames at a low rate such as 1 FPS, resizes frames to reduce CPU load, runs YOLOE object detection for pets and street garbage, validates the full frame with Amazon Bedrock Nova, annotates the frame, uploads evidence to S3, and sends confirmed incidents to Salesforce and AWS IoT Core MQTT.

## Current business rule

External notifications are sent only for confirmed actionable incidents:

| Detected scenario | Bedrock reasoning result | Save/log | Send to Salesforce | Publish to IoT Core |
|---|---|---:|---:|---:|
| Garbage/trash can appears unsafe or unhealthy | `status = unsafe` | yes | yes | yes |
| Garbage/trash can appears safe or healthy | `status = safe` | log only | no | no |
| Pet appears likely lost or unattended | `status = likely_lost` | yes | yes | yes |
| Pet appears supervised / not lost | `status = not_lost` | log only | no | no |
| Pet result is uncertain | `status = uncertain` | log only | no | no |
| YOLOE finds no target object | no Bedrock call | log only | no | no |

This protects Salesforce and IoT Core from receiving tickets/messages for every object detection.

## Important security note

Do not commit real credentials. Keep `.env` local only.

If a Salesforce `client_secret`, AWS key, RTSP username/password, or any other credential was shared in chat, email, or code, treat it as exposed and rotate it.

## Project structure

```text
street_incident_ai/
  .env
  .env.example
  cameras.yaml
  requirements.txt
  pyproject.toml
  main.py
  README.md
  data/
    input/
    output/
  logs/
  tmp/
  scripts/
    _bootstrap.py
    test_camera_stream.py
    test_detection.py
    test_reasoning.py
    test_s3_upload.py
    test_iot.py
    test_salesforce_token.py
    test_salesforce_case.py
    test_incident_artifacts.py
    test_full_pipeline_once.py
  src/street_incident_ai/
    __init__.py
    models.py
    config.py
    logging_config.py
    camera_source.py
    detector.py
    prompts.py
    bedrock_reasoner.py
    s3_storage.py
    iot_core.py
    salesforce_client.py
    incident_service.py
    cli.py
```

## What each module does

| File | Purpose |
|---|---|
| `main.py` | Main production runner. Reads `.env` and `cameras.yaml`, starts camera loops, and calls the incident service. |
| `models.py` | Typed dataclasses for camera config, detection results, reasoning results, S3 artifacts, Salesforce results, and incident events. |
| `config.py` | Loads `.env` and `cameras.yaml` into typed config objects. |
| `logging_config.py` | Configures loguru console/file logging. |
| `camera_source.py` | Reads frames from local image, local video, OpenCV RTSP, or VLC RTSP. Handles sampling and resizing. |
| `detector.py` | Loads YOLOE, detects pet/garbage target classes, and annotates frames with `supervision`. |
| `prompts.py` | Stores Bedrock prompts for waste and lost pet reasoning. |
| `bedrock_reasoner.py` | Sends full-frame images to Amazon Bedrock Nova and maps JSON responses into internal reasoning results. |
| `s3_storage.py` | Uploads annotated images and metadata JSON to S3 and returns the evidence URL. |
| `iot_core.py` | Publishes incident JSON to AWS IoT Core MQTT over WebSockets using IAM SigV4. |
| `salesforce_client.py` | Gets Salesforce OAuth token and creates Salesforce cases. |
| `incident_service.py` | Orchestrates detection, Bedrock validation, S3 evidence, cooldown, Salesforce, and IoT. |
| `cli.py` | Optional module CLI entrypoint when installing the project with `pip install -e .`. |

## Windows setup

Run from the project root:

```powershell
cd C:\Users\Administrator\Desktop\eslam\aws-boto-test\street_incident_ai
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `py -3.11` is not available, use:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional editable install:

```powershell
pip install -e .
```

After editable install, you can run:

```powershell
python -m street_incident_ai.cli --camera-id video_001 --max-frames 100
```

or, if the console script is available:

```powershell
street-incident-ai --camera-id video_001 --max-frames 100
```

Direct execution also works:

```powershell
python main.py --camera-id video_001 --max-frames 100
```

## VLC requirement for some RTSP streams

Some RTSP streams fail in OpenCV/FFmpeg but work in VLC because VLC handles authentication/options differently.

For those cameras:

1. Install VLC Desktop on Windows.
2. Keep `python-vlc` installed from `requirements.txt`.
3. Use `reader: vlc` in `cameras.yaml`.
4. Put RTSP username/password in the camera config.

Example:

```yaml
reader: vlc
username: your-rtsp-user
password: your-rtsp-password
```

## Environment configuration

Create your real `.env` from the example:

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum recommended `.env`:

```env
# AWS
AWS_REGION=eu-west-1
S3_BUCKET=your-s3-bucket-name
S3_PREFIX=street-incidents

# S3 URL mode
S3_URL_MODE=presigned
S3_PRESIGNED_EXPIRES_SECONDS=604800
S3_PUBLIC_BASE_URL=
CLOUDFRONT_BASE_URL=

# Bedrock Nova
BEDROCK_MODEL_ID=eu.amazon.nova-lite-v1:0
BEDROCK_MAX_TOKENS=800
BEDROCK_TEMPERATURE=0.1

# YOLOE
DETECTOR_MODEL_PATH=yoloe-26x-seg.pt
DETECTOR_CONFIDENCE=0.25

# AWS IoT Core
IOT_ENDPOINT=your-iot-endpoint-ats.iot.eu-west-1.amazonaws.com
IOT_CLIENT_ID=ec2-python-incidents
IOT_TOPIC=street/incidents/prod

# Salesforce
SALESFORCE_HOST=your-host-or-sandbox-host
SALESFORCE_CLIENT_ID=your-client-id
SALESFORCE_CLIENT_SECRET=your-client-secret
SALESFORCE_TOKEN_URL=
SALESFORCE_CASE_URL=

# Local folders/logging
OUTPUT_DIR=data/output
TMP_DIR=tmp
LOG_LEVEL=INFO

# Dry-run switches
DRY_RUN_BEDROCK=false
DRY_RUN_IOT=false
DRY_RUN_SALESFORCE=false
```

### Dry-run modes

Use dry run when you want to test the pipeline without external side effects.

```env
DRY_RUN_BEDROCK=true
DRY_RUN_IOT=true
DRY_RUN_SALESFORCE=true
```

For production:

```env
DRY_RUN_BEDROCK=false
DRY_RUN_IOT=false
DRY_RUN_SALESFORCE=false
```

## AWS permissions needed

When running on EC2, prefer an IAM role attached to the instance instead of hardcoded AWS keys.

The role/user needs permissions for:

```text
S3:
  s3:GetObject
  s3:PutObject
  s3:ListBucket

Bedrock:
  bedrock:InvokeModel
  bedrock:Converse

IoT Core:
  iot:Connect
  iot:Publish
  iot:Subscribe
  iot:Receive
```

## Bedrock model options

Recommended starting model:

```env
BEDROCK_MODEL_ID=eu.amazon.nova-lite-v1:0
```

Stronger model for better visual reasoning:

```env
BEDROCK_MODEL_ID=eu.amazon.nova-pro-v1:0
```

Use Nova Lite for cheaper/faster testing. Use Nova Pro if the false positive/false negative rate is too high.

## S3 evidence layout

Incident evidence is organized like this:

```text
S3_PREFIX/
  date=YYYY-MM-DD/
    incident_type=street_garbage|lost_pet/
      camera_id=<camera_id>/
        incident_id=<uuid>/
          annotated.jpg
          metadata.json
```

Example:

```text
street-incidents/date=2026-04-26/incident_type=street_garbage/camera_id=gate_01/incident_id=5a2.../annotated.jpg
street-incidents/date=2026-04-26/incident_type=street_garbage/camera_id=gate_01/incident_id=5a2.../metadata.json
```

Manual S3 test uploads use this style:

```text
street-incidents/manual-tests/<image-name>.jpg
street-incidents/manual-tests/<image-name>.json
```

## S3 URL modes

The URL sent to Salesforce is:

```json
"imgList": [
  {
    "imgUrl": "THE_ANNOTATED_IMAGE_URL"
  }
]
```

There are three URL modes.

### 1. Temporary private S3 URL

```env
S3_URL_MODE=presigned
S3_PRESIGNED_EXPIRES_SECONDS=604800
```

This generates a temporary S3 presigned URL. `604800` seconds equals 7 days.

A normal S3 presigned URL cannot be truly non-expiring.

### 2. Stable CloudFront URL

Recommended for production:

```env
S3_URL_MODE=cloudfront
CLOUDFRONT_BASE_URL=https://your-distribution.cloudfront.net
```

This produces:

```text
https://your-distribution.cloudfront.net/<object-key>
```

### 3. Public/custom base URL

Only use this if your S3 object or custom domain is intentionally public:

```env
S3_URL_MODE=public
S3_PUBLIC_BASE_URL=https://your-public-domain.example.com
```

## Camera configuration

Edit `cameras.yaml`.

### Local video example

```yaml
cameras:
  - camera_id: video_001
    name: Local Video Test Camera
    enabled: true
    source_type: video
    reader: opencv
    url: data/input/full.mp4
    location: Local Test
    sample_fps: 1.0
    resize_width: 650
    resize_height: 280
    cooldown_seconds_pet: 300
    cooldown_seconds_garbage: 900
    loop_video: false
    metadata:
      site: local_test
      area: test_video
```

### Local image example

```yaml
cameras:
  - camera_id: image_001
    name: Local Image Test Camera
    enabled: true
    source_type: image
    reader: opencv
    url: data/input/sample_image.jpg
    location: Local Image Test
    sample_fps: 1.0
    resize_width: 650
    resize_height: 280
    cooldown_seconds_pet: 300
    cooldown_seconds_garbage: 900
    loop_video: false
    metadata:
      site: local_test
      area: still_image
```

### RTSP camera with VLC example

```yaml
cameras:
  - camera_id: gate_01
    name: Gate 01 Camera
    enabled: true
    source_type: rtsp
    reader: vlc
    url: rtsp://10.10.15.10:554/live/your-stream-id
    username: your-rtsp-username
    password: your-rtsp-password
    location: Main Gate 01
    sample_fps: 1.0
    resize_width: 650
    resize_height: 280
    cooldown_seconds_pet: 300
    cooldown_seconds_garbage: 900
    loop_video: false
    metadata:
      site: Emaar
      area: Main Gate
      vendor: milestone
      purpose: pets_and_garbage_detection
```

### RTSP camera with OpenCV example

Use this only when OpenCV can open the stream successfully:

```yaml
cameras:
  - camera_id: gate_02
    name: Gate 02 Camera
    enabled: true
    source_type: rtsp
    reader: opencv
    url: rtsp://username:password@camera-ip:554/stream-path
    location: Main Gate 02
    sample_fps: 1.0
    resize_width: 650
    resize_height: 280
    cooldown_seconds_pet: 300
    cooldown_seconds_garbage: 900
    loop_video: false
    metadata:
      site: Emaar
      area: Main Gate
```

## Cooldown behavior

Cooldown prevents duplicate incidents from the same camera and incident type.

```yaml
cooldown_seconds_pet: 300       # 5 minutes
cooldown_seconds_garbage: 900   # 15 minutes
```

Example:

- `gate_01` detects unsafe garbage.
- The system sends one Salesforce ticket and one IoT message.
- More unsafe-garbage detections from `gate_01` are skipped until the garbage cooldown expires.
- Lost-pet cooldown is tracked separately from garbage cooldown.

## How the pipeline decides to send an incident

1. Camera source returns a sampled resized frame.
2. YOLOE detects classes from the configured pet and garbage class lists.
3. If YOLOE finds no target class, the frame is ignored.
4. If YOLOE finds target classes, Bedrock analyzes the full frame, not only the crop.
5. Bedrock returns JSON.
6. The project maps Bedrock status to actionable/non-actionable:
   - Waste `unsafe` means actionable.
   - Waste `safe` means no ticket/message.
   - Pet `likely_lost` means actionable.
   - Pet `not_lost` or `uncertain` means no ticket/message.
7. Actionable incidents are annotated, uploaded to S3, sent to Salesforce, published to IoT, and added to cooldown.
8. Non-actionable detections are logged only.

## Salesforce behavior

The Salesforce endpoint currently expects a car/traffic-style payload, so the project keeps the same keys and changes the values.

Endpoint:

```text
POST https://{SALESFORCE_HOST}.my.salesforce.com/services/apexrest/DahuaCreateCaseAPI
```

OAuth token endpoint:

```text
POST https://{SALESFORCE_HOST}.my.salesforce.com/services/oauth2/token
```

Payload mapping:

| Salesforce key | Value sent by this project |
|---|---|
| `SnapshotTime` | Current UTC detection time. |
| `ImageType` | `street_garbage` or `lost_pet`. |
| `PlateNo` | Empty string. |
| `VehicleColor` | Camera name or useful camera context. |
| `Type` | Detected class or incident type. |
| `Speed` | Detection confidence as string. |
| `Logo` | Camera/location context when available. |
| `DriverSeatbelt` | Empty string or not-applicable value. |
| `imgList[0].imgUrl` | Annotated image URL from S3/CloudFront. |

The API may return text containing JSON, for example:

```text
{"caseNumber":"02187950","status":"success"}
```

The Salesforce client parses this response and logs/stores `caseNumber` and `status`.

## IoT Core behavior

The IoT publisher sends the complete incident JSON to:

```env
IOT_TOPIC=street/incidents/prod
```

Only confirmed actionable incidents are published:

```text
street_garbage + unsafe
lost_pet + likely_lost
```

Safe, not-lost, uncertain, or rejected detections are logged only.

## Run modes

### Test one camera/video/image source only

This checks reading, frame sampling, resizing, and saving output frames. It does not call YOLOE, Bedrock, S3, Salesforce, or IoT.

```powershell
python scripts/test_camera_stream.py --camera-id video_001 --frames 5
```

With a custom camera YAML:

```powershell
python scripts/test_camera_stream.py --cameras cameras.yaml --camera-id gate_01 --frames 10
```

With a custom env file:

```powershell
python scripts/test_camera_stream.py --env .env.dev --camera-id gate_01 --frames 5
```

Expected output:

```text
data/output/camera_test/<camera_id>/frame_001.jpg
data/output/camera_test/<camera_id>/frame_002.jpg
...
```

### Test YOLOE detection and annotation

This checks YOLOE model loading, target class detection, supervision annotation, and local image output. It does not call Bedrock, S3, Salesforce, or IoT.

```powershell
python scripts/test_detection.py --image data/input/sample_image.jpg
```

Custom output path:

```powershell
python scripts/test_detection.py --image data/input/garbage.jpg --output data/output/garbage_annotated.jpg
```

Custom env file:

```powershell
python scripts/test_detection.py --env .env.dev --image data/input/pet.jpg --output data/output/pet_annotated.jpg
```

Expected output:

```text
JSON detection result printed in terminal
Annotated image saved to data/output/test_detection_annotated.jpg
```

### Test Bedrock reasoning only

This checks the prompt and Bedrock/Nova JSON response mapping. It does not run YOLOE, upload to S3, open Salesforce cases, or publish IoT messages.

Waste/garbage prompt:

```powershell
python scripts/test_reasoning.py --image data/input/garbage.jpg --incident-type street_garbage
```

Pet prompt:

```powershell
python scripts/test_reasoning.py --image data/input/pet.jpg --incident-type lost_pet
```

Generic/unknown prompt:

```powershell
python scripts/test_reasoning.py --image data/input/scene.jpg --incident-type unknown
```

Dry-run Bedrock:

```env
DRY_RUN_BEDROCK=true
```

Then run:

```powershell
python scripts/test_reasoning.py --image data/input/garbage.jpg --incident-type street_garbage
```

Expected output fields:

```json
{
  "is_incident": true,
  "incident_type": "street_garbage",
  "confidence_score": 0.9,
  "description": "...",
  "raw_response": {
    "status": "unsafe"
  }
}
```

### Test S3 image and metadata upload

This checks S3 upload and evidence URL generation. It does not call Bedrock, Salesforce, or IoT.

```powershell
python scripts/test_s3_upload.py --image data/input/sample_image.jpg
```

Custom S3 key prefix:

```powershell
python scripts/test_s3_upload.py --image data/input/garbage.jpg --key-prefix manual-tests/garbage
```

Custom env file:

```powershell
python scripts/test_s3_upload.py --env .env.dev --image data/input/test.jpg --key-prefix manual-tests/dev
```

Expected output:

```json
{
  "image_s3_uri": "s3://bucket/street-incidents/manual-tests/...jpg",
  "image_url": "https://...",
  "metadata_s3_uri": "s3://bucket/street-incidents/manual-tests/...json"
}
```

### Test AWS IoT Core MQTT

This checks MQTT subscribe/publish over AWS IoT Core WebSockets. It does not call YOLOE, Bedrock, S3, or Salesforce.

```powershell
python scripts/test_iot.py
```

Custom topic:

```powershell
python scripts/test_iot.py --topic street/incidents/test
```

Custom wait time:

```powershell
python scripts/test_iot.py --topic street/incidents/test --wait 10
```

Dry-run IoT:

```env
DRY_RUN_IOT=true
```

Then run:

```powershell
python scripts/test_iot.py --topic street/incidents/test
```

Expected output:

```text
Connected to IoT Core
Subscribed to topic
Published test JSON payload
Received message back if subscription is allowed
```

### Test Salesforce token only

This checks Salesforce OAuth client credentials token retrieval. It does not create a case.

```powershell
python scripts/test_salesforce_token.py
```

Custom env file:

```powershell
python scripts/test_salesforce_token.py --env .env.dev
```

Dry-run Salesforce:

```env
DRY_RUN_SALESFORCE=true
```

Then run:

```powershell
python scripts/test_salesforce_token.py
```

Expected output:

```json
{
  "access_token": "eyJ0bmsiOi...",
  "token_type": "Bearer",
  "instance_url": "https://..."
}
```

The script masks the token before printing.

### Test Salesforce case creation

This checks both Salesforce token retrieval and case creation using a prepared image URL.

Use a real S3/CloudFront/presigned image URL:

```powershell
python scripts/test_salesforce_case.py --image-url "https://example.com/test.jpg" --incident-type street_garbage
```

Lost pet case:

```powershell
python scripts/test_salesforce_case.py --image-url "https://example.com/pet.jpg" --incident-type lost_pet
```

Custom env file:

```powershell
python scripts/test_salesforce_case.py --env .env.dev --image-url "https://example.com/test.jpg" --incident-type street_garbage
```

Dry-run Salesforce:

```env
DRY_RUN_SALESFORCE=true
```

Then run:

```powershell
python scripts/test_salesforce_case.py --image-url "https://example.com/test.jpg" --incident-type street_garbage
```

Expected output:

```json
{
  "payload": {
    "SnapshotTime": "...",
    "ImageType": "street_garbage",
    "PlateNo": "",
    "imgList": [
      {
        "imgUrl": "https://example.com/test.jpg"
      }
    ]
  },
  "result": {
    "success": true,
    "case_number": "02187950",
    "status": "success"
  }
}
```

### Test detection annotation plus S3 artifact upload

This checks YOLOE detection, local annotation, S3 image upload, S3 metadata upload, and organized S3 object keys. It does not call Bedrock, Salesforce, or IoT.

```powershell
python scripts/test_incident_artifacts.py --image data/input/garbage.jpg
```

Custom env file:

```powershell
python scripts/test_incident_artifacts.py --env .env.dev --image data/input/pet.jpg
```

Expected S3 layout:

```text
street-incidents/date=YYYY-MM-DD/incident_type=<type>/camera_id=artifact_test/incident_id=<uuid>/annotated.jpg
street-incidents/date=YYYY-MM-DD/incident_type=<type>/camera_id=artifact_test/incident_id=<uuid>/metadata.json
```

Expected terminal output:

```json
{
  "incident_id": "...",
  "detection": {...},
  "image_s3_uri": "s3://.../annotated.jpg",
  "image_url": "https://...",
  "metadata_s3_uri": "s3://.../metadata.json"
}
```

### Test full pipeline once

This reads one sampled frame from a configured camera and runs the integrated flow:

```text
camera -> YOLOE -> Bedrock -> annotation -> S3 -> optional Salesforce/IoT if actionable
```

Run one frame from a configured camera:

```powershell
python scripts/test_full_pipeline_once.py --camera-id video_001
```

For RTSP:

```powershell
python scripts/test_full_pipeline_once.py --camera-id gate_01
```

Custom env and camera config:

```powershell
python scripts/test_full_pipeline_once.py --env .env.dev --cameras cameras.dev.yaml --camera-id gate_01
```

Expected behavior:

- If no YOLOE target is detected, the script prints `created_incident: false`.
- If Bedrock says garbage is `safe`, the script logs it and does not send Salesforce/IoT.
- If Bedrock says pet is `not_lost` or `uncertain`, the script logs it and does not send Salesforce/IoT.
- If Bedrock says garbage is `unsafe`, the script saves evidence, creates Salesforce case, publishes IoT, and prints the event JSON.
- If Bedrock says pet is `likely_lost`, the script saves evidence, creates Salesforce case, publishes IoT, and prints the event JSON.

## Run the full pipeline

### Limited integration run

Use this for integration testing:

```powershell
python main.py --camera-id video_001 --max-frames 100
```

This stops after 100 sampled frames.

### Continuous production run for one camera

Use this for production:

```powershell
python main.py --camera-id gate_01
```

Do not pass `--max-frames` in production.

### Continuous run for all enabled cameras

```powershell
python main.py
```

Important: the current `main.py` processes cameras sequentially. For live RTSP cameras, the first camera loop can run forever, so the next camera may not start.

For production with multiple live cameras, run one process per camera:

```powershell
python main.py --camera-id gate_01
python main.py --camera-id gate_02
python main.py --camera-id gate_03
```

Use separate terminals, Windows Task Scheduler, NSSM, or Windows services to keep each process running.

## Recommended production validation sequence

Run these in order before enabling production alerts:

```powershell
python scripts/test_camera_stream.py --camera-id gate_01 --frames 5
python scripts/test_detection.py --image data/output/camera_test/gate_01/frame_001.jpg --output data/output/gate_01_detection.jpg
python scripts/test_reasoning.py --image data/output/camera_test/gate_01/frame_001.jpg --incident-type street_garbage
python scripts/test_s3_upload.py --image data/output/gate_01_detection.jpg --key-prefix manual-tests/gate_01
python scripts/test_iot.py --topic street/incidents/test --wait 5
python scripts/test_salesforce_token.py
python scripts/test_salesforce_case.py --image-url "PASTE_IMAGE_URL_FROM_S3_TEST" --incident-type street_garbage
python scripts/test_full_pipeline_once.py --camera-id gate_01
```

Then run continuously:

```powershell
python main.py --camera-id gate_01
```

## Common command examples

### Local video, limited run

```powershell
python main.py --camera-id video_001 --max-frames 100
```

### Local video, continuous loop

Set in `cameras.yaml`:

```yaml
loop_video: true
```

Then run:

```powershell
python main.py --camera-id video_001
```

### Real RTSP camera, production

```powershell
python main.py --camera-id gate_01
```

### Use custom config files

```powershell
python main.py --env .env.prod --cameras cameras.prod.yaml --camera-id gate_01
```

### Run everything in dry-run mode

Set:

```env
DRY_RUN_BEDROCK=true
DRY_RUN_IOT=true
DRY_RUN_SALESFORCE=true
```

Then:

```powershell
python main.py --camera-id video_001 --max-frames 100
```

### Run real Bedrock but no Salesforce or IoT

Set:

```env
DRY_RUN_BEDROCK=false
DRY_RUN_IOT=true
DRY_RUN_SALESFORCE=true
```

Then:

```powershell
python main.py --camera-id video_001 --max-frames 100
```

### Run real S3 + Salesforce + IoT but limited frames

Set:

```env
DRY_RUN_BEDROCK=false
DRY_RUN_IOT=false
DRY_RUN_SALESFORCE=false
```

Then:

```powershell
python main.py --camera-id gate_01 --max-frames 100
```

## Output locations

Local outputs:

```text
data/output/
logs/
tmp/
```

S3 outputs:

```text
s3://<bucket>/<S3_PREFIX>/date=YYYY-MM-DD/incident_type=<type>/camera_id=<camera_id>/incident_id=<uuid>/annotated.jpg
s3://<bucket>/<S3_PREFIX>/date=YYYY-MM-DD/incident_type=<type>/camera_id=<camera_id>/incident_id=<uuid>/metadata.json
```

## Logs

Logs are written to console and log files under `logs/`.

To increase detail:

```env
LOG_LEVEL=DEBUG
```

Then rerun your command.

## Troubleshooting

### `ModuleNotFoundError: No module named 'street_incident_ai'`

Use the updated `main.py`, which adds `src/` automatically, or install the package:

```powershell
pip install -e .
```

Then run:

```powershell
python main.py --camera-id video_001 --max-frames 100
```

or:

```powershell
python -m street_incident_ai.cli --camera-id video_001 --max-frames 100
```

### `AppConfig object has no attribute __dict__`

Use the fixed `config.py` that imports `asdict`:

```python
from dataclasses import asdict, dataclass
```

and logs config using:

```python
safe_config = {k: v for k, v in asdict(config).items() if "secret" not in k.lower()}
```

### RTSP works in VLC but not OpenCV

Use VLC reader:

```yaml
reader: vlc
username: your-user
password: your-password
```

Then test:

```powershell
python scripts/test_camera_stream.py --camera-id gate_01 --frames 5
```

### YOLOE model file not found

Check:

```env
DETECTOR_MODEL_PATH=yoloe-26x-seg.pt
```

Either place the model file in the project root or provide a full path:

```env
DETECTOR_MODEL_PATH=C:\models\yoloe-26x-seg.pt
```

### Bedrock access denied

Check:

- AWS region in `.env`.
- Bedrock model access is enabled.
- EC2 IAM role/user has `bedrock:InvokeModel` and `bedrock:Converse`.
- The model ID is available in the selected region.

### S3 presigned URL expires

This is expected for `S3_URL_MODE=presigned`.

For stable production image URLs, use:

```env
S3_URL_MODE=cloudfront
CLOUDFRONT_BASE_URL=https://your-distribution.cloudfront.net
```

### Salesforce receives no ticket for safe garbage or supervised pet

This is expected.

The current business rule sends Salesforce/IoT only when:

```text
street_garbage + unsafe
lost_pet + likely_lost
```

Safe, not-lost, uncertain, or rejected detections are logged only.

### Salesforce response is text, not JSON

The client supports text responses like:

```text
{"caseNumber":"02187950","status":"success"}
```

It parses and logs the case number/status.

### IoT test connects but does not receive its own message

Check that the IAM role/policy allows:

```text
iot:Subscribe
iot:Receive
iot:Publish
iot:Connect
```

Also verify the topic in the AWS IoT Core MQTT test client.

## Production checklist

Before running production:

- [ ] Real `.env` exists and is not committed.
- [ ] `DRY_RUN_BEDROCK=false`.
- [ ] `DRY_RUN_IOT=false`.
- [ ] `DRY_RUN_SALESFORCE=false`.
- [ ] `S3_BUCKET` is correct.
- [ ] `S3_URL_MODE` is chosen correctly.
- [ ] For stable Salesforce image URLs, CloudFront is configured.
- [ ] `IOT_ENDPOINT` is correct.
- [ ] `IOT_TOPIC` is production topic.
- [ ] Salesforce token and case tests pass.
- [ ] RTSP camera test saves frames successfully.
- [ ] Detection test finds expected classes.
- [ ] Bedrock reasoning returns valid JSON.
- [ ] Cooldown values are correct.
- [ ] Only intended cameras are `enabled: true` in `cameras.yaml`.
- [ ] Each production RTSP camera is started in its own process/service if multiple live cameras are used.

## Quick command reference

```powershell
# Activate environment
.\.venv\Scripts\activate

# Camera read test
python scripts/test_camera_stream.py --camera-id gate_01 --frames 5

# YOLOE detection test
python scripts/test_detection.py --image data/input/sample_image.jpg --output data/output/annotated.jpg

# Bedrock reasoning tests
python scripts/test_reasoning.py --image data/input/garbage.jpg --incident-type street_garbage
python scripts/test_reasoning.py --image data/input/pet.jpg --incident-type lost_pet

# S3 upload test
python scripts/test_s3_upload.py --image data/input/sample_image.jpg --key-prefix manual-tests

# IoT test
python scripts/test_iot.py --topic street/incidents/test --wait 5

# Salesforce tests
python scripts/test_salesforce_token.py
python scripts/test_salesforce_case.py --image-url "https://example.com/test.jpg" --incident-type street_garbage

# Artifact test
python scripts/test_incident_artifacts.py --image data/input/sample_image.jpg

# Full pipeline, one frame
python scripts/test_full_pipeline_once.py --camera-id gate_01

# Full pipeline, limited frames
python main.py --camera-id gate_01 --max-frames 100

# Full pipeline, production continuous
python main.py --camera-id gate_01
```
