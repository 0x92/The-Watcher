from flask import Blueprint

from .admin import admin_api_bp
from .crawlers import crawlers_api_bp
from .graph import graph
from .health import health
from .items import get_items
from .patterns import latest_patterns
from .heatmap import heatmap


api_bp = Blueprint("api", __name__)
api_bp.add_url_rule("/health", view_func=health)
api_bp.add_url_rule("/items", view_func=get_items)
api_bp.add_url_rule("/graph", view_func=graph)
api_bp.add_url_rule("/patterns/latest", view_func=latest_patterns)
api_bp.add_url_rule("/analytics/heatmap", view_func=heatmap)


__all__ = ["api_bp", "admin_api_bp", "crawlers_api_bp"]

