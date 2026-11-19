"""Small coercions for values that come back from third-party APIs.

Numbers arrive as `""`, `null`, `"0.5"` or a real number depending on the
provider and the field. `int("")` and `float(None)` raise, and parsers are
usually wrapped in one broad `except` that abandons the whole response, so a
single missing field can cost the entire result. These helpers default instead.
"""

from __future__ import annotations

from typing import Any, cast


def coerce_int(value: object, default: int = 0) -> int:
    """Return ``value`` as an int, or ``default`` when it is unusable."""
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return default


def coerce_float(value: object, default: float = 0.0) -> float:
    """Return ``value`` as a float, or ``default`` when it is unusable."""
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default
