"""Run AI (OpenAI vision) on store screenshots and return structured report JSON."""
from __future__ import annotations

import json
import re

from flask import current_app


REPORT_JSON_SCHEMA = """
Return a single JSON object (no markdown, no code fence). Only describe what you see. Do not invent metrics. Tailor to brand (e.g. no countdown timers for premium).
{
  "store_name": "<brand name>",
  "overall_score": <0-100>,
  "executive_summary": {
    "what_is_working": "<2-4 sentences. Synthesize across all three pages (homepage, collection, product); do not focus only on the homepage.>",
    "what_is_hurting": "<2-4 sentences. Include collection and product page issues where relevant.>",
    "biggest_opportunity": "<2-3 sentences. Draw from the full funnel.>"
  },
  "customer_research": {
    "target_audience_hypothesis": "<Infer from products, pricing, positioning>",
    "customer_motivations": "<What motivations does the site speak to?>",
    "customer_fears_frustrations": "<Fears or frustrations the site could address?>",
    "desired_outcomes": "<What outcomes does the customer want?>"
  },
  "pages": {
    "homepage": {
      "score": <0-100>,
      "page_anatomy": { "promise": "<Status>: <short explanation>. Status must be exactly one of: Present, Good, Weak, Missing. E.g. Present: Clear value prop. Or Weak: CTA blends in. Or Missing: No reviews.>", "offer": "...", "pain_point": "...", "solution": "...", "social_proof": "...", "trust_signals": "...", "cta": "...", "visual_hierarchy": "..." },
      "motivation": "<Does the page create desire to buy?>",
      "clarity": "<Is value proposition obvious?>",
      "friction": ["<CRO or UI/UX issue>", ...],
      "page_summary": "<Short paragraph: conversion and UX biggest weakness>",
      "ui_ux_notes": ["<2-5 short UI/UX observations: hierarchy, readability, consistency, mobile usability>", ...],
      "testing_ideas": ["<2-4 experiment ideas>", ...]
    },
    "collection": { "score": <0-100>, "page_anatomy": {...}, "motivation": "...", "clarity": "...", "friction": [], "page_summary": "...", "ui_ux_notes": [], "testing_ideas": [] },
    "product": { "score": <0-100>, "above_the_fold": "<optional>", "below_the_fold": "<optional>", "page_anatomy": {...}, "motivation": "...", "clarity": "...", "friction": [], "page_summary": "...", "ui_ux_notes": [], "testing_ideas": [] }
  },
  "ugly_truth": "<One clear statement: biggest strategic weakness>",
  "biggest_opportunity": { "title": "...", "explanation": "...", "why_it_matters": "...", "example_tests": [] },
  "fast_wins": ["<3-5 quick improvements; can include UI/UX>", ...],
  "roadmap_90_days": { "month1": [], "month2": [], "month3": [] },
  "experiment_backlog": ["<10 A/B tests across funnel>", ...],
  "what_good_looks_like": "<What high-converting, good-UX pages include>",
  "next_steps": "<Summary of recommended actions>"
}
Rules: Each page has page_anatomy. For every page_anatomy field (promise, offer, pain_point, solution, social_proof, trust_signals, cta, visual_hierarchy) you must start the value with exactly one of: Present, Good, Weak, Missing—then a colon and space—then a short explanation. Example: "Present: Clear sale messaging" or "Weak: CTA blends with background" or "Missing: No trust badges". Never output only a description without the status word. Also include page_summary, testing_ideas (2-4), and optionally ui_ux_notes. Include executive_summary, customer_research, ugly_truth, biggest_opportunity, fast_wins (3-5), roadmap_90_days, experiment_backlog (10), what_good_looks_like, next_steps. If page missing use null. Keep concise.
"""


def _fetch_image_as_base64(url: str, timeout: int = 50, retries: int = 2) -> str | None:
    """Download image from URL and return as data URL (data:image/...;base64,...). Retries on timeout or failure."""
    import base64
    import requests
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
            )
            r.raise_for_status()
            raw = r.content
            if not raw:
                continue
            ct = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            if ct not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                ct = "image/png"
            b64 = base64.standard_b64encode(raw).decode("ascii")
            return f"data:{ct};base64,{b64}"
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                current_app.logger.info("CRO scan: retry %s for image (attempt %s)", attempt + 2, url[:50])
    if last_error:
        current_app.logger.warning("CRO scan: failed to fetch image %s: %s", url[:60], last_error)
    return None


def _call_openai_vision(
    image_payloads: list[str],
    prompt: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    timeout: int = 120,
) -> dict:
    """image_payloads: list of data URLs (data:image/...;base64,...) or plain URLs. Prefer base64 to avoid OpenAI fetch timeouts."""
    import requests

    base = (current_app.config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

    content: list[dict] = [{"type": "text", "text": prompt}]
    for payload in image_payloads:
        if payload:
            content.append({"type": "image_url", "image_url": {"url": payload}})

    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": content},
        ],
    }
    r = requests.post(
        f"{base}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    if r.status_code >= 400:
        try:
            err_body = (r.text or "")[:500]
            current_app.logger.warning("CRO scan: OpenAI API %s response: %s", r.status_code, err_body)
        except Exception:
            pass
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    raw = (choice.get("message") or {}).get("content") or ""
    return {"raw": raw, "data": data}


def analyze_screenshots(store_url: str, screenshot_urls: dict[str, str]) -> dict:
    """
    Run OpenAI vision on the given screenshot URLs and return a report dict.
    screenshot_urls: {"homepage": url, "collection": url, "product": url}
    """
    api_key = (
        (current_app.config.get("OPENAI_API_KEY") or "")
        or (current_app.config.get("OPEN_AI_KEY") or "")
        or ""
    ).strip()
    if not api_key:
        current_app.logger.warning("CRO scan: OPENAI_API_KEY / OPEN_AI_KEY not set, skipping AI analysis")
        return _mock_report(store_url)

    urls = [
        screenshot_urls.get("homepage") or "",
        screenshot_urls.get("collection") or "",
        screenshot_urls.get("product") or "",
    ]
    urls = [u for u in urls if u]

    if not urls:
        return _mock_report(store_url)

    # Download images to base64 (longer timeout + retries; thum.io can be slow)
    image_payloads: list[str] = []
    for url in urls:
        if url.startswith("data:"):
            image_payloads.append(url)
        else:
            data_url = _fetch_image_as_base64(url, timeout=50, retries=2)
            if data_url:
                image_payloads.append(data_url)
    if not image_payloads:
        current_app.logger.warning("CRO scan: could not fetch any screenshot images (thum.io may be slow or down)")
        return _mock_report(store_url, api_failed=True)

    prompt = f"""You are an expert in both conversion rate optimization (CRO) and UI/UX for e-commerce. Your audit should combine:
- **CRO lens**: conversion intent, value clarity, trust and social proof, CTAs, page anatomy (promise, offer, pain point, solution, etc.), and friction that blocks purchase.
- **UI/UX lens**: visual hierarchy and scannability, readability (type size, contrast, line length), consistency (patterns, spacing, alignment), mobile usability (tap targets, thumb reach, clear next step), and perceived complexity. Call out when layout or interaction design hurts clarity or trust.

Analyze only what you see in these mobile screenshots. Do not invent metrics or funnel data. Tailor every recommendation to the brand: no countdown timers or heavy discount urgency for premium/luxury sites; suggest tactics that fit (e.g. quality, trust, real scarcity). Be accurate, not generic.

The first image is the HOMEPAGE, the second (if present) is a COLLECTION page, the third (if present) is a PRODUCT page.

Important: The executive_summary must synthesize findings across all three pages (homepage, collection, product). Do not write it as if only the homepage was analyzed—mention collection and product page strengths and issues where relevant. Weave in both conversion and UI/UX where they matter (e.g. "Product page has strong social proof but dense copy and small tap targets hurt mobile conversion").

If a popup, modal, or overlay (e.g. email signup, cookie banner) is visible in a screenshot, base your assessment of that page on the main page content behind it. Treat the overlay as secondary; you may note "popup visible" in the relevant page_summary or anatomy if it affects clarity, but score and anatomy should reflect the actual page structure and conversion elements, not the overlay.

For each page, use friction for both conversion blockers and UI/UX issues (e.g. "CTA buried below fold", "Text too small on mobile"). Use ui_ux_notes for 2–5 short, specific UI/UX observations: e.g. "Clear visual hierarchy; hero and CTA stand out", "Body text may be hard to scan; consider shorter paragraphs", "Primary button has good contrast and size".

{REPORT_JSON_SCHEMA}
"""

    try:
        resp = _call_openai_vision(image_payloads, prompt, api_key)
        raw = (resp.get("raw") or "").strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
        report = json.loads(raw)
        report["store_url"] = store_url
        return _normalize_report(report)
    except json.JSONDecodeError as e:
        current_app.logger.warning("CRO scan: AI returned invalid JSON: %s", e)
        return _mock_report(store_url, api_failed=True)
    except Exception as e:
        current_app.logger.warning("CRO scan: AI analysis failed: %s", e)
        return _mock_report(store_url, api_failed=True)


def _empty_page_dict() -> dict:
    """Return a minimal page dict so the report always has something to render for each page."""
    anatomy_keys = ("promise", "offer", "pain_point", "solution", "social_proof", "trust_signals", "cta", "visual_hierarchy")
    return {
        "score": None,
        "motivation": "",
        "friction": [],
        "clarity": "",
        "page_anatomy": {k: "" for k in anatomy_keys},
        "page_summary": "",
        "ui_ux_notes": [],
        "testing_ideas": [],
        "above_the_fold": "",
        "below_the_fold": "",
    }


def _normalize_report(report: dict) -> dict:
    """Ensure required keys exist and types are correct. All three pages (homepage, collection, product) are always dicts."""
    if "pages" not in report:
        report["pages"] = {}
    for key in ("homepage", "collection", "product"):
        if key not in report["pages"] or report["pages"][key] is None:
            report["pages"][key] = _empty_page_dict()
        elif not isinstance(report["pages"][key], dict):
            report["pages"][key] = _empty_page_dict()
    anatomy_keys = ("promise", "offer", "pain_point", "solution", "social_proof", "trust_signals", "cta", "visual_hierarchy")
    for key in ("homepage", "collection", "product"):
        page = report["pages"].get(key)
        if isinstance(page, dict):
            for list_key in ("testing_ideas", "friction", "ui_ux_notes"):
                if list_key not in page or not isinstance(page[list_key], list):
                    page[list_key] = page.get(list_key) if isinstance(page.get(list_key), list) else []
            if key == "product":
                if "above_the_fold" not in page:
                    page["above_the_fold"] = page.get("above_the_fold") or ""
                if "below_the_fold" not in page:
                    page["below_the_fold"] = page.get("below_the_fold") or ""
            if "page_anatomy" not in page or not isinstance(page.get("page_anatomy"), dict):
                page["page_anatomy"] = page.get("page_anatomy") if isinstance(page.get("page_anatomy"), dict) else {}
            for anat_key in anatomy_keys:
                if anat_key not in page["page_anatomy"]:
                    page["page_anatomy"][anat_key] = ""
            if "page_summary" not in page:
                page["page_summary"] = page.get("page_summary") or ""
    if "overall_score" not in report:
        report["overall_score"] = 0
    if "store_name" not in report:
        report["store_name"] = "Store"
    if "executive_summary" not in report or not isinstance(report.get("executive_summary"), dict):
        report["executive_summary"] = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    for k in ("what_is_working", "what_is_hurting", "biggest_opportunity"):
        if k not in report["executive_summary"]:
            report["executive_summary"][k] = ""
    if "customer_research" not in report or not isinstance(report.get("customer_research"), dict):
        report["customer_research"] = report.get("customer_research") if isinstance(report.get("customer_research"), dict) else {}
    for k in ("target_audience_hypothesis", "customer_motivations", "customer_fears_frustrations", "desired_outcomes"):
        if k not in report["customer_research"]:
            report["customer_research"][k] = ""
    if "ugly_truth" not in report:
        report["ugly_truth"] = ""
    if "biggest_opportunity" not in report or not isinstance(report["biggest_opportunity"], dict):
        report["biggest_opportunity"] = report.get("biggest_opportunity") if isinstance(report.get("biggest_opportunity"), dict) else {}
    for k in ("title", "explanation", "why_it_matters", "example_tests"):
        if k not in report["biggest_opportunity"]:
            report["biggest_opportunity"][k] = "" if k != "example_tests" else []
    if not isinstance(report["biggest_opportunity"].get("example_tests"), list):
        report["biggest_opportunity"]["example_tests"] = report["biggest_opportunity"].get("example_tests") or []
    if "fast_wins" not in report or not isinstance(report["fast_wins"], list):
        report["fast_wins"] = report.get("fast_wins") if isinstance(report.get("fast_wins"), list) else []
    if "roadmap_90_days" not in report or not isinstance(report["roadmap_90_days"], dict):
        report["roadmap_90_days"] = report.get("roadmap_90_days") if isinstance(report.get("roadmap_90_days"), dict) else {}
    for m in ("month1", "month2", "month3"):
        if report["roadmap_90_days"].get(m) is None or not isinstance(report["roadmap_90_days"].get(m), list):
            report["roadmap_90_days"][m] = report["roadmap_90_days"].get(m) if isinstance(report["roadmap_90_days"].get(m), list) else []
    backlog = report.get("experiment_backlog") or report.get("potential_tests_backlog")
    if not isinstance(backlog, list):
        backlog = []
    report["experiment_backlog"] = backlog
    if "what_good_looks_like" not in report:
        report["what_good_looks_like"] = ""
    if "next_steps" not in report:
        report["next_steps"] = ""
    if "report_date" not in report:
        from datetime import datetime
        report["report_date"] = datetime.utcnow().strftime("%B %d, %Y")
    return report


def _mock_report(store_url: str, api_failed: bool = False) -> dict:
    """Return a minimal valid report when AI is unavailable or fails."""
    from urllib.parse import urlparse
    name = urlparse(store_url).netloc or "Store"
    name = name.replace("www.", "").split(".")[0] if name else "Store"
    if api_failed:
        motivation = "AI analysis could not be completed. Please try again or re-run the scan later."
    else:
        motivation = "AI analysis was not run. Set OPEN_AI_KEY in .env and re-run for full insights."
    anatomy_keys = ("promise", "offer", "pain_point", "solution", "social_proof", "trust_signals", "cta", "visual_hierarchy")
    empty_anatomy = {k: "" for k in anatomy_keys}
    placeholder_page = {
        "score": 0,
        "motivation": motivation,
        "friction": [],
        "clarity": "",
        "page_anatomy": empty_anatomy,
        "page_summary": "",
        "ui_ux_notes": [],
        "testing_ideas": [],
        "above_the_fold": "",
        "below_the_fold": "",
    }
    product_page = dict(placeholder_page)
    product_page["page_anatomy"] = dict(empty_anatomy)
    return _normalize_report({
        "store_url": store_url,
        "store_name": name,
        "overall_score": 0,
        "executive_summary": {"what_is_working": "", "what_is_hurting": "", "biggest_opportunity": ""},
        "customer_research": {"target_audience_hypothesis": "", "customer_motivations": "", "customer_fears_frustrations": "", "desired_outcomes": ""},
        "pages": {"homepage": dict(placeholder_page), "collection": dict(placeholder_page), "product": product_page},
        "ugly_truth": "",
        "biggest_opportunity": {"title": "", "explanation": "", "why_it_matters": "", "example_tests": []},
        "fast_wins": [],
        "roadmap_90_days": {"month1": [], "month2": [], "month3": []},
        "experiment_backlog": [],
        "what_good_looks_like": "",
        "next_steps": "",
    })
