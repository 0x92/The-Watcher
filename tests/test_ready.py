from app import create_app


def test_ready_endpoint():
    app = create_app()
    client = app.test_client()
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.data == b"ok"
