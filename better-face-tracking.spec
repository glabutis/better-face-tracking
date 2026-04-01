# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Better Face Tracking
#
# Build:
#   pyinstaller better-face-tracking.spec --clean --noconfirm
#
# The resulting .app is placed in dist/BetterFaceTracking.app

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

# ---------------------------------------------------------------------------
# Collect mediapipe model data (it ships binary model files inside the package)
# ---------------------------------------------------------------------------
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

mediapipe_datas   = collect_data_files("mediapipe")
mediapipe_binaries = collect_dynamic_libs("mediapipe")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=mediapipe_binaries,
    datas=[
        (str(ROOT / "config.json"), "."),   # default config inside bundle
        *mediapipe_datas,
    ],
    hiddenimports=[
        # PyQt6 modules that PyInstaller misses via static analysis
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        # CV / ML
        "cv2",
        "numpy",
        "mediapipe",
        "mediapipe.python.solutions.face_detection",
        # Networking
        "requests",
        "urllib3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep the bundle lean — these are never used
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BetterFaceTracking",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can break signed binaries; leave off
    console=False,      # no terminal window on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,   # None = match current runner arch (set by CI matrix)
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BetterFaceTracking",
)

app = BUNDLE(
    coll,
    name="BetterFaceTracking.app",
    icon="assets/AppIcon.icns",
    bundle_identifier="com.bft.better-face-tracking",
    version="0.1.4",
    info_plist={
        "CFBundleName":                "Better Face Tracking",
        "CFBundleDisplayName":         "Better Face Tracking",
        "CFBundleShortVersionString":  "0.1.4",
        "CFBundleVersion":             "0.1.4",
        "NSHighResolutionCapable":     True,
        "NSCameraUsageDescription":    "Camera access is not used directly — video is received via RTSP.",
        "NSMicrophoneUsageDescription":"Microphone access is not used.",
        "LSMinimumSystemVersion":      "12.0",
        "NSRequiresAquaSystemAppearance": False,  # supports Dark Mode
    },
)
