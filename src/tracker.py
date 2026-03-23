"""
Face lock and tracking logic.

The FaceTracker maintains a 'locked' face target across frames using
IoU-based matching. It exposes the current pan/tilt error relative to
the frame center so the PID controller can drive the camera.
"""

from typing import Optional

from .face_detector import FaceDetection


def _iou(face: FaceDetection, cx: float, cy: float, w: float, h: float) -> float:
    """Intersection-over-union between a FaceDetection and an (cx,cy,w,h) box."""
    ax1, ay1 = face.x, face.y
    ax2, ay2 = face.x + face.w, face.y + face.h
    bx1 = cx - w / 2
    by1 = cy - h / 2
    bx2 = cx + w / 2
    by2 = cy + h / 2

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    intersection = (ix2 - ix1) * (iy2 - iy1)
    union = face.w * face.h + w * h - intersection
    return intersection / union if union > 0 else 0.0


class FaceTracker:
    """
    Manages which face the camera should follow.

    States
    ------
    IDLE      — no lock has ever been set (or was explicitly cleared)
    TRACKING  — locked face is being matched each frame
    LOST      — locked face could not be matched for `lost_threshold` frames
    """

    def __init__(self, lost_threshold: int = 30, min_iou: float = 0.25):
        self.lost_threshold = lost_threshold
        self.min_iou = min_iou

        self.locked: Optional[FaceDetection] = None
        self.is_tracking: bool = False
        self._frames_lost: int = 0
        self._ever_locked: bool = False  # distinguishes IDLE from LOST

    # ------------------------------------------------------------------ #
    # Lock management                                                      #
    # ------------------------------------------------------------------ #

    def lock(self, face: FaceDetection):
        self.locked = face
        self._frames_lost = 0
        self.is_tracking = True
        self._ever_locked = True

    def unlock(self):
        self.locked = None
        self._frames_lost = 0
        self.is_tracking = False
        self._ever_locked = False

    def click_to_lock(self, nx: float, ny: float, detections: list[FaceDetection]) -> bool:
        """
        Try to lock onto the face whose bounding box contains the normalized
        click point (nx, ny). Returns True if a face was locked.
        """
        for face in detections:
            if face.x <= nx <= face.x + face.w and face.y <= ny <= face.y + face.h:
                self.lock(face)
                return True
        return False

    # ------------------------------------------------------------------ #
    # Per-frame update                                                     #
    # ------------------------------------------------------------------ #

    def update(self, detections: list[FaceDetection]) -> Optional[FaceDetection]:
        """
        Match the locked face against new detections.
        Returns the matched FaceDetection (or None if no match / not tracking).
        Call this once per control cycle.
        """
        if not self.is_tracking or self.locked is None:
            return None

        if detections:
            best = max(
                detections,
                key=lambda f: _iou(f, self.locked.cx, self.locked.cy,
                                   self.locked.w, self.locked.h),
            )
            score = _iou(best, self.locked.cx, self.locked.cy,
                         self.locked.w, self.locked.h)
            if score >= self.min_iou:
                self.locked = best
                self._frames_lost = 0
                return best

        # No suitable match
        self._frames_lost += 1
        if self._frames_lost >= self.lost_threshold:
            self.is_tracking = False
        return None

    # ------------------------------------------------------------------ #
    # Error for PID                                                        #
    # ------------------------------------------------------------------ #

    def get_error(self) -> tuple[float, float]:
        """
        Return (pan_error, tilt_error) normalized to [-1, 1].
          +pan_error  → face is right of center → camera should pan right
          +tilt_error → face is above center   → camera should tilt up
        """
        if self.locked is None:
            return 0.0, 0.0
        pan_error = self.locked.cx - 0.5      # positive = right of center
        tilt_error = 0.5 - self.locked.cy     # positive = above center (y↓)
        return pan_error, tilt_error

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    @property
    def status(self) -> str:
        if not self._ever_locked:
            return "IDLE"
        return "TRACKING" if self.is_tracking else "LOST"

    @property
    def frames_lost(self) -> int:
        return self._frames_lost
