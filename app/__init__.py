from __future__ import annotations

import os
from flask import Flask

from app.blueprints.admin import admin_bp
from app.blueprints.api import api_bp
from app.blueprints.auth import auth_bp
from app.blueprints.ui import ui_bp
from app.extensions import csrf, limiter, login_manager
from app.security import get_user_by_id


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        return get_user_by_id(user_id)

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp)

    limiter.limit("10/minute")(api_bp)

    @app.route("/health")
    def health() -> tuple[str, int]:
        return "ok", 200

    return app
