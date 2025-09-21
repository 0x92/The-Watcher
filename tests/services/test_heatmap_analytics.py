from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Alert, Base, Event, Item, Source
from app.services.analytics.heatmap import compute_heatmap


def _setup_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_item(session: Session, source: Source, minutes_ago: int, *, title: str = "headline") -> None:
    fetched = datetime.utcnow() - timedelta(minutes=minutes_ago)
    session.add(
        Item(
            source_id=source.id,
            fetched_at=fetched,
            published_at=fetched,
            url=f"https://example.com/{source.name}/{minutes_ago}",
            title=title,
            dedupe_hash=f"{source.name}-{minutes_ago}",
        )
    )


def test_compute_heatmap_counts_and_buckets():
    session = _setup_session()

    source = Source(name="Reuters", type="rss", endpoint="https://example.com/rss")
    other = Source(name="AP", type="rss", endpoint="https://example.com/ap")
    session.add_all([source, other])
    session.flush()

    _add_item(session, source, minutes_ago=30)
    _add_item(session, source, minutes_ago=90)
    _add_item(session, other, minutes_ago=15)
    session.commit()

    alert = Alert(name="cyber", rule_yaml="when: {}", enabled=True)
    session.add(alert)
    session.flush()
    session.add(
        Event(alert_id=alert.id, triggered_at=datetime.utcnow() - timedelta(minutes=10), severity=2)
    )
    session.commit()

    result = compute_heatmap(session, interval="6h", value_min=0)

    assert result.meta["bucket_count"] >= 6
    sources = {series.source: series.total for series in result.series}
    assert sources["Reuters"] == 2
    assert sources["AP"] == 1
    assert result.timeline

    session.close()


def test_compute_heatmap_source_filter_and_threshold():
    session = _setup_session()

    reuters = Source(name="Reuters", type="rss", endpoint="https://example.com/rss")
    ap = Source(name="AP", type="rss", endpoint="https://example.com/ap")
    session.add_all([reuters, ap])
    session.flush()

    _add_item(session, reuters, minutes_ago=20)
    _add_item(session, reuters, minutes_ago=40)
    _add_item(session, ap, minutes_ago=10)
    session.commit()

    result = compute_heatmap(session, interval="6h", sources=["Reuters"], value_min=2)
    assert len(result.series) == 1
    assert result.series[0].source == "Reuters"
    assert result.series[0].total == 2

    result_filtered = compute_heatmap(session, interval="6h", sources=["Reuters"], value_min=3)
    assert result_filtered.series == []

    session.close()

