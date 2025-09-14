from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict


class GraphNode(BaseModel):
    id: str
    title: str
    value: int


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(..., alias="from")
    to: str
    weight: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def graph() -> tuple[dict, int]:
    sample = GraphResponse(
        nodes=[GraphNode(id="uuid1", title="...", value=93)],
        edges=[GraphEdge(from_="uuid1", to="uuid2", weight=0.8)],
    )
    return sample.model_dump(by_alias=True), 200


__all__ = ["GraphNode", "GraphEdge", "GraphResponse", "graph"]
