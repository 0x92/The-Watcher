from app import create_app


ROUTES = [
    ("/", "Overview"),
    ("/stream", "Stream"),
    ("/heatmap", "Heatmap"),
    ("/graph", "Graph"),
    ("/alerts", "Alerts"),
    ("/admin", "Administration"),
]


def test_ui_routes():
    app = create_app()
    client = app.test_client()
    for route, text in ROUTES:
        resp = client.get(route)
        assert resp.status_code == 200
        assert text in resp.get_data(as_text=True)
