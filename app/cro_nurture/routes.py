"""HTTP surface for CRO nurture (isolated blueprint)."""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, redirect, render_template, request
from sqlalchemy.orm import selectinload

from app.models import Lead, db
from app.cro_nurture.models import CroNurtureEmailSend, CroNurtureLead
from app.cro_nurture.services import config as cn_config
from app.cro_nurture.services.dispatch import _unsub_serializer, run_dispatch_batch_until_quiet
from app.cro_nurture.services.enrichment import run_enrichment_batch
from app.cro_nurture.services.fetch_page import normalize_site_url
from app.cro_nurture.intake import (
    extract_ingest_secret,
    merge_ingest_payload,
    parse_cro_payload,
    pick_cro_scan_raw,
    pick_email,
    pick_names,
    pick_site_url,
)
from app.cro_nurture.leads import create_nurture_lead_from_api_dict

cro_nurture_bp = Blueprint(
    "cro_nurture",
    __name__,
    url_prefix="/cro-nurture",
)


def _check_ingest_secret() -> bool:
    expected = cn_config.ingest_secret()
    if not expected:
        return False
    got = extract_ingest_secret(request)
    return bool(got) and got == expected


def _token_from_request() -> str:
    """Query ?token=, header X-Cron-Token, or Authorization: Bearer …"""
    q = (request.args.get("token") or "").strip()
    if q:
        return q
    h = (request.headers.get("X-Cron-Token") or "").strip()
    if h:
        return h
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _check_cron_token() -> bool:
    expected = cn_config.cron_token()
    if not expected:
        return False
    return _token_from_request() == expected


def _check_webhook_token() -> bool:
    expected = cn_config.brevo_webhook_token()
    if not expected:
        return False
    return request.args.get("token") == expected


def _nurture_lead_display_rows(leads: list, max_subject_len: int = 72) -> List[Dict[str, Any]]:
    """Build template-friendly rows: flow summary + per-step send lines."""
    out = []
    for lead in leads:
        sends = sorted(
            lead.email_sends,
            key=lambda s: (s.sequence_step.step_order if s.sequence_step else 0, s.id),
        )
        send_lines = []
        for s in sends:
            step_order = s.sequence_step.step_order if s.sequence_step else None
            subj = (s.subject or "").strip()
            if len(subj) > max_subject_len:
                subj = subj[: max_subject_len - 1] + "…"
            sent_at = s.sent_at
            send_lines.append(
                {
                    "step_order": step_order,
                    "status": s.status,
                    "sent_at": sent_at,
                    "sent_at_label": (
                        sent_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                        if sent_at
                        else "— (not sent yet)"
                    ),
                    "subject": subj or "—",
                    "opens": int(s.open_count or 0),
                    "clicks": int(s.click_count or 0),
                    "error_message": (s.error_message or "").strip(),
                }
            )
        profile_keys: List[str] = []
        bp = lead.business_profile
        if isinstance(bp, dict):
            profile_keys = sorted(bp.keys())
        scan = lead.cro_scan_payload if isinstance(lead.cro_scan_payload, dict) else {}
        has_full_report = bool(scan.get("full_report"))
        out.append(
            {
                "lead": lead,
                "send_lines": send_lines,
                "profile_keys": profile_keys,
                "has_full_report": has_full_report,
            }
        )
    return out


def _optional_int_query(name: str) -> Optional[int]:
    """
    None = no SQL limit (all rows). Optional ?limit= / ?form_limit= caps rows (1..100_000).
    """
    if name not in request.args:
        return None
    raw = (request.args.get(name) or "").strip()
    if raw == "":
        return None
    return min(max(int(raw), 1), 100_000)


@cro_nurture_bp.route("/internal/leads", methods=["GET"])
def internal_leads_dashboard():
    """Staff-only HTML: all nurture leads on one page + form leads."""
    expected = cn_config.internal_dashboard_token()
    if not expected:
        return render_template("cro_nurture_internal_not_configured.html"), 503
    if _token_from_request() != expected:
        return render_template("cro_nurture_internal_unauthorized.html"), 401
    limit_nurture = _optional_int_query("limit")
    limit_forms = _optional_int_query("form_limit")

    nq = CroNurtureLead.query.options(
        selectinload(CroNurtureLead.email_sends).selectinload(CroNurtureEmailSend.sequence_step),
        selectinload(CroNurtureLead.sequence),
    ).order_by(CroNurtureLead.id.desc())
    if limit_nurture is not None:
        nq = nq.limit(limit_nurture)
    nurture_leads = nq.all()

    fq = Lead.query.order_by(Lead.id.desc())
    if limit_forms is not None:
        fq = fq.limit(limit_forms)
    form_leads = fq.all()

    return render_template(
        "cro_nurture_internal_leads.html",
        nurture_rows=_nurture_lead_display_rows(nurture_leads, max_subject_len=4000),
        form_leads=form_leads,
        nurture_count=len(nurture_leads),
        form_count=len(form_leads),
        limit_nurture=limit_nurture,
        limit_forms=limit_forms,
    )


@cro_nurture_bp.route("/api/ingest", methods=["POST"])
def api_ingest():
    if not _check_ingest_secret():
        return jsonify({"error": "Unauthorized"}), 401

    data = merge_ingest_payload(request)
    email = pick_email(data)
    if not email or "@" not in email:
        return jsonify({"error": "valid email required"}), 400

    site_url = pick_site_url(data)
    try:
        site_url = normalize_site_url(site_url)
    except Exception as e:
        return jsonify({"error": f"invalid site_url: {e}"}), 400

    first_name, last_name = pick_names(data)
    source_tag = (data.get("source_tag") or data.get("source") or "").strip() or None
    if not source_tag:
        source_tag = os.getenv("CRO_NURTURE_DEFAULT_SOURCE_TAG", "cro-scan").strip() or "cro-scan"

    cro_payload = parse_cro_payload(pick_cro_scan_raw(data))

    lead = create_nurture_lead_from_api_dict(
        email=email,
        site_url=site_url,
        first_name=first_name,
        last_name=last_name,
        cro_payload=cro_payload,
        source_tag=source_tag,
    )
    if not lead:
        return jsonify({"error": "no active cro_nurture_sequence"}), 503

    return jsonify({"ok": True, "lead_id": lead.id}), 201


@cro_nurture_bp.route("/api/cron/enrich", methods=["GET", "POST"])
def cron_enrich():
    if not _check_cron_token():
        return jsonify({"error": "Unauthorized"}), 401
    stats = run_enrichment_batch()
    return jsonify({"ok": True, **stats}), 200


@cro_nurture_bp.route("/api/cron/dispatch", methods=["GET", "POST"])
def cron_dispatch():
    if not _check_cron_token():
        return jsonify({"error": "Unauthorized"}), 401
    stats = run_dispatch_batch_until_quiet()
    return jsonify({"ok": True, **stats}), 200


@cro_nurture_bp.route("/api/cron/run", methods=["GET", "POST"])
def cron_run():
    if not _check_cron_token():
        return jsonify({"error": "Unauthorized"}), 401
    en = run_enrichment_batch()
    disp = run_dispatch_batch_until_quiet()
    return jsonify({"ok": True, "enrichment": en, "dispatch": disp}), 200


@cro_nurture_bp.route("/unsubscribe/<token>", methods=["GET"])
def unsubscribe(token):
    try:
        payload = _unsub_serializer().loads(token, max_age=60 * 60 * 24 * 730)
        lead_id = int(payload["i"])
    except Exception:
        return jsonify({"error": "invalid or expired link"}), 400

    lead = CroNurtureLead.query.get(lead_id)
    if not lead:
        return jsonify({"error": "not found"}), 404
    lead.unsubscribed_at = datetime.utcnow()
    lead.next_send_at = None
    db.session.commit()

    done = os.getenv("CRO_NURTURE_UNSUBSCRIBE_REDIRECT_URL", "").strip()
    if done:
        return redirect(done, code=302)
    return jsonify({"ok": True, "message": "You are unsubscribed."}), 200


@cro_nurture_bp.route("/api/webhooks/brevo", methods=["POST"])
def webhook_brevo():
    if not _check_webhook_token():
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "JSON body required"}), 400

    events = body if isinstance(body, list) else [body]
    updated = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        mid = ev.get("message-id") or ev.get("messageId") or ev.get("message_id")
        if not mid:
            continue
        send_row = CroNurtureEmailSend.query.filter_by(brevo_message_id=str(mid)).first()
        if not send_row:
            continue
        event = (ev.get("event") or ev.get("type") or "").lower()
        now = datetime.utcnow()
        if "open" in event:
            send_row.open_count = int(send_row.open_count or 0) + 1
            send_row.last_opened_at = now
            updated += 1
        elif "click" in event:
            send_row.click_count = int(send_row.click_count or 0) + 1
            send_row.last_clicked_at = now
            updated += 1
    if updated:
        db.session.commit()
    return jsonify({"ok": True, "updated": updated}), 200
