#!/usr/bin/env bash
# Compress the CRO scan hero GIF for faster loading.
# Usage: from repo root, run: ./scripts/compress_cro_hero_gif.sh
# Requires: gifsicle (install with: brew install gifsicle)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GIF="$REPO_ROOT/app/static/images/cro_scan_hero.gif"

if [ ! -f "$GIF" ]; then
  echo "No GIF found at app/static/images/cro_scan_hero.gif"
  echo "Copy your file there first, e.g.:"
  echo "  cp '/Users/you/Downloads/Heading (1).gif' $GIF"
  exit 1
fi

if ! command -v gifsicle &>/dev/null; then
  echo "gifsicle is not installed. Install with: brew install gifsicle"
  exit 1
fi

BYTES_BEFORE=$(stat -f%z "$GIF" 2>/dev/null || stat -c%s "$GIF" 2>/dev/null)
TMP="$GIF.tmp"
gifsicle -O3 --lossy=80 -o "$TMP" "$GIF"
mv "$TMP" "$GIF"
BYTES_AFTER=$(stat -f%z "$GIF" 2>/dev/null || stat -c%s "$GIF" 2>/dev/null)
echo "Compressed cro_scan_hero.gif: ${BYTES_BEFORE} -> ${BYTES_AFTER} bytes"
