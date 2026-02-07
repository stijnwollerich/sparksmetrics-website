"""Sparksmetrics Flask application factory."""
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from app.models import db
from app.routes.main import CASE_STUDIES, CASE_STUDY_ORDER, main_bp
from app.youtube import get_latest_video_ids

# Load .env from project root (parent of app/) so it works regardless of cwd
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def create_app(config_object="app.config") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)

    db.init_app(app)
    with app.app_context():
        if app.config.get("SQLALCHEMY_DATABASE_URI"):
            from app.models import Lead  # noqa: F401
            db.create_all()

    app.register_blueprint(main_bp)

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow}

    # Default video IDs when nothing is configured (so gallery always shows something)
    _DEFAULT_YT_IDS = ["BKN3rEt45Sk", "qEd0zrqFYeg"]

    @app.context_processor
    def inject_youtube_videos():
        """Inject YouTube video IDs for gallery: config list, else channel RSS, else default IDs."""
        manual_ids = app.config.get("YOUTUBE_VIDEO_IDS") or []
        if manual_ids:
            video_ids = list(manual_ids)[:12]
        else:
            channel_id = app.config.get("YOUTUBE_CHANNEL_ID") or ""
            video_ids = get_latest_video_ids(channel_id, max_results=8) if channel_id else []
        if not video_ids:
            video_ids = _DEFAULT_YT_IDS
        return {"youtube_video_ids": video_ids}

    @app.context_processor
    def inject_case_studies():
        """Inject ordered case studies for cards (homepage + results). Single source of truth."""
        case_studies_list = [
            (slug, CASE_STUDIES[slug]) for slug in CASE_STUDY_ORDER if slug in CASE_STUDIES
        ]
        return {"case_studies_list": case_studies_list}

    return app
