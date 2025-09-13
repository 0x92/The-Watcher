from app.services.search import items_index_body


def test_items_index_body_structure():
    body = items_index_body()
    assert body["settings"] == {"number_of_shards": 1, "number_of_replicas": 0}
    props = body["mappings"]["properties"]
    assert props["id"]["type"] == "keyword"
    assert props["title"]["analyzer"] == "english"
    assert props["published_at"]["type"] == "date"
    templates = body["mappings"]["dynamic_templates"]
    assert templates[0]["gematria_values_ints"]["path_match"] == "gematria_values.*"
