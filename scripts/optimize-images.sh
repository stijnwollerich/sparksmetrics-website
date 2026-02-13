#!/usr/bin/env bash
# Optimize images for the Sparksmetrics site.
# - Requires: ffmpeg, cwebp
# - Reads source images from app/static/images (and logos in app/static/images/logos)
# - Writes optimized derivatives to app/static/images/optimized/{webp,jpg}
set -euo pipefail
SRC_DIR="app/static/images"
OUT_DIR="$SRC_DIR/optimized"
mkdir -p "$OUT_DIR/webp" "$OUT_DIR/jpg" "$OUT_DIR/logos"

echo "Finding images in $SRC_DIR..."
shopt -s nullglob
for img in "$SRC_DIR"/*.{png,jpg,jpeg} "$SRC_DIR"/**/*.{png,jpg,jpeg}; do
  [ -f "$img" ] || continue
  rel="${img#$SRC_DIR/}"
  echo "Processing $rel"
  filename="$(basename "$img")"
  name="${filename%.*}"
  # create a large webp (1200px wide), a medium (800), and a thumbnail (320)
  ffmpeg -y -i "$img" -vf "scale='min(1200,iw)':'-2'" -q:v 4 "$OUT_DIR/webp/${name}-1200.webp"
  ffmpeg -y -i "$img" -vf "scale='min(800,iw)':'-2'" -q:v 6 "$OUT_DIR/webp/${name}-800.webp"
  ffmpeg -y -i "$img" -vf "scale='min(320,iw)':'-2'" -q:v 8 "$OUT_DIR/webp/${name}-320.webp"
  # also produce progressive jpg fallbacks
  ffmpeg -y -i "$img" -vf "scale='min(1200,iw)':'-2'" -q:v 4 "$OUT_DIR/jpg/${name}-1200.jpg"
done

echo "Optimizing logos..."
LOGO_DIR="$SRC_DIR/logos"
for logo in "$LOGO_DIR"/*.{png,jpg,jpeg,svg}; do
  [ -f "$logo" ] || continue
  filename="$(basename "$logo")"
  name="${filename%.*}"
  # raster logos -> webp at height 48 and 96
  if [[ "$logo" =~ \.(png|jpe?g)$ ]]; then
    ffmpeg -y -i "$logo" -vf "scale=-2:48" -q:v 6 "$OUT_DIR/logos/${name}-48.webp"
    ffmpeg -y -i "$logo" -vf "scale=-2:96" -q:v 6 "$OUT_DIR/logos/${name}-96.webp"
  else
    # svg: copy as-is to optimized folder (browsers load SVG small anyway)
    cp "$logo" "$OUT_DIR/logos/${filename}"
  fi
done

echo "Done. Optimized images are in $OUT_DIR. Update templates to use them (srcset/picture)."

