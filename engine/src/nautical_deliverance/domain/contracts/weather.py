"""Weather contract: variables, per-point quality, sample container and provider protocol.

`WeatherSample.values` is keyed by `WeatherVariable`; every member value carries its unit suffix,
so the mapping keys carry the unit (the S0b-R01 suffix gate accepts such a mapping).
Interpolation rules (D-052): bilinear in space, linear in time, directions through unit vectors,
no extrapolation (flagged per point).
"""

from collections.abc import Mapping  # noqa: TC003 - read at runtime by the suffix gate
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray  # noqa: TC002 - read at runtime by the suffix gate

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    MissingRequiredVariableError,
)

if TYPE_CHECKING:
    from datetime import datetime

    from nautical_deliverance.domain.contracts.geo import Position


class WeatherVariable(StrEnum):
    """Weather variables; the value is the field name and carries the unit suffix (D-051)."""

    WIND_U_MPS = "wind_u_mps"
    WIND_V_MPS = "wind_v_mps"
    TOTAL_SEA_HEIGHT_M = "total_sea_height_m"
    TOTAL_SEA_PERIOD_S = "total_sea_period_s"
    TOTAL_SEA_DIRECTION_FROM_DEG = "total_sea_direction_from_deg"
    WIND_SEA_HEIGHT_M = "wind_sea_height_m"
    WIND_SEA_PERIOD_S = "wind_sea_period_s"
    WIND_SEA_DIRECTION_FROM_DEG = "wind_sea_direction_from_deg"
    SWELL_HEIGHT_M = "swell_height_m"
    SWELL_PERIOD_S = "swell_period_s"
    SWELL_DIRECTION_FROM_DEG = "swell_direction_from_deg"
    CURRENT_U_MPS = "current_u_mps"
    CURRENT_V_MPS = "current_v_mps"
    SEA_ICE_CONCENTRATION_RATIO = "sea_ice_concentration_ratio"
    VISIBILITY_M = "visibility_m"
    MEAN_SEA_LEVEL_PRESSURE_PA = "mean_sea_level_pressure_pa"


_OPTIONAL = frozenset(
    {
        WeatherVariable.SEA_ICE_CONCENTRATION_RATIO,
        WeatherVariable.VISIBILITY_M,
        WeatherVariable.MEAN_SEA_LEVEL_PRESSURE_PA,
    }
)
REQUIRED: frozenset[WeatherVariable] = frozenset(WeatherVariable) - _OPTIONAL

_FULL_CIRCLE = 360.0
DIRECTIONS: frozenset[WeatherVariable] = frozenset(
    v for v in WeatherVariable if v.value.endswith("_from_deg")
)


class SampleQuality(StrEnum):
    """Per-point quality of a sample (D-056).

    Providers set OK, OUT_OF_COVERAGE and OUT_OF_TIME_RANGE; when a point is both out of coverage
    and out of time range, OUT_OF_COVERAGE wins. STALE is never set by a provider: the consumer
    (C3) assigns it using the warn/block thresholds of D-056.
    """

    OK = "ok"
    OUT_OF_COVERAGE = "out_of_coverage"
    OUT_OF_TIME_RANGE = "out_of_time_range"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class WeatherSample:
    """All variables at N points; values are NaN exactly where quality is not OK."""

    values: Mapping[WeatherVariable, NDArray[np.float64]]
    quality: NDArray[np.str_]
    source: str
    run_time: NDArray[np.datetime64]
    unavailable: frozenset[WeatherVariable]

    def __post_init__(self) -> None:
        """Validate, then freeze: arrays become read-only copies and `values` a read-only view."""
        missing = (REQUIRED - self.values.keys()) | (self.unavailable & REQUIRED)
        if missing:
            raise MissingRequiredVariableError(frozenset(v.value for v in missing))
        if both := self.unavailable & self.values.keys():
            msg = f"variables both present and unavailable: {sorted(both)}"
            raise InvalidInputError(msg)
        n = len(self.quality)
        if len(self.run_time) != n or any(len(a) != n for a in self.values.values()):
            msg = "sample arrays must have equal length"
            raise InvalidInputError(msg)
        if not np.isin(self.quality, [q.value for q in SampleQuality]).all():
            msg = "quality contains unknown values"
            raise InvalidInputError(msg)
        not_ok = self.quality != SampleQuality.OK.value
        if any(not np.array_equal(np.isnan(a), not_ok) for a in self.values.values()):
            msg = "values must be NaN exactly where quality is not ok"
            raise InvalidInputError(msg)
        if np.isnat(self.run_time[~not_ok]).any():
            msg = "run_time must be set at ok points"
            raise InvalidInputError(msg)
        object.__setattr__(
            self, "values", MappingProxyType({k: _readonly(a) for k, a in self.values.items()})
        )
        object.__setattr__(self, "quality", _readonly(self.quality))
        object.__setattr__(self, "run_time", _readonly(self.run_time))


def _readonly[T: np.generic](a: NDArray[T]) -> NDArray[T]:
    copy = np.array(a, copy=True)
    copy.setflags(write=False)
    return copy


class WeatherProvider(Protocol):
    """A source of weather; all implementations must pass the conformance suite (S0b-R07)."""

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        """Sample all variables at N points (equal-length 1-D arrays)."""
        ...

    def sample_point(self, position: Position, valid_time: datetime) -> WeatherSample:
        """Scalar convenience wrapper around `sample` (length-1 result)."""
        ...


def validate_query(
    lat_deg: NDArray[np.float64],
    lon_deg: NDArray[np.float64],
    valid_time: NDArray[np.datetime64],
) -> None:
    """Reject non-arrays, non-1-D, unequal-length, non-finite or non-`datetime64[s]` queries."""
    if not all(isinstance(a, np.ndarray) for a in (lat_deg, lon_deg, valid_time)):
        msg = "query inputs must be numpy arrays"
        raise InvalidInputError(msg)
    if not (lat_deg.ndim == lon_deg.ndim == valid_time.ndim == 1):
        msg = "query arrays must be 1-D"
        raise InvalidInputError(msg)
    if not len(lat_deg) == len(lon_deg) == len(valid_time):
        msg = "query arrays must have equal length"
        raise InvalidInputError(msg)
    if not (np.isfinite(lat_deg).all() and np.isfinite(lon_deg).all()):
        msg = "coordinates must be finite"
        raise InvalidInputError(msg)
    if valid_time.dtype != np.dtype("datetime64[s]") or np.isnat(valid_time).any():
        msg = "valid_time must be datetime64[s] without NaT"
        raise InvalidInputError(msg)


def interpolate_direction_deg(
    weights: NDArray[np.float64], directions_from_deg: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Weighted unit-vector average over axis 0, result in [0, 360)."""
    rad = np.deg2rad(directions_from_deg)
    east = (weights * np.sin(rad)).sum(axis=0)
    north = (weights * np.cos(rad)).sum(axis=0)
    deg = np.rad2deg(np.arctan2(east, north)) % _FULL_CIRCLE
    return np.where(deg >= _FULL_CIRCLE, 0.0, deg)  # -1e-15 % 360 rounds up to 360.0
