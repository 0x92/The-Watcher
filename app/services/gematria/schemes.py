from __future__ import annotations

"""Gematria letter mappings for various schemes."""

from typing import Dict


def _build_ordinal() -> Dict[str, int]:
    return {chr(ord("A") + i): i + 1 for i in range(26)}


def _build_reduction() -> Dict[str, int]:
    ordinal = _build_ordinal()
    return {ch: (val - 1) % 9 + 1 for ch, val in ordinal.items()}


def _build_reverse() -> Dict[str, int]:
    return {chr(ord("Z") - i): i + 1 for i in range(26)}


def _build_reverse_reduction() -> Dict[str, int]:
    reverse = _build_reverse()
    return {ch: (val - 1) % 9 + 1 for ch, val in reverse.items()}


SCHEMES: Dict[str, Dict[str, int]] = {
    "ordinal": _build_ordinal(),
    "reduction": _build_reduction(),
    "reverse": _build_reverse(),
    "reverse_reduction": _build_reverse_reduction(),
}


__all__ = ["SCHEMES"]
