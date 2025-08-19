from __future__ import annotations

from datetime import datetime


def parse_google_timestamp(ts: str) -> datetime:
    """Return naive UTC ``datetime`` from a Google API timestamp string.

    Google APIs return RFC3339 timestamps, e.g. ``"2021-09-15T14:30:00.123Z"``.
    This helper converts such strings to a timezone-naive ``datetime``.
    """
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)

