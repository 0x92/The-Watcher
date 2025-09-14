from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import login_required

from app.security import role_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admin/panel")
@login_required
@role_required("admin")
def admin_panel() -> tuple[dict, int]:
    return jsonify({"status": "admin ok"}), 200


__all__ = ["admin_bp"]
