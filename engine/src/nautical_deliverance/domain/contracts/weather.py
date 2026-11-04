"""Weather contract: variables, groups, per-point quality, sample container and provider protocol.

`WeatherSample.values` is keyed by `WeatherVariable`; every member value carries its unit suffix,
so the mapping keys carry the unit (the S0b-R01 suffix gate accepts such a mapping).
Interpolation rules (D-052): bilinear in space, linear in time, directions through unit vectors,
no extrapolation (flagged per point). Source, run time and quality are reported per variable
group (D-062); STALE points keep their values (D-063).
"""

from collections.abc import Mapping  # noqa: TC003 - read at runtime by the suffix gate
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray  # noqa: TC002 - read at runtime by the suffix gate

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    InvalidPositionError,
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
_MAX_LAT_DEG = 90.0
DIRECTIONS: frozenset[WeatherVariable] = frozenset(
    v for v in WeatherVariable if v.value.endswith("_from_deg")
)


class WeatherGroup(StrEnum):
    """Variable groups that share one source, run time and quality (D-062).

    A provider that merges sources (for example wind from one model and waves from another)
    reports each group separately; each optional variable is a group of its own.
    """

    WIND = "wind"
    WAVES = "waves"
    CURRENT = "current"
    SEA_ICE = "sea_ice"
    VISIBILITY = "visibility"
    PRESSURE = "pressure"


_V = WeatherVariable
_G = WeatherGroup
GROUP_OF: Mapping[WeatherVariable, WeatherGroup] = MappingProxyType(
    {
        _V.WIND_U_MPS: _G.WIND,
        _V.WIND_V_MPS: _G.WIND,
        _V.TOTAL_SEA_HEIGHT_M: _G.WAVES,
        _V.TOTAL_SEA_PERIOD_S: _G.WAVES,
        _V.TOTAL_SEA_DIRECTION_FROM_DEG: _G.WAVES,
        _V.WIND_SEA_HEIGHT_M: _G.WAVES,
        _V.WIND_SEA_PERIOD_S: _G.WAVES,
        _V.WIND_SEA_DIRECTION_FROM_DEG: _G.WAVES,
        _V.SWELL_HEIGHT_M: _G.WAVES,
        _V.SWELL_PERIOD_S: _G.WAVES,
        _V.SWELL_DIRECTION_FROM_DEG: _G.WAVES,
        _V.CURRENT_U_MPS: _G.CURRENT,
        _V.CURRENT_V_MPS: _G.CURRENT,
        _V.SEA_ICE_CONCENTRATION_RATIO: _G.SEA_ICE,
        _V.VISIBILITY_M: _G.VISIBILITY,
        _V.MEAN_SEA_LEVEL_PRESSURE_PA: _G.PRESSURE,
    }
)
REQUIRED_GROUPS: frozenset[WeatherGroup] = frozenset(GROUP_OF[v] for v in REQUIRED)


class SampleQuality(IntEnum):
    """Per-point, per-group quality of a sample (D-056, D-063); arrays store the `uint8` code.

    Providers set OK, OUT_OF_COVERAGE and OUT_OF_TIME_RANGE; when a point is both out of coverage
    and out of time range, OUT_OF_COVERAGE wins. Values are NaN exactly at OUT_OF_COVERAGE and
    OUT_OF_TIME_RANGE points; STALE points keep their values. STALE is never set by a provider:
    the consumer (C3) assigns it using the warn/block thresholds of D-056.
    """

    OK = 0
    OUT_OF_COVERAGE = 1
    OUT_OF_TIME_RANGE = 2
    STALE = 3


_NO_VALUES = (SampleQuality.OUT_OF_COVERAGE.value, SampleQuality.OUT_OF_TIME_RANGE.value)


def has_values(quality: NDArray[np.uint8]) -> NDArray[np.bool_]:
    """Return the mask of points whose values are real numbers (OK or STALE), not NaN."""
    return ~np.isin(quality, _NO_VALUES)


def _check_array(name: str, a: object, dtype: str, n: int | None) -> int:
    if not isinstance(a, np.ndarray) or a.dtype != np.dtype(dtype) or a.ndim != 1:
        msg = f"{name} must be a 1-D {dtype} numpy array"
        raise InvalidInputError(msg)
    if n is not None and len(a) != n:
        msg = "sample arrays must have equal length"
        raise InvalidInputError(msg)
    return len(a)


@dataclass(frozen=True, slots=True, eq=False)
class WeatherSample:
    """All variables at N points with source, run time and quality per `WeatherGroup`.

    `values` holds one `float64` array per available variable. For each group present, `quality`
    holds `SampleQuality` codes (`uint8`), `source` a non-empty name and `run_time` a
    `datetime64[s]` array (NaT only where the group has no values). A variable is NaN exactly where
    its group is OUT_OF_COVERAGE or OUT_OF_TIME_RANGE (D-062, D-063). Every variable is either in
    `values` or in `unavailable` (optional ones only); the groups wind, waves and current are
    mandatory. Equality is identity, because the type holds arrays.
    """

    values: Mapping[WeatherVariable, NDArray[np.float64]]
    quality: Mapping[WeatherGroup, NDArray[np.uint8]]
    source: Mapping[WeatherGroup, str]
    run_time: Mapping[WeatherGroup, NDArray[np.datetime64]]
    unavailable: frozenset[WeatherVariable]

    def __post_init__(self) -> None:
        """Validate, then freeze: arrays become read-only copies and mappings read-only views."""
        self._check_variables()
        groups = {GROUP_OF[v] for v in self.values}
        self._check_groups(groups)
        n = _check_array("quality", next(iter(self.quality.values())), "uint8", None)
        for group in groups:
            self._check_group_arrays(group, n)
        for var, a in self.values.items():
            _check_array(f"values[{var}]", a, "float64", n)
            if np.isinf(a).any():
                msg = "values must not be infinite"
                raise InvalidInputError(msg)
            if not np.array_equal(np.isnan(a), ~has_values(self.quality[GROUP_OF[var]])):
                msg = "values must be NaN exactly at out-of-coverage and out-of-time-range points"
                raise InvalidInputError(msg)
        for name in ("values", "quality", "run_time"):
            frozen = {k: _readonly(a) for k, a in getattr(self, name).items()}
            object.__setattr__(self, name, MappingProxyType(frozen))
        object.__setattr__(self, "source", MappingProxyType(dict(self.source)))

    def _check_groups(self, groups: set[WeatherGroup]) -> None:
        for name, mapping in (
            ("quality", self.quality),
            ("source", self.source),
            ("run_time", self.run_time),
        ):
            keys = list(mapping)
            if not all(isinstance(k, WeatherGroup) for k in keys) or set(keys) != groups:
                msg = f"{name} needs exactly one entry per present WeatherGroup"
                raise InvalidInputError(msg)
        if not all(isinstance(s, str) and s.strip() for s in self.source.values()):
            msg = "source names must be non-empty strings"
            raise InvalidInputError(msg)

    def _check_group_arrays(self, group: WeatherGroup, n: int) -> None:
        _check_array(f"quality[{group}]", self.quality[group], "uint8", n)
        _check_array(f"run_time[{group}]", self.run_time[group], "datetime64[s]", n)
        if not np.isin(self.quality[group], [q.value for q in SampleQuality]).all():
            msg = "quality contains unknown codes"
            raise InvalidInputError(msg)
        if np.isnat(self.run_time[group][has_values(self.quality[group])]).any():
            msg = "run_time must be set wherever the group has values"
            raise InvalidInputError(msg)

    def _check_variables(self) -> None:
        if not all(isinstance(v, WeatherVariable) for v in (*self.values, *self.unavailable)):
            msg = "variables must be WeatherVariable members"
            raise InvalidInputError(msg)
        missing = (REQUIRED - self.values.keys()) | (self.unavailable & REQUIRED)
        if missing:
            raise MissingRequiredVariableError(frozenset(v.value for v in missing))
        if both := self.unavailable & self.values.keys():
            msg = f"variables both present and unavailable: {sorted(both)}"
            raise InvalidInputError(msg)
        if vanished := set(WeatherVariable) - self.values.keys() - self.unavailable:
            msg = f"optional variables neither present nor marked unavailable: {sorted(vanished)}"
            raise InvalidInputError(msg)

    def __len__(self) -> int:
        """Return the number of points."""
        return len(next(iter(self.quality.values())))


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
    """Reject non-arrays, non-1-D, unequal-length, non-finite or non-`datetime64[s]` queries.

    A latitude beyond +-90 is an `InvalidPositionError`. Longitudes are not range-checked:
    providers wrap them, so any finite longitude is a valid query.
    """
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
    if (np.abs(lat_deg) > _MAX_LAT_DEG).any():
        msg = "latitude must be within [-90, 90]"
        raise InvalidPositionError(msg)
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
