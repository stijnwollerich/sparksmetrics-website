"""Orchestrate CRO scan pipeline: screenshots → AI → store report → email (link) → Slack."""
from __future__ import annotations

import json
import secrets
from datetime import datetime

from flask import current_app


def _notify_slack_report_ready(report_view_url: str, store_name: str, to_email: str) -> None:
    """Post report link to Slack when CRO scan is done and email was sent. Logs errors, does not raise."""
    webhook_url = (current_app.config.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    text = "CRO scan report ready: *{}* – sent to {} – <{}|View report>".format(
        store_name, to_email, report_view_url
    )
    try:
        import requests
    except ModuleNotFoundError:
        current_app.logger.warning("Slack notify skipped: install requests (pip install requests)")
        return
    try:
        r = requests.post(
            webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        if r.status_code != 200:
            current_app.logger.warning(
                "Slack webhook failed: HTTP %s – %s", r.status_code, (r.text or "")[:200]
            )
    except Exception as e:
        current_app.logger.warning("Slack notify error: %s", e)


def run_scan(store_url: str, email: str, fname: str) -> None:
    """
    Run the full CRO scan pipeline in the current (or pushed) app context:
    1. Discover homepage, collection, product and get mobile screenshot URLs
    2. Run AI analysis on screenshots → report JSON
    3. Store report by secret token for private web viewing
    4. Send email with link to view report (no PDF attachment)

    Logs errors and does not raise; safe to run in a background thread.
    """
    from app.cro_scan.screenshots import get_screenshot_urls
    from app.cro_scan.ai_analysis import analyze_screenshots
    from app.cro_scan.email_report import send_report_email

    try:
        current_app.logger.info("CRO scan: starting for %s → %s", store_url, email)
    except RuntimeError:
        pass

    # 1. Screenshot URLs (mobile). Shopify: discover collection + product; other stores: discover category + product.
    from app.cro_scan.platform import is_shopify_store
    is_shopify = is_shopify_store(store_url)
    try:
        screenshot_urls = get_screenshot_urls(store_url, is_shopify=is_shopify)
        provider = "Browserless" if current_app.config.get("BROWSERLESS_API_TOKEN") else "Scrapfly" if current_app.config.get("SCRAPFLY_API_KEY") else "thum.io"
        current_app.logger.info("CRO scan: %s store, provider=%s for %s", "Shopify" if is_shopify else "generic", provider, store_url[:50])
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
        url = (screenshot_urls.get(page_key) or "").strip()
        # Only use URL as img src if it returns an image (thum.io / Scrapfly). With Browserless we get
        # raw page URLs here—using those as img src returns HTML and breaks; show "unavailable" instead.
        if url and ("thum.io" in url or "scrapfly" in url.lower()):
            report["pages"][page_key]["screenshot_url"] = url

    # Log report image status so prod logs show why images might be missing on the report page
    try:
        summary = []
        for pk in ("homepage", "collection", "product"):
            p = (report.get("pages") or {}).get(pk) or {}
            if p.get("screenshot_data_uri"):
                summary.append(f"{pk}=embedded")
            elif p.get("screenshot_url"):
                summary.append(f"{pk}=url")
            else:
                summary.append(f"{pk}=none")
        current_app.logger.info("CRO scan: report images %s", ", ".join(summary))
    except Exception:
        pass

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

    # 4. Email: link to on-site report only (no PDF attachment)
    send_report_email(
        to_email=email,
        fname=fname or "there",
        store_name=store_name,
        report_view_url=report_view_url,
    )

    # 5. Slack: post report link to channel (same webhook as lead notifications)
    if report_view_url:
        _notify_slack_report_ready(report_view_url, store_name, email)

    # 6. Nurture: attach report JSON to lead (same email + store URL)
    try:
        if current_app.config.get("CRO_NURTURE_ENABLED"):
            from app.cro_nurture.leads import attach_cro_scan_report_to_lead

            attach_cro_scan_report_to_lead(email=email, store_url=store_url, report=report)
            # Local dev: cron is usually not installed — run one enrich + dispatch pass after attach.
            if current_app.debug:
                import threading
                import time

                app = current_app._get_current_object()

                def _nurture_cron_kick():
                    time.sleep(0.75)
                    with app.app_context():
                        try:
                            from app.cro_nurture.services.enrichment import run_enrichment_batch
                            from app.cro_nurture.services.dispatch import run_dispatch_batch_until_quiet

                            en = run_enrichment_batch()
                            di = run_dispatch_batch_until_quiet()
                            app.logger.info(
                                "cro_nurture: DEBUG post-scan cron kick enrich=%s dispatch=%s",
                                en,
                                di,
                            )
                        except Exception:
                            app.logger.exception("cro_nurture: DEBUG post-scan cron kick failed")

                threading.Thread(target=_nurture_cron_kick, daemon=True).start()
    except Exception as e:
        current_app.logger.warning("cro_nurture: attach report failed: %s", e)
