from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Alert, Base, Event, Gematria, Item, Source
from app.services.alerts import evaluate_alerts


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_evaluate_alerts_triggers_event():
    session = _session()
    src = Source(name="Reuters", type="rss", endpoint="http://example.com")
    session.add(src)
    session.flush()

    alert_rule = """
    when:
      all:
        - scheme: simple
          value_in: [93]
        - source_in: ["Reuters"]
        - window: { period: "24h", min_count: 1 }
    """
    alert = Alert(name="reuters_93", rule_yaml=alert_rule)
    session.add(alert)
    session.flush()

    item = Item(source_id=src.id, url="http://item")
    session.add(item)
    session.flush()
    gem = Gematria(item_id=item.id, scheme="simple", value=93)
    session.add(gem)
    session.commit()

    triggered = evaluate_alerts(session)

    assert triggered == 1
    events = session.scalars(select(Event)).all()
    assert len(events) == 1
    assert events[0].alert_id == alert.id


def test_evaluate_alerts_no_match():
    session = _session()
    src = Source(name="Reuters", type="rss", endpoint="http://example.com")
    session.add(src)
    session.flush()

    alert_rule = """
    when:
      all:
        - scheme: simple
          value_in: [93]
        - source_in: ["Reuters"]
        - window: { period: "24h", min_count: 1 }
    """
    alert = Alert(name="reuters_93", rule_yaml=alert_rule)
    session.add(alert)
    session.commit()

    triggered = evaluate_alerts(session)

    assert triggered == 0
    assert session.scalars(select(Event)).first() is None
