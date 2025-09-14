from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Alert, Base, Source
from scripts import seed_sources


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_seed_demo_data_creates_sources_and_alert():
    session = _session()
    seed_sources.main(session=session)

    sources = session.query(Source).all()
    assert len(sources) == 4
    names = {s.name for s in sources}
    assert {"Reuters", "Associated Press", "Mastodon #news", "YouTube Channel"} == names

    alerts = session.query(Alert).all()
    assert len(alerts) == 1
    assert "value_in: [93]" in alerts[0].rule_yaml
