#!/usr/bin/env python3
"""
Generate assets/AppIcon.icns for the macOS app bundle.

Requires: Pillow  (pip install pillow)
Requires: macOS   (uses sips + iconutil)

Run from the project root:
    python assets/generate_icon.py
"""

import os
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

ASSETS = Path(__file__).parent
ICONSET = ASSETS / "AppIcon.iconset"
ICNS = ASSETS / "AppIcon.icns"

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def draw_icon(size: int) -> Image.Image:
    """Draw a simple camera-tracking icon at the given pixel size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle — dark slate
    margin = int(size * 0.04)
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(28, 32, 42, 255),
    )

    cx, cy = size // 2, size // 2
    r = size // 2 - margin

    # Outer reticle ring
    ring_r = int(r * 0.72)
    ring_w = max(1, size // 40)
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        outline=(0, 200, 120, 255),
        width=ring_w,
    )

    # Crosshair lines (with gap in the middle)
    gap = int(r * 0.18)
    line_len = int(r * 0.48)
    lw = max(1, size // 50)
    green = (0, 200, 120, 255)
    # horizontal
    draw.line([(cx - ring_r, cy), (cx - gap, cy)], fill=green, width=lw)
    draw.line([(cx + gap, cy), (cx + ring_r, cy)], fill=green, width=lw)
    # vertical
    draw.line([(cx, cy - ring_r), (cx, cy - gap)], fill=green, width=lw)
    draw.line([(cx, cy + gap), (cx, cy + ring_r)], fill=green, width=lw)

    # Inner dot
    dot_r = max(2, size // 28)
    draw.ellipse(
        [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
        fill=(0, 255, 150, 255),
    )

    # Corner tick marks on reticle
    tick = max(2, int(r * 0.15))
    tick_lw = max(1, size // 36)
    tick_offset = int(ring_r * 0.70)
    corners = [
        (cx - tick_offset, cy - tick_offset, 1,  1),
        (cx + tick_offset, cy - tick_offset, -1,  1),
        (cx - tick_offset, cy + tick_offset, 1, -1),
        (cx + tick_offset, cy + tick_offset, -1, -1),
    ]
    for tx, ty, sx, sy in corners:
        draw.line([(tx, ty), (tx + tick * sx, ty)], fill=green, width=tick_lw)
        draw.line([(tx, ty), (tx, ty + tick * sy)], fill=green, width=tick_lw)

    return img


def main():
    ICONSET.mkdir(exist_ok=True)

    for size in SIZES:
        img = draw_icon(size)
        img.save(ICONSET / f"icon_{size}x{size}.png")
        # @2x versions (retina)
        if size <= 512:
            img2 = draw_icon(size * 2)
            img2.save(ICONSET / f"icon_{size}x{size}@2x.png")

    # Convert iconset → icns using macOS iconutil
    if sys.platform != "darwin":
        print("⚠  iconutil is macOS-only. PNG iconset written to assets/AppIcon.iconset/")
        print("   Run on macOS to produce the final .icns file.")
        return

    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("iconutil failed:", result.stderr, file=sys.stderr)
        sys.exit(1)

    print(f"✓  Icon written to {ICNS}")


if __name__ == "__main__":
    main()
