import pytest

from app.services.gematria import compute_all, digital_root, factor_signature


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


def test_digital_root():
    assert digital_root(942) == 6
    assert digital_root(0) == 0


def test_factor_signature():
    assert factor_signature(84) == {2: 2, 3: 1, 7: 1}
    assert factor_signature(13) == {13: 1}
    assert factor_signature(1) == {}
