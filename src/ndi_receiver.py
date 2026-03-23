"""
NDI stream receiver.

Runs in a QThread. Discovers NDI sources on the LAN, connects to the
requested source, and emits BGR numpy frames via frame_ready().

Requires:
  1. NDI SDK installed on the system (https://ndi.video/download-ndi-sdk/)
  2. ndi-python pip package: pip install ndi-python
"""

import logging
import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

try:
    import ndi as _ndi
    NDI_AVAILABLE = True
except ImportError:
    NDI_AVAILABLE = False


class NDIReceiver(QThread):
    frame_ready = pyqtSignal(object)        # numpy ndarray (BGR, uint8)
    sources_updated = pyqtSignal(list)      # list[str] of discovered source names
    error_occurred = pyqtSignal(str)        # human-readable error message

    def __init__(self, source_name: str = ""):
        super().__init__()
        self.source_name = source_name
        self._running = False

    def set_source(self, source_name: str):
        self.source_name = source_name

    # ------------------------------------------------------------------ #
    # One-shot source discovery (called from main thread before run())    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def discover_sources(wait_seconds: float = 2.0) -> list[str]:
        """Block briefly and return a list of visible NDI source names."""
        if not NDI_AVAILABLE:
            return []
        if not _ndi.initialize():
            return []
        finder = _ndi.find_create_v2()
        if not finder:
            _ndi.destroy()
            return []
        time.sleep(wait_seconds)
        sources = _ndi.find_get_current_sources(finder)
        names = [s.ndi_name for s in sources]
        _ndi.find_destroy(finder)
        _ndi.destroy()
        return names

    # ------------------------------------------------------------------ #
    # Thread body                                                          #
    # ------------------------------------------------------------------ #

    def run(self):
        if not NDI_AVAILABLE:
            self.error_occurred.emit(
                "ndi-python is not installed.\n"
                "1. Install the NDI SDK: https://ndi.video/download-ndi-sdk/\n"
                "2. Run: pip install ndi-python"
            )
            return

        if not _ndi.initialize():
            self.error_occurred.emit(
                "NDI initialization failed. Is the NDI Runtime/SDK installed?"
            )
            return

        self._running = True

        # ---- Discover the target source --------------------------------
        finder = _ndi.find_create_v2()
        if not finder:
            self.error_occurred.emit("Failed to create NDI finder.")
            _ndi.destroy()
            return

        source = None
        deadline = time.monotonic() + 8.0
        while self._running and time.monotonic() < deadline:
            sources = _ndi.find_get_current_sources(finder)
            self.sources_updated.emit([s.ndi_name for s in sources])

            if self.source_name:
                for s in sources:
                    if self.source_name.lower() in s.ndi_name.lower():
                        source = s
                        break
            elif sources:
                source = sources[0]

            if source:
                break
            time.sleep(0.5)

        _ndi.find_destroy(finder)

        if not source:
            msg = (
                f"NDI source not found: '{self.source_name}'. "
                "Check that the camera is on the same network and NDI output is enabled."
            )
            self.error_occurred.emit(msg)
            _ndi.destroy()
            return

        # ---- Create receiver -------------------------------------------
        recv_desc = _ndi.RecvCreateV3()
        recv_desc.color_format = _ndi.RECV_COLOR_FORMAT_BGRX_BGRA
        recv_desc.bandwidth = _ndi.RECV_BANDWIDTH_HIGHEST
        recv_desc.allow_video_fields = False

        receiver = _ndi.recv_create_v3(recv_desc)
        if not receiver:
            self.error_occurred.emit("Failed to create NDI receiver.")
            _ndi.destroy()
            return

        _ndi.recv_connect(receiver, source)
        logger.info("NDI connected to: %s", source.ndi_name)

        # ---- Receive loop ----------------------------------------------
        while self._running:
            frame_type, video, _audio, _meta = _ndi.recv_capture_v2(receiver, 100)

            if frame_type == _ndi.FRAME_TYPE_VIDEO:
                # video.data is (H, W, 4) uint8 in BGRX order
                raw: np.ndarray = video.data
                frame = raw[:, :, :3].copy()  # drop X channel → BGR
                self.frame_ready.emit(frame)
                _ndi.recv_free_video_v2(receiver, video)

        # ---- Cleanup ---------------------------------------------------
        _ndi.recv_destroy(receiver)
        _ndi.destroy()
        logger.info("NDI receiver stopped.")

    def stop(self):
        self._running = False
        self.wait(3000)
