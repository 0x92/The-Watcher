from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Base,
    Event,
    Gematria,
    Item,
    ItemTag,
    Setting,
    Source,
    Tag,
    User,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_item_unique_url(session: Session):
    src = Source(name="rss", type="rss", endpoint="http://ex")
    session.add(src)
    session.commit()

    first = Item(source_id=src.id, url="http://example.com")
    session.add(first)
    session.commit()

    second = Item(source_id=src.id, url="http://example.com")
    session.add(second)
    with pytest.raises(IntegrityError):
        session.commit()
        session.rollback()


def test_gematria_relationship(session: Session):
    src = Source(name="rss", type="rss", endpoint="http://ex")
    session.add(src)
    session.flush()

    item = Item(source_id=src.id, url="http://x")
    session.add(item)
    session.flush()

    gem = Gematria(item_id=item.id, scheme="ordinal", value=42)
    session.add(gem)
    session.commit()

    session.refresh(item)
    fetched = session.get(Gematria, (item.id, "ordinal"))
    assert fetched is not None
    assert fetched.item.id == item.id
    assert fetched.scheme == "ordinal"
    assert fetched.value == 42
    assert len(item.gematria) == 1


def test_tag_association(session: Session):
    src = Source(name="rss", type="rss", endpoint="http://ex")
    tag = Tag(label="news")
    session.add_all([src, tag])
    session.flush()

    item = Item(source_id=src.id, url="http://a")
    session.add(item)
    session.flush()

    link = ItemTag(item_id=item.id, tag_id=tag.id, weight=0.5)
    session.add(link)
    session.commit()

    assert item.item_tags[0].tag.label == "news"


def test_alert_event_user_setting(session: Session):
    alert = Alert(name="a", rule_yaml="{}")
    session.add(alert)
    session.flush()

    event = Event(alert_id=alert.id, triggered_at=datetime.utcnow())
    user = User(email="u@example.com", password_hash="hash")
    setting = Setting(key="k", value_json={"a": 1})
    session.add_all([event, user, setting])
    session.commit()

    assert event.alert_id == alert.id
    assert user.email == "u@example.com"
    assert session.get(Setting, "k").value_json["a"] == 1
