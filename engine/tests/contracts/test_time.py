"""Time helper tests."""

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nautical_deliverance.domain.contracts.errors import InvalidInputError, NaiveDatetimeError
from nautical_deliverance.domain.contracts.time import (
    from_datetime64,
    require_utc,
    to_datetime64,
    to_datetime64_array,
)

if TYPE_CHECKING:
    from collections.abc import Callable

NAIVE = datetime(2026, 1, 1, 12)  # noqa: DTZ001 - the point of the test


@pytest.mark.req("S0b-R03")
@pytest.mark.parametrize(
    "call",
    [require_utc, to_datetime64, lambda d: to_datetime64_array([d])],
)
def test_naive_rejected(call: Callable[[datetime], object]) -> None:
    """Every helper refuses naive datetimes."""
    with pytest.raises(NaiveDatetimeError):
        call(NAIVE)


@pytest.mark.req("S0b-R03")
def test_non_utc_converted() -> None:
    """Offsets are normalised to UTC."""
    dt = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))
    assert require_utc(dt) == datetime(2026, 1, 1, 10, tzinfo=UTC)
    assert to_datetime64(dt) == np.datetime64("2026-01-01T10:00:00")
    assert to_datetime64_array([dt]).dtype == np.dtype("datetime64[s]")


@pytest.mark.req("S0b-R03")
@settings(max_examples=1000)
@given(
    st.datetimes(
        min_value=datetime(1900, 1, 1),  # noqa: DTZ001
        max_value=datetime(2200, 1, 1),  # noqa: DTZ001
        timezones=st.integers(-14 * 60, 14 * 60).map(lambda m: timezone(timedelta(minutes=m))),
    ).map(lambda d: d.replace(microsecond=0))
)
def test_round_trip(dt: datetime) -> None:
    """Round trip through datetime64 is the identity (as an instant)."""
    back = from_datetime64(to_datetime64(dt))
    assert back == dt
    assert back.tzinfo == UTC


@pytest.mark.req("S0b-R03")
@settings(max_examples=1000)
@given(st.integers(-(2**34), 2**34))
def test_reverse_round_trip(sec: int) -> None:
    """datetime64[s] -> datetime -> datetime64[s] is the identity."""
    t = np.datetime64(sec, "s")
    assert to_datetime64(from_datetime64(t)) == t


@pytest.mark.req("S0b-R03")
def test_array_round_trip() -> None:
    """The array path agrees with the scalar path."""
    dts = [datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(3)]
    arr = to_datetime64_array(dts)
    assert [from_datetime64(t) for t in arr] == dts


@pytest.mark.req("S0b-R03")
def test_nat_rejected() -> None:
    """NaT is not an instant."""
    with pytest.raises(InvalidInputError):
        from_datetime64(np.datetime64("NaT", "s"))


@pytest.mark.req("S0b-R03")
def test_sub_second_rejected() -> None:
    """Microseconds are rejected, never silently truncated."""
    dt = datetime(2026, 1, 1, 12, 0, 0, 1, tzinfo=UTC)
    with pytest.raises(InvalidInputError):
        to_datetime64(dt)
    with pytest.raises(InvalidInputError):
        to_datetime64_array([dt])
