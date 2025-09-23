from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.models import Alert, Base, Event, Gematria, Item, ItemTag, Source, Tag


def _seed_graph_fixture(session: Session) -> None:
    now = datetime.utcnow()

    source = Source(name="Reuters", type="rss", endpoint="https://example.com/rss", interval_sec=300)
    source_two = Source(name="AP", type="rss", endpoint="https://example.com/ap")
    tag = Tag(label="geopolitics")
    session.add_all([source, source_two, tag])
    session.flush()

    item = Item(
        source_id=source.id,
        fetched_at=now,
        published_at=now,
        url="https://example.com/news-1",
        title="Sample headline",
        dedupe_hash="hash-1",
    )
    session.add(item)
    session.flush()

    session.add(ItemTag(item_id=item.id, tag_id=tag.id, weight=2.0))
    session.add(Gematria(item_id=item.id, scheme="simple", value=93))

    alert_rule = """
when:
  all:
    - scheme: simple
      value_in: [93]
    - source_in: ["Reuters"]
    - window: { period: "24h", min_count: 1 }
"""
    alert = Alert(name="reuters_93", enabled=True, rule_yaml=alert_rule)
    session.add(alert)
    session.flush()

    session.add(Event(alert_id=alert.id, triggered_at=now, severity=2))
    session.commit()


def test_graph_endpoint_returns_expected_structure(tmp_path, monkeypatch):
    db_path = tmp_path / "graph.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_graph_fixture(session)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/graph?window=48h&limit=10")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["meta"]["window"] == "48h"
    assert payload["meta"]["limit"] == 10
    assert payload["nodes"]
    assert payload["edges"]

    kinds = {node["kind"] for node in payload["nodes"]}
    assert kinds == {"source", "tag", "alert"}

    node_ids = {node["id"] for node in payload["nodes"]}
    assert "source:1" in node_ids
    assert "tag:1" in node_ids
    assert "alert:1" in node_ids

    edge_kinds = {edge["kind"] for edge in payload["edges"]}
    assert "source_tag" in edge_kinds
    assert "source_alert" in edge_kinds

    engine.dispose()


def test_graph_endpoint_role_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "graph_roles.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_graph_fixture(session)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()
    response = client.get("/api/graph?role=source&limit=5")
    data = response.get_json()

    assert all(node["kind"] == "source" for node in data["nodes"])
    assert not data["edges"]

    engine.dispose()
