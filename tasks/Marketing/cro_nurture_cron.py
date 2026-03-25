#!/usr/bin/env python3
"""
POST the CRO nurture cron (enrich + dispatch).

When SPARK_BACKEND_URL is set, hits Spark (nurture DB lives there).
Otherwise hits SITE_URL (legacy: nurture on sparksmetrics).

Env: SPARK_BACKEND_URL (optional), SITE_URL (or APP_URL), CRO_NURTURE_CRON_TOKEN
"""
import os
import sys

import requests


def main():
    base = (
        (os.environ.get("SPARK_BACKEND_URL") or "").strip()
        or (os.environ.get("SITE_URL") or os.environ.get("APP_URL") or "")
    ).rstrip("/")
    token = os.environ.get("CRO_NURTURE_CRON_TOKEN", "")
    if not base or not token:
        print("SITE_URL (or APP_URL) and CRO_NURTURE_CRON_TOKEN must be set", file=sys.stderr)
        sys.exit(1)
    url = f"{base}/cro-nurture/api/cron/run"
    r = requests.post(url, params={"token": token}, timeout=300)
    print(r.status_code, r.text)
    r.raise_for_status()


if __name__ == "__main__":
    main()
