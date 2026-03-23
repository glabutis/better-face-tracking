"""
Canon CR-N series HTTP CGI API wrapper.

Command reference (AW-compatible PTZ protocol):
  Pan/Tilt velocity:  #PTS<pan><tilt>   (decimal 01-99, 50 = stop)
  Zoom velocity:      #ZS<speed>        (decimal 01-99, 50 = stop)
  Stop all:           #PTS5050
  Recall preset:      #R<nn>            (00-99)
  Query power:        #O
"""

import logging
import threading

import requests
from requests.auth import HTTPDigestAuth

logger = logging.getLogger(__name__)


class CanonCamera:
    def __init__(self, ip: str, port: int = 80, user: str = "admin", password: str = "admin"):
        self.base_url = f"http://{ip}:{port}/cgi-bin/aw_ptz"
        self._auth = HTTPDigestAuth(user, password)
        self._lock = threading.Lock()
        self.timeout = 1.0

    def _send(self, cmd: str) -> str | None:
        """Send a raw PTZ command string (without leading #). Thread-safe."""
        url = f"{self.base_url}?cmd=%23{cmd}&res=1"
        try:
            with self._lock:
                resp = requests.get(url, auth=self._auth, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text.strip()
        except requests.RequestException as exc:
            logger.debug("Camera command failed (%s): %s", cmd, exc)
            return None

    # ------------------------------------------------------------------ #
    # Movement                                                             #
    # ------------------------------------------------------------------ #

    def pan_tilt(self, pan_speed: int, tilt_speed: int):
        """
        Set continuous pan/tilt velocity.
        pan_speed, tilt_speed: 1-99  (50 = stop, <50 = left/down, >50 = right/up)
        """
        pan_speed = max(1, min(99, pan_speed))
        tilt_speed = max(1, min(99, tilt_speed))
        self._send(f"PTS{pan_speed:02d}{tilt_speed:02d}")

    def stop(self):
        """Stop all pan/tilt movement."""
        self._send("PTS5050")

    def zoom(self, speed: int):
        """Set continuous zoom velocity. 1-99 (50 = stop, <50 = wide, >50 = tele)."""
        speed = max(1, min(99, speed))
        self._send(f"ZS{speed:02d}")

    def zoom_stop(self):
        self._send("ZS50")

    def recall_preset(self, preset: int):
        """Recall a camera preset (0-99)."""
        preset = max(0, min(99, preset))
        self._send(f"R{preset:02d}")

    # ------------------------------------------------------------------ #
    # Utilities                                                            #
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        """Return True if the camera responds to a power-state query."""
        return self._send("O") is not None

    @staticmethod
    def error_to_speed(pid_output: float, max_speed: int = 40) -> int:
        """
        Map a PID output value to a camera speed integer.
        pid_output: typically in [-1, 1]  (positive = right/up)
        Returns: integer in [1, 99] with 50 = stop
        """
        return max(1, min(99, int(50 + pid_output * max_speed)))
