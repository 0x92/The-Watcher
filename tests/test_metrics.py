from app import create_app


def test_metrics_endpoint_counts_request():
    app = create_app()
    client = app.test_client()
    # trigger a request to create metrics
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"flask_app_requests_total" in resp.data
