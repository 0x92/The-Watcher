from app.services.gematria import (
    DEFAULT_ENABLED_SCHEMES,
    compute_all,
    digital_root,
    factor_signature,
    list_available_schemes,
)


def test_compute_all_known_examples():
    text = "CAT"
    result = compute_all(text, ["ordinal", "reduction", "reverse", "reverse_reduction"])
    assert result == {
        "ordinal": 24,
        "reduction": 6,
        "reverse": 57,
        "reverse_reduction": 21,
    }


def test_compute_all_ignores_non_letters():
    text = "C4T 🎉"
    result = compute_all(text, ["ordinal", "reduction"])
    assert result == {"ordinal": 23, "reduction": 5}


def test_compute_all_unicode_normalization():
    text = "Café"
    result = compute_all(text, ["ordinal"])
    assert result == {"ordinal": 10}


def test_compute_all_empty_string():
    assert compute_all("", ["ordinal"]) == {"ordinal": 0}


def test_compute_all_additional_schemes():
    text = "CAB"
    result = compute_all(text, ["prime", "sumerian"])
    assert result == {"prime": 10, "sumerian": 36}


def test_digital_root():
    assert digital_root(942) == 6
    assert digital_root(0) == 0


def test_factor_signature():
    assert factor_signature(84) == {2: 2, 3: 1, 7: 1}
    assert factor_signature(13) == {13: 1}
    assert factor_signature(1) == {}


def test_list_available_schemes_contains_metadata():
    schemes = list_available_schemes()
    assert any(entry["key"] == "ordinal" for entry in schemes)
    assert all("label" in entry and "description" in entry for entry in schemes)


def test_default_enabled_schemes_are_known():
    available = {entry["key"] for entry in list_available_schemes()}
    for scheme in DEFAULT_ENABLED_SCHEMES:
        assert scheme in available
