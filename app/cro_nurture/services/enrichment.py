"""Run site fetch + business profile for pending leads."""

import json
import logging
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

from app.models import db
from app.cro_nurture.models import CroNurtureLead, CroNurtureSequenceStep
from app.cro_nurture.services import config as cn_config
from app.cro_nurture.services.fetch_page import fetch_visible_text, normalize_site_url
from app.cro_nurture.services import openai_llm
from app.cro_nurture.lead_flags import lead_skip_sequence_delays
from app.cro_nurture.scan_schedule import (
    first_send_delay_seconds_from_sequence,
    lead_has_attached_cro_scan,
)


def _set_next_send_after_enrichment(lead: CroNurtureLead) -> None:
    """
    Prod: schedule first nurture email only once scan JSON is on the lead; delay = sequence step 1
    (time after attach / after enrich-if-scan-already-there). Instant-test leads: never via cron here.
    """
    preserved = lead.next_send_at
    if lead_skip_sequence_delays(lead):
        lead.next_send_at = None
        return
    if preserved is not None:
        lead.next_send_at = preserved
        return
    if not lead_has_attached_cro_scan(lead):
        lead.next_send_at = None
        return
    delay = first_send_delay_seconds_from_sequence(lead)
    lead.next_send_at = datetime.utcnow() + timedelta(seconds=delay)


def enrich_lead(lead: CroNurtureLead) -> None:
    url = normalize_site_url(lead.site_url)
    lead.site_url = url
    text, meta = fetch_visible_text(url)
    profile = openai_llm.build_business_profile(
        site_url=url,
        page_text=text,
        page_meta=meta,
        cro_scan=lead.cro_scan_payload,
    )
    lead.business_profile = profile
    lead.fetched_pages = {"homepage": {"meta": meta, "text_len": len(text)}}
    lead.enrichment_status = "ok"
    lead.enrichment_error = None
    lead.last_enriched_at = datetime.utcnow()
    _set_next_send_after_enrichment(lead)
    _log.info(
        "cro_nurture enrich ok lead_id=%s email=%s profile_keys=%s",
        lead.id,
        lead.email,
        sorted((lead.business_profile or {}).keys()),
    )


def enrich_lead_failed(lead: CroNurtureLead, err: str) -> None:
    lead.enrichment_status = "failed"
    lead.enrichment_error = (err or "")[:2000]
    lead.business_profile = lead.business_profile or {}
    lead.last_enriched_at = datetime.utcnow()
    _set_next_send_after_enrichment(lead)


def run_enrichment_batch() -> dict:
    limit = cn_config.enrichment_batch_limit()
    leads = (
        CroNurtureLead.query.filter_by(enrichment_status="pending")
        .order_by(CroNurtureLead.id.asc())
        .limit(limit)
        .all()
    )
    ok, failed = 0, 0
    for lead in leads:
        lead.enrichment_status = "running"
        db.session.commit()
        try:
            enrich_lead(lead)
            ok += 1
        except Exception as e:
            _log.warning(
                "cro_nurture enrich failed lead_id=%s email=%s: %s",
                lead.id,
                lead.email,
                e,
                exc_info=True,
            )
            enrich_lead_failed(lead, str(e))
            failed += 1
        db.session.commit()
    return {"processed": len(leads), "ok": ok, "failed": failed}


def enrich_pending_lead_by_id(lead_id: int) -> dict:
    """Run fetch + profile for one lead if still pending (instant-test thread or manual)."""
    lead = CroNurtureLead.query.get(lead_id)
    if not lead:
        return {"error": "not_found"}
    if lead.enrichment_status != "pending":
        return {"skipped": lead.enrichment_status}
    lead.enrichment_status = "running"
    db.session.commit()
    try:
        enrich_lead(lead)
        db.session.commit()
        return {"status": "enriched", "profile_keys": sorted((lead.business_profile or {}).keys())}
    except Exception as e:
        enrich_lead_failed(lead, str(e))
        db.session.commit()
        return {"status": "enrich_failed", "error": str(e)[:500]}


def force_re_enrich_lead(lead_id: int) -> dict:
    """
    Reset enrichment to pending, clear cached profile/fetch, run fetch + OpenAI profile again.
    Use from CLI when you changed prompts or want to verify enrichment without resubmitting the form.
    """
    lead = CroNurtureLead.query.get(lead_id)
    if not lead:
        return {"error": "not_found"}
    lead.enrichment_status = "pending"
    lead.enrichment_error = None
    lead.business_profile = None
    lead.fetched_pages = None
    db.session.commit()
    out = enrich_pending_lead_by_id(lead_id)
    if out.get("status") == "enriched":
        lead = CroNurtureLead.query.get(lead_id)
        out["next_send_at"] = lead.next_send_at.isoformat() if lead and lead.next_send_at else None
    return out


def dump_lead_enrichment_summary(lead_id: int, *, profile_value_max: int = 600) -> dict:
    """Human/CLI-friendly snapshot of scan attachment + enrichment (truncated profile values)."""
    lead = CroNurtureLead.query.get(lead_id)
    if not lead:
        return {"error": "not_found"}
    payload = lead.cro_scan_payload if isinstance(lead.cro_scan_payload, dict) else {}
    fr = payload.get("full_report")
    prof = lead.business_profile if isinstance(lead.business_profile, dict) else {}
    fp = lead.fetched_pages if isinstance(lead.fetched_pages, dict) else {}

    def _short(v: object) -> object:
        if v is None:
            return None
        if isinstance(v, (dict, list)):
            s = json.dumps(v, ensure_ascii=False)
            return v if len(s) <= profile_value_max else s[: profile_value_max - 1] + "…"
        s = str(v)
        return v if len(s) <= profile_value_max else s[: profile_value_max - 1] + "…"

    profile_preview = {k: _short(prof[k]) for k in sorted(prof.keys())}

    pages = (fr.get("pages") if isinstance(fr, dict) else None) or {}
    page_keys = list(pages.keys()) if isinstance(pages, dict) else []

    return {
        "id": lead.id,
        "email": lead.email,
        "site_url": lead.site_url,
        "first_name": lead.first_name,
        "enrichment_status": lead.enrichment_status,
        "enrichment_error": lead.enrichment_error,
        "last_enriched_at": lead.last_enriched_at.isoformat() if lead.last_enriched_at else None,
        "next_step_order": lead.next_step_order,
        "next_send_at": lead.next_send_at.isoformat() if lead.next_send_at else None,
        "paused": lead.paused,
        "cro_scan_payload_keys": sorted(payload.keys()),
        "scan_status": payload.get("scan_status"),
        "has_full_report": isinstance(fr, dict) and bool(fr),
        "full_report_top_keys": sorted(fr.keys())[:40] if isinstance(fr, dict) else [],
        "full_report_pages": page_keys,
        "fetched_pages": fp,
        "homepage_text_len": (fp.get("homepage") or {}).get("text_len") if isinstance(fp.get("homepage"), dict) else None,
        "business_profile_keys": sorted(prof.keys()),
        "business_profile": profile_preview,
    }
