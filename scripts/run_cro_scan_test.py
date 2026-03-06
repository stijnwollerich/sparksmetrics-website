#!/usr/bin/env python3
"""Run a one-off CRO scan for a store URL and save the report PDF locally. No email sent.

Usage (from project root):
  python scripts/run_cro_scan_test.py https://outdoorresearch.com

Requires: OPENAI_API_KEY in .env for AI analysis; BREVO_* not required for PDF-only run.
"""
import sys
import os

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    store_url = (sys.argv[1] if len(sys.argv) > 1 else "https://outdoorresearch.com").strip()
    if not store_url.startswith("http"):
        store_url = "https://" + store_url

    from app import create_app
    app = create_app()
    with app.app_context():
        from app.cro_scan.screenshots import get_screenshot_urls
        from app.cro_scan.ai_analysis import analyze_screenshots
        from app.cro_scan.report import build_report_pdf

        print("1. Getting mobile screenshot URLs...")
        screenshot_urls = get_screenshot_urls(store_url)
        for k, v in screenshot_urls.items():
            print(f"   {k}: {v[:60]}..." if len(v) > 60 else f"   {k}: {v}")

        print("2. Running AI analysis (OpenAI vision)...")
        report = analyze_screenshots(store_url, screenshot_urls)
        print(f"   Overall score: {report.get('overall_score')}, store_name: {report.get('store_name')}")

        print("3. Injecting screenshot URLs into report...")
        for page_key, url in screenshot_urls.items():
            if url and report.get("pages") and isinstance(report["pages"].get(page_key), dict):
                report["pages"][page_key]["screenshot_url"] = url

        print("4. Building PDF...")
        pdf_bytes = build_report_pdf(report)
        if not pdf_bytes:
            print("   ERROR: PDF is empty (check weasyprint install?).")
            return 1

        out_name = "cro_scan_report_test.pdf"
        out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), out_name)
        with open(out_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"5. Done. Report saved to: {out_path}")
        return 0

if __name__ == "__main__":
    sys.exit(main())
