from __future__ import annotations

from urllib.parse import urljoin, urlparse

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.extensions import csrf
from app.security import get_user_by_email

auth_bp = Blueprint("auth", __name__)


def _is_safe_redirect(target: str) -> bool:
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in {"http", "https"} and ref_url.netloc == test_url.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf.exempt
def login():
    if request.method == "GET":
        if current_user.is_authenticated:
            return redirect(url_for("ui.overview"))
        next_url = request.args.get("next")
        return render_template("ui/login.html", error=None, next_url=next_url)

    if request.is_json:
        data = request.get_json() or {}
        email = data.get("email")
        password = data.get("password")
        user = get_user_by_email(email)
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "invalid credentials"}), 401
        login_user(user)
        return jsonify({"status": "logged_in"}), 200

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    next_url = request.form.get("next") or request.args.get("next")
    user = get_user_by_email(email)
    if not user or not check_password_hash(user.password_hash, password):
        return (
            render_template(
                "ui/login.html",
                error="Ungültige Zugangsdaten. Bitte erneut versuchen.",
                next_url=next_url,
            ),
            401,
        )

    login_user(user)
    if next_url and _is_safe_redirect(next_url):
        return redirect(next_url)
    return redirect(url_for("ui.overview"))


@auth_bp.post("/logout")
@csrf.exempt
@login_required
def logout():
    logout_user()
    if request.is_json:
        return jsonify({"status": "logged_out"}), 200
    next_url = request.form.get("next") or request.args.get("next")
    if next_url and _is_safe_redirect(next_url):
        return redirect(next_url)
    return redirect(url_for("auth.login"))


__all__ = ["auth_bp"]
