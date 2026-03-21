#!/usr/bin/env python3
"""Print enrichment + JSON shape for recent cro_nurture_lead rows (run from project root with .env loaded)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app import create_app
from app.cro_nurture.models import CroNurtureLead


def main() -> None:
    limit = int(os.environ.get("INSPECT_LIMIT", "10"))
    app = create_app()
    with app.app_context():
        n = CroNurtureLead.query.count()
        print("total_cro_nurture_leads:", n)
        rows = CroNurtureLead.query.order_by(CroNurtureLead.id.desc()).limit(limit).all()
        for r in rows:
            payload = r.cro_scan_payload if isinstance(r.cro_scan_payload, dict) else {}
            prof = r.business_profile if isinstance(r.business_profile, dict) else {}
            fp = r.fetched_pages if isinstance(r.fetched_pages, dict) else {}
            print("\n=== lead id=%s ===" % r.id)
            print("email:", r.email)
            print("site_url:", (r.site_url or "")[:120])
            print("enrichment_status:", r.enrichment_status)
            if r.enrichment_error:
                print("enrichment_error:", (r.enrichment_error or "")[:200])
            print("last_enriched_at:", r.last_enriched_at)
            print("next_step_order:", r.next_step_order, "next_send_at:", r.next_send_at)
            print("cro_scan_payload keys:", sorted(payload.keys()))
            print("  scan_status:", payload.get("scan_status"))
            fr = payload.get("full_report")
            if isinstance(fr, dict):
                print("  full_report keys:", sorted(fr.keys()))
                pages = fr.get("pages")
                if isinstance(pages, dict):
                    for pk, pv in pages.items():
                        if isinstance(pv, dict):
                            print("  full_report.pages[%s] keys:" % pk, sorted(pv.keys()))
            elif fr is not None:
                print("  full_report type:", type(fr).__name__)
            print("business_profile keys:", sorted(prof.keys()))
            for k in (
                "industry",
                "business_type",
                "business_summary",
                "value_proposition_why",
                "likely_products_or_services",
                "likely_offerings",
                "cro_audit_themes",
                "hooks_for_email",
                "confidence",
            ):
                v = prof.get(k)
                if v is None:
                    continue
                s = str(v)
                print("  %s: %s%s" % (k, s[:400], "…" if len(s) > 400 else ""))
            print("fetched_pages keys:", sorted(fp.keys()))
            if "homepage" in fp and isinstance(fp["homepage"], dict):
                hm = fp["homepage"]
                meta = hm.get("meta") if isinstance(hm.get("meta"), dict) else {}
                print("  homepage meta keys:", sorted(meta.keys()), "text_len:", hm.get("text_len"))


if __name__ == "__main__":
    main()
