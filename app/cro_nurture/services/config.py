import os


def ingest_secret():
    return os.getenv("CRO_NURTURE_INGEST_SECRET", "")


def cron_token():
    return os.getenv("CRO_NURTURE_CRON_TOKEN", "")


def brevo_webhook_token():
    return os.getenv("CRO_NURTURE_BREVO_WEBHOOK_TOKEN", "")


def brevo_list_ids():
    raw = os.getenv("CRO_NURTURE_BREVO_LIST_IDS", "")
    if not raw.strip():
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


def brevo_sender():
    try:
        from flask import has_request_context, current_app

        if has_request_context():
            cfg = current_app.config
            email = (cfg.get("CRO_NURTURE_BREVO_SENDER_EMAIL") or cfg.get("BREVO_SENDER_EMAIL") or "").strip()
            name = (cfg.get("CRO_NURTURE_BREVO_SENDER_NAME") or cfg.get("BREVO_SENDER_NAME") or "Sparksmetrics").strip()
            if email:
                return name, email
    except Exception:
        pass
    email = os.getenv("CRO_NURTURE_BREVO_SENDER_EMAIL") or os.getenv("BREVO_SENDER_EMAIL", "")
    name = os.getenv("CRO_NURTURE_BREVO_SENDER_NAME") or os.getenv("BREVO_SENDER_NAME", "Sparksmetrics")
    return name, email


def app_base_url():
    try:
        from flask import has_request_context, current_app

        if has_request_context():
            u = (current_app.config.get("SITE_URL") or "").strip().rstrip("/")
            if u:
                return u
    except Exception:
        pass
    return (os.getenv("APP_URL") or os.getenv("CRO_NURTURE_APP_URL") or os.getenv("SITE_URL") or "").rstrip("/")


def openai_model_profile():
    return os.getenv("CRO_NURTURE_OPENAI_MODEL_PROFILE", "gpt-4o-mini")


def openai_model_email():
    return os.getenv("CRO_NURTURE_OPENAI_MODEL_EMAIL", "gpt-4o-mini")


def fetch_timeout_seconds():
    return int(os.getenv("CRO_NURTURE_FETCH_TIMEOUT", "20"))


def fetch_max_bytes():
    return int(os.getenv("CRO_NURTURE_FETCH_MAX_BYTES", "1_500_000").replace("_", ""))


def enrichment_batch_limit():
    return int(os.getenv("CRO_NURTURE_ENRICH_BATCH", "15"))


def profile_homepage_text_max_chars():
    """Homepage visible text sent into the profile/summarization model (not stored on the lead)."""
    return int(os.getenv("CRO_NURTURE_PROFILE_HOMEPAGE_CHARS", "3500"))


def profile_slim_audit_json_max_chars():
    """Max JSON size for the condensed CRO audit passed to the profile model."""
    return int(os.getenv("CRO_NURTURE_PROFILE_AUDIT_JSON_MAX", "6000"))


def profile_llm_input_max_chars():
    """Hard cap on the first user message JSON (homepage meta + excerpts + slim audit)."""
    return int(os.getenv("CRO_NURTURE_PROFILE_INPUT_MAX_CHARS", "12000"))


def email_llm_input_max_chars():
    """Max characters for the serialized user message (slim lead + step_instructions) on nurture email calls."""
    return int(os.getenv("CRO_NURTURE_EMAIL_INPUT_MAX_CHARS", "20000"))


def email_slim_audit_json_max_chars():
    """Initial max JSON size for condensed cro_scan_payload inside slim email lead (shrunk further if total ctx is too big)."""
    return int(os.getenv("CRO_NURTURE_EMAIL_AUDIT_JSON_MAX", "7000"))


def email_business_profile_max_chars():
    """Max characters for serialized business_profile inside slim email lead."""
    return int(os.getenv("CRO_NURTURE_EMAIL_PROFILE_JSON_MAX", "3200"))


def openai_email_max_completion_tokens():
    """Completion budget for nurture email JSON (subject + html + text) — prefer spending here vs huge inputs."""
    return int(os.getenv("CRO_NURTURE_EMAIL_MAX_COMPLETION_TOKENS", "2800"))


def email_static_asset_origin():
    """
    Public https origin for /static/ images embedded in nurture HTML (step 5 screenshot, etc.).

    Unsubscribe links still use SITE_URL / app_base_url. This defaults to production so images work when the app
    runs on localhost or staging (those hosts are not reachable from inboxes).
    """
    raw = (os.getenv("CRO_NURTURE_EMAIL_STATIC_ORIGIN") or "").strip().rstrip("/")
    if raw:
        return raw
    return "https://sparksmetrics.com"


def dispatch_batch_limit():
    return int(os.getenv("CRO_NURTURE_DISPATCH_BATCH", "25"))


def env_flask_debug_enabled() -> bool:
    """True when FLASK_DEBUG is set in the environment (accepts 1, true, yes — not only the literal '1')."""
    return os.getenv("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _app_debug() -> bool:
    try:
        from flask import current_app, has_app_context

        return bool(has_app_context() and current_app.debug)
    except Exception:
        return False


def test_zero_sequence_delays() -> bool:
    """
    When True, all sequence step delays are treated as 0 so local testing can drain the drip in one kick.

    Requires CRO_NURTURE_TEST_ZERO_DELAYS=1 **and** a debug signal: FLASK_DEBUG in env (1/true/yes) **or**
    current_app.debug. The env check fixes CLI runs where Config.DEBUG stayed False because FLASK_DEBUG
    was ``true`` instead of ``1``.
    """
    raw = os.getenv("CRO_NURTURE_TEST_ZERO_DELAYS", "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        return False
    if env_flask_debug_enabled():
        return True
    return _app_debug()


def nurture_terminal_burst_ok() -> bool:
    """
    Dev-only gate for ``cro-nurture-lead-burst``: user must opt in (zero-delay or CLI burst flag) + debug signal.
    """
    z = os.getenv("CRO_NURTURE_TEST_ZERO_DELAYS", "").strip().lower() in ("1", "true", "yes", "on")
    b = os.getenv("CRO_NURTURE_CLI_BURST", "").strip().lower() in ("1", "true", "yes", "on")
    if not (z or b):
        return False
    return env_flask_debug_enabled() or _app_debug()


def test_wait_before_nurture_burst_seconds():
    """After scan data exists, wait this long before instant-test burst (default 2 minutes)."""
    return int(os.getenv("CRO_NURTURE_TEST_WAIT_BEFORE_NURTURE_SECONDS", "120"))


def test_wait_for_scan_report_max_seconds():
    """Instant-test thread: max time to poll for full_report (default 15 minutes)."""
    return int(os.getenv("CRO_NURTURE_TEST_WAIT_FOR_SCAN_MAX_SECONDS", "900"))
