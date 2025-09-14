from __future__ import annotations

from opensearchpy import OpenSearch


ITEMS_INDEX = "items"


def items_index_body(*, shards: int = 1, replicas: int = 0) -> dict:
    """Return the index creation body for the items index."""

    return {
        "settings": {"number_of_shards": shards, "number_of_replicas": replicas},
        "mappings": {
            "dynamic_templates": [
                {
                    "gematria_values_ints": {
                        "path_match": "gematria_values.*",
                        "mapping": {"type": "integer"},
                    }
                }
            ],
            "properties": {
                "id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "published_at": {"type": "date"},
                "lang": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "english"},
                "url": {"type": "keyword"},
                "gematria_values": {"type": "object"},
                "tags": {"type": "keyword"},
                "author": {"type": "keyword"},
            },
        },
    }


def create_items_index(
    client: OpenSearch,
    *,
    index_name: str = ITEMS_INDEX,
    shards: int = 1,
    replicas: int = 0,
) -> None:
    """Create the items index if it does not already exist."""

    body = items_index_body(shards=shards, replicas=replicas)
    if not client.indices.exists(index=index_name):
        client.indices.create(index=index_name, body=body)


__all__ = ["ITEMS_INDEX", "items_index_body", "create_items_index"]
