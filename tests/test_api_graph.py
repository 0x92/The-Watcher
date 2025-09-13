from app import create_app
from app.blueprints.api.graph import GraphResponse


def test_graph_endpoint_returns_sample():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    data = resp.get_json()
    GraphResponse(**data)
    assert data["nodes"][0]["id"] == "uuid1"
