"""Performance contract: vessel description, operating condition, result and model protocol.

A `PerformanceModel` converts between shaft power and speed through water at N operating points
for a given fuel type, and reports fuel rate per consumer and a motion-risk ratio.
Implementations must pass the conformance suite (S0b-R08).

Fuel (D-064): `VesselSpec.sfoc_curve_kg_per_j` holds one curve per `Consumer`, measured on a fuel
with the ISO reference lower calorific value (42.7 MJ/kg, ISO 3046-1). The model converts to the
requested fuel type (the same energy needs less mass of a higher-LCV fuel); the returned fuel rates
are the mass of that fuel. The conversion data belong to C2.

Power above MCR is returned as asked, never capped: C3 enforces the MCR limit. The curve load
fraction is shaft (or auxiliary) power divided by `mcr_w`.
"""

import re
from collections.abc import Mapping  # noqa: TC003 - read at runtime by the suffix gate
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from types import MappingProxyType
from typing import Protocol

import numpy as np
from numpy.typing import NDArray  # noqa: TC002 - read at runtime by the suffix gate

from nautical_deliverance.domain.contracts._values import ValueEquality
from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.weather import (
    REQUIRED_GROUPS,
    WeatherSample,
    has_values,
)

_IMO_WEIGHTS = (7, 6, 5, 4, 3, 2)


class FuelType(StrEnum):
    """Marine fuels."""

    HFO = "hfo"
    VLSFO = "vlsfo"
    ULSFO = "ulsfo"
    MGO = "mgo"
    LNG = "lng"


class Consumer(StrEnum):
    """Fuel consumers on board."""

    MAIN_ENGINE = "main_engine"
    AUXILIARY = "auxiliary"


class OperatingState(StrEnum):
    """Vessel operating state, selects the auxiliary load."""

    AT_SEA = "at_sea"
    IN_PORT = "in_port"


def _positive(**values: float) -> None:
    for name, v in values.items():
        if not (v > 0.0 and np.isfinite(v)):
            msg = f"{name} must be positive and finite, got {v}"
            raise InvalidInputError(msg)


def _frozen(a: NDArray[np.float64]) -> NDArray[np.float64]:
    copy = np.array(a, dtype=np.float64, copy=True)
    copy.setflags(write=False)
    return copy


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    """Operational limits beyond which the vessel must not sail."""

    max_significant_wave_height_m: float
    max_wind_speed_mps: float
    min_under_keel_clearance_m: float

    def __post_init__(self) -> None:
        """Reject non-positive limits."""
        _positive(
            max_significant_wave_height_m=self.max_significant_wave_height_m,
            max_wind_speed_mps=self.max_wind_speed_mps,
            min_under_keel_clearance_m=self.min_under_keel_clearance_m,
        )


def is_valid_imo(imo_number: str) -> bool:
    """Return True for 7 ASCII digits whose last digit is the IMO check digit."""
    if not re.fullmatch(r"[0-9]{7}", imo_number):
        return False
    digits = [int(c) for c in imo_number]
    # strict=False: 6 weights pair with the first 6 of 7 digits; the 7th is the check digit
    return sum(d * w for d, w in zip(digits, _IMO_WEIGHTS, strict=False)) % 10 == digits[-1]


def _check_sfoc_curve(consumer: Consumer, curve: tuple[tuple[float, float], ...]) -> None:
    loads = [p[0] for p in curve]
    if len(loads) < 2:  # noqa: PLR2004
        msg = f"sfoc curve of {consumer} needs at least 2 points"
        raise InvalidInputError(msg)
    increasing = all(a < b for a, b in pairwise(loads))
    if not (increasing and loads[0] >= 0.0 and loads[-1] <= 1.0):
        msg = f"sfoc curve of {consumer}: load fractions must be strictly increasing within [0, 1]"
        raise InvalidInputError(msg)
    _positive(**{f"sfoc[{consumer}][{i}]": p[1] for i, p in enumerate(curve)})


@dataclass(frozen=True, slots=True, eq=False)
class VesselSpec(ValueEquality):
    """Static vessel description.

    `sfoc_curve_kg_per_j` maps each `Consumer` to (load fraction, kg/J) pairs at the ISO reference
    lower calorific value (D-064). Equality and hash are by value (mappings compared by content),
    so a spec can be a `dict` key or `lru_cache` argument.
    """

    imo_number: str
    length_m: float
    beam_m: float
    design_draft_m: float
    mcr_w: float
    sfoc_curve_kg_per_j: Mapping[Consumer, tuple[tuple[float, float], ...]]
    auxiliary_load_w: Mapping[OperatingState, float]
    safety_limits: SafetyLimits

    def __post_init__(self) -> None:
        """Validate, then freeze the mappings as read-only views."""
        if not is_valid_imo(self.imo_number):
            msg = f"invalid IMO number {self.imo_number!r}"
            raise InvalidInputError(msg)
        _positive(
            length_m=self.length_m,
            beam_m=self.beam_m,
            design_draft_m=self.design_draft_m,
            mcr_w=self.mcr_w,
        )
        if self.sfoc_curve_kg_per_j.keys() != set(Consumer):
            msg = "sfoc_curve_kg_per_j needs exactly one curve per Consumer"
            raise InvalidInputError(msg)
        curves = {
            c: tuple((float(p[0]), float(p[1])) for p in curve)
            for c, curve in self.sfoc_curve_kg_per_j.items()
        }
        for consumer, curve in curves.items():
            _check_sfoc_curve(consumer, curve)
        if self.auxiliary_load_w.keys() != set(OperatingState):
            msg = "auxiliary_load_w needs exactly one entry per OperatingState"
            raise InvalidInputError(msg)
        if not all(np.isfinite(v) and v >= 0.0 for v in self.auxiliary_load_w.values()):
            msg = "auxiliary loads must be finite and non-negative"
            raise InvalidInputError(msg)
        object.__setattr__(self, "sfoc_curve_kg_per_j", MappingProxyType(curves))
        object.__setattr__(self, "auxiliary_load_w", MappingProxyType(dict(self.auxiliary_load_w)))


@dataclass(frozen=True, slots=True, eq=False)
class OperatingCondition:
    """Draft, heading and weather at N points (equal lengths).

    Models may ignore draft and heading (the analytical reference does). Water depth and
    under-keel clearance are not part of the condition: C3 gets them from a separate depth
    provider (D-019, one interface per data type). Equality is identity (the type holds arrays).
    """

    draft_fwd_m: NDArray[np.float64]
    draft_aft_m: NDArray[np.float64]
    heading_deg: NDArray[np.float64]
    weather: WeatherSample

    def __post_init__(self) -> None:
        """Validate, then freeze arrays as read-only copies."""
        arrays = (self.draft_fwd_m, self.draft_aft_m, self.heading_deg)
        n = len(self.weather)
        if any(a.ndim != 1 or len(a) != n for a in arrays):
            msg = "condition arrays must be 1-D with the weather sample length"
            raise InvalidInputError(msg)
        if not all(np.isfinite(a).all() for a in arrays):
            msg = "condition arrays must be finite"
            raise InvalidInputError(msg)
        object.__setattr__(self, "draft_fwd_m", _frozen(self.draft_fwd_m))
        object.__setattr__(self, "draft_aft_m", _frozen(self.draft_aft_m))
        object.__setattr__(self, "heading_deg", _frozen(self.heading_deg))

    def __len__(self) -> int:
        """Return the number of operating points."""
        return len(self.weather)


@dataclass(frozen=True, slots=True, eq=False)
class PerformanceResult:
    """Model output at N points (1-D arrays); one fuel-rate array per `Consumer`.

    Equality is identity (the type holds arrays).
    """

    speed_through_water_mps: NDArray[np.float64]
    shaft_power_w: NDArray[np.float64]
    fuel_rate_kgps: Mapping[Consumer, NDArray[np.float64]]
    motion_risk_ratio: NDArray[np.float64]

    def __post_init__(self) -> None:
        """Validate dimensions, lengths and consumers, then freeze arrays and mapping."""
        if self.fuel_rate_kgps.keys() != set(Consumer):
            msg = "fuel_rate_kgps needs exactly one entry per Consumer"
            raise InvalidInputError(msg)
        arrays = (
            self.speed_through_water_mps,
            self.shaft_power_w,
            self.motion_risk_ratio,
            *self.fuel_rate_kgps.values(),
        )
        if any(a.ndim != 1 for a in arrays):
            msg = "result arrays must be 1-D"
            raise InvalidInputError(msg)
        if any(len(a) != len(self.speed_through_water_mps) for a in arrays):
            msg = "result arrays must have equal length"
            raise InvalidInputError(msg)
        object.__setattr__(self, "speed_through_water_mps", _frozen(self.speed_through_water_mps))
        object.__setattr__(self, "shaft_power_w", _frozen(self.shaft_power_w))
        object.__setattr__(self, "motion_risk_ratio", _frozen(self.motion_risk_ratio))
        object.__setattr__(
            self,
            "fuel_rate_kgps",
            MappingProxyType({k: _frozen(a) for k, a in self.fuel_rate_kgps.items()}),
        )


def validate_performance_input(
    condition: OperatingCondition,
    values: NDArray[np.float64],
    name: str,
    fuel_type: FuelType,
) -> None:
    """Shared call checks for every model.

    `values` is a 1-D float64 array of the condition's length, finite and non-negative;
    `fuel_type` a `FuelType`; and the wind, waves and current groups of the weather must be OK or
    STALE at every point (D-063: STALE keeps its values, C3 decides whether to warn or block).
    Out-of-coverage and out-of-time-range points carry NaN and are rejected. The optional groups
    are not needed and are ignored.
    """
    if not isinstance(values, np.ndarray) or values.dtype != np.float64 or values.ndim != 1:
        msg = f"{name} must be a 1-D float64 numpy array"
        raise InvalidInputError(msg)
    if not isinstance(fuel_type, FuelType):
        msg = f"fuel_type must be a FuelType, got {fuel_type!r}"
        raise InvalidInputError(msg)
    if len(values) != len(condition):
        msg = f"{name} and condition must have equal length"
        raise InvalidInputError(msg)
    if not (np.isfinite(values).all() and (values >= 0.0).all()):
        msg = f"{name} must be finite and non-negative"
        raise InvalidInputError(msg)
    for group in sorted(REQUIRED_GROUPS):
        if not has_values(condition.weather.quality[group]).all():
            msg = f"weather group {group} must be ok or stale at every point"
            raise InvalidInputError(msg)


class PerformanceModel(Protocol):
    """A vessel performance model; all implementations must pass the conformance suite."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        """Speed through water achieved with the given shaft power at each point.

        Power above MCR is not an error; the model reports what it implies and C3 caps it.
        """
        ...

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        """Shaft power needed for the given speed through water at each point."""
        ...
