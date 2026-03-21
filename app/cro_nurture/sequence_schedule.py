"""
CRO nurture — edit THIS file to control which emails send and when.

Then apply to the database:

  cd sparksmetrics-website
  flask --app run cro-nurture-sync-sequence

Use ``--force`` to overwrite existing steps (your edits in this file replace DB rows).

Sequence (10 emails) — each step feels like **Stijn’s personal review** of their store (not “the report” speaking). Copy should vary funnel pages (PDP/collection/homepage), not only the homepage.
---------------------------------------------------------------------------------------------------
1. First follow-up — 2–4 concrete observations from *your* review (pages, leaks, CTAs) + soft call.
2. One YouTube pick — fixed **audit walkthrough** video (WXndZHSscFw); copy must match that topic; app injects thumbnail+link.
3. Ebook — tie to their scan, then https://sparksmetrics.com/13-actionable-conversion-rate-optimization-strategies-ebook/
4. **90-day ROI guarantee** — how you improve conversions (link + video on site); early angle vs scan-only emails.
5. One AOV / revenue-per-session test — aligned with an injected client experiment screenshot + numbers.
6. ~30-day sketch — week beats mapped to their real pages/findings.
7. Feastables / MrBeast conversion lesson — video thumbnail injected; relevance to their store.
8. One leak — go deeper on a single issue from their audit.
9. Category pattern — “scale like [leader brand]” in the subject; bridge PDP/collection when present.
10. Closing only — no site critique; thanks + ROI guarantee reminder + 7-day window (reply/book) + soft out.

Public links (also referenced inside step prompts)
--------------------------------------------------
- Book a call: https://sparksmetrics.com/schedule-a-call
- YouTube: https://www.youtube.com/@stijnwollerich
- CRO ebook: https://sparksmetrics.com/13-actionable-conversion-rate-optimization-strategies-ebook/
- How we improve conversions (90-day ROI / video): https://sparksmetrics.com/how-we-improve-conversions

Timing rules
------------
- **Step 1** ``delay_after_previous_seconds``: wait this many seconds **after the CRO scan
  report is attached** to the lead (``full_report`` on ``cro_scan_payload``) before sending
  the first nurture email. If enrichment runs only after the scan exists, this is also the
  delay after enrichment in that case.
- **Step 2+** ``delay_after_previous_seconds``: wait this many seconds **after the previous
  email was sent** before sending this step.

So in production you only get **one email at a time**; step 2 arrives days after step 1, etc. To fire **all 10**
in one go locally, use ``CRO_NURTURE_TEST_ZERO_DELAYS=1`` + ``FLASK_DEBUG=1`` (see README). Alternatively
``CRO_NURTURE_TEST_INSTANT_SEQUENCE=1`` + ``FLASK_DEBUG=1`` (2 min wait, separate thread).

Optional: set ``model_name`` to e.g. ``\"gpt-4o-mini\"`` or ``None`` for env default.
"""

from __future__ import annotations

from app.models import db
from app.cro_nurture.models import CroNurtureSequence, CroNurtureSequenceStep

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

SEQUENCE_NAME = "default"
SEQUENCE_IS_ACTIVE = True

# ---------------------------------------------------------------------------
# Steps (order = step_order). Edit prompts and delays here.
# ---------------------------------------------------------------------------

_TWO_HOURS = 7200  # first nurture email after scan data is on the lead
_TWO_DAYS = 172800
_THREE_DAYS = 259200
_FOUR_DAYS = 345600

# Prepended to every step so the model must use enrichment + scan JSON, not boilerplate.
_NURTURE_GROUNDING = (
    "You are writing to one real lead who has business_profile (industry, hooks_for_email, cro_audit_themes, "
    "value_proposition_why, likely_offerings, etc.) AND cro_scan_payload.full_report from their CRO scan.\n"
    "Rules: (1) Include at least one concrete, recognizable detail from THEIR scan or profile in the body "
    "(e.g. a biggest_conversion_leaks title, a friction line from homepage/collection/product, a testing_idea, "
    "ugly_truth, executive_summary beat, or a specific page type + issue). (2) If audit_store_name is present, "
    "use it naturally—like you remember the brand. (3) Do not write advice that could apply unchanged to any "
    "random ecommerce site; tie sentences to their payload. (4) Follow global email rules from the system prompt "
    "(greeting, no brochure intro, no ‘I saw on your site’ cliché openers, short subject). "
    "(5) Do not default every email to the homepage: when full_report.pages has product (PDP) and/or collection, "
    "use those for at least part of the angle across the sequence—PDP often matters more for conversion than the homepage alone.\n"
    "(6) When the JSON includes this_step_audit_focus, that is **this email’s** assigned primary angle from the scan "
    "(a different slot per step). Lead the subject + opening on it; do not drift back to the same improvement headline "
    "another step would use.\n\n"
)

# Final email only: no audit recap — avoids repeating homepage/PDP/leaks with the rest of the sequence.
_CLOSING_EMAIL_GROUNDING = (
    "You are writing the final email in a nurture sequence to one real lead. "
    "Use first_name, and optionally audit_store_name or industry for a light personal greeting only.\n"
    "Do not describe what is wrong on their website, homepage, collection, PDP, leaks, friction, or any CRO scan findings. "
    "Do not introduce new audit themes or testing ideas. This is a human sign-off, not another review.\n\n"
)

STEPS: list[dict] = [
    {
        "step_order": 1,
        "delay_after_previous_seconds": _TWO_HOURS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 1 — right after they ran the scan: sound like *you* just finished reviewing their store yourself.\n"
            "Greeting (Hi + first_name / Hi there / Hi team). Optional one line that you hope the scan was useful.\n"
            "Body: pick 2–4 threads from full_report—name the *page* when you can (homepage / collection / product), "
            "and reference real strings from friction, page_summary, biggest_conversion_leaks, testing_ideas, or trust/CTA "
            "notes. If this_step_audit_focus is present, make that label/detail the **spine** of the email (other points "
            "should support it, not replace it). Weave in one hook from business_profile only if it matches the audit "
            "(no generic industry lecture).\n"
            "Do not frame the email as the report summarizing itself; it’s your personal take.\n"
            "~220–300 words, short paragraphs. Soft CTA: https://sparksmetrics.com/schedule-a-call.\n"
            "Subject: ≤45 chars feel; audit_store_name or one sharp audit phrase.\n"
            "JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 2,
        "delay_after_previous_seconds": _TWO_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 2 — one **fixed** YouTube video. The app injects a clickable thumbnail + link below; do not paste the full URL in the body.\n"
            "**What this video is actually about:** doing a **conversion / CRO audit**—how you walk through auditing a store, what you look at, and how you structure a review (the audit process itself). It is **not** a grab-bag of unrelated CRO topics.\n"
            "Your copy must describe and sell **that** topic: bridge from something real in THEIR cro_audit_themes, hooks_for_email, or full_report to why a short watch on **how you approach auditing a store** is useful *for them* right after their scan.\n"
            "Do **not** invent mismatched video themes (e.g. ‘videos on product differentiation and trust signals’ as if those were the point) unless you explicitly tie them to **audit/review thinking** and their payload; default framing should stay on **audit walkthrough / how to think through a store audit**.\n"
            "Optional extra context: https://www.youtube.com/@stijnwollerich — only if it fits in one line.\n"
            "Video: https://www.youtube.com/watch?v=WXndZHSscFw&t=18s — ~120–180 words. Optional light schedule-a-call. Subject: audit / review angle, still short.\n"
            "JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 3,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 3 — ebook as the *structured follow-up to what you already flagged in your review*.\n"
            "Start with one specific finding or theme from full_report (or cro_audit_themes) in plain language—then offer the "
            "ebook as the ‘if you want the full playbook’ layer.\n"
            "Link (use this exact URL): https://sparksmetrics.com/13-actionable-conversion-rate-optimization-strategies-ebook/\n"
            "Name 1–2 chapters or ideas from the ebook framing that map to their leaks or testing_ideas (stay factual—don’t "
            "invent chapter titles; keep descriptions generic if needed).\n"
            "~130–200 words. CTA: grab the ebook. Subject: their angle + ‘playbook’ or ‘strategies’ vibe, still short.\n"
            "JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 4,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 4 — introduce the 90-day ROI guarantee as a fresh angle (not another pass over the same scan problems as emails 1–3).\n"
            "Focus on Sparksmetrics’ 90-day ROI guarantee on conversion lift: plain language, why you stand behind results, "
            "and how it ties to serious CRO work—not a warranty brochure. "
            "The app will append a fixed link to a page with a video that goes deeper—do not paste that URL in the body; "
            "write one short paragraph that tees up why they might want to watch it after the scan + ebook context they’ve already seen.\n"
            "Optional one-sentence nod to their audit (audit_store_name or industry) for warmth—without repeating leaks, tests, "
            "or hooks already used in emails 1–3.\n"
            "Do not rehash the same CRO test suggestions or homepage/PDP beats from emails 1–3.\n"
            "Page (for your context only; link is injected): https://sparksmetrics.com/how-we-improve-conversions\n"
            "~110–170 words. Subject: ROI guarantee / confidence / risk angle—not ‘another scan thought’. "
            "Optional soft reply or https://sparksmetrics.com/schedule-a-call.\n"
            "JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 5,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 5 — *one* test only, like a DM after your review.\n"
            "Recommend **one** experiment that is about **AOV / revenue per session** (e.g. cart upsell, bundle, shipping "
            "threshold, cross-sell on PDP/cart)—not a pure traffic or CVR-only angle. Tie it to their real leaks or "
            "testing_ideas from full_report.\n"
            "The app will append a screenshot of a **control + three variants** from another client + a short results line; "
            "your copy must match that story: **CVR roughly flat, AOV up, per-session value up** across variants.\n"
            "Optional soft reply / schedule. ~90–140 words. Subject = that test in miniature (still short).\n"
            "JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 6,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 6 — First ~30 days roadmap sketch.\n"
            "Outline a tiny roadmap: audit → hypotheses → tests → measurement, but map each phrase to THEIR funnel "
            "using cro_scan_payload (pages/steps mentioned) and business_profile—not a generic slide deck.\n"
            "~180–250 words. Clear CTA to book a call to unpack it: "
            "https://sparksmetrics.com/schedule-a-call\n"
            "JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 7,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 7 — measurement *for the bets implied by their audit*, plus one concrete lesson video.\n"
            "Tie to concrete things in full_report (e.g. tests you’d run on PDP vs collection, trust near checkout, "
            "mobile friction mentioned in ui_ux_notes)—what would you measure to know if it worked? Stay honest: do not "
            "claim you know their GA/GTM stack.\n"
            "The app will append a **clickable thumbnail** for this video—do not paste the full YouTube URL in the body. "
            "Video topic: why Feastables (MrBeast) converts well and what to steal from that for *their* store. "
            "Link: https://www.youtube.com/watch?v=vuYRwIst4JY\n"
            "Optional secondary: https://www.youtube.com/@stijnwollerich and/or ebook only if natural.\n"
            "~150–210 words. Soft CTA. JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 8,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 8 — zoom in on *one* leak they already have signal for.\n"
            "Prefer quoting or paraphrasing one biggest_conversion_leaks item OR the strongest page_summary + friction combo "
            "from a single page (homepage/collection/product). Go one level deeper than the scan PDF headline—why it hurts "
            "*their* shopper, in your words.\n"
            "Not a second generic ‘common leak’ essay. ~140–200 words. Soft CTA. JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 9,
        "delay_after_previous_seconds": _THREE_DAYS,
        "instruction_prompt": (
            _NURTURE_GROUNDING
            + "Email 9 — ‘Someone like you’ (pattern, not a fabricated case study).\n"
            "Speak to businesses similar to theirs (use likely_offerings, target_audience_guess, business_summary). "
            "Describe a plausible anonymized pattern or outcome we often see in that space—without naming a real "
            "client company or inventing revenue/% lifts unless present in lead JSON.\n"
            "Bridge the pattern to their funnel using friction/testing ideas from product (PDP) and/or collection "
            "when those appear in full_report.pages—not only the homepage. Examples: clarity on the PDP, comparison, specs, "
            "shipping/returns near the buy box, collection merchandising—only if grounded in their scan.\n"
            "Subject: **must** read like: scale like [named category leader] — optional short second clause (all lowercase). "
            "Pick one plausible public brand in their space as a parallel (e.g. a well-known leader in the same industry "
            "or niche), not their company name. Do not use a near-duplicate of emails 7–8 subjects; this one is the "
            "leader-pattern subject.\n"
            "Bridge to: on a call we can explain how we’d apply that thinking to their funnel. "
            "CTA: https://sparksmetrics.com/schedule-a-call — keep confident but not pushy.\n"
            "~160–220 words. JSON: subject, html, text."
        ),
        "model_name": None,
    },
    {
        "step_order": 10,
        "delay_after_previous_seconds": _FOUR_DAYS,
        "instruction_prompt": (
            _CLOSING_EMAIL_GROUNDING
            + "Email 10 — last message in the sequence: closing only.\n"
            "Tone: we’ve shared ideas over these emails to help; if the timing isn’t right or you’re not ready to work together, "
            "that’s completely fine—when you are, you’ll know where to find us.\n"
            "Briefly restate the 90-day ROI guarantee on conversion lift (confidence / standing behind the work)—enough to "
            "remind them why engaging with Sparksmetrics is different, without legal jargon.\n"
            "Offer a clear 7-day window from this email: if they reply or book a call within those 7 days, they lock in "
            "that conversation under the guarantee framing and a no-obligation CRO audit discussion (next-step chat)—"
            "after that, you’re still around but this specific window closes (say it warmly, not threatening).\n"
            "The app will append fixed links (ROI page + schedule a call)—do not paste those URLs in the body.\n"
            "Optional one line: YouTube (https://www.youtube.com/@stijnwollerich) for free ideas to borrow.\n"
            "Do not pitch ‘run another scan’ as the main CTA. Subject: gratitude / door open / when you’re ready—not homepage, "
            "clarity, or audit problems.\n"
            "~120–190 words. JSON: subject, html, text."
        ),
        "model_name": None,
    },
]


def _validate_steps() -> None:
    orders = [s["step_order"] for s in STEPS]
    if len(orders) != len(set(orders)):
        raise ValueError("sequence_schedule.STEPS: duplicate step_order")
    if sorted(orders) != list(range(1, len(orders) + 1)):
        raise ValueError("sequence_schedule.STEPS: step_order must be 1..N with no gaps")


def apply_scheduled_steps_to_database(*, replace_existing: bool) -> str:
    """
    Sync STEPS to the DB for SEQUENCE_NAME.

    - replace_existing=False: only fill steps if the sequence is missing or has zero steps
      (safe for first deploy / create_all).
    - replace_existing=True: delete existing steps for this sequence and insert STEPS from this file.
    """
    _validate_steps()

    seq = CroNurtureSequence.query.filter_by(name=SEQUENCE_NAME).first()
    if not seq:
        seq = CroNurtureSequence(name=SEQUENCE_NAME, is_active=SEQUENCE_IS_ACTIVE)
        db.session.add(seq)
        db.session.flush()
    else:
        seq.is_active = SEQUENCE_IS_ACTIVE

    existing = CroNurtureSequenceStep.query.filter_by(sequence_id=seq.id).count()
    if existing > 0 and not replace_existing:
        db.session.commit()
        return f"skipped: sequence {SEQUENCE_NAME!r} already has {existing} step(s); run with --force to replace"

    if existing > 0:
        CroNurtureSequenceStep.query.filter_by(sequence_id=seq.id).delete()
        db.session.flush()

    for row in STEPS:
        db.session.add(
            CroNurtureSequenceStep(
                sequence_id=seq.id,
                step_order=int(row["step_order"]),
                delay_after_previous_seconds=int(row["delay_after_previous_seconds"]),
                instruction_prompt=str(row["instruction_prompt"]),
                model_name=row.get("model_name"),
                allowed_facts=row.get("allowed_facts"),
            )
        )
    db.session.commit()
    return f"ok: {SEQUENCE_NAME!r} now has {len(STEPS)} step(s)"


def ensure_default_sequence_from_schedule() -> None:
    """Called on app startup: create sequence + steps only when nothing configured yet."""
    apply_scheduled_steps_to_database(replace_existing=False)
