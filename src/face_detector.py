"""
MediaPipe-based face detector running in its own QThread.

Frames are pushed via push_frame() from the main thread (non-blocking —
if the queue is full the frame is dropped to stay real-time).
Detection results are emitted via detections_ready().
"""

import logging
import queue
from dataclasses import dataclass

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False


@dataclass
class FaceDetection:
    """A single detected face, coordinates normalized to [0, 1]."""
    x: float   # left edge
    y: float   # top edge
    w: float   # width
    h: float   # height
    confidence: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def to_pixels(self, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) in pixel coordinates."""
        return (
            int(self.x * frame_w),
            int(self.y * frame_h),
            int(self.w * frame_w),
            int(self.h * frame_h),
        )


class FaceDetector(QThread):
    # Emits the source frame alongside detections so the UI can pair them
    detections_ready = pyqtSignal(object, list)  # (np.ndarray, list[FaceDetection])

    def __init__(self, confidence: float = 0.6, model_selection: int = 1):
        """
        model_selection:
          0 = short-range model (faces within ~2 m, faster)
          1 = full-range model  (faces within ~5 m, recommended for PTZ)
        """
        super().__init__()
        self.confidence = confidence
        self.model_selection = model_selection
        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)
        self._running = False

    def push_frame(self, frame: np.ndarray):
        """Non-blocking: drop frames when the detector can't keep up."""
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            pass

    def run(self):
        if not MEDIAPIPE_AVAILABLE:
            logger.error("mediapipe not installed. Run: pip install mediapipe")
            return

        mp_face = mp.solutions.face_detection
        self._running = True

        with mp_face.FaceDetection(
            model_selection=self.model_selection,
            min_detection_confidence=self.confidence,
        ) as detector:
            while self._running:
                try:
                    frame = self._frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = detector.process(rgb)

                faces: list[FaceDetection] = []
                if results.detections:
                    for det in results.detections:
                        bb = det.location_data.relative_bounding_box
                        x = max(0.0, bb.xmin)
                        y = max(0.0, bb.ymin)
                        w = min(1.0 - x, bb.width)
                        h = min(1.0 - y, bb.height)
                        faces.append(FaceDetection(
                            x=x, y=y, w=w, h=h,
                            confidence=det.score[0],
                        ))

                self.detections_ready.emit(frame, faces)

    def stop(self):
        self._running = False
        self.wait(3000)

    def update_confidence(self, confidence: float):
        """Update detection confidence threshold (takes effect on next restart)."""
        self.confidence = confidence
