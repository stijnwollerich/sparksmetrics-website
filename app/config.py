"""Application configuration."""
import os
from pathlib import Path

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent.parent
_env_file = BASE_DIR / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines from path; return dict. Does not rely on dotenv or import order."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        for line in raw.splitlines():
            line = line.strip().replace("\r", "")
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            k = key.strip()
            v = value.strip().strip("'\"").replace("\r", "")
            if k and v:
                out[k] = v
    except Exception:
        pass
    return out


# Load .env into os.environ (overwrite so file always wins; same pattern as Upwork run.mjs)
_env_vars = _read_env_file(_env_file)
if not _env_vars and (Path.cwd() / ".env").exists():
    _env_vars = _read_env_file(Path.cwd() / ".env")
for key, value in _env_vars.items():
    if value:
        os.environ[key] = value

# Fallback: if DATABASE_URL still missing, read file for any line containing DATABASE_URL=
if not (os.environ.get("DATABASE_URL") or "").strip() and _env_file.exists():
    try:
        for line in _env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if "DATABASE_URL=" in line:
                v = line.split("=", 1)[1].strip().strip("'\"").replace("\r", "")
                if v:
                    os.environ["DATABASE_URL"] = v
                break
    except Exception:
        pass

# Then load_dotenv for any vars not in our read (e.g. multi-line or other formats)
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except Exception:
        pass

# Re-apply DATABASE_URL from our parse so load_dotenv can't overwrite it with empty
if _env_vars.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = _env_vars["DATABASE_URL"]
elif not (os.environ.get("DATABASE_URL") or "").strip() and _env_file.exists():
    try:
        for line in _env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if "DATABASE_URL=" in line:
                v = line.split("=", 1)[1].strip().strip("'\"").replace("\r", "")
                if v:
                    os.environ["DATABASE_URL"] = v
                break
    except Exception:
        pass


def _get_database_uri() -> str | None:
    uri = (os.environ.get("DATABASE_URL") or "").strip()
    if uri:
        return uri.replace("postgres://", "postgresql://", 1)
    # Last resort: read .env directly (avoids any load_dotenv / import-order issues)
    for path in (_env_file, Path.cwd() / ".env"):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "DATABASE_URL=" in line:
                    v = line.split("=", 1)[1].strip().strip("'\"").replace("\r", "")
                    if v:
                        return v.replace("postgres://", "postgresql://", 1)
                    break
        except Exception:
            pass
    return None


def _get_sqlalchemy_uri() -> str:
    """Database URI: from DATABASE_URL, or SQLite for local dev when unset."""
    uri = _get_database_uri()
    if uri:
        return uri
    # Local dev: no PostgreSQL → use SQLite in project root (no setup required)
    path = BASE_DIR / "local.db"
    return f"sqlite:///{path.as_posix()}"


def get_spark_nurture_enrollment_types() -> frozenset[str]:
    """
    submission_type values that send enroll_nurture=True on Spark POST /api/site/lead.

    Env ``SPARK_NURTURE_ENROLLMENT_TYPES``: comma-separated, e.g. ``cro_scan`` or ``cro_scan,audit``.
    If unset, default is ``cro_scan`` only. Set to empty to disable all (all forms send
    ``enroll_nurture: false``). Spark must honor the ``enroll_nurture`` boolean.
    """
    raw = os.environ.get("SPARK_NURTURE_ENROLLMENT_TYPES")
    if raw is None:
        return frozenset({"cro_scan"})
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def spark_background_cro_scan_after_ingest_enabled() -> bool:
    """
    When Spark ingest succeeds and the lead has a store/website URL, enqueue a **silent** CRO scan
    (``lead_magnet_enrich``): store report + attach to Spark, **no** report email to the lead.

    Env ``SPARK_BACKGROUND_CRO_SCAN`` — default ``1`` (on). Set to ``0`` / ``false`` to disable.
    """
    raw = (os.environ.get("SPARK_BACKGROUND_CRO_SCAN") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


class Config:
    """Default configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")
    TESTING = False
    # PostgreSQL: set DATABASE_URL (e.g. postgresql://user:pass@localhost:5432/dbname). Else SQLite for local dev.
    SQLALCHEMY_DATABASE_URI = _get_sqlalchemy_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    # YouTube: manual list (comma-separated in env) or default below. Thumbnails from img.youtube.com.
    _yt_env = os.environ.get("YOUTUBE_VIDEO_IDS", "").strip()
    YOUTUBE_VIDEO_IDS = (
        [x.strip() for x in _yt_env.split(",") if x.strip()]
        if _yt_env
        else ["BKN3rEt45Sk", "qEd0zrqFYeg"]
    )
    YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()

    # Brevo: sync leads to Brevo (email marketing). If unset, leads are not sent to Brevo.
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
    # Optional: comma-separated list IDs to add contacts to (e.g. "2,5"). Find in Brevo: Contacts → Lists.
    _brevo_lists = os.environ.get("BREVO_LIST_IDS", "").strip()
    BREVO_LIST_IDS = [int(x.strip()) for x in _brevo_lists.split(",") if x.strip().isdigit()] if _brevo_lists else []
    # CRO Ebook list (id 7): contacts who download the ebook are added to this list.
    _cro_ebook = (os.environ.get("BREVO_CRO_EBOOK_LIST_ID") or "7").strip()
    BREVO_CRO_EBOOK_LIST_ID = int(_cro_ebook) if _cro_ebook.isdigit() else 7
    # Free CRO audit list (id 11): contacts who request the audit are added to this list.
    _audit_list = (os.environ.get("BREVO_AUDIT_LIST_ID") or "11").strip()
    BREVO_AUDIT_LIST_ID = int(_audit_list) if _audit_list.isdigit() else 11
    # CRO scan (Shopify) lead list: list ID for cro-scan thank-you signups (default 12).
    _cro_scan_list = (os.environ.get("BREVO_CRO_SCAN_LIST_ID") or "12").strip()
    BREVO_CRO_SCAN_LIST_ID = int(_cro_scan_list) if _cro_scan_list.isdigit() else 12

    # Slack: webhook URL for lead notifications. If set, every lead submission posts to Slack.
    SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    # Optional: Incoming Webhook for #sparksmetrics (CRO cost/ROI calculator email submits). Falls back to SLACK_WEBHOOK_URL.
    SLACK_SPARKSMETRICS_WEBHOOK_URL = os.environ.get("SLACK_SPARKSMETRICS_WEBHOOK_URL", "").strip()

    # CRO nurture (AI drip after /cro-scan): optional; see app/cro_nurture/README.md
    CRO_NURTURE_ENABLED = os.environ.get("CRO_NURTURE_ENABLED", "").strip() == "1"
    # Local/dev: after /cro-scan submit, enrich then send all sequence emails back-to-back (still real OpenAI + Brevo).
    # Only runs when Flask DEBUG is True — never enable on production debug=False.
    CRO_NURTURE_TEST_INSTANT_SEQUENCE = (
        os.environ.get("CRO_NURTURE_TEST_INSTANT_SEQUENCE", "").strip() == "1"
    )

    # CRO scan report pipeline: OpenAI for analysis, Brevo for sending the PDF. Either key name works.
    _openai_key = os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("OPEN_AI_KEY", "").strip()
    OPENAI_API_KEY = _openai_key
    OPEN_AI_KEY = _openai_key
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1"
    # Sender for transactional email (CRO report). Must be a verified sender in Brevo.
    BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "").strip() or os.environ.get("BREVO_TRANSACTIONAL_SENDER_EMAIL", "").strip()
    BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "Sparksmetrics").strip() or "Sparksmetrics"
    # Base URL for the site (used for report view links in email). No trailing slash.
    SITE_URL = (os.environ.get("SITE_URL", "").strip() or "https://sparksmetrics.com").rstrip("/")
    # Scrapfly: when set, CRO scan uses Scrapfly screenshot API (Cloudflare bypass). ~60 credits/screenshot; 100 screenshots/mo fits free or low tier.
    SCRAPFLY_API_KEY = os.environ.get("SCRAPFLY_API_KEY", "").strip()
    # Browserless: when set, CRO scan uses Browserless /unblock (Cloudflare bypass). 1000 free requests/mo. Takes precedence over Scrapfly if both set.
    BROWSERLESS_API_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "").strip()
    # Thank-you page preview: when True (default), run Cloudflare/challenge check (adds ~5–10s). Set to False for faster preview (may sometimes show challenge).
    CRO_PREVIEW_CHECK_CHALLENGE = os.environ.get("CRO_PREVIEW_CHECK_CHALLENGE", "true").strip().lower() in ("1", "true", "yes")

    # Optional: forward leads to Spark POST /api/site/lead (see Spark docs/SPARKS_SITE_BACKEND.md).
    # SPARK_BACKEND_URL — Spark base URL, no trailing slash
    # SPARK_SITE_INGEST_SECRET — must match Spark SPARK_SITE_INGEST_SECRET (header X-Spark-Site-Secret)
    # SPARK_CRO_NURTURE_CRON_TOKEN — optional; same as Spark CRO_NURTURE_CRON_TOKEN for post-scan HTTP cron kick
    # SPARK_NURTURE_ENROLLMENT_TYPES — comma-separated submission_type values that send enroll_nurture=true (see get_spark_nurture_enrollment_types)
    # SPARK_BACKGROUND_CRO_SCAN — default 1: after successful Spark ingest with a URL, run silent CRO scan → attach full_report (no report email)
    SPARK_NURTURE_ENROLLMENT_TYPES = get_spark_nurture_enrollment_types()


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
