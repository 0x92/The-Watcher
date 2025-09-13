from pathlib import Path
import json

from app.services.search import items_index_body, SearchResponse


def test_items_index_body_structure():
    body = items_index_body()
    assert body["settings"] == {"number_of_shards": 1, "number_of_replicas": 0}
    props = body["mappings"]["properties"]
    assert props["id"]["type"] == "keyword"
    assert props["title"]["analyzer"] == "english"
    assert props["published_at"]["type"] == "date"
    templates = body["mappings"]["dynamic_templates"]
    assert templates[0]["gematria_values_ints"]["path_match"] == "gematria_values.*"


def test_search_response_example_validates():
    example_path = Path("app/services/search/search_response_example.json")
    data = json.loads(example_path.read_text())
    resp = SearchResponse(**data)
    assert resp.items[0].source == "Reuters"
