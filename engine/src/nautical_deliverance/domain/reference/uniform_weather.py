"""Analytical reference weather provider: a regular grid of uniform or linear fields.

Interpolation follows the contract (D-052): bilinear in space, linear in time, directions via unit
vectors, no extrapolation. Longitudes are handled as an offset from the west edge modulo 360, so a
grid may span the antimeridian (`lon_range_deg=(170.0, -170.0)`).
"""

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
    REQUIRED,
    SampleQuality,
    WeatherSample,
    WeatherVariable,
    interpolate_direction_deg,
    validate_query,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime, timedelta

    from numpy.typing import NDArray

    from nautical_deliverance.domain.contracts.geo import Position

# "linear" field: value = base + LAT * (lat - lat_min) + LON * (lon offset from west) + TIME * s.
# Direction variables are instead 350 deg on the west node, 10 deg on the next, then +20 deg per
# node, constant in latitude and time (a fixture for the unit-vector rule).
LAT_GRADIENT = 0.5
LON_GRADIENT = 0.25
TIME_GRADIENT_PER_S = 0.001
_FULL_CIRCLE = 360.0
_SOURCE = "uniform"
_SIDE = (0, 1)


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
        time_range: tuple[datetime, datetime],
        run_time: datetime,
        grid_step_deg: float,
        time_step: timedelta,
        field: Literal["uniform", "linear"] = "uniform",
    ) -> None:
        """Build the grid; `values` must contain every required variable."""
        missing = REQUIRED - values.keys()
        if missing:
            raise MissingRequiredVariableError(frozenset(v.value for v in missing))
        self._lat0, self._lat1 = lat_range_deg
        self._west = lon_range_deg[0]
        self._width = (lon_range_deg[1] - lon_range_deg[0]) % _FULL_CIRCLE
        self._step = grid_step_deg
        self._t0 = to_datetime64(time_range[0])
        self._t1 = to_datetime64(time_range[1])
        self._tstep = time_step.total_seconds()
        t_span = (self._t1 - self._t0) / np.timedelta64(1, "s")
        self._shape = (
            _count(float(t_span), self._tstep),
            _count(self._lat1 - self._lat0, self._step),
            _count(self._width, self._step),
        )
        self._run_time = to_datetime64(run_time)
        self._unavailable = frozenset(v for v in WeatherVariable if v not in values)
        it, ilat, ilon = np.ogrid[: self._shape[0], : self._shape[1], : self._shape[2]]
        self._grid = {v: self._field(v, base, field, it, ilat, ilon) for v, base in values.items()}

    def _field(  # noqa: PLR0913, PLR0917
        self,
        var: WeatherVariable,
        base: float,
        field: str,
        it: NDArray[np.intp],
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
            + LAT_GRADIENT * self._step * ilat
            + LON_GRADIENT * self._step * ilon
            + TIME_GRADIENT_PER_S * self._tstep * it
            + np.zeros(shape)
        )

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        """Sample all variables; points outside the grid or time range are NaN and flagged."""
        validate_query(lat_deg, lon_deg, valid_time)
        offset = (lon_deg - self._west) % _FULL_CIRCLE
        secs = (valid_time - self._t0) / np.timedelta64(1, "s")
        in_space = (lat_deg >= self._lat0) & (lat_deg <= self._lat1) & (offset <= self._width)
        in_time = (valid_time >= self._t0) & (valid_time <= self._t1)
        quality = np.where(
            ~in_space,
            SampleQuality.OUT_OF_COVERAGE.value,
            np.where(~in_time, SampleQuality.OUT_OF_TIME_RANGE.value, SampleQuality.OK.value),
        )
        ok = quality == SampleQuality.OK.value

        it, ft = _locate(secs / self._tstep, self._shape[0])
        iy, fy = _locate((lat_deg - self._lat0) / self._step, self._shape[1])
        ix, fx = _locate(offset / self._step, self._shape[2])
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
            values[var] = np.where(ok, out, np.nan)
        run_time = np.where(ok, self._run_time, np.datetime64("NaT", "s")).astype("datetime64[s]")
        return WeatherSample(values, quality, _SOURCE, run_time, self._unavailable)

    def sample_point(self, position: Position, valid_time: datetime) -> WeatherSample:
        """Scalar convenience wrapper around `sample`."""
        return self.sample(
            np.array([position.lat_deg]),
            np.array([position.lon_deg]),
            np.array([to_datetime64(valid_time)], dtype="datetime64[s]"),
        )
