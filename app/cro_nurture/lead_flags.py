"""Small helpers for per-lead nurture behavior (no extra DB columns)."""

from __future__ import annotations

from app.cro_nurture.models import CroNurtureLead

# Set on cro_scan_payload for local instant-sequence tests; stripped when the sequence finishes.
NURTURE_INSTANT_TEST_KEY = "_nurture_instant_test"


def lead_skip_sequence_delays(lead: CroNurtureLead) -> bool:
    p = lead.cro_scan_payload
    if not isinstance(p, dict):
        return False
    return bool(p.get(NURTURE_INSTANT_TEST_KEY))


def clear_instant_test_flag(lead: CroNurtureLead) -> None:
    p = lead.cro_scan_payload
    if not isinstance(p, dict) or NURTURE_INSTANT_TEST_KEY not in p:
        return
    lead.cro_scan_payload = {k: v for k, v in p.items() if k != NURTURE_INSTANT_TEST_KEY}
