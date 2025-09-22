"""Gematria computation utilities."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

from .schemes import (
    DEFAULT_ENABLED_SCHEMES,
    SCHEMES,
    available_scheme_metadata,
)


def normalize(text: str, *, ignore_pattern: str = r"[^A-Z]") -> str:
    """Normalize text by uppercasing and removing characters matching ignore_pattern."""
    pattern = re.compile(ignore_pattern)
    return pattern.sub("", text.upper())


def compute_all(
    text: str,
    schemes: Iterable[str] | None = None,
    *,
    ignore_pattern: str = r"[^A-Z]",
) -> Dict[str, int]:
    """Compute gematria values for ``text`` across ``schemes``."""
    if schemes is None:
        schemes = SCHEMES.keys()
    normalized = normalize(text, ignore_pattern=ignore_pattern)
    results: Dict[str, int] = {}
    for name in schemes:
        mapping = SCHEMES.get(name)
        if mapping is None:
            continue
        results[name] = sum(mapping.get(ch, 0) for ch in normalized)
    return results


def list_available_schemes() -> List[Dict[str, str]]:
    """Return metadata describing the configured gematria schemes."""

    return [
        {
            "key": definition.key,
            "label": definition.label,
            "description": definition.description,
        }
        for definition in available_scheme_metadata()
    ]


def digital_root(n: int) -> int:
    """Return the digital root of ``n`` (iterative sum of digits)."""
    n = abs(n)
    while n >= 10:
        n = sum(int(d) for d in str(n))
    return n


def factor_signature(n: int) -> Dict[int, int]:
    """Return the prime factorization of ``n`` as a mapping prime→count."""
    n = abs(n)
    factors: Dict[int, int] = {}
    divisor = 2
    while divisor * divisor <= n:
        while n % divisor == 0:
            factors[divisor] = factors.get(divisor, 0) + 1
            n //= divisor
        divisor += 1
    if n > 1:
        factors[n] = factors.get(n, 0) + 1
    return factors


__all__ = [
    "DEFAULT_ENABLED_SCHEMES",
    "SCHEMES",
    "compute_all",
    "digital_root",
    "factor_signature",
    "list_available_schemes",
    "normalize",
]
