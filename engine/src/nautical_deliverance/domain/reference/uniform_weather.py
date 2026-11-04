"""Analytical reference weather provider: a regular grid of uniform or linear fields.

Interpolation follows the contract (D-052): bilinear in space, linear in time, directions via unit
vectors, no extrapolation. Longitudes are handled as an offset from the west edge modulo 360, so a
grid may span the antimeridian (`lon_range_deg=(170.0, -170.0)`); on a full 360-degree grid the
east edge is the west column again. The latitude and longitude steps may differ, and the valid
times are an explicit increasing list (for example hourly, then 3-hourly).

Each variable group can have a narrower latitude range, time range, run time and source than the
grid (`GroupWindow`), which is how a test shows one group in coverage while another is not (D-062).
"""

from dataclasses import dataclass
from itertools import product
from typing import TYPE_CHECKING, Literal

import numpy as np

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    MissingRequiredVariableError,
)
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.weather import (
    DIRECTIONS,
    GROUP_OF,
    REQUIRED,
    SampleQuality,
    WeatherGroup,
    WeatherSample,
    WeatherVariable,
    interpolate_direction_deg,
    validate_query,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from numpy.typing import NDArray

    from nautical_deliverance.domain.contracts.geo import Position

# "linear" field: value = base + LAT * (lat - lat_min) + LON * (lon offset from west)
# + TIME * (seconds since the first valid time).
# Direction variables are instead 350 deg on the west node, 10 deg on the next, then +20 deg per
# node, constant in latitude and time (a fixture for the unit-vector rule).
LAT_GRADIENT = 0.5
LON_GRADIENT = 0.25
TIME_GRADIENT_PER_S = 0.001
_FULL_CIRCLE = 360.0
_SOURCE = "uniform"
_SIDE = (0, 1)


@dataclass(frozen=True, slots=True)
class GroupWindow:
    """Narrower coverage of one variable group; `None` inherits the provider's value."""

    lat_range_deg: tuple[float, float] | None = None
    time_range: tuple[datetime, datetime] | None = None
    run_time: datetime | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class _Window:
    lat0: float
    lat1: float
    t0: np.datetime64
    t1: np.datetime64
    run_time: np.datetime64
    source: str


def _count(span: float, step: float) -> int:
    """Node count of an axis of length `span`; `step` must divide it."""
    n = round(span / step)
    if n < 1 or abs(n * step - span) > 1e-9 * max(1.0, abs(span)):
        msg = f"grid step {step} does not evenly divide span {span}"
        raise InvalidInputError(msg)
    return n + 1


def _locate(x: NDArray[np.float64], count: int) -> tuple[NDArray[np.intp], NDArray[np.float64]]:
    """Lower node index and fraction for fractional node coordinates (clamped to the axis)."""
    x = np.clip(x, 0.0, count - 1.0)
    i = np.minimum(np.floor(x), count - 2.0).astype(np.intp)
    return i, x - i


class UniformWeather:
    """Gridded provider with uniform (or linear) fields; implements `WeatherProvider`."""

    def __init__(  # noqa: PLR0913, PLR0917 - mirrors the contract's grid description
        self,
        values: Mapping[WeatherVariable, float],
        lat_range_deg: tuple[float, float],
        lon_range_deg: tuple[float, float],
        times: Sequence[datetime],
        run_time: datetime,
        lat_step_deg: float,
        lon_step_deg: float,
        field: Literal["uniform", "linear"] = "uniform",
        group_windows: Mapping[WeatherGroup, GroupWindow] | None = None,
    ) -> None:
        """Build the grid; `values` must contain every required variable."""
        missing = REQUIRED - values.keys()
        if missing:
            raise MissingRequiredVariableError(frozenset(v.value for v in missing))
        self._lat0, self._lat1 = lat_range_deg
        self._west = lon_range_deg[0]
        width = (lon_range_deg[1] - lon_range_deg[0]) % _FULL_CIRCLE
        # a full 360-degree span wraps: the east edge is the west node again
        self._width = (
            _FULL_CIRCLE if width == 0.0 and lon_range_deg[1] != lon_range_deg[0] else width
        )
        self._lat_step, self._lon_step = lat_step_deg, lon_step_deg
        self._times = np.array([to_datetime64(t) for t in times], dtype="datetime64[s]")
        if len(self._times) < 2 or not (np.diff(self._times) > np.timedelta64(0, "s")).all():  # noqa: PLR2004
            msg = "times must be at least two strictly increasing instants"
            raise InvalidInputError(msg)
        self._tsec = (self._times - self._times[0]) / np.timedelta64(1, "s")
        self._shape = (
            len(self._times),
            _count(self._lat1 - self._lat0, lat_step_deg),
            _count(self._width, lon_step_deg),
        )
        self._unavailable = frozenset(v for v in WeatherVariable if v not in values)
        it, ilat, ilon = np.ogrid[: self._shape[0], : self._shape[1], : self._shape[2]]
        self._grid = {
            v: self._field(v, base, field, self._tsec[it], ilat, ilon) for v, base in values.items()
        }
        if self._width == _FULL_CIRCLE:  # the east column is the west column again
            for grid in self._grid.values():
                grid[:, :, -1] = grid[:, :, 0]
        self._windows = self._resolve({GROUP_OF[v] for v in values}, group_windows or {}, run_time)

    def _resolve(
        self,
        groups: set[WeatherGroup],
        windows: Mapping[WeatherGroup, GroupWindow],
        run_time: datetime,
    ) -> dict[WeatherGroup, _Window]:
        if unknown := set(windows) - groups:
            msg = f"windows for groups without variables: {sorted(unknown)}"
            raise InvalidInputError(msg)
        resolved = {}
        for group in groups:
            w = windows.get(group, GroupWindow())
            lat0, lat1 = w.lat_range_deg or (self._lat0, self._lat1)
            t0, t1 = (
                (to_datetime64(w.time_range[0]), to_datetime64(w.time_range[1]))
                if w.time_range
                else (self._times[0], self._times[-1])
            )
            if (
                lat0 < self._lat0
                or lat1 > self._lat1
                or t0 < self._times[0]
                or t1 > self._times[-1]
            ):
                msg = f"window of {group} must lie inside the grid"
                raise InvalidInputError(msg)
            rt = to_datetime64(w.run_time or run_time)
            resolved[group] = _Window(lat0, lat1, t0, t1, rt, w.source or _SOURCE)
        return resolved

    def _field(  # noqa: PLR0913, PLR0917
        self,
        var: WeatherVariable,
        base: float,
        field: str,
        tsec: NDArray[np.float64],
        ilat: NDArray[np.intp],
        ilon: NDArray[np.intp],
    ) -> NDArray[np.float64]:
        shape = self._shape
        if field == "uniform":
            return np.full(shape, base)
        if var in DIRECTIONS:
            return np.broadcast_to((350.0 + 20.0 * ilon) % _FULL_CIRCLE, shape).copy()
        return np.asarray(
            base
            + LAT_GRADIENT * self._lat_step * ilat
            + LON_GRADIENT * self._lon_step * ilon
            + TIME_GRADIENT_PER_S * tsec
            + np.zeros(shape)
        )

    def _locate_time(
        self, secs: NDArray[np.float64]
    ) -> tuple[NDArray[np.intp], NDArray[np.float64]]:
        """Lower time index and fraction for seconds since the first valid time."""
        last = len(self._tsec) - 2
        i = np.clip(np.searchsorted(self._tsec, secs, side="right") - 1, 0, last)
        frac = (secs - self._tsec[i]) / (self._tsec[i + 1] - self._tsec[i])
        return i.astype(np.intp), np.clip(frac, 0.0, 1.0)

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        """Sample all variables; a group's points outside its window are NaN and flagged."""
        validate_query(lat_deg, lon_deg, valid_time)
        offset = (lon_deg - self._west) % _FULL_CIRCLE
        secs = (valid_time - self._times[0]) / np.timedelta64(1, "s")
        in_grid = (lat_deg >= self._lat0) & (lat_deg <= self._lat1) & (offset <= self._width)

        quality: dict[WeatherGroup, NDArray[np.uint8]] = {}
        run_time: dict[WeatherGroup, NDArray[np.datetime64]] = {}
        for group, w in self._windows.items():
            covered = in_grid & (lat_deg >= w.lat0) & (lat_deg <= w.lat1)
            in_time = (valid_time >= w.t0) & (valid_time <= w.t1)
            quality[group] = np.where(
                ~covered,
                SampleQuality.OUT_OF_COVERAGE,
                np.where(~in_time, SampleQuality.OUT_OF_TIME_RANGE, SampleQuality.OK),
            ).astype(np.uint8)
            ok = quality[group] == SampleQuality.OK
            run_time[group] = np.where(ok, w.run_time, np.datetime64("NaT", "s")).astype(
                "datetime64[s]"
            )

        it, ft = self._locate_time(secs)
        iy, fy = _locate((lat_deg - self._lat0) / self._lat_step, self._shape[1])
        ix, fx = _locate(offset / self._lon_step, self._shape[2])
        corners = list(product(_SIDE, repeat=3))
        weights = np.stack(
            [
                (ft if dt else 1.0 - ft) * (fy if dy else 1.0 - fy) * (fx if dx else 1.0 - fx)
                for dt, dy, dx in corners
            ]
        )
        values: dict[WeatherVariable, NDArray[np.float64]] = {}
        for var, grid in self._grid.items():
            nodes = np.stack([grid[it + dt, iy + dy, ix + dx] for dt, dy, dx in corners])
            if var in DIRECTIONS:
                out = interpolate_direction_deg(weights, nodes)
            else:
                out = (weights * nodes).sum(axis=0)
            values[var] = np.where(quality[GROUP_OF[var]] == SampleQuality.OK, out, np.nan)
        source = {g: w.source for g, w in self._windows.items()}
        return WeatherSample(values, quality, source, run_time, self._unavailable)

    def sample_point(self, position: Position, valid_time: datetime) -> WeatherSample:
        """Scalar convenience wrapper around `sample`."""
        return self.sample(
            np.array([position.lat_deg]),
            np.array([position.lon_deg]),
            np.array([to_datetime64(valid_time)], dtype="datetime64[s]"),
        )
