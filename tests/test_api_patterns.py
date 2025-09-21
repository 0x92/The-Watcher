from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.models import Base, Pattern


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / "patterns_api.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    now = datetime.utcnow()
    with Session(engine) as session:
        session.add_all(
            [
                Pattern(
                    label="cyber",
                    created_at=now,
                    top_terms=["cyber", "attack"],
                    anomaly_score=0.75,
                    item_ids=[1, 2],
                    meta={"size": 2},
                ),
                Pattern(
                    label="markets",
                    created_at=now - timedelta(hours=10),
                    top_terms=["market", "stocks"],
                    anomaly_score=0.45,
                    item_ids=[3, 4, 5],
                ),
            ]
        )
        session.commit()

    engine.dispose()

    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    with app.test_client() as client:
        yield client


def test_patterns_latest_endpoint(app_client):
    response = app_client.get("/api/patterns/latest?window=48h&limit=5")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["meta"]["count"] == 2
    assert len(payload["patterns"]) == 2
    first = payload["patterns"][0]
    assert first["label"] == "cyber"
    assert "cyber" in first["top_terms"]
