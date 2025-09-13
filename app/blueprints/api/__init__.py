from flask import Blueprint

from .graph import graph
from .health import health
from .items import get_items


api_bp = Blueprint("api", __name__)
api_bp.add_url_rule("/health", view_func=health)
api_bp.add_url_rule("/items", view_func=get_items)
api_bp.add_url_rule("/graph", view_func=graph)


__all__ = ["api_bp"]

