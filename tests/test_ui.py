from app import create_app


USERS = {
    "viewer": {"email": "viewer@example.com", "password": "viewerpass"},
    "analyst": {"email": "analyst@example.com", "password": "analystpass"},
    "admin": {"email": "admin@example.com", "password": "adminpass"},
}


def _login(client, role: str) -> None:
    creds = USERS[role]
    resp = client.post("/auth/login", json=creds)
    assert resp.status_code == 200


def test_ui_routes_require_authentication():
    app = create_app()
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code in {302, 401}


def test_ui_routes_for_admin():
    app = create_app()
    client = app.test_client()
    _login(client, "admin")
    routes = [
        ("/", "Overview"),
        ("/stream", "Stream"),
        ("/heatmap", "Heatmap"),
        ("/graph", "Graph"),
        ("/alerts", "Alerts"),
        ("/patterns", "Patterns"),
        ("/admin", "Administration"),
        ("/crawlers", "Crawler Control Center"),
    ]
    for route, text in routes:
        resp = client.get(route)
        assert resp.status_code == 200
        assert text in resp.get_data(as_text=True)


def test_role_based_access_control():
    app = create_app()
    client = app.test_client()

    _login(client, "viewer")
    assert client.get("/").status_code == 200
    assert client.get("/stream").status_code == 200
    assert client.get("/heatmap").status_code == 403
    assert client.get("/graph").status_code == 403
    assert client.get("/alerts").status_code == 403
    assert client.get("/patterns").status_code == 403
    assert client.get("/admin").status_code == 403
    assert client.get("/crawlers").status_code == 403

    client.post("/auth/logout", json={})

    _login(client, "analyst")
    assert client.get("/").status_code == 200
    assert client.get("/stream").status_code == 200
    assert client.get("/heatmap").status_code == 200
    assert client.get("/graph").status_code == 200
    assert client.get("/alerts").status_code == 200
    assert client.get("/patterns").status_code == 200
    assert client.get("/admin").status_code == 403
    assert client.get("/crawlers").status_code == 403


def test_stream_live_rejects_invalid_parameters():
    app = create_app()
    client = app.test_client()
    _login(client, "viewer")
    response = client.get("/stream/live?value=abc")
    assert response.status_code == 400
    assert "error" in response.get_json()
