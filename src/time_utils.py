"""Utility helpers for parsing Google API timestamps."""

from __future__ import annotations

from datetime import datetime


def parse_google_timestamp(ts: str) -> datetime:
    """Convert a Google API RFC3339 timestamp to a naive UTC ``datetime``.

    Google APIs return RFC3339 timestamps, e.g. ``"2021-09-15T14:30:00.123Z"``.
    This helper converts such strings to a timezone-naive ``datetime``.

    Parameters
    ----------
    ts : str
        Timestamp string from a Google API in RFC3339 format.

    Returns
    -------
    datetime
        Parsed timestamp as a timezone-naive UTC ``datetime``.
    """
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)

