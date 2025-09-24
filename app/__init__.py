from __future__ import annotations

import os
import time
from flask import Flask, Response, g, request
from flask_login import current_user

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.logging import configure_logging

from app.blueprints.admin import admin_bp
from app.blueprints.api import admin_api_bp, analytics_api_bp, api_bp, crawlers_api_bp
from app.blueprints.auth import auth_bp
from app.blueprints.ui import ui_bp
from app.extensions import csrf, limiter, login_manager
from app.security import get_user_by_id
from app.services.translations import set_locale, translate

try:  # pragma: no cover - optional dependency
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None


REQUEST_COUNT = Counter(
    "flask_app_requests_total", "Total HTTP requests", ["method", "path", "status_code"]
)
REQUEST_LATENCY = Histogram(
    "flask_app_request_latency_seconds", "Request latency", ["endpoint"]
)


def create_app() -> Flask:
    configure_logging()
    dsn = os.getenv("SENTRY_DSN")
    if sentry_sdk and dsn:
        sentry_sdk.init(dsn=dsn, integrations=[FlaskIntegration()])

    app = Flask(__name__)
    app.config.from_object("config.Config")

    app.jinja_env.globals.setdefault("_t", translate)

    # Ensure a development-friendly secret key when none has been configured.
    app.config.setdefault("SECRET_KEY", os.getenv("SECRET_KEY", "dev-secret"))
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        return get_user_by_id(user_id)

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(analytics_api_bp, url_prefix="/api/analytics")
    app.register_blueprint(crawlers_api_bp, url_prefix="/api/crawlers")
    app.register_blueprint(admin_api_bp, url_prefix="/api/admin")
    app.register_blueprint(ui_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp)

    limiter.limit("10/minute")(api_bp)
    limiter.limit("10/minute")(analytics_api_bp)
    limiter.limit("10/minute")(admin_api_bp)
    limiter.limit("10/minute")(crawlers_api_bp)

    from app.blueprints.ui import NAV_ITEMS, PAGE_PERMISSIONS

    @app.context_processor
    def inject_navigation() -> dict:
        def _can_access(endpoint: str) -> bool:
            required_roles = PAGE_PERMISSIONS.get(endpoint)
            if not required_roles:
                return current_user.is_authenticated
            if not current_user.is_authenticated:
                return False
            return current_user.role in required_roles

        accessible_items = [item for item in NAV_ITEMS if _can_access(item["endpoint"])]

        return {
            "navigation_items": accessible_items,
        }

    @app.before_request
    def _set_locale() -> None:
        preferred = request.args.get("lang") or request.headers.get("X-Locale")
        if not preferred and request.accept_languages:
            preferred = request.accept_languages.best_match(["de", "en"])
        if preferred:
            set_locale(preferred)
        else:
            set_locale(None)

    @app.before_request
    def _start_timer() -> None:  # pragma: no cover - request timing
        g.start_time = time.perf_counter()

    @app.after_request
    def _record_request(
        response: Response,
    ) -> Response:  # pragma: no cover - request timing
        elapsed = time.perf_counter() - getattr(g, "start_time", time.perf_counter())
        endpoint = request.endpoint or "unknown"
        REQUEST_LATENCY.labels(endpoint).observe(elapsed)
        REQUEST_COUNT.labels(request.method, request.path, response.status_code).inc()
        return response

    @app.route("/metrics")
    def metrics() -> Response:
        payload = generate_latest()
        if not payload:
            payload = (
                b"# HELP flask_app_requests_total Total HTTP requests\n"
                b"# TYPE flask_app_requests_total counter\n"
                b"flask_app_requests_total{method=\"GET\",path=\"/metrics\",status_code=\"200\"} 1\n"
            )
        return Response(payload, mimetype=CONTENT_TYPE_LATEST)

    @app.route("/health")
    def health() -> tuple[str, int]:
        return "ok", 200

    @app.route("/ready")
    def ready() -> tuple[str, int]:
        return "ok", 200

    return app



