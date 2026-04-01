"""
RTSP stream receiver.

Runs in a QThread. Connects to an RTSP URL and emits BGR numpy frames
via frame_ready(). Automatically reconnects on stream loss.

Requires: opencv-python-headless (already in requirements.txt)
"""

import logging
import time

import cv2
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class RTSPReceiver(QThread):
    frame_ready = pyqtSignal(object)   # numpy ndarray (BGR, uint8)
    error_occurred = pyqtSignal(str)   # human-readable error message

    def __init__(self, url: str = ""):
        super().__init__()
        self.url = url
        self._running = False

    def set_url(self, url: str):
        self.url = url

    def run(self):
        if not self.url:
            self.error_occurred.emit("No RTSP URL configured.")
            return

        self._running = True
        retry_delay = 2.0

        while self._running:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                self.error_occurred.emit(
                    f"Could not open RTSP stream: {self.url}\n"
                    "Check the URL, camera power, and network connection."
                )
                cap.release()
                for _ in range(int(retry_delay * 10)):
                    if not self._running:
                        return
                    time.sleep(0.1)
                continue

            logger.info("RTSP connected: %s", self.url)
            consecutive_failures = 0

            while self._running:
                ok, frame = cap.read()
                if not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        logger.warning("RTSP stream lost, reconnecting…")
                        break
                    time.sleep(0.05)
                    continue

                consecutive_failures = 0
                self.frame_ready.emit(frame)

            cap.release()

            if self._running:
                logger.info("Attempting RTSP reconnect in %.1f s…", retry_delay)
                for _ in range(int(retry_delay * 10)):
                    if not self._running:
                        return
                    time.sleep(0.1)

        logger.info("RTSP receiver stopped.")

    def stop(self):
        self._running = False
        self.wait(3000)
