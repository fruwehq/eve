"""Minimal semver range matcher for plugin ``requires`` core gate.

Supports the range forms relevant to ``requires.eve`` and ``requires.plugins``:

- Exact: ``"4.0"``, ``"4.0.0"``
- Caret: ``"^4.0"`` (``>=4.0.0,<5.0.0`` for major >= 1)
- Tilde: ``"~4.0"`` (``>=4.0.0,<4.1.0``)
- Comparison: ``">=4.0"``, ``"<5.0"``, ``">4.0"``, ``"<=5.0"``, ``"=4.0"``
- Comma-separated AND: ``">=4.0,<5.0"``
"""

from __future__ import annotations

import re

__all__ = ["SemverError", "parse_version", "satisfies"]

_CONSTRAINT_RE = re.compile(r"^(>=|<=|>|<|=|\^|~)?\s*(.+)$")
_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


class SemverError(ValueError):
    """Raised when a version or range string cannot be parsed."""


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse ``"1.2.3"`` / ``"1.2"`` / ``"1"`` into a ``(major, minor, patch)`` tuple."""
    match = _VERSION_RE.match(text.strip())
    if not match:
        raise SemverError(f"invalid version: {text!r}")
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) is not None else 0
    patch = int(match.group(3)) if match.group(3) is not None else 0
    return (major, minor, patch)


# Backwards-compatible private alias (the matcher uses this name internally).
_parse_version = parse_version


def _expand_caret(ver: tuple[int, int, int]) -> list[tuple[str, tuple[int, int, int]]]:
    major, minor, patch = ver
    if major > 0:
        upper = (major + 1, 0, 0)
    elif minor > 0:
        upper = (0, minor + 1, 0)
    else:
        upper = (0, 0, patch + 1)
    return [(">=", ver), ("<", upper)]


def _expand_tilde(ver: tuple[int, int, int]) -> list[tuple[str, tuple[int, int, int]]]:
    upper = (ver[0], ver[1] + 1, 0)
    return [(">=", ver), ("<", upper)]


def _parse_range(range_str: str) -> list[tuple[str, tuple[int, int, int]]]:
    constraints: list[tuple[str, tuple[int, int, int]]] = []
    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue
        match = _CONSTRAINT_RE.match(part)
        if not match:
            raise SemverError(f"invalid range constraint: {part!r}")
        op = match.group(1)
        ver = _parse_version(match.group(2))
        if op == "^":
            constraints.extend(_expand_caret(ver))
        elif op == "~":
            constraints.extend(_expand_tilde(ver))
        else:
            constraints.append((op or "=", ver))
    return constraints


def _check(version: tuple[int, int, int], op: str, target: tuple[int, int, int]) -> bool:
    if op == "=":
        return version == target
    if op == ">=":
        return version >= target
    if op == "<=":
        return version <= target
    if op == ">":
        return version > target
    if op == "<":
        return version < target
    return False


def satisfies(version: str, range_str: str) -> bool:
    """Return ``True`` if *version* satisfies every constraint in *range_str*."""
    ver = _parse_version(version)
    constraints = _parse_range(range_str)
    if not constraints:
        raise SemverError(f"empty range: {range_str!r}")
    return all(_check(ver, op, target) for op, target in constraints)
