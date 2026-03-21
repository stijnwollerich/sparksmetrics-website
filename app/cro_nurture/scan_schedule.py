"""When to schedule the first nurture email relative to CRO scan data."""

from __future__ import annotations

from app.cro_nurture.lead_flags import lead_skip_sequence_delays
from app.cro_nurture.models import CroNurtureEmailSend, CroNurtureLead, CroNurtureSequenceStep
from app.cro_nurture.services import config as cn_config


def effective_delay_seconds(lead: CroNurtureLead, configured: int) -> int:
    """Instant-test flag on lead, or dev test-zero-delays env + DEBUG → 0; else DB delay."""
    if lead_skip_sequence_delays(lead):
        return 0
    if cn_config.test_zero_sequence_delays():
        return 0
    return max(0, int(configured or 0))


def lead_has_attached_cro_scan(lead: CroNurtureLead) -> bool:
    """True once the scan pipeline merged report JSON (full_report) onto the lead."""
    p = lead.cro_scan_payload
    if not isinstance(p, dict):
        return False
    return bool(p.get("full_report"))


def step1_email_already_sent(lead: CroNurtureLead) -> bool:
    step = CroNurtureSequenceStep.query.filter_by(
        sequence_id=lead.sequence_id,
        step_order=1,
    ).first()
    if not step:
        return False
    return (
        CroNurtureEmailSend.query.filter_by(
            lead_id=lead.id,
            sequence_step_id=step.id,
            status="sent",
        ).first()
        is not None
    )


def first_send_delay_seconds_from_sequence(lead: CroNurtureLead) -> int:
    """Step 1 row delay = time after scan attach before first nurture email (prod)."""
    step = CroNurtureSequenceStep.query.filter_by(
        sequence_id=lead.sequence_id,
        step_order=1,
    ).first()
    if not step:
        return effective_delay_seconds(lead, 7200)
    return effective_delay_seconds(lead, int(step.delay_after_previous_seconds or 0))
