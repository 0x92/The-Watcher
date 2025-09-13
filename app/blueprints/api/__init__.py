from flask import Blueprint

from .graph import graph


api_bp = Blueprint("api", __name__)
api_bp.add_url_rule("/graph", view_func=graph)


__all__ = ["api_bp"]

