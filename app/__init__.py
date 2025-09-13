from flask import Flask

from app.blueprints.api import api_bp
from app.blueprints.ui import ui_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)

    @app.route("/health")
    def health() -> tuple[str, int]:
        return "ok", 200

    return app
