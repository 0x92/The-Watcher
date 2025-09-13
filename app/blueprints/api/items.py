from flask import request
from pydantic import BaseModel, Field


class Item(BaseModel):
    """Simplified item representation."""

    id: int | None = None
    title: str | None = None
    value: int | None = None


class ItemsResponse(BaseModel):
    items: list[Item] = Field(default_factory=list)


def get_items() -> tuple[dict, int]:
    """Return a list of items.

    Currently returns an empty list and ignores filters.
    """
    # query parameters can be accessed via request.args if needed
    response = ItemsResponse()
    return response.model_dump(), 200


__all__ = ["Item", "ItemsResponse", "get_items"]
