"""Route contract tests (S0b-R10)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nautical_deliverance.domain.contracts.errors import InvalidInputError, NaiveDatetimeError
from nautical_deliverance.domain.contracts.geo import LegGeometry, Position
from nautical_deliverance.domain.contracts.performance import Consumer, FuelType
from nautical_deliverance.domain.contracts.route import (
    DataQuality,
    ForecastRun,
    OperatingMode,
    Route,
    RouteLeg,
    Waypoint,
)

_T0 = datetime(2026, 11, 4, tzinfo=UTC)


def wp(i: int, hours: float | None = None) -> Waypoint:
    """Waypoint `i`, one hour per step unless `hours` is given."""
    return Waypoint(Position(50.0 + i, 0.0), _T0 + timedelta(hours=i if hours is None else hours))


def leg(a: Waypoint, b: Waypoint, **overrides: Any) -> RouteLeg:  # noqa: ANN401 - to `replace`
    """Build a valid leg from `a` to `b`."""
    base = RouteLeg(
        a,
        b,
        LegGeometry.RHUMB_LINE,
        7.0,
        7.5,
        FuelType.VLSFO,
        {Consumer.MAIN_ENGINE: 1000.0},
        2.0,
        10.0,
        frozenset(),
    )
    return replace(base, **overrides)


def route(legs: tuple[RouteLeg, ...] | None = None, **overrides: Any) -> Route:  # noqa: ANN401
    """Build a valid two-leg route."""
    base = Route(
        legs or (leg(wp(0), wp(1)), leg(wp(1), wp(2))),
        OperatingMode.CONSTANT_SPEED,
        (ForecastRun("test", _T0),),
        DataQuality.OK,
        (),
    )
    return replace(base, **overrides)


@pytest.mark.req("S0b-R10")
def test_valid_route() -> None:
    """A contiguous route is accepted; fuel is read-only."""
    r = route()
    assert r.legs[0].end == r.legs[1].start
    with pytest.raises(TypeError):
        r.legs[0].fuel_kg[Consumer.AUXILIARY] = 1.0  # type: ignore[index]


@pytest.mark.req("S0b-R10")
def test_gap_between_legs_rejected() -> None:
    """Consecutive legs must share their waypoint."""
    with pytest.raises(InvalidInputError):
        route((leg(wp(0), wp(1)), leg(wp(2), wp(3))))


@pytest.mark.req("S0b-R10")
def test_non_increasing_eta_rejected() -> None:
    """A leg must end after it starts."""
    with pytest.raises(InvalidInputError):
        leg(wp(0), wp(1, hours=0))


@pytest.mark.req("S0b-R10")
def test_degraded_without_reasons_rejected() -> None:
    """DEGRADED needs reasons."""
    with pytest.raises(InvalidInputError):
        route(data_quality=DataQuality.DEGRADED)
    assert route(data_quality=DataQuality.DEGRADED, quality_reasons=("stale",))


@pytest.mark.req("S0b-R10")
def test_ok_with_reasons_rejected() -> None:
    """OK forbids reasons."""
    with pytest.raises(InvalidInputError):
        route(quality_reasons=("stale",))


@pytest.mark.req("S0b-R10")
def test_naive_eta_rejected() -> None:
    """Naive instants are rejected for waypoints and forecast runs."""
    with pytest.raises(NaiveDatetimeError):
        Waypoint(Position(0.0, 0.0), datetime(2026, 11, 4))  # noqa: DTZ001
    with pytest.raises(NaiveDatetimeError):
        ForecastRun("x", datetime(2026, 11, 4))  # noqa: DTZ001


@pytest.mark.req("S0b-R10")
def test_empty_route_rejected() -> None:
    """A route has at least one leg."""
    with pytest.raises(InvalidInputError):
        Route((), OperatingMode.FIXED_ARRIVAL, (), DataQuality.OK, ())


@pytest.mark.req("S0b-R10")
@pytest.mark.parametrize(
    "bad",
    [
        {"speed_through_water_mps": -1.0},
        {"worst_wind_speed_mps": float("nan")},
        {"fuel_kg": {Consumer.MAIN_ENGINE: -1.0}},
    ],
)
def test_bad_leg_numbers_rejected(bad: dict[str, Any]) -> None:
    """Negative or non-finite numbers are rejected."""
    with pytest.raises(InvalidInputError):
        leg(wp(0), wp(1), **bad)
