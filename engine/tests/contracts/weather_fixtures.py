"""Shared weather test fixtures: the reference grid and a builder for `UniformWeather`."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from nautical_deliverance.domain.contracts.weather import REQUIRED, WeatherGroup, WeatherVariable
from nautical_deliverance.domain.reference.uniform_weather import GroupWindow, UniformWeather
from tests.contracts.conformance_weather import GridDescription

if TYPE_CHECKING:
    from collections.abc import Mapping

RUN = datetime(2026, 11, 3, 18, tzinfo=UTC)
BASE = {v: float(i + 1) for i, v in enumerate(sorted(REQUIRED))}


def uniform_times(start: datetime, end: datetime, step: timedelta) -> tuple[datetime, ...]:
    """Return the valid times from `start` to `end` inclusive, `step` apart."""
    count = round((end - start) / step)
    return tuple(start + step * k for k in range(count + 1))


GRID = GridDescription(
    lat_min_deg=40.0,
    lat_max_deg=44.0,
    lon_west_deg=170.0,
    lon_east_deg=-170.0,
    lat_step_deg=1.0,
    lon_step_deg=1.0,
    times=uniform_times(
        datetime(2026, 11, 4, tzinfo=UTC), datetime(2026, 11, 4, 12, tzinfo=UTC), timedelta(hours=3)
    ),
)


def make_uniform(  # noqa: PLR0913, PLR0917 - a test builder with one knob per concern
    field: Literal["uniform", "linear"],
    cls: type[UniformWeather] = UniformWeather,
    grid: GridDescription = GRID,
    values: Mapping[WeatherVariable, float] | None = None,
    group_windows: Mapping[WeatherGroup, GroupWindow] | None = None,
    run_time: datetime = RUN,
) -> UniformWeather:
    """Build a `UniformWeather` covering `grid`."""
    g = grid
    return cls(
        BASE if values is None else values,
        (g.lat_min_deg, g.lat_max_deg),
        (g.lon_west_deg, g.lon_east_deg),
        g.times,
        run_time,
        g.lat_step_deg,
        g.lon_step_deg,
        field=field,
        group_windows=group_windows,
    )
