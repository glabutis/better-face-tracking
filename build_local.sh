#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build_local.sh — build a DMG on your local Mac for testing
#
# Usage:
#   chmod +x build_local.sh
#   ./build_local.sh              # builds with current version tag
#   ./build_local.sh v1.2.3       # builds with specific tag name
# ---------------------------------------------------------------------------
set -euo pipefail

# ---- version --------------------------------------------------------------
TAG="${1:-$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0-local")}"
ARCH="$(uname -m)"           # arm64 or x86_64
DMG_NAME="BetterFaceTracking-${TAG}-${ARCH}.dmg"

echo "================================================"
echo "  Building  Better Face Tracking"
echo "  Tag:  ${TAG}   Arch: ${ARCH}"
echo "================================================"

# ---- checks ---------------------------------------------------------------
if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERROR: This script must run on macOS." >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "python3 not found"; exit 1; }
command -v pyinstaller >/dev/null 2>&1 || {
  echo "PyInstaller not found — installing…"
  pip install pyinstaller
}
command -v create-dmg >/dev/null 2>&1 || {
  echo "create-dmg not found — installing via Homebrew…"
  brew install create-dmg
}

# ---- Python deps ----------------------------------------------------------
echo ""
echo "→ Installing Python dependencies…"
pip install -r requirements.txt pillow --quiet

# ---- Icon -----------------------------------------------------------------
echo "→ Generating app icon…"
python3 assets/generate_icon.py

# ---- PyInstaller ----------------------------------------------------------
echo "→ Building app bundle…"
pyinstaller better-face-tracking.spec --clean --noconfirm

# ---- Code sign (ad-hoc) ---------------------------------------------------
echo "→ Ad-hoc code signing…"
codesign --deep --force --sign - dist/BetterFaceTracking.app

# ---- DMG ------------------------------------------------------------------
echo "→ Creating DMG: ${DMG_NAME}…"
rm -f "${DMG_NAME}"

create-dmg \
  --volname "Better Face Tracking ${TAG}" \
  --volicon "assets/AppIcon.icns" \
  --window-pos 200 150 \
  --window-size 620 420 \
  --icon-size 120 \
  --icon "BetterFaceTracking.app" 155 185 \
  --hide-extension "BetterFaceTracking.app" \
  --app-drop-link 465 185 \
  --no-internet-enable \
  "${DMG_NAME}" \
  "dist/"

echo ""
echo "================================================"
echo "  Done!  →  ${DMG_NAME}"
echo "  Size:  $(du -sh "${DMG_NAME}" | cut -f1)"
echo "================================================"

# Open DMG in Finder for a quick sanity check
open "${DMG_NAME}"
