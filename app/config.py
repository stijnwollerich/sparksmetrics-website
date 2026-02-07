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

# Then load_dotenv for any vars not in our read (e.g. multi-line or other formats)
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except Exception:
        pass


def _get_database_uri() -> str | None:
    uri = os.environ.get("DATABASE_URL", "").strip()
    if uri:
        return uri.replace("postgres://", "postgresql://", 1)
    return None


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
