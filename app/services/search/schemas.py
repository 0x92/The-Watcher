from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ItemDocument(BaseModel):
    id: str
    source: str
    published_at: datetime
    lang: str | None = None
    title: str
    url: str
    gematria_values: dict[str, int] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    author: str | None = None


class Buckets(BaseModel):
    by_source: dict[str, int] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    items: list[ItemDocument]
    buckets: Buckets | None = None


__all__ = ["ItemDocument", "Buckets", "SearchResponse"]
