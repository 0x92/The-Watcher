from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.models import Alert, Base, Event, Item, Source


def _seed(db_url: str) -> None:
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    with Session(engine) as session:
        reuters = Source(name="Reuters", type="rss", endpoint="https://example.com/rss")
        ap = Source(name="AP", type="rss", endpoint="https://example.com/ap")
        session.add_all([reuters, ap])
        session.flush()

        session.add_all(
            [
                Item(
                    source_id=reuters.id,
                    fetched_at=now - timedelta(hours=2),
                    published_at=now - timedelta(hours=2),
                    url="https://example.com/r1",
                    title="Headline 1",
                    dedupe_hash="r1",
                ),
                Item(
                    source_id=reuters.id,
                    fetched_at=now - timedelta(hours=1),
                    published_at=now - timedelta(hours=1),
                    url="https://example.com/r2",
                    title="Headline 2",
                    dedupe_hash="r2",
                ),
                Item(
                    source_id=ap.id,
                    fetched_at=now - timedelta(minutes=30),
                    published_at=now - timedelta(minutes=30),
                    url="https://example.com/a1",
                    title="AP Headline",
                    dedupe_hash="a1",
                ),
            ]
        )

        alert = Alert(name="markets", rule_yaml="when: {}", enabled=True)
        session.add(alert)
        session.flush()
        session.add(
            Event(
                alert_id=alert.id,
                triggered_at=now - timedelta(minutes=20),
                severity=3,
            )
        )
        session.commit()
    engine.dispose()


def test_heatmap_endpoint(monkeypatch, tmp_path):
    db_path = tmp_path / "heatmap.db"
    url = f"sqlite:///{db_path}"
    _seed(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/analytics/heatmap?interval=6h&value_min=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["meta"]["bucket_count"] >= 6
    assert payload["series"]
    assert any(series["source"] == "Reuters" for series in payload["series"])
    assert payload["timeline"]


def test_heatmap_endpoint_invalid_interval(monkeypatch, tmp_path):
    db_path = tmp_path / "heatmap-invalid.db"
    url = f"sqlite:///{db_path}"
    _seed(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/analytics/heatmap?interval=invalid")
    assert response.status_code == 400
    error = response.get_json()
    assert "error" in error
