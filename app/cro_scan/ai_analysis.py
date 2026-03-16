"""Run AI (OpenAI vision) on store screenshots and return structured report JSON."""
from __future__ import annotations

import base64
import json
import re
import struct
from urllib.parse import quote

from flask import current_app

# Min dimensions to treat as a real screenshot (not thum.io "Image not authorized" etc.)
MIN_SCREENSHOT_WIDTH = 380
MIN_SCREENSHOT_HEIGHT = 400


def _image_dimensions_from_bytes(raw: bytes) -> tuple[int, int] | None:
    """Return (width, height) from PNG, JPEG, or WebP bytes, or None if unreadable."""
    if not raw or len(raw) < 24:
        return None
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            w, h = struct.unpack(">II", raw[16:24])
            return (w, h)
        except Exception:
            return None
    if raw[:2] == b"\xff\xd8":
        i = 2
        while i < len(raw) - 9:
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            i += 2
            if marker == 0xC0 or marker == 0xC1 or marker == 0xC2:
                try:
                    h, w = struct.unpack(">HH", raw[i + 5 : i + 9])
                    return (w, h)
                except Exception:
                    return None
            if marker == 0xD9 or marker == 0xDA:
                break
            try:
                length = struct.unpack(">H", raw[i : i + 2])[0]
                i += 2 + length
            except Exception:
                break
    # WebP: RIFF....WEBP then VP8X chunk. Payload (at 20): 1b flags, 3b reserved, 3b width-1 LE, 3b height-1 LE.
    if len(raw) >= 30 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        try:
            w = 1 + (raw[24] | (raw[25] << 8) | (raw[26] << 16))
            h = 1 + (raw[27] | (raw[28] << 8) | (raw[29] << 16))
            if 0 < w <= 10000 and 0 < h <= 10000:
                return (w, h)
        except Exception:
            pass
    return None


REPORT_JSON_SCHEMA = """
Return a single JSON object (no markdown, no code fence). Only describe what you see. Do not invent metrics. Tailor to brand (e.g. no countdown timers for premium). Be specific to this site—reference actual buttons, copy, and layout; avoid generic phrasing.
{
  "store_name": "<brand name>",
  "overall_score": <0-100>,
  "score_components": "<Short line explaining how the score is derived, e.g. 'Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability.'>",
  "biggest_conversion_leaks": [
    { "title": "<Short leak name, e.g. Product differentiation is unclear>", "explanation": "<1-2 sentences. Reference exact UI where possible; e.g. Visitors do not immediately understand why [product] is better than [alternative].>" },
    { "title": "...", "explanation": "..." },
    { "title": "...", "explanation": "..." }
  ],
  "executive_summary": {
    "what_is_working": "<2-4 sentences. Synthesize across all three pages; reference specific elements.>",
    "what_is_hurting": "<2-4 sentences. Include collection and product issues; name what you see.>",
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
      "page_anatomy": { "promise": "<Status>: <explanation>. Status: Present, Good, Weak, or Missing. For pain_point: if no explicit pain copy, reframe as missing benefit/differentiation (e.g. why this product vs alternatives).>", "offer": "...", "pain_point": "...", "solution": "...", "social_proof": "...", "trust_signals": "...", "cta": "...", "visual_hierarchy": "..." },
      "motivation": "...", "clarity": "...",
      "friction": ["<CRO or UI/UX issue; reference specific UI when possible>", ...],
      "page_summary": "<Short paragraph: reference what you see; conversion and UX weakness>",
      "ui_ux_notes": ["<2-5 specific observations: name elements, hierarchy, readability, mobile>", ...],
      "testing_ideas": ["<2-4 ecommerce-specific ideas: lifestyle imagery, size reference, bundles, comparison, endorsements—not only generic 'add testimonials'>", ...]
    },
    "collection": { "score": <0-100>, "page_anatomy": {...}, "motivation": "...", "clarity": "...", "friction": [], "page_summary": "...", "ui_ux_notes": [], "testing_ideas": [] },
    "product": { "score": <0-100>, "above_the_fold": "<optional>", "below_the_fold": "<optional>", "page_anatomy": {...}, "motivation": "...", "clarity": "...", "friction": [], "page_summary": "...", "ui_ux_notes": [], "testing_ideas": [] }
  },
  "ugly_truth": "<One direct, memorable sentence—biggest strategic weakness. Not soft or polite; e.g. site looks premium but does not justify the price, so visitors will compare elsewhere.>",
  "biggest_opportunity": { "title": "...", "explanation": "...", "why_it_matters": "...", "example_tests": [] },
  "fast_wins": ["<3-5 quick improvements; specific to this site. Prefer value, trust, clarity, offer—not generic 'test button color' or 'test CTA'>", ...],
  "roadmap_90_days": { "month1": ["<concrete actionable item, e.g. Increase CTA contrast across PDPs; Add trust badges under Add to Cart; Break product descriptions into bullet benefits>", ...], "month2": [...], "month3": [...] },
  "experiment_backlog": ["<10 A/B tests; ecommerce-specific (e.g. Test 'recommended by dermatologists' above hero; Test before/after visual; Test comparison vs traditional product; Test bundle offers). Not generic 'test CTA positioning' or 'test lifestyle imagery'>", ...],
  "what_good_looks_like": "<What high-converting, good-UX pages include>",
  "next_steps": "<Summary of recommended actions>"
}
Rules: biggest_conversion_leaks: exactly 3 items. Each title is a short leak name; explanation references what you see (e.g. "The Add to Cart button blends with the interface and competes with other UI elements"). score_components: one short line (e.g. "Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability."). page_anatomy: each value must start with Present, Good, Weak, or Missing—then ": "—then explanation. For pain_point: do NOT say "Missing: homepage does not address health frustrations". Reframe as differentiation: "Missing: Homepage focuses on lifestyle imagery but does not quickly explain why this [product] is better than a standard [alternative]." ugly_truth: bold, not polite; create urgency (e.g. "The site looks premium but does not explain why the product is worth the price. Many visitors will compare alternatives before purchasing."). When describing issues use UI-specific language: name the exact element (Add to Cart button, Shop Pay button, product description), its problem (blends with palette, uses similar color to surrounding UI), and what should be true (primary action should visually dominate). Roadmap: actionable bullets (Increase CTA contrast across PDPs; Add trust badges under Add to Cart), not vague ("Begin integrating testimonials"). testing_ideas and experiment_backlog: ecommerce-specific experiments (Test "recommended by X" above hero; Test before/after visual; Test comparison vs traditional; Test bundle offers with replacement parts). Scores: conservative; when in doubt score lower. Include all required keys. If page missing use null. Keep concise but specific.
"""


def _fetch_image_as_base64(url: str, timeout: int = 50, retries: int = 2) -> str | None:
    """Download image from URL and return as data URL. Retries on timeout or failure."""
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


def _fetch_screenshot_browserless(
    page_url: str, token: str, timeout: int = 90, retries: int = 2
) -> tuple[str | None, bool]:
    """Fetch full-page screenshot via Browserless /unblock (bypass). Returns (data_uri, is_valid)."""
    import requests
    api_url = "https://production-sfo.browserless.io/unblock"
    payload = {
        "url": page_url,
        "content": False,
        "cookies": False,
        "screenshot": True,
        "browserWSEndpoint": False,
    }
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            r = requests.post(
                f"{api_url}?token={quote(token, safe='')}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            b64 = (data.get("screenshot") or "").strip()
            if not b64:
                current_app.logger.info("CRO scan: Browserless returned no screenshot for %s", page_url[:50])
                continue
            raw = base64.standard_b64decode(b64)
            dims = _image_dimensions_from_bytes(raw)
            if dims:
                w, h = dims
                if w < MIN_SCREENSHOT_WIDTH or h < MIN_SCREENSHOT_HEIGHT:
                    current_app.logger.info(
                        "CRO scan: Browserless image too small (%sx%s): %s", w, h, page_url[:50]
                    )
                    return None, False
            elif len(raw) < 12000:
                # Accept from 12KB up when dimensions unreadable (e.g. some WebP); ~17KB real screenshots were wrongly rejected at 30KB
                current_app.logger.info(
                    "CRO scan: Browserless image too small (%s bytes), skipping: %s", len(raw), page_url[:50]
                )
                continue
            else:
                current_app.logger.debug(
                    "CRO scan: Browserless image %s KB, dimensions unreadable (e.g. WebP variant), accepting: %s",
                    round(len(raw) / 1024, 1), page_url[:50],
                )
            mime = "image/webp" if raw[8:12] == b"WEBP" else "image/png"
            return f"data:{mime};base64,{b64}", True
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                current_app.logger.info("CRO scan: Browserless retry %s for %s", attempt + 2, page_url[:50])
    if last_error:
        current_app.logger.warning("CRO scan: Browserless failed for %s: %s", page_url[:50], last_error)
    return None, False


def _fetch_and_validate_screenshot(
    url: str, timeout: int = 50, retries: int = 2
) -> tuple[str | None, bool]:
    """Fetch image; return (data_uri, is_valid). Valid = real screenshot dimensions, not thum.io error image."""
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
            dims = _image_dimensions_from_bytes(raw)
            if not dims:
                current_app.logger.info("CRO scan: could not read image dimensions for %s", url[:50])
                return None, False
            w, h = dims
            if w < MIN_SCREENSHOT_WIDTH or h < MIN_SCREENSHOT_HEIGHT:
                current_app.logger.info(
                    "CRO scan: image too small (%sx%s), likely error image: %s", w, h, url[:50]
                )
                return None, False
            ct = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            if ct not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                ct = "image/png"
            b64 = base64.standard_b64encode(raw).decode("ascii")
            return f"data:{ct};base64,{b64}", True
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                current_app.logger.info("CRO scan: retry %s for image (attempt %s)", attempt + 2, url[:50])
    if last_error:
        current_app.logger.warning("CRO scan: failed to fetch image %s: %s", url[:60], last_error)
    return None, False


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


def _is_challenge_page(data_uri: str, api_key: str, timeout: int = 15) -> bool:
    """Return True if the image shows a CAPTCHA, Cloudflare challenge, or similar bot-blocking page."""
    prompt = (
        "Does this screenshot show a CAPTCHA, 'Checking your browser', 'Just a moment', "
        "Cloudflare challenge, 'Access denied', 'Please complete the security check', "
        "or any other bot/challenge page instead of real website content? Reply with only YES or NO."
    )
    try:
        resp = _call_openai_vision([data_uri], prompt, api_key, model="gpt-4o-mini", timeout=timeout)
        raw = (resp.get("raw") or "").strip().upper()
        return "YES" in raw[:10]
    except Exception as e:
        current_app.logger.info("CRO scan: challenge check failed (treating as valid): %s", e)
        return False


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

    keys_in_order = ("homepage", "collection", "product")
    browserless_token = (current_app.config.get("BROWSERLESS_API_TOKEN") or "").strip()
    scrapfly_key = (current_app.config.get("SCRAPFLY_API_KEY") or "").strip()
    # Fetch each screenshot and validate dimensions (skip thum.io "Image not authorized" etc.)
    valid_screenshots: dict[str, str] = {}
    for key in keys_in_order:
        url = (screenshot_urls.get(key) or "").strip()
        if not url:
            continue
        if url.startswith("data:"):
            valid_screenshots[key] = url
            continue
        # Browserless (bypass) takes precedence; then Scrapfly; then thum.io GET
        if browserless_token and "image.thum.io" not in url:
            data_uri, is_valid = _fetch_screenshot_browserless(url, browserless_token, timeout=90, retries=2)
        elif scrapfly_key and "image.thum.io" not in url:
            from app.cro_scan.screenshots import scrapfly_screenshot_api_url
            fetch_url = scrapfly_screenshot_api_url(url, scrapfly_key)
            data_uri, is_valid = _fetch_and_validate_screenshot(fetch_url, timeout=70, retries=2)
        else:
            data_uri, is_valid = _fetch_and_validate_screenshot(url, timeout=50, retries=2)
        if is_valid and data_uri:
            valid_screenshots[key] = data_uri

    # Exclude screenshots that are Cloudflare/captcha challenge pages (not the real store).
    # Skip this when we used Browserless (already bypasses Cloudflare; avoids false positives).
    if not browserless_token:
        for key in list(valid_screenshots.keys()):
            if _is_challenge_page(valid_screenshots[key], api_key):
                current_app.logger.info("CRO scan: excluding %s screenshot (challenge/captcha page detected)", key)
                del valid_screenshots[key]

    # Build ordered image list and mapping for prompt (only pages that passed)
    image_payloads: list[str] = []
    keys_passed: list[str] = []
    for key in keys_in_order:
        if key in valid_screenshots:
            image_payloads.append(valid_screenshots[key])
            keys_passed.append(key)

    if not image_payloads:
        current_app.logger.warning(
            "CRO scan: no valid screenshots after filtering (thum.io error images or challenge pages)"
        )
        return _mock_report(store_url, api_failed=True)

    # Tell the AI which image is which page and which pages have no screenshot
    page_labels = {"homepage": "HOMEPAGE", "collection": "COLLECTION", "product": "PRODUCT"}
    image_mapping = " ".join(
        f"Image {i + 1} is the {page_labels[k]}." for i, k in enumerate(keys_passed)
    )
    missing = [page_labels[k] for k in keys_in_order if k not in valid_screenshots]
    missing_phrase = (
        f" No screenshot was provided for: {', '.join(missing)} (unavailable, e.g. bot protection)."
        if missing
        else ""
    )

    prompt = f"""You are an expert in both conversion rate optimization (CRO) and UI/UX for e-commerce. Your audit should combine:
- **CRO lens**: conversion intent, value clarity, trust and social proof, CTAs, page anatomy (promise, offer, pain point, solution, etc.), and friction that blocks purchase.
- **UI/UX lens**: visual hierarchy and scannability, readability (type size, contrast, line length), consistency (patterns, spacing, alignment), mobile usability (tap targets, thumb reach, clear next step), and perceived complexity. Call out when layout or interaction design hurts clarity or trust.

**Prioritization**: Design is important and can be wrong—call that out when it is (e.g. poor hierarchy, unreadable text, confusing layout). But **information and clarity usually matter more than design alone**. Prioritize recommendations that (1) **raise perceived value**: USPs, benefits, how compelling the offer and store feel (not just product catalog but how good they make the offer seem), and (2) **lower risk**: guarantees, social proof, trust signals, clear policies. Simple design tweaks (e.g. changing colors, minor styling) are easy but often low benefit—mention them only when design is clearly wrong or hurting conversion. Lead with clarity, motivation, and risk reduction; treat pure cosmetic design as secondary unless it is genuinely broken.

**Specificity and tone (critical)**: The report should feel like a $500 expert audit, not a generic template. The reader should think "they really understood my site."
- **Reference the actual UI—never generic**: A CRO expert always references exact things on the page. Bad: "The CTA lacks prominence." Good: "The Add to Cart button blends into the design palette; it uses a similar color to surrounding UI elements; the primary action does not visually dominate the page." Name specific elements (Add to Cart, Shop Pay, product description block), what is wrong (blends with beige, dense paragraph), and competing elements (e.g. Shop Pay button draws more attention than Add to Cart). Where useful, use a "spotted in screenshot" style: "Issue: Add to Cart button blends with surrounding color. Competing element: Shop Pay button draws more attention. Primary action should visually dominate."
- **Differentiation, not pain-point checklist**: Most ecommerce sites do not explicitly state "pain points". Do NOT write things like "Missing: The homepage does not clearly address potential health frustrations regarding air quality." Instead reframe as differentiation: "The homepage focuses on lifestyle imagery but does not quickly explain why this humidifier is better than a standard one." Or: "Missing: Page does not highlight why [product] beats [alternative] (e.g. benefits)."
- **Bold tone, create urgency**: Avoid polite, forgettable language. Bad: "The site could benefit from clearer product differentiation." Good: "The site looks premium, but it does not clearly explain why the product is worth the price. Many visitors will compare alternatives before purchasing." Ugly truth and biggest leaks should feel direct and create urgency.
- **Testing ideas—ecommerce-specific, not blog advice**: Avoid generic "A/B test CTA positioning" or "Test lifestyle imagery." Prefer experiments that feel like real CRO thinking: e.g. "Test showing 'recommended by dermatologists' above the hero", "Test a before/after air quality visual", "Test comparison vs traditional humidifiers", "Test bundle offers with replacement filters". Product-specific, trust-specific, differentiation-specific.
- **Roadmap—actionable, not vague**: Bad: "Begin integrating testimonials." Good: "Increase CTA contrast across PDPs", "Add trust badges under Add to Cart", "Break product descriptions into bullet benefits." Each item should be a concrete action someone can execute.
- **Score components**: Output score_components as one short line so the number does not feel arbitrary, e.g. "Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability."
- **Three biggest conversion leaks**: Output exactly 3 items in biggest_conversion_leaks. Each has a short title (e.g. "Product differentiation is unclear", "Primary CTA lacks visual dominance") and an explanation that references what you see (e.g. "The Add to Cart button blends with the interface and competes with other UI elements"). This section makes the report feel much smarter.
- **Scores**: Be conservative; when in doubt score lower so the reader is motivated to improve.

Analyze only what you see in these mobile screenshots. Do not invent metrics or funnel data. Tailor every recommendation to the brand: no countdown timers or heavy discount urgency for premium/luxury sites; suggest tactics that fit (e.g. quality, trust, real scarcity). Be accurate and specific, not generic.

{image_mapping}.{missing_phrase} For any page without a screenshot, set page_summary to note that the screenshot was unavailable (e.g. site may use bot protection) and leave other fields minimal.

Important: The executive_summary must synthesize findings across all pages that have screenshots (and note if any page was unavailable). Do not write it as if only the homepage was analyzed—mention collection and product page strengths and issues where relevant. Weave in both conversion and UI/UX where they matter (e.g. "Product page has strong social proof but dense copy and small tap targets hurt mobile conversion").

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
        # Parse JSON: use first valid object if model returned "Extra data" (trailing text or second JSON)
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as e:
            if "Extra data" in str(e):
                decoder = json.JSONDecoder()
                report, _ = decoder.raw_decode(raw)
            else:
                raise
        report["store_url"] = store_url
        for key, data_uri in valid_screenshots.items():
            if report.get("pages") and isinstance(report["pages"].get(key), dict):
                report["pages"][key]["screenshot_data_uri"] = data_uri
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
    if "score_components" not in report or not isinstance(report.get("score_components"), str):
        report["score_components"] = (report.get("score_components") or "Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability.") if isinstance(report.get("score_components"), str) else "Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability."
    if "biggest_conversion_leaks" not in report or not isinstance(report.get("biggest_conversion_leaks"), list):
        report["biggest_conversion_leaks"] = report.get("biggest_conversion_leaks") if isinstance(report.get("biggest_conversion_leaks"), list) else []
    for i, leak in enumerate(report["biggest_conversion_leaks"]):
        if not isinstance(leak, dict):
            report["biggest_conversion_leaks"][i] = {"title": "", "explanation": ""}
        else:
            if "title" not in leak:
                leak["title"] = ""
            if "explanation" not in leak:
                leak["explanation"] = ""
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
