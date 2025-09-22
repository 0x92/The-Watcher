"""Gematria letter mappings for various schemes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class SchemeDefinition:
    """Metadata and mapping for a gematria scheme."""

    key: str
    label: str
    description: str
    mapping: Dict[str, int]


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


def _build_prime() -> Dict[str, int]:
    primes = [
        2,
        3,
        5,
        7,
        11,
        13,
        17,
        19,
        23,
        29,
        31,
        37,
        41,
        43,
        47,
        53,
        59,
        61,
        67,
        71,
        73,
        79,
        83,
        89,
        97,
        101,
    ]
    return {chr(ord("A") + i): primes[i] for i in range(26)}


def _build_sumerian() -> Dict[str, int]:
    ordinal = _build_ordinal()
    return {ch: val * 6 for ch, val in ordinal.items()}


SCHEME_DEFINITIONS: Dict[str, SchemeDefinition] = {
    "ordinal": SchemeDefinition(
        key="ordinal",
        label="Ordinal",
        description="Klassische Zuordnung A=1 … Z=26.",
        mapping=_build_ordinal(),
    ),
    "reduction": SchemeDefinition(
        key="reduction",
        label="Pythagoräisch",
        description="Reduktion der Ordinalwerte auf einstellige Zahlen (1–9).",
        mapping=_build_reduction(),
    ),
    "reverse": SchemeDefinition(
        key="reverse",
        label="Reverse Ordinal",
        description="Spiegelung: Z=1 … A=26.",
        mapping=_build_reverse(),
    ),
    "reverse_reduction": SchemeDefinition(
        key="reverse_reduction",
        label="Reverse Pythagoräisch",
        description="Reduktion der gespiegelten Ordinalwerte auf 1–9.",
        mapping=_build_reverse_reduction(),
    ),
    "prime": SchemeDefinition(
        key="prime",
        label="Primzahlen",
        description="Zuweisung der ersten 26 Primzahlen (A=2 … Z=101).",
        mapping=_build_prime(),
    ),
    "sumerian": SchemeDefinition(
        key="sumerian",
        label="Sumerisch",
        description="Ordinalwerte multipliziert mit 6 (A=6 … Z=156).",
        mapping=_build_sumerian(),
    ),
}


SCHEMES: Dict[str, Dict[str, int]] = {
    key: definition.mapping for key, definition in SCHEME_DEFINITIONS.items()
}


DEFAULT_ENABLED_SCHEMES: Tuple[str, ...] = (
    "ordinal",
    "reduction",
    "reverse",
)


def available_scheme_metadata() -> Iterable[SchemeDefinition]:
    """Return scheme definitions sorted by label for display purposes."""

    return sorted(SCHEME_DEFINITIONS.values(), key=lambda definition: definition.label)


__all__ = [
    "DEFAULT_ENABLED_SCHEMES",
    "SCHEMES",
    "SCHEME_DEFINITIONS",
    "SchemeDefinition",
    "available_scheme_metadata",
]
