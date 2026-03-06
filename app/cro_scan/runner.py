"""Orchestrate CRO scan pipeline: screenshots → AI → PDF → store → email."""
from __future__ import annotations

import json
import secrets
from datetime import datetime

from flask import current_app


def run_scan(store_url: str, email: str, fname: str) -> None:
    """
    Run the full CRO scan pipeline in the current (or pushed) app context:
    1. Discover homepage, collection, product and get mobile screenshot URLs
    2. Run AI analysis on screenshots → report JSON
    3. Build PDF from report
    4. Store report by secret token for private web viewing
    5. Send email with link to view report (and optional PDF attachment)

    Logs errors and does not raise; safe to run in a background thread.
    """
    from app.cro_scan.screenshots import get_screenshot_urls
    from app.cro_scan.ai_analysis import analyze_screenshots
    from app.cro_scan.report import build_report_pdf
    from app.cro_scan.email_report import send_report_email

    try:
        current_app.logger.info("CRO scan: starting for %s → %s", store_url, email)
    except RuntimeError:
        pass

    # 1. Screenshot URLs (mobile). Uses Browserless when BROWSERLESS_API_TOKEN set, else thum.io.
    try:
        screenshot_urls = get_screenshot_urls(store_url)
        provider = "Browserless" if current_app.config.get("BROWSERLESS_API_TOKEN") else "Scrapfly" if current_app.config.get("SCRAPFLY_API_KEY") else "thum.io"
        current_app.logger.info("CRO scan: screenshot provider=%s for %s", provider, store_url[:50])
    except Exception as e:
        current_app.logger.warning("CRO scan: screenshot discovery failed: %s", e)
        screenshot_urls = {"homepage": f"https://image.thum.io/get/width/400/{store_url}", "collection": "", "product": ""}

    # 2. AI analysis
    try:
        report = analyze_screenshots(store_url, screenshot_urls)
    except Exception as e:
        current_app.logger.warning("CRO scan: AI analysis failed: %s", e)
        from app.cro_scan.ai_analysis import _mock_report
        report = _mock_report(store_url)

    if "report_date" not in report or not report.get("report_date"):
        report["report_date"] = datetime.utcnow().strftime("%B %d, %Y")

    # Ensure all three pages exist; only set screenshot_url when we don't have embedded screenshot_data_uri
    # (valid screenshots are embedded by ai_analysis to avoid "Image not authorized" when viewing later)
    from app.cro_scan.ai_analysis import _empty_page_dict
    for page_key in ("homepage", "collection", "product"):
        if report.get("pages") is None:
            report["pages"] = {}
        if not isinstance(report["pages"].get(page_key), dict):
            report["pages"][page_key] = _empty_page_dict()
        if report["pages"][page_key].get("screenshot_data_uri"):
            continue
        url = screenshot_urls.get(page_key) or ""
        if url:
            report["pages"][page_key]["screenshot_url"] = url

    # 3. Store report for private web viewing (secret token; only link holders can view)
    store_name = (report.get("store_name") or "your store").strip()
    report_view_url: str | None = None
    try:
        from app.models import db, CroScanReport
        token = secrets.token_urlsafe(32)
        report_json_str = json.dumps(report, default=str)
        rec = CroScanReport(
            token=token,
            report_json=report_json_str,
            store_url=store_url,
            store_name=store_name,
        )
        db.session.add(rec)
        db.session.commit()
        base = (current_app.config.get("SITE_URL") or "").strip().rstrip("/") or "https://sparksmetrics.com"
        report_view_url = f"{base}/cro-scan/report/{token}"
    except Exception as e:
        current_app.logger.warning("CRO scan: failed to store report for web view: %s", e)
        report_view_url = None

    # 4. PDF (optional; still send if we have it so user can download)
    pdf_bytes = b""
    try:
        pdf_bytes = build_report_pdf(report)
    except Exception as e:
        current_app.logger.warning("CRO scan: PDF build failed: %s", e)

    # 5. Email: prefer link to view on site; attach PDF if available
    send_report_email(
        to_email=email,
        fname=fname or "there",
        store_name=store_name,
        report_view_url=report_view_url,
        pdf_bytes=pdf_bytes,
    )
