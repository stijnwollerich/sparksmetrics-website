"""Sparksmetrics Flask application factory."""
from datetime import datetime

from flask import Flask

from app.routes.main import main_bp


def create_app(config_object="app.config") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)

    app.register_blueprint(main_bp)

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow}

    return app
