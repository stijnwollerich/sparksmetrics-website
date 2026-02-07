"""Application configuration."""
import os
from pathlib import Path

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root before reading env vars (so it works regardless of cwd/call order)
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

# If DATABASE_URL still not in env, read .env directly (handles encoding / path quirks)
def _get_database_uri() -> str | None:
    uri = os.environ.get("DATABASE_URL", "").strip()
    if uri:
        return uri.replace("postgres://", "postgresql://", 1)

    def _read_env(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            for line in raw.splitlines():
                line = line.strip().replace("\r", "")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == "DATABASE_URL":
                    uri = value.strip().strip("'\"").replace("\r", "").replace("postgres://", "postgresql://", 1)
                    return uri if uri else None
        except Exception:
            pass
        return None

    return _read_env(_env_file) or _read_env(Path.cwd() / ".env")


class Config:
    """Default configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    TESTING = False
    # PostgreSQL: set DATABASE_URL (e.g. postgresql://user:pass@localhost:5432/dbname)
    SQLALCHEMY_DATABASE_URI = _get_database_uri()
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


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
