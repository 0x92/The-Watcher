from flask import Blueprint, render_template

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
def overview():
    return render_template('ui/overview.html')

@ui_bp.route('/stream')
def stream():
    return render_template('ui/stream.html')

@ui_bp.route('/heatmap')
def heatmap():
    return render_template('ui/heatmap.html')

@ui_bp.route('/graph')
def graph():
    return render_template('ui/graph.html')

@ui_bp.route('/alerts')
def alerts():
    return render_template('ui/alerts.html')

@ui_bp.route('/admin')
def admin():
    return render_template('ui/admin.html')
