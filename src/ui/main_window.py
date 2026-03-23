"""Main application window.

Layout
------
  ┌─────────────────────────────────────────────────────────┐
  │  [Camera IP ______] [Connect Camera]  [NDI Source ▼] [Connect NDI]  [⚙ Settings] │  ← toolbar
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
    QComboBox,
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
from ..ndi_receiver import NDIReceiver
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
    "ndi_source":           "",
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

        self.ndi_receiver  = NDIReceiver(cfg.get("ndi_source", ""))
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
        self.status_bar.showMessage("Ready — connect a camera and NDI source to begin")

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

        # ---- NDI section ---------------------------------------------- #
        layout.addWidget(_label("NDI Source", _LABEL_STYLE))

        self.ndi_combo = QComboBox()
        self.ndi_combo.setEditable(True)
        self.ndi_combo.setMinimumWidth(200)
        self.ndi_combo.setStyleSheet(_INPUT_STYLE)
        self.ndi_combo.setPlaceholderText("Select or type source name…")
        current_ndi = self.config.get("ndi_source", "")
        if current_ndi:
            self.ndi_combo.addItem(current_ndi)
            self.ndi_combo.setCurrentText(current_ndi)
        layout.addWidget(self.ndi_combo)

        self.btn_scan_ndi = QPushButton("Scan")
        self.btn_scan_ndi.setStyleSheet(_BTN_STYLE)
        self.btn_scan_ndi.setToolTip("Scan the network for NDI sources (~2 s)")
        self.btn_scan_ndi.clicked.connect(self._on_scan_ndi)
        layout.addWidget(self.btn_scan_ndi)

        self.btn_connect_ndi = QPushButton("Connect NDI")
        self.btn_connect_ndi.setStyleSheet(_BTN_STYLE)
        self.btn_connect_ndi.clicked.connect(self._on_connect_ndi)
        layout.addWidget(self.btn_connect_ndi)

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
        self.ndi_receiver.frame_ready.connect(self._on_frame)
        self.ndi_receiver.error_occurred.connect(self._on_ndi_error)
        self.ndi_receiver.sources_updated.connect(self._on_sources_discovered)
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

    def _on_scan_ndi(self):
        self.btn_scan_ndi.setEnabled(False)
        self.btn_scan_ndi.setText("Scanning…")
        self.status_bar.showMessage("Scanning for NDI sources (~2 s)…")
        # Defer to keep UI responsive
        QTimer.singleShot(100, self._do_scan_ndi)

    def _do_scan_ndi(self):
        sources = NDIReceiver.discover_sources(wait_seconds=2.0)
        current = self.ndi_combo.currentText()
        self.ndi_combo.clear()
        all_sources = list(dict.fromkeys(([current] if current else []) + sources))
        self.ndi_combo.addItems(all_sources)
        if current:
            idx = self.ndi_combo.findText(current)
            if idx >= 0:
                self.ndi_combo.setCurrentIndex(idx)
        self.btn_scan_ndi.setEnabled(True)
        self.btn_scan_ndi.setText("Scan")
        if sources:
            self.status_bar.showMessage(f"Found {len(sources)} NDI source(s): {', '.join(sources)}")
        else:
            self.status_bar.showMessage("No NDI sources found on this network")

    def _on_connect_ndi(self):
        source = self.ndi_combo.currentText().strip()
        self.config["ndi_source"] = source
        self._save_config()
        self._restart_pipeline()

    # ------------------------------------------------------------------ #
    # Pipeline                                                             #
    # ------------------------------------------------------------------ #

    def _restart_pipeline(self):
        if self.ndi_receiver.isRunning():
            self.ndi_receiver.stop()
        if self.face_detector.isRunning():
            self.face_detector.stop()

        self.ndi_receiver.set_source(self.config.get("ndi_source", ""))
        self.ndi_receiver.start()
        self.face_detector.start()
        self.control_timer.start()

        src = self.config.get("ndi_source", "") or "(first available)"
        self.status_bar.showMessage(f"Connecting to NDI source: {src}…")

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

    def _on_sources_discovered(self, sources: list[str]):
        if not sources:
            return
        current = self.ndi_combo.currentText()
        existing = [self.ndi_combo.itemText(i) for i in range(self.ndi_combo.count())]
        for s in sources:
            if s not in existing:
                self.ndi_combo.addItem(s)
        # Auto-select if nothing chosen yet
        if not current and sources:
            self.ndi_combo.setCurrentText(sources[0])

    def _on_ndi_error(self, msg: str):
        self.status_bar.showMessage(f"NDI error: {msg}")

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
        dlg = SettingsDialog(self.config, ndi_sources=[], parent=self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self.config.update(dlg.get_config())
            self._save_config()
            # Sync toolbar fields back from config
            self.ip_edit.setText(self.config["camera_ip"])
            src = self.config.get("ndi_source", "")
            if src and self.ndi_combo.findText(src) < 0:
                self.ndi_combo.insertItem(0, src)
            self.ndi_combo.setCurrentText(src)
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
        self.ndi_receiver.stop()
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
