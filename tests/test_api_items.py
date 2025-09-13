from app import create_app
from app.blueprints.api.items import ItemsResponse


def test_items_endpoint_returns_empty_list():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/items")
    assert resp.status_code == 200
    data = resp.get_json()
    ItemsResponse(**data)
    assert data["items"] == []
