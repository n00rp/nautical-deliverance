"""Instant helpers: aware UTC datetimes and `datetime64[s]` arrays."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from nautical_deliverance.domain.contracts.errors import NaiveDatetimeError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def require_utc(dt: datetime) -> datetime:
    """Return `dt` in UTC; naive datetimes are rejected."""
    if dt.tzinfo is None:
        msg = "naive datetime; pass an aware datetime"
        raise NaiveDatetimeError(msg)
    return dt.astimezone(UTC)


def to_datetime64(dt: datetime) -> np.datetime64:
    """Aware datetime to `datetime64[s]` (UTC, truncated to seconds)."""
    return np.datetime64(require_utc(dt).replace(tzinfo=None), "s")


def from_datetime64(t: np.datetime64) -> datetime:
    """`datetime64` to aware UTC datetime."""
    seconds = int(t.astype("datetime64[s]").astype(np.int64))
    return _EPOCH + timedelta(seconds=seconds)  # fromtimestamp fails <1970 on Windows


def to_datetime64_array(dts: Sequence[datetime]) -> NDArray[np.datetime64]:
    """Aware datetimes to a `datetime64[s]` array."""
    return np.array([to_datetime64(d) for d in dts], dtype="datetime64[s]")
