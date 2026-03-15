#!/usr/bin/env python3
"""
Compress the CRO scan hero GIF for faster loading (target < 400 KB).
Usage: from repo root, run: python scripts/compress_cro_hero_gif.py
Requires: pip install Pillow
"""
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
GIF_PATH = os.path.join(REPO_ROOT, "app", "static", "images", "cro_scan_hero.gif")
TARGET_BYTES = 400 * 1024  # 400 KB

if not os.path.isfile(GIF_PATH):
    print(f"No GIF found at {GIF_PATH}")
    sys.exit(1)

size_before = os.path.getsize(GIF_PATH)
img = Image.open(GIF_PATH)

# Get all frames and durations (GIF can be animated)
frames = []
durations = []
try:
    while True:
        frames.append(img.copy())
        durations.append(img.info.get("duration", 100))
        img.seek(img.tell() + 1)
except EOFError:
    pass

if not frames:
    frames = [img]
    durations = [img.info.get("duration", 100)]

# Reduce to 128 colors per frame to cut file size
p_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames]

out_path = GIF_PATH + ".tmp"
dur = durations[0] if len(durations) == 1 else durations
p_frames[0].save(
    out_path,
    save_all=len(p_frames) > 1,
    append_images=p_frames[1:] if len(p_frames) > 1 else [],
    loop=0,
    duration=dur,
    optimize=True,
)

os.replace(out_path, GIF_PATH)
size_after = os.path.getsize(GIF_PATH)
print(f"Compressed cro_scan_hero.gif: {size_before:,} -> {size_after:,} bytes ({100 * size_after // size_before}% of original)")
