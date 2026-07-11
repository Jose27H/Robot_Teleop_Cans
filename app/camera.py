"""
MJPEG stream reader.

Connects to an MJPEG-over-HTTP stream (e.g. ROS web_video_server), extracts
JPEG frames from the byte stream, and delivers each one as a full-resolution
PIL Image to a callback. Knows nothing about tkinter, robots, or config —
give it a URL and a function, and it runs on its own daemon thread.

Note: the callback fires on the camera thread. GUI consumers must marshal
back to their main thread themselves (e.g. tkinter's root.after).
"""

import io
import threading
import time
import urllib.request

from PIL import Image

JPEG_START = b"\xff\xd8"
JPEG_END   = b"\xff\xd9"


class MjpegCamera:
    def __init__(self, url, on_frame, reconnect_delay=2.0):
        self.url = url
        self.on_frame = on_frame
        self.reconnect_delay = reconnect_delay
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _read_loop(self):
        while self._running:
            try:
                stream = urllib.request.urlopen(self.url, timeout=8)
                buf = b""
                while self._running:
                    chunk = stream.read(8192)
                    if not chunk:
                        break          # server closed the stream; reconnect
                    buf += chunk
                    buf = self._extract_frames(buf)
            except Exception as e:
                if self._running:
                    print(f"[camera] stream error: {e}")
                    time.sleep(self.reconnect_delay)

    def _extract_frames(self, buf):
        """Emit every complete JPEG in buf; return the leftover bytes."""
        while True:
            start = buf.find(JPEG_START)
            if start == -1:
                return b""
            end = buf.find(JPEG_END, start + 2)
            if end == -1:
                return buf[start:]     # incomplete frame; keep for next chunk
            jpg = buf[start:end + 2]
            buf = buf[end + 2:]
            try:
                self.on_frame(Image.open(io.BytesIO(jpg)))
            except Exception as e:
                print(f"[camera] bad frame: {e}")
