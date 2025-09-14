from app import create_app


def test_admin_route_requires_login():
    app = create_app()
    client = app.test_client()

    resp = client.get("/admin/panel")
    assert resp.status_code in {302, 401, 403}

    login_resp = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "adminpass"}
    )
    assert login_resp.status_code == 200

    resp2 = client.get("/admin/panel")
    assert resp2.status_code == 200
    assert resp2.get_json() == {"status": "admin ok"}
