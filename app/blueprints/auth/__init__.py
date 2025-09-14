from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.extensions import csrf
from app.security import get_user_by_email

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
@csrf.exempt
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    user = get_user_by_email(email)
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "invalid credentials"}), 401
    login_user(user)
    return jsonify({"status": "logged_in"}), 200


@auth_bp.post("/logout")
@csrf.exempt
@login_required
def logout():
    logout_user()
    return jsonify({"status": "logged_out"}), 200


__all__ = ["auth_bp"]
