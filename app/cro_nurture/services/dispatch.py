"""Generate and send due sequence emails."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

from flask import current_app
from itsdangerous import URLSafeTimedSerializer

from app.models import db
from app.cro_nurture.models import CroNurtureEmailSend, CroNurtureLead, CroNurtureSequence, CroNurtureSequenceStep
from app.cro_nurture.lead_flags import clear_instant_test_flag, lead_skip_sequence_delays
from app.cro_nurture.scan_schedule import effective_delay_seconds
from app.cro_nurture.services import config as cn_config
from app.cro_nurture.services import brevo_send, openai_llm


def _unsub_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="cro-nurture-unsub-v1")


def unsubscribe_token_for_lead(lead_id: int) -> str:
    return _unsub_serializer().dumps({"i": lead_id})


def unsubscribe_url_for_lead(lead_id: int) -> str:
    base = cn_config.app_base_url()
    token = unsubscribe_token_for_lead(lead_id)
    if not base:
        return f"/cro-nurture/unsubscribe/{token}"
    return f"{base}/cro-nurture/unsubscribe/{token}"


# Model output is stripped of these before inject/footer so a hallucinated comment cannot skip the real blocks.
_PHANTOM_NURTURE_COMMENT_RE = re.compile(
    r"<!--\s*nurture:(?:signature-block|media:\d+)\s*-->",
    re.I,
)


def _strip_phantom_nurture_comments(fragment: str) -> str:
    return _PHANTOM_NURTURE_COMMENT_RE.sub("", fragment or "")


def _html_has_signature_logo_img(fragment: str) -> bool:
    """True only when an <img> points at our logo — not plain text mentioning the filename (old false positive)."""
    for m in re.finditer(r"<img\s[\s\S]*?>", fragment or "", re.I):
        if "signature-logo-name.png" in m.group(0):
            return True
    return False


def _strip_html_presentation_attrs(fragment: str) -> str:
    """Remove inline styles / presentation attrs so the message follows the client default font and colors."""
    if not fragment:
        return fragment or ""
    h = fragment
    h = re.sub(r"\s+style\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+style\s*=\s*'[^']*'", "", h, flags=re.I)
    h = re.sub(r"\s+class\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+class\s*=\s*'[^']*'", "", h, flags=re.I)
    h = re.sub(r"\s+bgcolor\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+bgcolor\s*=\s*'[^']*'", "", h, flags=re.I)
    h = re.sub(r"\s+color\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+color\s*=\s*'[^']*'", "", h, flags=re.I)
    h = re.sub(r"\s+face\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+align\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+align\s*=\s*'[^']*'", "", h, flags=re.I)
    h = re.sub(r"\s+valign\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+dir\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+id\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+title\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"\s+data-[a-z0-9_-]+\s*=\s*\"[^\"]*\"", "", h, flags=re.I)
    h = re.sub(r"<hr\s*/?\s*>", "", h, flags=re.I)
    return h


def _normalize_nurture_html_body(fragment: str) -> str:
    """
    One pipeline for all 10 steps: no custom fonts/colors/sizes from model or injected blocks.
    Strips presentation markup; unwraps emphasis/wrapper tags; keeps only minimal <a>/<img> attrs.
    """
    h = _strip_html_presentation_attrs(fragment or "")
    h = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", h, flags=re.I)
    h = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", h, flags=re.I)
    # Outlook / Word cruft that changes how the “first block” renders
    h = re.sub(r"<!--\[if[\s\S]*?<!\[endif\]-->", "", h, flags=re.I)
    h = re.sub(r"</?(?:table|tbody|thead|tfoot|tr|td|th|caption)[^>]*>", "", h, flags=re.I)
    h = re.sub(r"</?center[^>]*>", "", h, flags=re.I)
    h = re.sub(r"</?o:[^>]*>", "", h, flags=re.I)
    h = re.sub(r"</?w:[^>]*>", "", h, flags=re.I)

    for _ in range(12):
        for tag in ("span", "font"):
            h = re.sub(rf"<{tag}[^>]*>", "", h, flags=re.I)
            h = re.sub(rf"</{tag}>", "", h, flags=re.I)
        # Must not use <i[^>]*> — that matches the whole <img ...> tag (second char of "img" is i).
        for tag in ("strong", "em", "b", "i", "u"):
            h = re.sub(rf"<{tag}(?:\s[^>]*)?>", "", h, flags=re.I)
            h = re.sub(rf"</{tag}>", "", h, flags=re.I)

    h = re.sub(r"<div[^>]*>", "<p>", h, flags=re.I)
    h = re.sub(r"</div>", "</p>", h, flags=re.I)
    h = re.sub(r"<blockquote[^>]*>", "<p>", h, flags=re.I)
    h = re.sub(r"</blockquote>", "</p>", h, flags=re.I)
    h = re.sub(r"<h[1-6][^>]*>", "<p>", h, flags=re.I)
    h = re.sub(r"</h[1-6]>", "</p>", h, flags=re.I)
    h = re.sub(r"<br\s*/?>", " ", h, flags=re.I)

    for t in ("p", "ul", "ol", "li"):
        h = re.sub(rf"<{t}(\s[^>]*)?>", f"<{t}>", h, flags=re.I)

    def _a_open(m: re.Match) -> str:
        inner = m.group(1) or ""
        hm = re.search(r"href\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", inner, re.I)
        if not hm:
            return "<a>"
        return f"<a href={hm.group(1)}>"

    h = re.sub(r"<a\s+([^>]*)>", _a_open, h, flags=re.I)

    def _img_open(m: re.Match) -> str:
        inner = m.group(1) or ""
        sm = re.search(r"src\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", inner, re.I)
        if not sm:
            return ""
        parts = [f"src={sm.group(1)}"]
        for attr in ("width", "height", "alt"):
            am = re.search(rf"{attr}\s*=\s*(\"[^\"]*\"|'[^']*')", inner, re.I)
            if am:
                parts.append(f"{attr}={am.group(1)}")
        return "<img " + " ".join(parts) + ">"

    # Match <img ...> even when attributes span lines (some clients break tags oddly).
    h = re.sub(r"<img\s+([\s\S]*?)>", _img_open, h, flags=re.I)

    return h


def _closing_and_signature_html() -> str:
    """Closing lines + signature — plain HTML, client default typography (no bold/inline styles)."""
    origin = cn_config.email_static_asset_origin()
    logo = f"{origin}/static/images/signature-logo-name.png"
    # quote=False: escape & < > for attribute text; avoid quote=True mangling edge-case URLs.
    he_logo = html.escape(logo, quote=False)
    return (
        "<p>If there's anything I can help with, let me know.</p>"
        "<p>Thanks,</p>"
        f'<p><a href="https://sparksmetrics.com/">'
        f'<img src="{he_logo}" width="195" height="40" alt="Sparksmetrics"></a></p>'
        "<p>Stijn Wollerich</p>"
    )


def _signature_links_row_html(unsubscribe_url: str | None) -> str:
    """One line: site · book · unsub — avoids extra vertical gap between separate <p> blocks."""
    bits = [
        '<a href="https://sparksmetrics.com/">sparksmetrics.com</a>',
        '<a href="https://sparksmetrics.com/schedule-a-call/">Book a call</a>',
    ]
    if unsubscribe_url:
        href = html.escape(unsubscribe_url, quote=True)
        bits.append(f'<a href="{href}">Unsubscribe</a>')
    return "<p>" + " · ".join(bits) + "</p>"


def _strip_model_unsubscribe_html(fragment: str, url: str) -> str:
    if not fragment or not url:
        return fragment or ""
    for u in dict.fromkeys((url, url.replace("&", "&amp;"))):
        if not u:
            continue
        esc = re.escape(u)
        fragment = re.sub(
            r'<p[^>]*>\s*<a[^>]+href=["\']' + esc + r'["\'][^>]*>[\s\S]*?</a>\s*</p>',
            "",
            fragment,
            flags=re.I,
        )
    fragment = re.sub(
        r'<p[^>]*>\s*<a[^>]+href=["\'][^"\']*cro-nurture/unsubscribe[^"\']*["\'][^>]*>[\s\S]*?</a>\s*</p>',
        "",
        fragment,
        flags=re.I,
    )
    return fragment


def _strip_placeholder_signoff_html(fragment: str) -> str:
    h = fragment
    h = re.sub(
        r'(?:<p[^>]*>\s*best\s*,?\s*</p>\s*)?<p[^>]*>\s*your\s+name\s*</p>\s*$',
        "",
        h,
        flags=re.I | re.S,
    )
    h = re.sub(r'<p[^>]*>\s*best\s*,?\s*</p>\s*$', "", h, flags=re.I | re.S)
    h = re.sub(r'<p[^>]*>\s*best\s+regards[^<]*</p>\s*$', "", h, flags=re.I | re.S)
    return h


def _normalize_nurture_subject(raw: str) -> str:
    """Lowercase subject, short enough for typical inbox preview (mobile ~35–50 chars)."""
    s = (raw or "").strip().lower()
    if s in (
        "quick thoughts after your scan",
        "quick thought after your scan",
        "quick thoughts on your scan",
    ):
        s = "one angle from your scan worth a look"
    max_preview = 48
    if len(s) > max_preview:
        cut = s[:max_preview]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        s = cut.rstrip(" —–-,.;:")
    if not s:
        s = "your scan + one idea"
    return s[:998]


def _strip_placeholder_signoff_text(text: str) -> str:
    lines = [ln for ln in (text or "").strip().split("\n")]
    while lines:
        last = lines[-1].strip()
        if re.match(r"^(best|thanks|cheers|sincerely)\s*,?\s*$", last, re.I):
            lines.pop()
            continue
        if re.match(r"^your\s+name\s*$", last, re.I):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _strip_unsubscribe_lines_text(text: str, url: str) -> str:
    if not text or not url:
        return text or ""
    out = []
    for line in text.split("\n"):
        if url in line:
            continue
        if re.match(r"^\s*unsubscribe\s*:", line, re.I):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _append_plaintext_signature_block(text: str, url: str) -> str | None:
    if not url:
        return text.strip() if text and text.strip() else None
    base = (text or "").strip()
    base = _strip_unsubscribe_lines_text(base, url)
    base = _strip_placeholder_signoff_text(base)
    footer = (
        "\n\nIf there's anything I can help with, let me know.\n\n"
        "Thanks,\n"
        "Stijn Wollerich\n"
        "sparksmetrics.com · Book a call: https://sparksmetrics.com/schedule-a-call/ · "
        f"Unsubscribe: {url}"
    )
    return (base + footer).strip() if base else footer.strip()


def _ensure_email_footer(html: str, url: str) -> str:
    """
    Body (from model) → optional strip model unsub/sign-off → strip presentation attrs → signature → Unsubscribe.
    """
    html = _strip_phantom_nurture_comments(html or "")
    if not url:
        html = _strip_placeholder_signoff_html(html)
        html = _normalize_nurture_html_body(html)
        if not _html_has_signature_logo_img(html):
            html = html + _closing_and_signature_html()
            html = html + _signature_links_row_html(None)
        return html
    html = _strip_model_unsubscribe_html(html, url)
    html = _strip_placeholder_signoff_html(html)
    html = _normalize_nurture_html_body(html)
    if not _html_has_signature_logo_img(html):
        html = html + _closing_and_signature_html()
    html = html + _signature_links_row_html(url)
    html = _normalize_nurture_html_body(html)
    return html


def _public_site_base() -> str:
    """Absolute origin for static image URLs in outbound email (falls back to production)."""
    b = (cn_config.app_base_url() or "").strip().rstrip("/")
    return b if b else "https://sparksmetrics.com"


def _inject_nurture_media_blocks(fragment: str, step_order: int) -> str:
    """
    Append fixed video/screenshot/link HTML for specific steps (after model body, before signature).
    Idempotent via HTML comment marker. Step 4: 90-day ROI page link. Step 10: ROI page + schedule-a-call (7-day window).

    Image paths are under Flask ``app/static/images/...`` so ``/static/images/...`` is reachable in production.
    """
    fragment = _strip_phantom_nurture_comments(fragment or "")
    marker = f"<!-- nurture:media:{step_order} -->"
    if marker in fragment:
        return fragment

    static_origin = cn_config.email_static_asset_origin()
    block = ""

    if step_order == 2:
        vid = "https://www.youtube.com/watch?v=WXndZHSscFw&t=18s"
        # Host thumb on our origin — many inboxes block or strip img.youtube.com (same as step 7).
        thumb = f"{static_origin}/static/images/youtube_thumbnails/audit_walkthrough_wxnd.jpg"
        he_vid = html.escape(vid, quote=True)
        he_thumb = html.escape(thumb, quote=True)
        block = (
            f'<p><a href="{he_vid}"><img src="{he_thumb}" width="480" height="360" alt="Play video"></a></p>'
            f'<p><a href="{he_vid}">▶ watch the video</a></p>'
            f"{marker}"
        )
    elif step_order == 5:
        img = f"{static_origin}/static/images/cro_nurture/test_aov_variants_client.png"
        he_img = html.escape(img, quote=True)
        block = (
            f'<p><img src="{he_img}" width="560" alt="Experiment: control vs three variants"></p>'
            "<p>For another client we ran a similar test—control plus three variants. "
            "Per-session value moved +7.5% (variant 1), +6.2% (v2), and +5.8% (v3); "
            "conversion rate held, and average order value rose.</p>"
            f"{marker}"
        )
    elif step_order == 7:
        vid = "https://www.youtube.com/watch?v=vuYRwIst4JY"
        # Host thumb on our origin — many inboxes block or strip img.youtube.com; matches step 5 / signature pattern.
        thumb = f"{static_origin}/static/images/youtube_thumbnails/feastables_conversion_lessons.jpg"
        he_vid = html.escape(vid, quote=True)
        he_thumb = html.escape(thumb, quote=True)
        block = (
            f'<p><a href="{he_vid}"><img src="{he_thumb}" width="480" height="360" alt="Play video: Feastables"></a></p>'
            f'<p><a href="{he_vid}">▶ watch the video</a></p>'
            f"{marker}"
        )
    elif step_order == 9:
        roi_page = "https://sparksmetrics.com/how-we-improve-conversions"
        he_page = html.escape(roi_page, quote=True)
        block = (
            f'<p><a href="{he_page}">How we improve conversions — 90-day ROI guarantee (video walkthrough)</a></p>'
            f"{marker}"
        )
    elif step_order == 10:
        roi_page = "https://sparksmetrics.com/how-we-improve-conversions"
        cal_page = "https://sparksmetrics.com/schedule-a-call"
        he_roi = html.escape(roi_page, quote=True)
        he_cal = html.escape(cal_page, quote=True)
        block = (
            f'<p><a href="{he_roi}">90-day ROI guarantee — how we improve conversions (video)</a></p>'
            f'<p><a href="{he_cal}">Book a call — 7-day window from this email (guarantee + free CRO audit chat)</a></p>'
            f"{marker}"
        )

    if not block:
        return fragment or ""
    return (fragment or "") + block


def _append_nurture_media_plaintext(text: str, step_order: int) -> str:
    """Mirror injected HTML assets as short plaintext lines for non-HTML clients."""
    static_origin = cn_config.email_static_asset_origin()
    t = (text or "").rstrip()
    extra = ""
    if step_order == 2:
        extra = (
            "\n\nVideo: https://www.youtube.com/watch?v=WXndZHSscFw&t=18s\n"
            f"Thumbnail: {static_origin}/static/images/youtube_thumbnails/audit_walkthrough_wxnd.jpg"
        )
    elif step_order == 5:
        extra = (
            f"\n\nExperiment image: {static_origin}/static/images/cro_nurture/test_aov_variants_client.png"
            "\n(Another client, same structure: per-session value +7.5% / +6.2% / +5.8% vs control; "
            "CVR flat, AOV up.)"
        )
    elif step_order == 7:
        extra = (
            "\n\nVideo: https://www.youtube.com/watch?v=vuYRwIst4JY\n"
            f"Thumbnail: {static_origin}/static/images/youtube_thumbnails/feastables_conversion_lessons.jpg"
        )
    elif step_order == 4:
        extra = "\n\n90-day ROI / how we improve conversions: https://sparksmetrics.com/how-we-improve-conversions"
    elif step_order == 10:
        extra = (
            "\n\n90-day ROI: https://sparksmetrics.com/how-we-improve-conversions\n"
            "Book within 7 days: https://sparksmetrics.com/schedule-a-call"
        )
    if not extra:
        return t
    return (t + extra).strip() if t else extra.strip()


# Map nurture step → index into flattened scan signals (steps 4, 9, 10 use other angles).
_AUDIT_FOCUS_STEP_SLOTS: dict[int, int] = {1: 0, 2: 1, 3: 2, 5: 3, 6: 4, 7: 5, 8: 6}


def _flatten_audit_signals(full_report: dict) -> list[dict]:
    """Ordered audit beats from full_report for rotating focus across steps."""
    out: list[dict] = []

    def push(label: str, detail: str, source: str) -> None:
        label = (label or "").strip()
        detail = (detail or "").strip()
        if not label and not detail:
            return
        if not label:
            label = (detail[:72] + "…") if len(detail) > 72 else detail
        out.append({"label": label[:220], "detail": detail[:900], "source": source})

    leaks = full_report.get("biggest_conversion_leaks")
    if isinstance(leaks, list):
        for item in leaks:
            if not isinstance(item, dict):
                continue
            t = item.get("title")
            e = item.get("explanation")
            ts = str(t).strip() if isinstance(t, str) else ""
            es = str(e).strip() if isinstance(e, str) else ""
            if ts or es:
                push(ts or "conversion leak", es or ts, "biggest_conversion_leaks")

    fw = full_report.get("fast_wins")
    if isinstance(fw, list):
        for x in fw:
            if isinstance(x, str) and x.strip():
                push("fast win", x.strip(), "fast_wins")

    bo = full_report.get("biggest_opportunity")
    if isinstance(bo, dict):
        t = bo.get("title")
        e = bo.get("explanation")
        wm = bo.get("why_it_matters")
        ts = str(t).strip() if isinstance(t, str) else ""
        parts = [p for p in (e, wm) if isinstance(p, str) and p.strip()]
        detail = " ".join(parts)
        if ts or detail:
            push(ts or "biggest opportunity", detail or ts, "biggest_opportunity")

    pages = full_report.get("pages")
    if isinstance(pages, dict):
        for pk in ("product", "collection", "homepage"):
            pg = pages.get(pk)
            if not isinstance(pg, dict):
                continue
            frictions = pg.get("friction")
            if isinstance(frictions, list):
                for fr in frictions:
                    if isinstance(fr, str) and fr.strip():
                        push(f"{pk} · friction", fr.strip(), f"pages.{pk}.friction")
            ideas = pg.get("testing_ideas")
            if isinstance(ideas, list):
                for idea in ideas:
                    if isinstance(idea, str) and idea.strip():
                        push(f"{pk} · test idea", idea.strip(), f"pages.{pk}.testing_ideas")

    return out


def _this_step_audit_focus(full_report: dict, step_order: int) -> dict | None:
    slot = _AUDIT_FOCUS_STEP_SLOTS.get(step_order)
    if slot is None:
        return None
    items = _flatten_audit_signals(full_report)
    if not items:
        return None
    chosen = items[slot % len(items)]
    detail = chosen["detail"]
    if len(detail) > 650:
        detail = detail[:649] + "…"
    return {
        "sequence_slot": slot + 1,
        "signals_available": len(items),
        "label": chosen["label"],
        "detail": detail,
        "source": chosen["source"],
        "instruction": (
            "Center this email’s subject AND body on this single focus. Do not recycle the same headline hook or "
            "theme you would use for another step (e.g. repeating ‘clarity’ or the same leak title). "
            "The subject should clearly match this angle, not a near-duplicate of another step’s subject."
        ),
    }


def _lead_llm_context(lead: CroNurtureLead, *, step_order: int | None = None) -> dict:
    ctx = {
        "email": lead.email,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "site_url": lead.site_url,
        "cro_scan_payload": lead.cro_scan_payload,
        "business_profile": lead.business_profile or {},
        "enrichment_status": lead.enrichment_status,
    }
    p = lead.cro_scan_payload if isinstance(lead.cro_scan_payload, dict) else {}
    fr = p.get("full_report")
    if isinstance(fr, dict):
        sn = fr.get("store_name")
        if isinstance(sn, str) and sn.strip():
            ctx["audit_store_name"] = sn.strip()
        if step_order is not None:
            af = _this_step_audit_focus(fr, step_order)
            if af:
                ctx["this_step_audit_focus"] = af
    if step_order is not None:
        ctx["sequence_step_order"] = step_order
    return ctx


def _pause_if_superseded_by_newer_lead(lead: CroNurtureLead) -> bool:
    """
    Same email + site_url often creates multiple rows (resubmits/tests). When the newer row
    is also due (or has no future first-send time), only that row should own the sequence.
    If the newer row is still waiting for next_send_at in the future, do not block this row.
    """
    now = datetime.utcnow()
    newer = (
        CroNurtureLead.query.filter(
            CroNurtureLead.email == lead.email,
            CroNurtureLead.site_url == lead.site_url,
            CroNurtureLead.id > lead.id,
            CroNurtureLead.unsubscribed_at.is_(None),
            CroNurtureLead.paused.is_(False),
        )
        .order_by(CroNurtureLead.id.asc())
        .first()
    )
    if not newer:
        return False
    nnext = newer.next_send_at
    if nnext is not None and nnext > now:
        return False
    lead.paused = True
    lead.next_send_at = None
    db.session.commit()
    _log.info(
        "cro_nurture: paused duplicate lead id=%s (newer row id=%s, same email+site_url)",
        lead.id,
        newer.id,
    )
    return True


def _following_step(sequence_id: int, after_order: int) -> CroNurtureSequenceStep | None:
    return (
        CroNurtureSequenceStep.query.filter(
            CroNurtureSequenceStep.sequence_id == sequence_id,
            CroNurtureSequenceStep.step_order > after_order,
        )
        .order_by(CroNurtureSequenceStep.step_order.asc())
        .first()
    )


def dispatch_one_lead(lead: CroNurtureLead) -> str | None:
    if lead.unsubscribed_at or lead.paused:
        return "skipped_inactive"
    if _pause_if_superseded_by_newer_lead(lead):
        return "skipped_superseded_duplicate"
    if lead.next_send_at is None:
        return "skipped_no_schedule"
    if lead.next_send_at > datetime.utcnow():
        return "skipped_not_due"
    if lead.enrichment_status not in ("ok", "failed"):
        return "skipped_enrichment_state"

    seq = CroNurtureSequence.query.get(lead.sequence_id)
    if not seq or not seq.is_active:
        return "skipped_inactive_sequence"

    step = CroNurtureSequenceStep.query.filter_by(
        sequence_id=lead.sequence_id,
        step_order=lead.next_step_order,
    ).first()
    if not step:
        lead.next_send_at = None
        db.session.commit()
        return "skipped_no_step"

    send_row = CroNurtureEmailSend.query.filter_by(lead_id=lead.id, sequence_step_id=step.id).first()
    if send_row and send_row.status == "sent":
        return "skipped_already_sent"

    if not send_row:
        send_row = CroNurtureEmailSend(lead_id=lead.id, sequence_step_id=step.id, status="queued")
        db.session.add(send_row)
        db.session.commit()

    unsub = unsubscribe_url_for_lead(lead.id)
    try:
        body = openai_llm.generate_step_email(
            instruction_prompt=step.instruction_prompt,
            lead=_lead_llm_context(lead, step_order=step.step_order),
            unsubscribe_url=unsub,
            model=step.model_name,
        )
        subject = _normalize_nurture_subject(body.get("subject") or "")
        raw_html = _inject_nurture_media_blocks(body.get("html") or "", step.step_order)
        html = _ensure_email_footer(raw_html, unsub)
        raw_text = _append_nurture_media_plaintext(body.get("text") or "", step.step_order)
        text = _append_plaintext_signature_block(raw_text, unsub)
    except Exception as e:
        _log.warning(
            "cro_nurture dispatch generation failed lead_id=%s step=%s: %s",
            lead.id,
            step.step_order,
            e,
            exc_info=True,
        )
        send_row.status = "failed"
        send_row.error_message = str(e)[:4000]
        db.session.commit()
        return "failed_generation"

    sender_name, sender_email = cn_config.brevo_sender()
    if not sender_email:
        send_row.status = "failed"
        send_row.error_message = "CRO_NURTURE_BREVO_SENDER_EMAIL / BREVO_SENDER_EMAIL not configured"
        db.session.commit()
        return "failed_config"

    try:
        resp = brevo_send.send_transactional_html(
            to_email=lead.email,
            subject=subject,
            html_content=html,
            text_content=text,
            sender_name=sender_name,
            sender_email=sender_email,
            tags=["cro-nurture", f"step-{step.step_order}"],
        )
        mid = resp.get("messageId") or resp.get("message_id")
        send_row.subject = subject
        send_row.html_body = html[:500_000]
        send_row.text_body = text[:100_000] if text else None
        send_row.brevo_message_id = str(mid) if mid else None
        send_row.status = "sent"
        send_row.sent_at = datetime.utcnow()
        send_row.error_message = None
    except Exception as e:
        _log.warning(
            "cro_nurture dispatch Brevo failed lead_id=%s step=%s: %s",
            lead.id,
            step.step_order,
            e,
            exc_info=True,
        )
        send_row.status = "failed"
        send_row.error_message = str(e)[:4000]
        db.session.commit()
        return "failed_brevo"

    following = _following_step(lead.sequence_id, step.step_order)
    if following:
        lead.next_step_order = following.step_order
        following_delay = int(following.delay_after_previous_seconds or 0)
        if lead_skip_sequence_delays(lead):
            following_delay = 0
        lead.next_send_at = datetime.utcnow() + timedelta(seconds=following_delay)
    else:
        lead.next_step_order = step.step_order + 1
        lead.next_send_at = None
        clear_instant_test_flag(lead)

    db.session.commit()
    return "sent"


def run_burst_dispatch_for_lead(lead_id: int, *, max_steps: int = 20) -> dict:
    """
    Send every due step for this lead in one go (used with lead_skip_sequence_delays + zero delays).
    """
    sent = failed = 0
    last: str | None = None
    for _ in range(max_steps):
        lead = CroNurtureLead.query.get(lead_id)
        if not lead or lead.unsubscribed_at or lead.paused:
            break
        if lead.enrichment_status not in ("ok", "failed"):
            last = "skipped_enrichment_state"
            break
        if lead.next_send_at is None:
            if not lead_skip_sequence_delays(lead):
                last = "done_no_schedule"
                break
            step = CroNurtureSequenceStep.query.filter_by(
                sequence_id=lead.sequence_id,
                step_order=lead.next_step_order,
            ).first()
            if not step:
                last = "done_no_step"
                break
            existing = CroNurtureEmailSend.query.filter_by(
                lead_id=lead.id,
                sequence_step_id=step.id,
                status="sent",
            ).first()
            if existing:
                last = "done_already_sent"
                break
            lead.next_send_at = datetime.utcnow()
            db.session.commit()
        now = datetime.utcnow()
        if lead.next_send_at > now:
            lead.next_send_at = now
            db.session.commit()
        last = dispatch_one_lead(lead)
        if last == "sent":
            sent += 1
        elif last and last.startswith("failed"):
            failed += 1
            break
        else:
            break
    return {"sent": sent, "failed": failed, "last": last}


def run_dispatch_batch() -> dict:
    limit = cn_config.dispatch_batch_limit()
    now = datetime.utcnow()
    leads = (
        CroNurtureLead.query.filter(
            CroNurtureLead.next_send_at.isnot(None),
            CroNurtureLead.next_send_at <= now,
            CroNurtureLead.unsubscribed_at.is_(None),
            CroNurtureLead.paused.is_(False),
            CroNurtureLead.enrichment_status.in_(("ok", "failed")),
        )
        .order_by(CroNurtureLead.id.asc())
        .limit(limit)
        .all()
    )
    sent = skipped = failed = 0
    for lead in leads:
        status = dispatch_one_lead(lead)
        if status == "sent":
            sent += 1
        elif status and status.startswith("failed"):
            failed += 1
        else:
            skipped += 1
    return {"candidates": len(leads), "sent": sent, "skipped": skipped, "failed": failed}


def run_dispatch_batch_until_quiet(*, max_rounds: int = 30) -> dict:
    """
    Run dispatch once (normal prod). With CRO_NURTURE_TEST_ZERO_DELAYS=1 and FLASK_DEBUG=1,
    repeat until nothing was sent or max_rounds — drains the full sequence in one kick.
    """
    total = {"candidates": 0, "sent": 0, "skipped": 0, "failed": 0, "rounds": 0}
    di = run_dispatch_batch()
    for k in ("candidates", "sent", "skipped", "failed"):
        total[k] += di.get(k, 0)
    total["rounds"] = 1

    if not cn_config.test_zero_sequence_delays() or di.get("failed", 0) > 0:
        return total

    while total["rounds"] < max_rounds and di.get("sent", 0) > 0:
        di = run_dispatch_batch()
        for k in ("candidates", "sent", "skipped", "failed"):
            total[k] += di.get(k, 0)
        total["rounds"] += 1
        if di.get("failed", 0) > 0:
            break
    return total


def run_cli_burst_nurture_lead(lead_id: int, *, max_steps: int = 15) -> dict:
    """
    Send every remaining sequence step for one lead in a single CLI call by forcing next_send_at=now
    before each dispatch. Does not rely on DB delay columns. Gated by nurture_terminal_burst_ok().
    """
    if not cn_config.nurture_terminal_burst_ok():
        return {
            "error": "denied",
            "hint": "Set FLASK_DEBUG=1 or true, and CRO_NURTURE_TEST_ZERO_DELAYS=1 or CRO_NURTURE_CLI_BURST=1",
        }
    sent = failed = 0
    last: str | None = None
    for _ in range(max_steps):
        lead = CroNurtureLead.query.get(lead_id)
        if not lead:
            last = "not_found"
            break
        if lead.unsubscribed_at or lead.paused:
            last = "skipped_inactive"
            break
        if lead.enrichment_status not in ("ok", "failed"):
            last = "skipped_enrichment_state"
            break
        step = CroNurtureSequenceStep.query.filter_by(
            sequence_id=lead.sequence_id,
            step_order=lead.next_step_order,
        ).first()
        if not step:
            last = "sequence_complete"
            break
        lead.next_send_at = datetime.utcnow()
        db.session.commit()
        status = dispatch_one_lead(lead)
        last = status
        if status == "sent":
            sent += 1
            continue
        if status and status.startswith("failed"):
            failed += 1
            break
        break
    return {"lead_id": lead_id, "sent": sent, "failed": failed, "last": last}


def reset_nurture_lead_sequence_for_retest(lead_id: int) -> dict:
    """
    Dev-only: delete send rows, rewind to step 1, clear unsub/pause so you can cro-nurture-lead-burst again.
    Gated by nurture_terminal_burst_ok() (same as burst).
    """
    if not cn_config.nurture_terminal_burst_ok():
        return {
            "error": "denied",
            "hint": "Set FLASK_DEBUG=1 or true, and CRO_NURTURE_TEST_ZERO_DELAYS=1 or CRO_NURTURE_CLI_BURST=1",
        }
    lead = CroNurtureLead.query.get(lead_id)
    if not lead:
        return {"error": "not_found", "lead_id": lead_id}
    n = CroNurtureEmailSend.query.filter_by(lead_id=lead_id).delete()
    lead.next_step_order = 1
    lead.next_send_at = None
    lead.paused = False
    lead.unsubscribed_at = None
    db.session.commit()
    return {
        "ok": True,
        "lead_id": lead_id,
        "deleted_email_send_rows": n,
        "next_step_order": lead.next_step_order,
        "hint": "Run: flask --app run cro-nurture-lead-burst %s" % lead_id,
    }
