from app.services.gematria import (
    DEFAULT_ENABLED_SCHEMES,
    compute_all,
    digital_root,
    factor_signature,
    list_available_schemes,
)


def test_compute_all_known_examples():
    text = "CAT"
    result = compute_all(text, ["simple", "english_sumerian", "reverse_satanic"])
    assert result == {
        "simple": 24,
        "english_sumerian": 144,
        "reverse_satanic": 162,
    }


def test_compute_all_ignores_non_letters():
    text = "C4T -YZ%"
    result = compute_all(text, ["simple", "unknown"])
    assert result == {
        "simple": 74,
        "unknown": 466,
    }


def test_compute_all_unicode_normalization():
    text = "CafǸ"
    result = compute_all(text, ["simple"])
    assert result == {"simple": 10}


def test_compute_all_empty_string():
    assert compute_all("", ["simple"]) == {"simple": 0}


def test_compute_all_additional_schemes():
    text = "CAB"
    result = compute_all(text, ["prime", "clock"])
    assert result == {"prime": 10, "clock": 6}


def test_digital_root():
    assert digital_root(942) == 6
    assert digital_root(0) == 0


def test_factor_signature():
    assert factor_signature(84) == {2: 2, 3: 1, 7: 1}
    assert factor_signature(13) == {13: 1}
    assert factor_signature(1) == {}


def test_list_available_schemes_contains_metadata():
    schemes = list_available_schemes()
    assert any(entry["key"] == "simple" for entry in schemes)
    assert all("label" in entry and "description" in entry for entry in schemes)


def test_default_enabled_schemes_are_known():
    available = {entry["key"] for entry in list_available_schemes()}
    assert set(DEFAULT_ENABLED_SCHEMES).issubset(available)
