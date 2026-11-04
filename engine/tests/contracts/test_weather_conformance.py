"""Run the weather conformance suite on the reference provider and prove it can fail (S0b-R09)."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import numpy as np
import pytest

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    MissingRequiredVariableError,
)
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.weather import (
    DIRECTIONS,
    REQUIRED,
    WeatherProvider,
    WeatherSample,
    WeatherVariable,
)
from nautical_deliverance.domain.reference import uniform_weather
from nautical_deliverance.domain.reference.uniform_weather import (
    LAT_GRADIENT,
    LON_GRADIENT,
    TIME_GRADIENT_PER_S,
    UniformWeather,
)
from tests.contracts.conformance_weather import (
    Expected,
    GridDescription,
    WeatherProviderConformance,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

GRID = GridDescription(
    lat_min_deg=40.0,
    lat_max_deg=44.0,
    lon_west_deg=170.0,
    lon_east_deg=-170.0,
    step_deg=1.0,
    start=datetime(2026, 11, 4, tzinfo=UTC),
    end=datetime(2026, 11, 4, 12, tzinfo=UTC),
    time_step=timedelta(hours=3),
)
_RUN = datetime(2026, 11, 3, 18, tzinfo=UTC)
_BASE = {v: float(i + 1) for i, v in enumerate(sorted(REQUIRED))}


def _make(
    field: Literal["uniform", "linear"], cls: type[UniformWeather] = UniformWeather
) -> UniformWeather:
    g = GRID
    return cls(
        _BASE,
        (g.lat_min_deg, g.lat_max_deg),
        (g.lon_west_deg, g.lon_east_deg),
        (g.start, g.end),
        _RUN,
        g.step_deg,
        g.time_step,
        field=field,
    )


class TestUniformWeather(WeatherProviderConformance):
    """The analytical reference provider passes the suite."""

    grid = GRID

    def make_provider(self) -> WeatherProvider:
        """Return the uniform field."""
        return _make("uniform")

    def make_linear_provider(self) -> tuple[WeatherProvider, Expected]:
        """Return the linear field and its analytical values."""

        def expected(
            lat: NDArray[np.float64], lon: NDArray[np.float64], t: NDArray[np.datetime64]
        ) -> dict[WeatherVariable, NDArray[np.float64]]:
            dlon = (lon - GRID.lon_west_deg) % 360.0
            secs = (t - to_datetime64(GRID.start)) / np.timedelta64(1, "s")
            return {
                v: base
                + LAT_GRADIENT * (lat - GRID.lat_min_deg)
                + LON_GRADIENT * dlon
                + TIME_GRADIENT_PER_S * secs
                for v, base in _BASE.items()
                if v not in DIRECTIONS
            }

        return _make("linear"), expected


class _Extrapolating(UniformWeather):
    """Broken: clamps queries into the grid instead of flagging them."""

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        lo, hi = to_datetime64(GRID.start), to_datetime64(GRID.end)
        return super().sample(
            np.clip(lat_deg, GRID.lat_min_deg, GRID.lat_max_deg),
            lon_deg,
            np.clip(valid_time, lo, hi),
        )


class _ExtrapolatingSuite(TestUniformWeather):
    def make_provider(self) -> WeatherProvider:
        return _make("uniform", _Extrapolating)


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_extrapolating_provider() -> None:
    """An extrapolating provider is rejected by the space and time checks."""
    suite = _ExtrapolatingSuite()
    with pytest.raises(AssertionError):
        suite.test_no_extrapolation_space()
    with pytest.raises(AssertionError):
        suite.test_no_extrapolation_time()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_naive_direction_average(monkeypatch: pytest.MonkeyPatch) -> None:
    """Averaging degrees arithmetically (350, 10 -> 180) is rejected."""

    def naive(weights: NDArray[np.float64], deg: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray((weights * deg).sum(axis=0) % 360.0)

    monkeypatch.setattr(uniform_weather, "interpolate_direction_deg", naive)
    with pytest.raises(AssertionError):
        TestUniformWeather().test_direction_unit_vector()


@pytest.mark.req("S0b-R07")
def test_uniform_weather_constructor_checks() -> None:
    """Missing required variables and steps that do not divide the grid are rejected."""
    g = GRID
    args = ((g.lat_min_deg, g.lat_max_deg), (170.0, 175.0), (g.start, g.end), _RUN)
    with pytest.raises(MissingRequiredVariableError):
        UniformWeather({}, *args, 1.0, g.time_step)
    with pytest.raises(InvalidInputError):
        UniformWeather(_BASE, *args, 1.5, g.time_step)
