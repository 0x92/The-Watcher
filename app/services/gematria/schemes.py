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


def _alphabet_mapping(values: Iterable[int]) -> Dict[str, int]:
    return {chr(ord("A") + index): int(value) for index, value in enumerate(values)}


SCHEME_DEFINITIONS: Dict[str, SchemeDefinition] = {
    "english_sumerian": SchemeDefinition(
        key="english_sumerian",
        label="English (6er-Schritte)",
        description="Multiplikation der Ordinalwerte mit 6 (A=6, Z=156).",
        mapping=_alphabet_mapping([6 * (i + 1) for i in range(26)]),
    ),
    "simple": SchemeDefinition(
        key="simple",
        label="Simple",
        description="Einfache Ordinalwerte A=1 bis Z=26.",
        mapping=_alphabet_mapping(range(1, 27)),
    ),
    "unknown": SchemeDefinition(
        key="unknown",
        label="Unknown",
        description="Konstante Offsets beginnend bei 99.",
        mapping=_alphabet_mapping([99 + i for i in range(26)]),
    ),
    "pythagoras": SchemeDefinition(
        key="pythagoras",
        label="Pythagoras",
        description="Benutzerdefinierte pythagoräische Zuordnung.",
        mapping=_alphabet_mapping([1, 2, 3, 4, 5, 6, 7, 8, 9, 1, 11, 3, 4, 5, 6, 7, 8, 9, 10, 2, 3, 22, 5, 6, 7, 8]),
    ),
    "jewish": SchemeDefinition(
        key="jewish",
        label="Jewish",
        description="Traditionelle jüdische Gematria-Werte.",
        mapping=_alphabet_mapping([1, 2, 3, 4, 5, 6, 7, 8, 9, 600, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 700, 900, 300, 400, 500]),
    ),
    "prime": SchemeDefinition(
        key="prime",
        label="Prime",
        description="Zuordnung der ersten 26 Primzahlen.",
        mapping=_alphabet_mapping([2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101]),
    ),
    "reverse_satanic": SchemeDefinition(
        key="reverse_satanic",
        label="Reverse Satanic",
        description="Absteigende Werte von 61 bis 36.",
        mapping=_alphabet_mapping(range(61, 35, -1)),
    ),
    "clock": SchemeDefinition(
        key="clock",
        label="Clock",
        description="Uhrwerte 1–12 wiederholend.",
        mapping=_alphabet_mapping([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]),
    ),
    "reverse_clock": SchemeDefinition(
        key="reverse_clock",
        label="Reverse Clock",
        description="Uhrwerte rückwärts von 12 nach 1.",
        mapping=_alphabet_mapping([2, 1, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]),
    ),
    "system9": SchemeDefinition(
        key="system9",
        label="System 9",
        description="Neuner-System mit 9er-Schritten (A=9).",
        mapping=_alphabet_mapping([9 * (i + 1) for i in range(26)]),
    ),
}


SCHEMES: Dict[str, Dict[str, int]] = {key: definition.mapping for key, definition in SCHEME_DEFINITIONS.items()}


DEFAULT_ENABLED_SCHEMES: Tuple[str, ...] = tuple(SCHEME_DEFINITIONS.keys())


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
