"""Settings dialog — camera connection, RTSP stream, tracking parameters."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._build_ui(config)

    def _build_ui(self, config: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ---- Camera ---------------------------------------------------- #
        cam_group = QGroupBox("Camera (Canon CR-N)")
        cam_form = QFormLayout(cam_group)

        self.ip_edit = QLineEdit(config.get("camera_ip", ""))
        self.ip_edit.setPlaceholderText("e.g. 192.168.1.100")
        self.user_edit = QLineEdit(config.get("camera_user", "admin"))
        self.pass_edit = QLineEdit(config.get("camera_pass", "admin"))
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)

        cam_form.addRow("IP Address:", self.ip_edit)
        cam_form.addRow("Username:", self.user_edit)
        cam_form.addRow("Password:", self.pass_edit)
        layout.addWidget(cam_group)

        # ---- RTSP ------------------------------------------------------- #
        rtsp_group = QGroupBox("Video Stream (RTSP)")
        rtsp_form = QFormLayout(rtsp_group)

        self.rtsp_edit = QLineEdit(config.get("rtsp_url", ""))
        self.rtsp_edit.setPlaceholderText("rtsp://user:pass@192.168.x.x/stream1")

        rtsp_hint = QLabel("Enter the full RTSP URL for your camera's stream.")
        rtsp_hint.setStyleSheet("color: #888; font-size: 11px;")
        rtsp_hint.setWordWrap(True)

        rtsp_form.addRow("RTSP URL:", self.rtsp_edit)
        rtsp_form.addRow("", rtsp_hint)
        layout.addWidget(rtsp_group)

        # ---- Tracking --------------------------------------------------- #
        track_group = QGroupBox("Tracking")
        track_form = QFormLayout(track_group)

        self.deadzone_spin = _make_double_spin(0.0, 0.5, 0.003, 3, config.get("deadzone", 0.03))
        self.max_speed_spin = QSpinBox()
        self.max_speed_spin.setRange(1, 49)
        self.max_speed_spin.setValue(config.get("max_speed", 30))
        self.confidence_spin = _make_double_spin(0.1, 1.0, 0.05, 2, config.get("detection_confidence", 0.6))

        track_form.addRow("Deadzone (normalized):", self.deadzone_spin)
        track_form.addRow("Max Speed (1-49):", self.max_speed_spin)
        track_form.addRow("Face Confidence:", self.confidence_spin)
        layout.addWidget(track_group)

        # ---- PID -------------------------------------------------------- #
        pid_group = QGroupBox("PID Gains")
        pid_form = QFormLayout(pid_group)

        pan  = config.get("pid_pan",  {})
        tilt = config.get("pid_tilt", {})

        self.pan_kp  = _make_pid_spin(pan.get("kp",  0.4))
        self.pan_ki  = _make_pid_spin(pan.get("ki",  0.0))
        self.pan_kd  = _make_pid_spin(pan.get("kd",  0.05))
        self.tilt_kp = _make_pid_spin(tilt.get("kp", 0.4))
        self.tilt_ki = _make_pid_spin(tilt.get("ki", 0.0))
        self.tilt_kd = _make_pid_spin(tilt.get("kd", 0.05))

        pid_form.addRow("Pan  Kp:", self.pan_kp)
        pid_form.addRow("Pan  Ki:", self.pan_ki)
        pid_form.addRow("Pan  Kd:", self.pan_kd)
        pid_form.addRow("Tilt Kp:", self.tilt_kp)
        pid_form.addRow("Tilt Ki:", self.tilt_ki)
        pid_form.addRow("Tilt Kd:", self.tilt_kd)
        layout.addWidget(pid_group)

        # ---- Buttons ---------------------------------------------------- #
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_config(self) -> dict:
        return {
            "camera_ip":            self.ip_edit.text().strip(),
            "camera_user":          self.user_edit.text().strip(),
            "camera_pass":          self.pass_edit.text(),
            "rtsp_url":             self.rtsp_edit.text().strip(),
            "deadzone":             self.deadzone_spin.value(),
            "max_speed":            self.max_speed_spin.value(),
            "detection_confidence": self.confidence_spin.value(),
            "pid_pan":  {"kp": self.pan_kp.value(),  "ki": self.pan_ki.value(),  "kd": self.pan_kd.value()},
            "pid_tilt": {"kp": self.tilt_kp.value(), "ki": self.tilt_ki.value(), "kd": self.tilt_kd.value()},
        }


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _make_double_spin(
    minimum: float, maximum: float, step: float, decimals: int, value: float
) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(value)
    return s


def _make_pid_spin(value: float) -> QDoubleSpinBox:
    return _make_double_spin(0.0, 5.0, 0.05, 3, value)
