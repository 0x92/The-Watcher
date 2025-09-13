"""Gematria computation utilities."""

from __future__ import annotations

import re
from typing import Dict, Iterable

from .schemes import SCHEMES


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
        mapping = SCHEMES[name]
        results[name] = sum(mapping.get(ch, 0) for ch in normalized)
    return results


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


__all__ = ["SCHEMES", "normalize", "compute_all", "digital_root", "factor_signature"]
