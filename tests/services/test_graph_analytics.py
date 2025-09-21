from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Alert, Base, Event, Gematria, Item, ItemTag, Source, Tag
from app.services.analytics import GraphResponse, build_graph


def _seed_graph(session: Session, now: datetime) -> None:
    source = Source(name="Reuters", type="rss", endpoint="https://example.com/rss")
    tag = Tag(label="geopolitics")
    session.add_all([source, tag])
    session.flush()

    recent_item = Item(
        source_id=source.id,
        fetched_at=now,
        published_at=now,
        url="https://example.com/item-1",
        title="Recent headline",
        dedupe_hash="recent",
    )
    old_item = Item(
        source_id=source.id,
        fetched_at=now - timedelta(days=3),
        published_at=now - timedelta(days=3),
        url="https://example.com/item-old",
        title="Old headline",
        dedupe_hash="old",
    )
    session.add_all([recent_item, old_item])
    session.flush()

    session.add(ItemTag(item_id=recent_item.id, tag_id=tag.id, weight=1.5))
    session.add(ItemTag(item_id=old_item.id, tag_id=tag.id, weight=4.0))

    session.add(Gematria(item_id=recent_item.id, scheme="ordinal", value=93))

    alert_rule = """
when:
  all:
    - scheme: ordinal
      value_in: [93]
    - source_in: ["Reuters"]
"""
    alert = Alert(name="ordinal_93", rule_yaml=alert_rule, enabled=True)
    session.add(alert)
    session.flush()

    session.add(Event(alert_id=alert.id, triggered_at=now, severity=2))
    session.commit()


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_build_graph_filters_since_window():
    session = _create_session()
    now = datetime.utcnow()
    _seed_graph(session, now)

    result: GraphResponse = build_graph(session, since=now - timedelta(days=1))

    node_map = {node.id: node for node in result.nodes}
    assert node_map["source:1"].value == 1
    assert node_map["tag:1"].value == 1
    assert node_map["alert:1"].value == 1

    edge_kinds = {edge.kind for edge in result.edges}
    assert edge_kinds == {"source_tag", "source_alert"}

    session.close()


def test_build_graph_no_since_includes_all():
    session = _create_session()
    now = datetime.utcnow()
    _seed_graph(session, now)

    result = build_graph(session)
    node_map = {node.id: node for node in result.nodes}

    assert node_map["source:1"].value == 2
    assert node_map["tag:1"].value == 2

    session.close()