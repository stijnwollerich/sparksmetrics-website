#!/usr/bin/env python3
"""Test Browserless screenshot: fetch one image and print dimensions. Run from project root."""
import base64
import os
import sys
from pathlib import Path

# Load .env
_root = Path(__file__).resolve().parent.parent
_env = _root / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"").strip()
            if k and v:
                os.environ.setdefault(k, v)

token = (os.environ.get("BROWSERLESS_API_TOKEN") or "").strip()
if not token:
    print("BROWSERLESS_API_TOKEN not set in .env")
    sys.exit(1)

# Test URL (use a simple site; or cghunter.com to test Cloudflare bypass)
test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.cghunter.com"
print(f"Fetching screenshot for {test_url} ...")

import requests
from urllib.parse import quote

api_url = "https://production-sfo.browserless.io/unblock"
payload = {
    "url": test_url,
    "content": False,
    "cookies": False,
    "screenshot": True,
    "browserWSEndpoint": False,
}
try:
    r = requests.post(
        f"{api_url}?token={quote(token, safe='')}",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    b64 = (data.get("screenshot") or "").strip()
    if not b64:
        print("FAIL: Browserless returned no screenshot field")
        sys.exit(1)
    raw = base64.standard_b64decode(b64)
    # Read dimensions (PNG or JPEG)
    w, h = None, None
    if len(raw) >= 24 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        import struct
        w, h = struct.unpack(">II", raw[16:24])
    elif raw[:2] == b"\xff\xd8":
        i = 2
        while i < len(raw) - 9:
            if raw[i] != 0xFF:
                i += 1
                continue
            if raw[i + 1] in (0xC0, 0xC1, 0xC2):
                import struct
                h, w = struct.unpack(">HH", raw[i + 5 : i + 9])
                break
            try:
                i += 2 + struct.unpack(">H", raw[i + 2 : i + 4])[0]
            except Exception:
                break
    if w and h:
        print(f"OK: image {w}x{h} px, size {len(raw) / 1024:.1f} KB")
    else:
        print(f"OK: got image, size {len(raw) / 1024:.1f} KB")
except requests.exceptions.HTTPError as e:
    print(f"FAIL: HTTP {e.response.status_code} - {e.response.text[:300]}")
    sys.exit(1)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
