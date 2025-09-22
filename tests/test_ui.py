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


def test_stream_live_rejects_invalid_parameters():
    app = create_app()
    client = app.test_client()
    response = client.get("/stream/live?value=abc")
    assert response.status_code == 400
    assert "error" in response.get_json()
