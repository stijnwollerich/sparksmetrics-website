"""OpenAI chat completions (OpenAI Python SDK v1+)."""

from __future__ import annotations

import json
import logging
import os
import re

from openai import OpenAI

from app.cro_nurture.services import config as cn_config

_log = logging.getLogger(__name__)


def _truncate_str(s: object, max_len: int) -> str:
    t = "" if s is None else str(s).strip()
    if len(t) <= max_len:
        return t
    return t[: max(0, max_len - 1)] + "…"


def _slim_page_block(page: object, *, summary_cap: int = 380, list_cap: int = 180, list_max: int = 4) -> dict | None:
    if not isinstance(page, dict):
        return None
    out: dict = {}
    for k in ("score", "motivation", "clarity"):
        if k in page and page[k] is not None:
            v = page[k]
            out[k] = _truncate_str(v, summary_cap) if isinstance(v, str) else v
    ps = page.get("page_summary")
    if isinstance(ps, str) and ps.strip():
        out["page_summary"] = _truncate_str(ps, summary_cap)
    fr = page.get("friction")
    if isinstance(fr, list):
        out["friction"] = [_truncate_str(x, list_cap) for x in fr[:list_max]]
    ideas = page.get("testing_ideas")
    if isinstance(ideas, list):
        out["testing_ideas"] = [_truncate_str(x, list_cap) for x in ideas[:3]]
    pa = page.get("page_anatomy")
    if isinstance(pa, dict):
        out["page_anatomy"] = {str(kk): _truncate_str(vv, 140) for kk, vv in list(pa.items())[:9]}
    return out or None


def _slim_full_report_for_profile(report: dict) -> dict:
    """Structured audit excerpt for enrichment — avoids sending huge JSON to the profile model."""
    out: dict = {}
    for k in ("store_name", "overall_score", "report_date"):
        if k in report and report[k] is not None:
            out[k] = report[k]
    sc = report.get("score_components")
    if sc is not None:
        out["score_components"] = _truncate_str(sc, 280)
    ut = report.get("ugly_truth")
    if isinstance(ut, str) and ut.strip():
        out["ugly_truth"] = _truncate_str(ut, 400)
    ns = report.get("next_steps")
    if isinstance(ns, str) and ns.strip():
        out["next_steps"] = _truncate_str(ns, 450)

    ex = report.get("executive_summary")
    if isinstance(ex, dict):
        out["executive_summary"] = {
            kk: _truncate_str(vv, 500) for kk, vv in ex.items() if isinstance(vv, str) and vv.strip()
        }

    leaks = report.get("biggest_conversion_leaks")
    if isinstance(leaks, list):
        slim_leaks = []
        for item in leaks[:3]:
            if not isinstance(item, dict):
                continue
            slim_leaks.append(
                {
                    "title": _truncate_str(item.get("title"), 120),
                    "explanation": _truncate_str(item.get("explanation"), 320),
                }
            )
        if slim_leaks:
            out["biggest_conversion_leaks"] = slim_leaks

    cr = report.get("customer_research")
    if isinstance(cr, dict):
        out["customer_research"] = {
            kk: _truncate_str(vv, 400) for kk, vv in cr.items() if isinstance(vv, str) and vv.strip()
        }

    fw = report.get("fast_wins")
    if isinstance(fw, list):
        out["fast_wins"] = [_truncate_str(x, 200) for x in fw[:6]]

    bo = report.get("biggest_opportunity")
    if isinstance(bo, dict):
        out["biggest_opportunity"] = {
            "title": _truncate_str(bo.get("title"), 120),
            "explanation": _truncate_str(bo.get("explanation"), 350),
            "why_it_matters": _truncate_str(bo.get("why_it_matters"), 280),
        }

    pages = report.get("pages")
    if isinstance(pages, dict):
        slim_pages = {}
        # Order: PDP and collection before homepage — models over-index on first keys / "homepage" in prose.
        for pk in ("product", "collection", "homepage"):
            block = _slim_page_block(pages.get(pk))
            if block:
                slim_pages[pk] = block
        if slim_pages:
            out["pages"] = slim_pages

    return out


def _reduce_pages_when_oversized(slim: dict, max_json: int) -> None:
    """
    When the slim audit JSON is too large, trim full_report.pages without the old bug of
    keeping *only* homepage (which dropped PDP/collection). Prefer product (PDP), then collection, then homepage.
    """
    if len(json.dumps(slim, ensure_ascii=False)) <= max_json:
        return
    fr = slim.get("full_report")
    if not isinstance(fr, dict) or "pages" not in fr:
        return
    pgs = fr.get("pages")
    if not isinstance(pgs, dict) or not pgs:
        return

    def sz() -> int:
        return len(json.dumps(slim, ensure_ascii=False))

    # 1) Drop homepage first if PDP or collection exists — frees space without losing higher-leverage pages.
    if "homepage" in pgs and ("product" in pgs or "collection" in pgs):
        fr["pages"] = {k: v for k, v in pgs.items() if k != "homepage"}
        if sz() <= max_json:
            return
    pgs = fr.get("pages") or {}
    # 2) Drop collection if product still present
    if isinstance(pgs, dict) and "collection" in pgs and "product" in pgs:
        fr["pages"] = {k: v for k, v in pgs.items() if k != "collection"}
        if sz() <= max_json:
            return
    pgs = fr.get("pages") or {}
    # 3) Single page left: keep product over collection over homepage
    if isinstance(pgs, dict) and len(pgs) > 1:
        if "product" in pgs:
            fr["pages"] = {"product": pgs["product"]}
        elif "collection" in pgs:
            fr["pages"] = {"collection": pgs["collection"]}
        elif "homepage" in pgs:
            fr["pages"] = {"homepage": pgs["homepage"]}


def _compact_cro_scan_for_profile(cro_scan: dict | None) -> dict:
    """Top-level scan fields + slim full_report only (no raw homepage dump, no screenshot URIs)."""
    if not cro_scan or not isinstance(cro_scan, dict):
        return {}
    base: dict = {}
    for k in ("scan_status", "orders_per_month"):
        if k in cro_scan and cro_scan[k] is not None:
            base[k] = cro_scan[k]
    fr = cro_scan.get("full_report")
    if isinstance(fr, dict):
        base["full_report"] = _slim_full_report_for_profile(fr)
    return base


def _shrink_slim_audit_inplace(slim: dict, max_json: int) -> None:
    """Drop heavy full_report parts until json.dumps(slim) fits max_json (or minimal audit left)."""
    def size() -> int:
        return len(json.dumps(slim, ensure_ascii=False))

    if size() <= max_json:
        return
    fr = slim.get("full_report")
    if isinstance(fr, dict):
        _reduce_pages_when_oversized(slim, max_json)
        if size() > max_json and "executive_summary" in fr:
            fr.pop("executive_summary", None)
        if size() > max_json:
            fr.pop("customer_research", None)
        if size() > max_json:
            fr.pop("pages", None)
        if size() > max_json and isinstance(fr.get("biggest_conversion_leaks"), list):
            fr["biggest_conversion_leaks"] = fr["biggest_conversion_leaks"][:2]
        if size() > max_json and isinstance(fr.get("fast_wins"), list):
            fr["fast_wins"] = fr["fast_wins"][:3]

    # Keep trimming until under cap (one pass above is not always enough).
    while size() > max_json:
        fr = slim.get("full_report")
        if not isinstance(fr, dict):
            break
        if fr.pop("executive_summary", None) is not None:
            continue
        if fr.pop("customer_research", None) is not None:
            continue
        if fr.pop("pages", None) is not None:
            continue
        if isinstance(fr.get("biggest_conversion_leaks"), list) and len(fr["biggest_conversion_leaks"]) > 1:
            fr["biggest_conversion_leaks"] = fr["biggest_conversion_leaks"][:1]
            continue
        if fr.pop("biggest_opportunity", None) is not None:
            continue
        if isinstance(fr.get("fast_wins"), list):
            if len(fr["fast_wins"]) > 2:
                fr["fast_wins"] = fr["fast_wins"][:2]
                continue
            fr.pop("fast_wins", None)
            continue
        if fr.pop("next_steps", None) is not None:
            continue
        if fr.pop("ugly_truth", None) is not None:
            continue
        if fr.pop("score_components", None) is not None:
            continue
        if isinstance(fr.get("biggest_conversion_leaks"), list):
            fr.pop("biggest_conversion_leaks", None)
            continue
        shrunk = False
        for k, v in list(fr.items()):
            if isinstance(v, str) and len(v) > 200:
                fr[k] = v[:200] + "…"
                shrunk = True
                break
            if isinstance(v, dict):
                for kk, vv in list(v.items()):
                    if isinstance(vv, str) and len(vv) > 200:
                        v[kk] = vv[:200] + "…"
                        shrunk = True
                        break
                if shrunk:
                    break
        if shrunk:
            continue
        slim.pop("full_report", None)
        break


def _truncate_business_profile_for_email(bp: dict, *, max_chars: int) -> dict:
    """Keep business_profile JSON small for nurture email context."""
    out = dict(bp)
    for k in ("business_summary", "value_proposition_why", "tone_notes", "target_audience_guess", "industry", "business_type"):
        if isinstance(out.get(k), str):
            out[k] = _truncate_str(out[k], 420)
    for arr in ("cro_audit_themes", "hooks_for_email", "likely_offerings", "likely_products_or_services"):
        if isinstance(out.get(arr), list):
            out[arr] = [_truncate_str(x, 140) for x in (out.get(arr) or [])[:6]]
    raw = json.dumps(out, ensure_ascii=False)
    if len(raw) <= max_chars:
        return out
    for lim in (320, 240, 180):
        for k in ("business_summary", "value_proposition_why", "tone_notes", "target_audience_guess"):
            if isinstance(out.get(k), str):
                out[k] = _truncate_str(out[k], lim)
        for arr in ("cro_audit_themes", "hooks_for_email", "likely_offerings", "likely_products_or_services"):
            if isinstance(out.get(arr), list):
                out[arr] = [_truncate_str(x, 100) for x in (out.get(arr) or [])[:4]]
        raw = json.dumps(out, ensure_ascii=False)
        if len(raw) <= max_chars:
            return out
    return out


def _compact_cro_scan_for_email(cro_scan: dict | None, *, audit_max: int) -> dict:
    base = _compact_cro_scan_for_profile(cro_scan if isinstance(cro_scan, dict) else None)
    _shrink_slim_audit_inplace(base, audit_max)
    return base


def _slim_lead_for_email(lead: dict, *, audit_max: int, bp_max: int) -> dict:
    """Only fields the model needs; cro_scan_payload is condensed (not raw scan blobs)."""
    out = {
        "email": lead.get("email"),
        "first_name": lead.get("first_name"),
        "last_name": lead.get("last_name"),
        "site_url": lead.get("site_url"),
        "audit_store_name": lead.get("audit_store_name"),
        "sequence_step_order": lead.get("sequence_step_order"),
        "enrichment_status": lead.get("enrichment_status"),
    }
    tsf = lead.get("this_step_audit_focus")
    if isinstance(tsf, dict):
        out["this_step_audit_focus"] = tsf
    bp = lead.get("business_profile")
    if isinstance(bp, dict):
        out["business_profile"] = _truncate_business_profile_for_email(bp, max_chars=bp_max)
    else:
        out["business_profile"] = bp
    out["cro_scan_payload"] = _compact_cro_scan_for_email(
        lead.get("cro_scan_payload") if isinstance(lead.get("cro_scan_payload"), dict) else None,
        audit_max=audit_max,
    )
    return out


def _fit_email_json_ctx(lead: dict, instruction_prompt: str) -> dict:
    """Build {lead, step_instructions} under email_llm_input_max_chars by tightening audit + profile."""
    max_total = cn_config.email_llm_input_max_chars()
    audit_max = cn_config.email_slim_audit_json_max_chars()
    bp_max = cn_config.email_business_profile_max_chars()
    for _ in range(16):
        slim = _slim_lead_for_email(lead, audit_max=audit_max, bp_max=bp_max)
        ctx = {"lead": slim, "step_instructions": instruction_prompt}
        raw = json.dumps(ctx, ensure_ascii=False)
        if len(raw) <= max_total:
            return ctx
        audit_max = max(800, audit_max * 3 // 4)
        bp_max = max(600, bp_max * 3 // 4)
    slim = _slim_lead_for_email(lead, audit_max=max(600, audit_max), bp_max=max(500, bp_max))
    ctx = {"lead": slim, "step_instructions": instruction_prompt}
    raw = json.dumps(ctx, ensure_ascii=False)
    if len(raw) > max_total:
        _log.warning(
            "cro_nurture email context still %s chars (max %s); tighten CRO_NURTURE_EMAIL_* env or shorten step prompts",
            len(raw),
            max_total,
        )
    return ctx


def _normalize_business_profile(d: dict) -> dict:
    """Keep sequence copy working: mirror product list into likely_offerings."""
    products = d.get("likely_products_or_services")
    if isinstance(products, list) and products:
        if not d.get("likely_offerings"):
            d["likely_offerings"] = products
    return d


def _api_key() -> str:
    key = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        try:
            from flask import has_request_context, current_app

            if has_request_context():
                key = (current_app.config.get("OPEN_AI_KEY") or current_app.config.get("OPENAI_API_KEY") or "").strip()
        except Exception:
            pass
    if not key:
        raise RuntimeError("OPEN_AI_KEY or OPENAI_API_KEY is not set")
    return key


def _client() -> OpenAI:
    kwargs: dict = {"api_key": _api_key()}
    base = os.getenv("OPENAI_BASE_URL", "").strip()
    if not base:
        try:
            from flask import has_request_context, current_app

            if has_request_context():
                base = (current_app.config.get("OPENAI_BASE_URL") or "").strip()
        except Exception:
            pass
    if base:
        kwargs["base_url"] = base.rstrip("/")
    return OpenAI(**kwargs)


def _strip_json_fence(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s, re.I)
    if m:
        return m.group(1).strip()
    return s


def chat_json(messages: list, model: str, max_tokens: int = 2500, temperature: float = 0.4) -> dict:
    """Chat completion; parse assistant message as JSON."""
    response = _client().chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content
    if text is None or not str(text).strip():
        raise ValueError("OpenAI returned empty message content")
    text = _strip_json_fence(str(text))
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        _log.warning("OpenAI JSON parse failed: %s — snippet: %s", e, text[:500])
        raise


def build_business_profile(*, site_url: str, page_text: str, page_meta: dict, cro_scan: dict | None = None) -> dict:
    """
    One LLM call: summarize homepage excerpt + condensed CRO audit into a small JSON profile stored on the lead.
    Raw page text is not persisted; only the returned profile is saved.
    """
    model = cn_config.openai_model_profile()
    homepage_cap = cn_config.profile_homepage_text_max_chars()
    audit_json_cap = cn_config.profile_slim_audit_json_max_chars()
    input_cap = cn_config.profile_llm_input_max_chars()

    slim_scan = _compact_cro_scan_for_profile(cro_scan if isinstance(cro_scan, dict) else None)
    _shrink_slim_audit_inplace(slim_scan, audit_json_cap)

    system = (
        "You summarize a business for personalized sales emails. "
        "Inputs are a short homepage text excerpt and a condensed CRO audit JSON (may be partial or empty). "
        "The audit JSON may include full_report.pages.product (PDP), .collection, and .homepage—when product or collection "
        "blocks exist, they are often higher-leverage than homepage alone; reflect that in cro_audit_themes and hooks_for_email "
        "(do not only echo homepage issues). "
        "Return ONLY valid JSON. Do not invent revenue, named clients, or metrics not supported by the input. "
        "If the audit is empty, infer only from the homepage excerpt and site URL; set confidence to medium or low. "
        "Use null or empty string/array where unknown."
    )
    payload = {
        "site_url": site_url,
        "page_title": page_meta.get("title"),
        "final_url": page_meta.get("final_url"),
        "homepage_text_excerpt": _truncate_str(page_text, homepage_cap),
        "cro_audit_condensed": slim_scan,
    }
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) > input_cap:
        payload["homepage_text_excerpt"] = _truncate_str(payload.get("homepage_text_excerpt", ""), max(2000, homepage_cap // 2))
        raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) > input_cap:
        raw = raw[:input_cap]

    user = (
        "Produce JSON with keys:\n"
        "- industry (string or null): e.g. beauty, apparel, electronics, B2B SaaS.\n"
        "- business_type (string or null): e.g. DTC ecommerce, marketplace, subscription, lead-gen.\n"
        "- business_summary (1-3 sentences): what they do.\n"
        "- likely_products_or_services (array of short strings): concrete products/services you see.\n"
        "- value_proposition_why (string or null): why someone would buy from them / their differentiation if visible.\n"
        "- target_audience_guess (string or null).\n"
        "- tone_notes (string): brand voice observed (casual, luxury, clinical, playful, etc.).\n"
        "- cro_audit_themes (array of 3-6 short strings): main issues or opportunities from the audit JSON, "
        "or honest gaps if audit is thin. Include PDP/collection angles when pages.product or pages.collection exist.\n"
        "- hooks_for_email (array of 3-5 short strings): specific angles for outreach tied to audit + site; "
        "vary across homepage vs collection vs product when the audit has multiple page blocks.\n"
        "- confidence (string): high|medium|low."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": raw},
        {"role": "user", "content": user},
    ]
    out = chat_json(messages, model=model, max_tokens=1600, temperature=0.3)
    if not isinstance(out, dict):
        raise ValueError("business profile model returned non-object JSON")
    return _normalize_business_profile(out)


def generate_step_email(
    *,
    instruction_prompt: str,
    lead: dict,
    unsubscribe_url: str,
    model: str | None = None,
) -> dict:
    """
    Generate one nurture email. ``lead`` may include full ``cro_scan_payload``; it is condensed
    (same slim audit as enrichment + caps) before the API call so input tokens stay bounded.
    """
    _ = unsubscribe_url  # appended server-side after signature; do not put in model context
    model = model or cn_config.openai_model_email()
    system = (
        "You write nurture emails as Stijn from Sparksmetrics — short, conversational, like you typed it yourself "
        "(not a marketing blast).\n\n"
        "Voice — personal review, not “the report” (except email 10 — see below):\n"
        "- Frame everything as *your* take after looking at their store yourself: “when I went through your site”, "
        "“what stood out to me”, “in my review”. "
        "- Do **not** sound like the PDF or scan is the sender: avoid phrases like “the report says”, “according to the scan”, "
        "“the audit document found”, or “as stated in your CRO report”. You can still use scan JSON for facts—just phrase it "
        "as your own observation.\n"
        "- If lead.sequence_step_order is 10, do not discuss their site, scan, homepage, PDP, leaks, or clarity—write a "
        "warm closing email only; ignore cro_scan_payload for body content.\n\n"
        "AIDA (keep it light, not textbook):\n"
        "- Attention: right after the greeting, open with something that earns the next sentence—curiosity, a useful pattern, "
        "a sharp question, or a concrete audit angle. No throat-clearing.\n"
        "- Interest / Desire: teach a little; use specifics from their audit or business_profile so it feels relevant.\n"
        "- Action: one soft CTA at the end, per step_instructions.\n\n"
        "Openings — every email must feel different; do NOT rinse-repeat:\n"
        "- Avoid defaulting to “I saw on your site…”, “on your site…”, “when I looked at your website…”, "
        "“browsing your store…”, “noticed on your homepage…”. Those sound robotic when every email starts that way. "
        "If something site-specific is essential, say it later or rephrase fresh.\n"
        "- Often lead with the idea, pattern, or audit point first—then tie to them. Sometimes lead with industry truth, "
        "sometimes with a question, sometimes with a single line from the scan—vary by sequence_step_order.\n"
        "- They already know their brand; do not open with “which specializes in…” or a brochure recap of what they sell.\n\n"
        "Greeting: one line — Hi + first_name when lead.first_name is non-empty; otherwise Hi there. "
        "Do not use “Hi team” unless first_name is missing.\n"
        "When lead.this_step_audit_focus is present: treat it as **this step’s assigned scan angle** (rotating through "
        "distinct signals). Subject and body must primarily reflect its label + detail; avoid reusing the same subject "
        "pattern or buzzword as other steps. For sequence_step_order 9, still follow step_instructions for the "
        "“scale like [leader]” subject rule.\n"
        "Body: mostly short <p> paragraphs; optional short list only if it fits. Sound like a peer, not a template.\n\n"
        "Facts: use ONLY JSON lead — site_url, first_name, audit_store_name (if present), cro_scan_payload, business_profile, "
        "sequence_step_order. Prefer industry, cro_audit_themes, hooks_for_email, value_proposition_why for relevance; "
        "use cro_scan_payload for page-level detail. "
        "full_report.pages may include product (PDP), collection, and homepage—use PDP/collection friction and testing_ideas when "
        "present; they often matter as much as or more than homepage. Do not make every email about the homepage unless the "
        "step_instructions require it; vary the page you emphasize across the sequence.\n"
        "Do not invent revenue, named clients, or metrics.\n"
        "Follow step_instructions for length and CTA strength. If step_instructions describe a **fixed** YouTube video, "
        "your body must match **that** video’s topic (e.g. audit walkthrough vs generic tips)—do not invent a different theme.\n\n"
        "Subject (field subject):\n"
        "- Lowercase letters, digits, spaces only.\n"
        "- **Short for inbox preview**: aim **≤ 45 characters** (about **4–6 words**). Cut filler words.\n"
        "- Make it about **their** situation: use audit_store_name if present, or industry, product niche, or one concrete "
        "audit theme—not generic “cro tips” or “after your scan”.\n"
        "- Do not reuse the same subject pattern as a previous step would.\n\n"
        "HTML (field html): plain structure only — <p>, optional <ul>/<ol>/<li>, and <a href=\"...\">. "
        "Plain text inside tags only (no bold/italic markup): do not use <strong>, <em>, <b>, <i>, <u>, <span>, <div>, "
        "<font>, <br>, headings, or <table>. Use several <p> paragraphs instead of line breaks. "
        "Do not add style=, class=, colors, font sizes, or layout attributes — the app forces client-default typography; "
        "anything else is stripped.\n"
        "Plain text (field text): same content, no HTML.\n\n"
        "Do NOT add closings or signatures; no unsubscribe link. The app appends signature + unsubscribe.\n\n"
        "Return ONLY valid JSON with keys: subject, html, text."
    )
    ctx = _fit_email_json_ctx(lead, instruction_prompt)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    out = chat_json(
        messages,
        model=model,
        max_tokens=cn_config.openai_email_max_completion_tokens(),
        temperature=0.72,
    )
    for k in ("subject", "html", "text"):
        if k not in out:
            raise ValueError(f"model output missing {k}")
    return out
