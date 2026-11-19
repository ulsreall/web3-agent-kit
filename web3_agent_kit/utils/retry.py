"""Retry-After parsing shared by both HTTP helpers.

RFC 9110 allows delta-seconds *and* an HTTP-date, and platforms send letters and
empty strings in practice. Feeding the header straight into ``int()`` throws a
``ValueError`` out of a retry loop that should instead be driven by it.
"""

from __future__ import annotations

import time
from typing import Optional

#: Cap on a server-provided ``Retry-After``. A platform answering "3600" would
#: otherwise stall a whole run for an hour between two tasks.
MAX_RETRY_AFTER = 300.0


def parse_retry_after(value: Optional[str], fallback: float) -> float:
    """Turn a ``Retry-After`` header into a sleep length.

    Anything unparsable, non-positive or above :data:`MAX_RETRY_AFTER` falls
    back to ``fallback``.
    """
    if value is None:
        return fallback
    text = value.strip()
    if not text:
        return fallback
    try:
        seconds = float(text)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            seconds = parsedate_to_datetime(text).timestamp() - time.time()
        except (TypeError, ValueError):
            return fallback
    if seconds <= 0 or seconds > MAX_RETRY_AFTER:
        return fallback
    return seconds
