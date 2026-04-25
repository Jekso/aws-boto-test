import os
import time
import cv2

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"

rtsp_url = "rtsp://test:Admin_123@10.10.15.10:554/live/CAMERA_GUID/1"

cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    raise RuntimeError("Could not open RTSP stream")

frame_interval_seconds = 3
last_processed = 0.0

while True:
    ret, frame = cap.read()

    if not ret:
        print("Frame read failed")
        time.sleep(1)
        continue

    now = time.time()

    if now - last_processed < frame_interval_seconds:
        continue

    last_processed = now

    frame = cv2.resize(frame, (640, 360))

    # Send this frame to your AI model
    print("Processing frame:", frame.shape)