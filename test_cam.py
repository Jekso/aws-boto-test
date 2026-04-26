import os
import time
from pathlib import Path

# Important on Windows: point Python to VLC installation folder
import vlc


RTSP_URL = "rtsp://10.10.15.10:554/live/9BC989DB-A305-455D-8622-247226C60D06"
USERNAME = "test"
PASSWORD = "Admin_123"

OUTPUT_DIR = Path("frames")
OUTPUT_DIR.mkdir(exist_ok=True)


instance = vlc.Instance(
    "--rtsp-tcp",
    "--network-caching=500",
    "--no-audio"
)

media = instance.media_new(RTSP_URL)

# This is the important part: pass auth like VLC, not only inside the URL
media.add_option(f":rtsp-user={USERNAME}")
media.add_option(f":rtsp-pwd={PASSWORD}")

player = instance.media_player_new()
player.set_media(media)

print("Starting stream...")
player.play()

# Give VLC time to connect and decode first frames
time.sleep(5)

for i in range(10):
    output_path = OUTPUT_DIR / f"camera_frame_{i:03d}.jpg"

    # Width/height here are the saved snapshot size.
    # VLC still receives the original stream, but saves the image smaller.
    result = player.video_take_snapshot(
        0,
        str(output_path),
        640,
        360
    )

    if result == 0:
        print(f"Saved: {output_path}")
    else:
        print("Snapshot failed. Stream may not be ready yet.")

    time.sleep(2)

player.stop()