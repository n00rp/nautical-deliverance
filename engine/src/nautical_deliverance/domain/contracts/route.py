"""Route contract: waypoints, legs, forecast runs and the data-quality summary (S0b-R10)."""

import math
from collections.abc import Mapping  # noqa: TC003 - read at runtime by the suffix gate
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 - read at runtime by the suffix gate
from enum import StrEnum
from itertools import pairwise
from types import MappingProxyType

from nautical_deliverance.domain.contracts._values import ValueEquality
from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.geo import LegGeometry, Position  # noqa: TC001 - gate
from nautical_deliverance.domain.contracts.performance import Consumer, FuelType
from nautical_deliverance.domain.contracts.time import require_utc


class OperatingMode(StrEnum):
    """How the speed profile of a route is chosen."""

    CONSTANT_POWER = "constant_power"
    CONSTANT_SPEED = "constant_speed"
    FIXED_ARRIVAL = "fixed_arrival"


class DataQuality(StrEnum):
    """Overall quality of the data behind a route."""

    OK = "ok"
    DEGRADED = "degraded"


class SafetyLimit(StrEnum):
    """The vessel safety limits (D-057) a leg can violate; a valid route has none."""

    MAX_SIGNIFICANT_WAVE_HEIGHT = "max_significant_wave_height"
    MAX_WIND_SPEED = "max_wind_speed"
    MIN_UNDER_KEEL_CLEARANCE = "min_under_keel_clearance"


@dataclass(frozen=True, slots=True)
class Waypoint:
    """A position with the time the vessel is there (aware UTC)."""

    position: Position
    eta: datetime

    def __post_init__(self) -> None:
        """Normalize the instant to UTC; naive datetimes are rejected."""
        object.__setattr__(self, "eta", require_utc(self.eta))


@dataclass(frozen=True, slots=True, eq=False)
class RouteLeg(ValueEquality):
    """One leg between two waypoints with its speeds, fuel and worst weather.

    `fuel_kg` has one entry per `Consumer`. `limit_violations` may be given as any iterable of
    `SafetyLimit` and is stored as a frozenset. Equality and hash are by value.
    """

    start: Waypoint
    end: Waypoint
    geometry: LegGeometry
    speed_through_water_mps: float
    speed_over_ground_mps: float
    fuel_type: FuelType
    fuel_kg: Mapping[Consumer, float]
    worst_significant_wave_height_m: float
    worst_wind_speed_mps: float
    limit_violations: frozenset[SafetyLimit]

    def __post_init__(self) -> None:
        """Validate time order, consumers, violations and finite non-negative numbers."""
        if self.end.eta <= self.start.eta:
            msg = "leg end must be after leg start"
            raise InvalidInputError(msg)
        if self.fuel_kg.keys() != set(Consumer):
            msg = "fuel_kg needs exactly one entry per Consumer"
            raise InvalidInputError(msg)
        numbers = (
            self.speed_through_water_mps,
            self.speed_over_ground_mps,
            self.worst_significant_wave_height_m,
            self.worst_wind_speed_mps,
            *self.fuel_kg.values(),
        )
        if not all(math.isfinite(v) and v >= 0.0 for v in numbers):
            msg = "leg numbers must be finite and non-negative"
            raise InvalidInputError(msg)
        try:
            violations = frozenset(SafetyLimit(v) for v in self.limit_violations)
        except ValueError as exc:
            msg = f"unknown safety limit in limit_violations: {exc}"
            raise InvalidInputError(msg) from exc
        object.__setattr__(self, "limit_violations", violations)
        object.__setattr__(self, "fuel_kg", MappingProxyType(dict(self.fuel_kg)))


@dataclass(frozen=True, slots=True)
class ForecastRun:
    """A weather forecast run the route was computed from."""

    source: str
    run_time: datetime

    def __post_init__(self) -> None:
        """Normalize the run time to UTC (naive datetimes are rejected); the source is named."""
        if not self.source.strip():
            msg = "forecast run source must not be blank"
            raise InvalidInputError(msg)
        object.__setattr__(self, "run_time", require_utc(self.run_time))


@dataclass(frozen=True, slots=True)
class Route:
    """A contiguous sequence of legs of one geometry; DEGRADED quality requires stated reasons.

    A route is drawn with one `LegGeometry` throughout (D-055: the choice is per route) and
    records at least one forecast run (C3 derives them from the weather samples it used).
    """

    legs: tuple[RouteLeg, ...]
    mode: OperatingMode
    forecast_runs: tuple[ForecastRun, ...]
    data_quality: DataQuality
    quality_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate contiguity, geometry, forecast runs and the quality/reasons coupling."""
        if not self.legs:
            msg = "a route needs at least one leg"
            raise InvalidInputError(msg)
        # Exact Waypoint equality: in a real route consecutive legs share the same objects.
        if any(a.end != b.start for a, b in pairwise(self.legs)):
            msg = "consecutive legs must share their waypoint"
            raise InvalidInputError(msg)
        if len({leg.geometry for leg in self.legs}) != 1:
            msg = "all legs of a route must use the same geometry"
            raise InvalidInputError(msg)
        if not self.forecast_runs:
            msg = "a route needs at least one forecast run"
            raise InvalidInputError(msg)
        if not all(r.strip() for r in self.quality_reasons):
            msg = "quality reasons must not be blank"
            raise InvalidInputError(msg)
        if (self.data_quality is DataQuality.DEGRADED) != bool(self.quality_reasons):
            msg = "data quality is degraded if and only if reasons are given"
            raise InvalidInputError(msg)
