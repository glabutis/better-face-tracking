"""Main application window.

Layout
------
  ┌─────────────────────────────────────────────────────────┐
  │  [Camera IP ______] [Connect Camera]  [RTSP URL ______] [Connect Stream]  [⚙ Settings] │  ← toolbar
  ├─────────────────────────────────────────────────────────┤
  │                                                         │
  │                   VIDEO FEED                            │
  │         (click a face to lock / track)                  │
  │                                                         │
  ├─────────────────────────────────────────────────────────┤
  │  [🔒 Lock Selected]  [Unlock]   ←hint text→   cam: ●   │  ← control bar
  └─────────────────────────────────────────────────────────┘
"""

import json
import logging
import os

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QPalette
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..canon_api import CanonCamera
from ..face_detector import FaceDetection, FaceDetector
from ..rtsp_receiver import RTSPReceiver
from ..pid import PID
from ..tracker import FaceTracker
from .settings_dialog import SettingsDialog
from .video_widget import VideoWidget

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(__file__)
CONFIG_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "config.json"))

DEFAULT_CONFIG: dict = {
    "camera_ip":            "192.168.1.100",
    "camera_user":          "admin",
    "camera_pass":          "admin",
    "camera_port":          80,
    "rtsp_url":             "",
    "pid_pan":              {"kp": 0.4, "ki": 0.0, "kd": 0.05},
    "pid_tilt":             {"kp": 0.4, "ki": 0.0, "kd": 0.05},
    "deadzone":             0.03,
    "max_speed":            30,
    "detection_confidence": 0.6,
    "frame_skip":           2,
}

_TOOLBAR_STYLE = "background:#1e1e1e; border-bottom:1px solid #3a3a3a;"
_BAR_STYLE     = "background:#1e1e1e; border-top:1px solid #3a3a3a;"
_LABEL_STYLE   = "color:#888; font-size:11px;"
_INPUT_STYLE   = (
    "QLineEdit, QComboBox {"
    "  background:#2c2c2c; color:#eee; border:1px solid #444;"
    "  border-radius:4px; padding:3px 6px; font-size:12px;"
    "}"
    "QLineEdit:focus, QComboBox:focus { border-color:#5599ff; }"
)
_BTN_STYLE = (
    "QPushButton {"
    "  background:#2c2c2c; color:#ddd; border:1px solid #444;"
    "  border-radius:4px; padding:4px 12px; font-size:12px;"
    "}"
    "QPushButton:hover  { background:#383838; border-color:#666; }"
    "QPushButton:pressed { background:#222; }"
    "QPushButton:disabled { color:#555; border-color:#333; }"
)
_BTN_PRIMARY_STYLE = (
    "QPushButton {"
    "  background:#1a5ccc; color:#fff; border:1px solid #2266dd;"
    "  border-radius:4px; padding:4px 14px; font-size:12px; font-weight:600;"
    "}"
    "QPushButton:hover   { background:#2266dd; }"
    "QPushButton:pressed { background:#1144aa; }"
    "QPushButton:disabled { background:#2a2a2a; color:#555; border-color:#333; }"
)
_BTN_DANGER_STYLE = (
    "QPushButton {"
    "  background:#2c2c2c; color:#ff6666; border:1px solid #553333;"
    "  border-radius:4px; padding:4px 14px; font-size:12px;"
    "}"
    "QPushButton:hover   { background:#3a2222; }"
    "QPushButton:pressed { background:#221111; }"
    "QPushButton:disabled { color:#555; border-color:#333; }"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Better Face Tracking — Canon PTZ")
        self.resize(1100, 700)
        self._apply_dark_palette()

        self.config = self._load_config()

        self._latest_detections: list[FaceDetection] = []
        self._frame_counter: int = 0

        self._setup_components()
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    # Dark palette                                                         #
    # ------------------------------------------------------------------ #

    def _apply_dark_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,          QColor("#1a1a1a"))
        palette.setColor(QPalette.ColorRole.WindowText,      QColor("#dddddd"))
        palette.setColor(QPalette.ColorRole.Base,            QColor("#2c2c2c"))
        palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#242424"))
        palette.setColor(QPalette.ColorRole.Text,            QColor("#eeeeee"))
        palette.setColor(QPalette.ColorRole.Button,          QColor("#2c2c2c"))
        palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#dddddd"))
        palette.setColor(QPalette.ColorRole.Highlight,       QColor("#1a5ccc"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)

    # ------------------------------------------------------------------ #
    # Config                                                               #
    # ------------------------------------------------------------------ #

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(DEFAULT_CONFIG)

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
        except OSError as exc:
            logger.warning("Could not save config: %s", exc)

    # ------------------------------------------------------------------ #
    # Component setup                                                      #
    # ------------------------------------------------------------------ #

    def _setup_components(self):
        cfg = self.config
        self.camera = CanonCamera(
            ip=cfg["camera_ip"],
            port=cfg.get("camera_port", 80),
            user=cfg["camera_user"],
            password=cfg["camera_pass"],
        )
        self.pid_pan  = PID(**cfg["pid_pan"])
        self.pid_tilt = PID(**cfg["pid_tilt"])
        self.tracker  = FaceTracker()

        self.rtsp_receiver = RTSPReceiver(cfg.get("rtsp_url", ""))
        self.face_detector = FaceDetector(confidence=cfg.get("detection_confidence", 0.6))

        self.control_timer = QTimer()
        self.control_timer.setInterval(67)   # ~15 Hz
        self.control_timer.timeout.connect(self._send_camera_command)

        # Ping timer — checks camera reachability every 5 s
        self._cam_online = False
        self.ping_timer = QTimer()
        self.ping_timer.setInterval(5000)
        self.ping_timer.timeout.connect(self._ping_camera)

    # ------------------------------------------------------------------ #
    # UI setup                                                             #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        # Video feed
        self.video_widget = VideoWidget()
        self.video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self.video_widget)

        root.addWidget(self._build_control_bar())

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("background:#1a1a1a; color:#888; font-size:11px;")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready — connect a camera and RTSP stream to begin")

        self._build_menu()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(_TOOLBAR_STYLE)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # ---- Camera section ------------------------------------------- #
        layout.addWidget(_label("Camera IP", _LABEL_STYLE))

        self.ip_edit = QLineEdit(self.config.get("camera_ip", ""))
        self.ip_edit.setFixedWidth(140)
        self.ip_edit.setPlaceholderText("192.168.x.x")
        self.ip_edit.setStyleSheet(_INPUT_STYLE)
        self.ip_edit.returnPressed.connect(self._on_connect_camera)
        layout.addWidget(self.ip_edit)

        self.btn_connect_cam = QPushButton("Connect Camera")
        self.btn_connect_cam.setStyleSheet(_BTN_STYLE)
        self.btn_connect_cam.clicked.connect(self._on_connect_camera)
        layout.addWidget(self.btn_connect_cam)

        self.lbl_cam_status = QLabel("●")
        self.lbl_cam_status.setStyleSheet("color:#555; font-size:14px;")
        self.lbl_cam_status.setToolTip("Camera connection status")
        layout.addWidget(self.lbl_cam_status)

        layout.addSpacing(16)
        _separator(layout)
        layout.addSpacing(16)

        # ---- RTSP section --------------------------------------------- #
        layout.addWidget(_label("RTSP URL", _LABEL_STYLE))

        self.rtsp_edit = QLineEdit(self.config.get("rtsp_url", ""))
        self.rtsp_edit.setMinimumWidth(260)
        self.rtsp_edit.setPlaceholderText("rtsp://user:pass@192.168.x.x/stream1")
        self.rtsp_edit.setStyleSheet(_INPUT_STYLE)
        self.rtsp_edit.returnPressed.connect(self._on_connect_stream)
        layout.addWidget(self.rtsp_edit)

        self.btn_connect_stream = QPushButton("Connect Stream")
        self.btn_connect_stream.setStyleSheet(_BTN_STYLE)
        self.btn_connect_stream.clicked.connect(self._on_connect_stream)
        layout.addWidget(self.btn_connect_stream)

        layout.addStretch()

        self.btn_settings = QPushButton("⚙  Settings")
        self.btn_settings.setStyleSheet(_BTN_STYLE)
        self.btn_settings.clicked.connect(self._on_settings)
        layout.addWidget(self.btn_settings)

        return bar

    def _build_control_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(_BAR_STYLE)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.btn_unlock = QPushButton("Unlock")
        self.btn_unlock.setStyleSheet(_BTN_DANGER_STYLE)
        self.btn_unlock.setToolTip("Release face lock and stop camera movement  [Esc]")
        self.btn_unlock.setEnabled(False)
        self.btn_unlock.clicked.connect(self._on_unlock)
        layout.addWidget(self.btn_unlock)

        layout.addStretch()

        self.lbl_hint = QLabel("Click on a face in the video to lock and track it")
        self.lbl_hint.setStyleSheet("color:#666; font-size:12px;")
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_hint)

        layout.addStretch()

        return bar

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        settings_action = QAction("Settings…", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_settings)

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------ #
    # Signal wiring                                                        #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self.rtsp_receiver.frame_ready.connect(self._on_frame)
        self.rtsp_receiver.error_occurred.connect(self._on_stream_error)
        self.face_detector.detections_ready.connect(self._on_detections)
        self.video_widget.face_clicked.connect(self._on_face_clicked)

    # ------------------------------------------------------------------ #
    # Toolbar actions                                                      #
    # ------------------------------------------------------------------ #

    def _on_connect_camera(self):
        ip = self.ip_edit.text().strip()
        if not ip:
            self.status_bar.showMessage("Enter a camera IP address first")
            return
        self.config["camera_ip"] = ip
        self._save_config()
        self.camera = CanonCamera(
            ip=ip,
            port=self.config.get("camera_port", 80),
            user=self.config["camera_user"],
            password=self.config["camera_pass"],
        )
        self.lbl_cam_status.setStyleSheet("color:#888; font-size:14px;")
        self.lbl_cam_status.setToolTip("Checking…")
        self.status_bar.showMessage(f"Connecting to camera at {ip}…")
        self._ping_camera()
        self.ping_timer.start()

    def _ping_camera(self):
        # Run in background so it doesn't block the UI
        QTimer.singleShot(0, self._do_ping)

    def _do_ping(self):
        online = self.camera.ping()
        self._cam_online = online
        if online:
            self.lbl_cam_status.setStyleSheet("color:#00cc66; font-size:14px;")
            self.lbl_cam_status.setToolTip(f"Camera online: {self.config['camera_ip']}")
            self.status_bar.showMessage(f"Camera connected: {self.config['camera_ip']}")
        else:
            self.lbl_cam_status.setStyleSheet("color:#cc3333; font-size:14px;")
            self.lbl_cam_status.setToolTip(f"Camera unreachable: {self.config['camera_ip']}")

    def _on_connect_stream(self):
        url = self.rtsp_edit.text().strip()
        self.config["rtsp_url"] = url
        self._save_config()
        self._restart_pipeline()

    # ------------------------------------------------------------------ #
    # Pipeline                                                             #
    # ------------------------------------------------------------------ #

    def _restart_pipeline(self):
        if self.rtsp_receiver.isRunning():
            self.rtsp_receiver.stop()
        if self.face_detector.isRunning():
            self.face_detector.stop()

        self.rtsp_receiver.set_url(self.config.get("rtsp_url", ""))
        self.rtsp_receiver.start()
        self.face_detector.start()
        self.control_timer.start()

        url = self.config.get("rtsp_url", "") or "(no URL set)"
        self.status_bar.showMessage(f"Connecting to RTSP stream: {url}…")

    # ------------------------------------------------------------------ #
    # Frame / detection slots                                              #
    # ------------------------------------------------------------------ #

    def _on_frame(self, frame: np.ndarray):
        self._frame_counter += 1
        if self._frame_counter % self.config.get("frame_skip", 2) == 0:
            self.face_detector.push_frame(frame)
        self.video_widget.update_frame(
            frame,
            self._latest_detections,
            self.tracker.locked,
            self.tracker.status,
        )

    def _on_detections(self, _frame: np.ndarray, detections: list[FaceDetection]):
        self._latest_detections = detections

    def _on_stream_error(self, msg: str):
        self.status_bar.showMessage(f"Stream error: {msg}")

    # ------------------------------------------------------------------ #
    # Lock / unlock                                                        #
    # ------------------------------------------------------------------ #

    def _on_face_clicked(self, nx: float, ny: float):
        if self.tracker.click_to_lock(nx, ny, self._latest_detections):
            self.btn_unlock.setEnabled(True)
            self.lbl_hint.setText("Tracking active — click another face to switch, or Unlock to stop")
            self.pid_pan.reset()
            self.pid_tilt.reset()
            self.status_bar.showMessage("Locked onto face")
        else:
            self.status_bar.showMessage("No face at that position — click directly on a detected face box")

    def _on_unlock(self):
        self.tracker.unlock()
        self.camera.stop()
        self.btn_unlock.setEnabled(False)
        self.lbl_hint.setText("Click on a face in the video to lock and track it")
        self.status_bar.showMessage("Tracking stopped")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.tracker.is_tracking:
            self._on_unlock()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Camera control loop                                                  #
    # ------------------------------------------------------------------ #

    def _send_camera_command(self):
        if not self.tracker.is_tracking:
            return

        matched = self.tracker.update(self._latest_detections)
        if matched is None:
            self.camera.stop()
            return

        pan_err, tilt_err = self.tracker.get_error()
        deadzone  = self.config.get("deadzone",  0.03)
        max_speed = self.config.get("max_speed", 30)

        if abs(pan_err) < deadzone and abs(tilt_err) < deadzone:
            self.camera.stop()
            self.pid_pan.reset()
            self.pid_tilt.reset()
            return

        pan_out  = self.pid_pan.compute(pan_err)   if abs(pan_err)  >= deadzone else 0.0
        tilt_out = self.pid_tilt.compute(tilt_err) if abs(tilt_err) >= deadzone else 0.0
        self.camera.pan_tilt(
            self.camera.error_to_speed(pan_out,  max_speed),
            self.camera.error_to_speed(tilt_out, max_speed),
        )

    # ------------------------------------------------------------------ #
    # Settings dialog                                                      #
    # ------------------------------------------------------------------ #

    def _on_settings(self):
        dlg = SettingsDialog(self.config, parent=self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self.config.update(dlg.get_config())
            self._save_config()
            # Sync toolbar fields back from config
            self.ip_edit.setText(self.config["camera_ip"])
            self.rtsp_edit.setText(self.config.get("rtsp_url", ""))
            # Apply
            self.camera = CanonCamera(
                ip=self.config["camera_ip"],
                port=self.config.get("camera_port", 80),
                user=self.config["camera_user"],
                password=self.config["camera_pass"],
            )
            self.pid_pan.update_gains(**self.config["pid_pan"])
            self.pid_tilt.update_gains(**self.config["pid_tilt"])
            self._restart_pipeline()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        self.control_timer.stop()
        self.ping_timer.stop()
        self.camera.stop()
        self.rtsp_receiver.stop()
        self.face_detector.stop()
        event.accept()


# ------------------------------------------------------------------ #
# Small helpers                                                        #
# ------------------------------------------------------------------ #

def _label(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


def _separator(layout: QHBoxLayout):
    line = QWidget()
    line.setFixedSize(1, 20)
    line.setStyleSheet("background:#3a3a3a;")
    layout.addWidget(line)
