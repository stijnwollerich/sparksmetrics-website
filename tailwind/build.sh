#!/usr/bin/env bash
# Rebuild app/static/css/tailwind.css after changing templates, JS or tailwind/input.css, then commit the CSS.
# Needs the Tailwind CLI v3 standalone binary (https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17),
# path in $TAILWIND or `tailwindcss` on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
"${TAILWIND:-tailwindcss}" -c tailwind.config.js -i tailwind/input.css -o app/static/css/tailwind.css --minify
