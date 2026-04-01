"""
VideoWidget — displays the live video frame with face-detection overlays.

  • All detected faces get a thin white bounding box.
  • The locked/tracked face gets a bright green box + corner ticks + crosshair.
  • A status pill (IDLE / TRACKING / LOST) is drawn in the top-right corner.
  • Mouse clicks are translated to normalized [0,1] coordinates and emitted
    via face_clicked so the caller can perform click-to-lock.
"""

from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..face_detector import FaceDetection


class VideoWidget(QWidget):
    face_clicked = pyqtSignal(float, float)  # normalized (x, y) within frame

    _STATUS_COLORS = {
        "TRACKING": "#00ff88",
        "LOST":     "#ff4444",
        "IDLE":     "#aaaaaa",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background: #111;")
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._qt_image: Optional[QImage] = None
        self._detections: list[FaceDetection] = []
        self._locked: Optional[FaceDetection] = None
        self._status = "IDLE"
        self._display_rect = QRect()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update_frame(
        self,
        frame: np.ndarray,
        detections: list[FaceDetection],
        locked: Optional[FaceDetection],
        status: str,
    ):
        self._detections = detections
        self._locked = locked
        self._status = status

        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            self._qt_image = QImage(bytes(rgb.data), w, h, ch * w,
                                    QImage.Format.Format_RGB888)
        self.update()

    # ------------------------------------------------------------------ #
    # Paint                                                                #
    # ------------------------------------------------------------------ #

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        if self._qt_image is None:
            painter.fillRect(0, 0, W, H, QColor("#111"))
            painter.setPen(QColor("#444"))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(0, 0, W, H, Qt.AlignmentFlag.AlignCenter,
                             "No video\n\nEnter an RTSP URL and click Connect Stream")
            painter.end()
            return

        # ---- Scale frame to fill widget (letterboxed) ------------------
        iw = self._qt_image.width()
        ih = self._qt_image.height()
        scale = min(W / iw, H / ih)
        dw = int(iw * scale)
        dh = int(ih * scale)
        ox = (W - dw) // 2
        oy = (H - dh) // 2
        self._display_rect = QRect(ox, oy, dw, dh)

        painter.fillRect(0, 0, W, H, QColor("#111"))
        painter.drawImage(self._display_rect, self._qt_image)

        # ---- Face boxes ------------------------------------------------
        has_unlocked_faces = False
        for face in self._detections:
            is_locked = (
                self._locked is not None
                and abs(face.cx - self._locked.cx) < 0.005
                and abs(face.cy - self._locked.cy) < 0.005
            )
            fx = ox + int(face.x * dw)
            fy = oy + int(face.y * dh)
            fw = int(face.w * dw)
            fh = int(face.h * dh)

            if is_locked:
                self._draw_locked_box(painter, fx, fy, fw, fh)
            else:
                has_unlocked_faces = True
                painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
                painter.drawRect(fx, fy, fw, fh)

        # ---- "Click to lock" hint when faces detected but none locked --
        if has_unlocked_faces and self._locked is None:
            self._draw_click_hint(painter, W, H)

        # ---- Status pill -----------------------------------------------
        self._draw_status_pill(painter, W)
        painter.end()

    def _draw_locked_box(self, painter: QPainter, x: int, y: int, w: int, h: int):
        color = QColor("#00ff88")
        thick = QPen(color, 2)
        painter.setPen(thick)
        painter.drawRect(x, y, w, h)

        # Corner ticks
        tick = max(8, min(20, w // 6))
        lines = [
            (x, y, x + tick, y), (x, y, x, y + tick),
            (x + w, y, x + w - tick, y), (x + w, y, x + w, y + tick),
            (x, y + h, x + tick, y + h), (x, y + h, x, y + h - tick),
            (x + w, y + h, x + w - tick, y + h), (x + w, y + h, x + w, y + h - tick),
        ]
        painter.setPen(QPen(color, 3))
        for x1, y1, x2, y2 in lines:
            painter.drawLine(x1, y1, x2, y2)

        # Crosshair at face center
        cx = x + w // 2
        cy = y + h // 2
        cs = max(6, min(14, w // 8))
        painter.setPen(QPen(color, 2))
        painter.drawLine(cx - cs, cy, cx + cs, cy)
        painter.drawLine(cx, cy - cs, cx, cy + cs)

    def _draw_click_hint(self, painter: QPainter, W: int, H: int):
        text = "Click a face to lock"
        font = QFont("Arial", 11)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        pad_x, pad_y = 10, 5
        rx = (W - tw - pad_x * 2) // 2
        ry = H - th - pad_y * 2 - 16
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(rx, ry, tw + pad_x * 2, th + pad_y * 2, 6, 6)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rx + pad_x, ry + pad_y + fm.ascent(), text)

    def _draw_status_pill(self, painter: QPainter, widget_width: int):
        color_hex = self._STATUS_COLORS.get(self._status, "#aaaaaa")
        label = f"● {self._status}"

        font = QFont("Courier", 11, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(label)
        th = fm.height()

        pad_x, pad_y = 10, 6
        pill_w = tw + pad_x * 2
        pill_h = th + pad_y * 2
        pill_x = widget_width - pill_w - 12
        pill_y = 12

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, 8, 8)

        painter.setPen(QColor(color_hex))
        painter.drawText(pill_x + pad_x, pill_y + pad_y + fm.ascent(), label)

    # ------------------------------------------------------------------ #
    # Mouse                                                                #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._display_rect.isEmpty():
            return
        rx = event.position().x() - self._display_rect.x()
        ry = event.position().y() - self._display_rect.y()
        nx = rx / self._display_rect.width()
        ny = ry / self._display_rect.height()
        if 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0:
            self.face_clicked.emit(nx, ny)
