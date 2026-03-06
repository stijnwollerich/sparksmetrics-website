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


class Config:
    """Default configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
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


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
