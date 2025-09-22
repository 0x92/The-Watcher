from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
    Index,
    Float,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_sec: Mapped[int] = mapped_column(Integer, default=0)
    auth_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    filters_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[List["Item"]] = relationship("Item", back_populates="source")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("url"),
        Index("ix_item_published_at", "published_at"),
        Index("ix_item_dedupe_hash", "dedupe_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(String(255))
    lang: Mapped[Optional[str]] = mapped_column(String(8))
    dedupe_hash: Mapped[Optional[str]] = mapped_column(String(64))
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON)

    source: Mapped["Source"] = relationship("Source", back_populates="items")
    gematria: Mapped[List["Gematria"]] = relationship("Gematria", back_populates="item")
    item_tags: Mapped[List["ItemTag"]] = relationship("ItemTag", back_populates="item")


class Gematria(Base):
    __tablename__ = "gematria"
    __table_args__ = (
        Index("ix_gematria_value", "value"),
        Index("ix_gematria_scheme", "scheme"),
    )

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    scheme: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    normalized_title: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped["Item"] = relationship("Item", back_populates="gematria")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    item_tags: Mapped[List["ItemTag"]] = relationship("ItemTag", back_populates="tag")


class ItemTag(Base):
    __tablename__ = "item_tags"
    __table_args__ = (UniqueConstraint("item_id", "tag_id"),)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    item: Mapped["Item"] = relationship("Item", back_populates="item_tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="item_tags")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rule_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    last_eval_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notify_json: Mapped[Optional[dict]] = mapped_column(JSON)
    severity: Mapped[Optional[int]] = mapped_column(Integer)

    events: Mapped[List["Event"]] = relationship("Event", back_populates="alert")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON)
    severity: Mapped[Optional[int]] = mapped_column(Integer)

    alert: Mapped["Alert"] = relationship("Alert", back_populates="events")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value_json: Mapped[Optional[dict]] = mapped_column(JSON)

class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    top_terms: Mapped[Optional[list[str]]] = mapped_column(JSON)
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float)
    item_ids: Mapped[Optional[list[int]]] = mapped_column(JSON)
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
