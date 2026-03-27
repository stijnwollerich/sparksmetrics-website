#!/usr/bin/env python3
"""Legacy entry point: the CRO scan pipeline runs on Spark, not this repo.

Use the Spark app with ``POST /api/site/cro-scan/run`` (authenticated with
``X-Spark-Site-Secret``) or run a full scan from Spark’s codebase under ``app/cro_scan/``.
"""
import sys


def main():
    print(
        "CRO scans run on Spark. Configure SPARK_BACKEND_URL on the marketing app and run the "
        "pipeline on Spark (see Spark docs/SPARKS_SITE_BACKEND.md).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
