"""Run the weather conformance suite on the reference provider and prove it can fail (S0b-R09)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np
import pytest

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    MissingRequiredVariableError,
)
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.weather import (
    DIRECTIONS,
    SampleQuality,
    WeatherGroup,
    WeatherProvider,
    WeatherSample,
    WeatherVariable,
)
from nautical_deliverance.domain.reference import uniform_weather
from nautical_deliverance.domain.reference.uniform_weather import (
    LAT_GRADIENT,
    LON_GRADIENT,
    TIME_GRADIENT_PER_S,
    GroupWindow,
    UniformWeather,
)
from tests.contracts.conformance_weather import (
    Expected,
    WeatherProviderConformance,
    wrap_lon,
)
from tests.contracts.weather_fixtures import BASE, GRID, RUN, make_uniform

if TYPE_CHECKING:
    from numpy.typing import NDArray

_OK = SampleQuality.OK.value
_START = datetime(2026, 11, 4, tzinfo=UTC)
_HOUR = timedelta(hours=1)
# GFS-like valid times: hourly for three hours, then every three hours
_GFS_TIMES = tuple(_START + _HOUR * h for h in (0, 1, 2, 3, 6, 9, 12))


def _f(*vals: float) -> NDArray[np.float64]:
    return np.array(vals, dtype=np.float64)


def _t(*vals: datetime) -> NDArray[np.datetime64]:
    return np.array([to_datetime64(v) for v in vals], dtype="datetime64[s]")


class _UniformSuite(WeatherProviderConformance):
    """Runs the suite on `UniformWeather` over `self.grid`."""

    def make_provider(self) -> WeatherProvider:
        """Return the uniform field."""
        return make_uniform("uniform", grid=self.grid)

    def make_linear_provider(self) -> tuple[WeatherProvider, Expected]:
        """Return the linear field and its analytical values."""
        g = self.grid

        def expected(
            lat: NDArray[np.float64], lon: NDArray[np.float64], t: NDArray[np.datetime64]
        ) -> dict[WeatherVariable, NDArray[np.float64]]:
            dlon = (lon - g.lon_west_deg) % 360.0
            secs = (t - to_datetime64(g.start)) / np.timedelta64(1, "s")
            return {
                v: base
                + LAT_GRADIENT * (lat - g.lat_min_deg)
                + LON_GRADIENT * dlon
                + TIME_GRADIENT_PER_S * secs
                for v, base in BASE.items()
                if v not in DIRECTIONS
            }

        return make_uniform("linear", grid=g), expected


class TestUniformWeather(_UniformSuite):
    """Antimeridian-crossing grid."""

    grid = GRID


class TestUniformWeatherPlain(_UniformSuite):
    """Ordinary non-crossing grid with non-integer steps."""

    grid = replace(
        GRID,
        lat_min_deg=50.1,
        lat_max_deg=60.3,
        lon_west_deg=-10.3,
        lon_east_deg=9.9,
        lat_step_deg=0.2,
        lon_step_deg=0.2,
    )


class TestUniformWeatherGlobal(_UniformSuite):
    """Global grid from -180: the east edge is the west node again."""

    grid = replace(GRID, lon_west_deg=-180.0, lon_east_deg=180.0)


class TestUniformWeatherGlobalFromZero(_UniformSuite):
    """Global grid from 0 (GFS style): the antimeridian is mid-grid."""

    grid = replace(GRID, lon_west_deg=0.0, lon_east_deg=360.0)


class TestUniformWeatherNonUniformTime(_UniformSuite):
    """Different lat/lon steps and valid times 1 h apart, then 3 h apart, across 180."""

    grid = replace(GRID, lat_step_deg=0.5, lon_step_deg=2.0, times=_GFS_TIMES)


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


class _NearestTime(UniformWeather):
    """Broken: snaps the valid time to the nearest forecast step instead of interpolating."""

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        nodes = _t(*GRID.times)
        inside = (valid_time >= nodes[0]) & (valid_time <= nodes[-1])
        nearest = nodes[np.abs(valid_time[:, None] - nodes[None, :]).argmin(axis=1)]
        return super().sample(lat_deg, lon_deg, np.where(inside, nearest, valid_time))


class _NoAntimeridianWrap(UniformWeather):
    """Broken: longitudes west of the grid's west edge are not wrapped round the globe."""

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        west = GRID.lon_west_deg
        return super().sample(lat_deg, np.where(lon_deg < west, west - 1.0, lon_deg), valid_time)


class _NoSeam(UniformWeather):
    """Broken: a global grid whose last column does not connect to the first."""

    def sample(
        self,
        lat_deg: NDArray[np.float64],
        lon_deg: NDArray[np.float64],
        valid_time: NDArray[np.datetime64],
    ) -> WeatherSample:
        g = TestUniformWeatherGlobal.grid
        seam = (lon_deg - g.lon_west_deg) % 360.0 > 360.0 - g.lon_step_deg
        return super().sample(np.where(seam, g.lat_max_deg + 10.0, lat_deg), lon_deg, valid_time)


def _broken(suite: type[_UniformSuite], cls: type[UniformWeather]) -> _UniformSuite:
    class Broken(suite):  # type: ignore[valid-type, misc]
        def make_provider(self) -> WeatherProvider:
            return make_uniform("uniform", cls, self.grid)

        def make_linear_provider(self) -> tuple[WeatherProvider, Expected]:
            _, expected = super().make_linear_provider()
            return make_uniform("linear", cls, self.grid), expected

    return Broken()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_extrapolating_provider() -> None:
    """An extrapolating provider is rejected by the space and time checks."""
    suite = _broken(TestUniformWeather, _Extrapolating)
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


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_nearest_neighbour_in_time() -> None:
    """Snapping to the nearest forecast step instead of interpolating fails the linear checks."""
    suite = _broken(TestUniformWeather, _NearestTime)
    with pytest.raises(AssertionError):
        suite.test_linear_field_exact_between_nodes()


@pytest.mark.req("S0b-R09")
def test_suite_fails_without_antimeridian_wrap() -> None:
    """A provider that does not wrap longitudes round 180 fails the antimeridian check."""
    suite = _broken(TestUniformWeather, _NoAntimeridianWrap)
    with pytest.raises(AssertionError):
        suite.test_antimeridian_query()


@pytest.mark.req("S0b-R09")
def test_suite_fails_without_global_seam() -> None:
    """A global grid that does not connect its last and first column fails the seam check."""
    suite = _broken(TestUniformWeatherGlobal, _NoSeam)
    with pytest.raises(AssertionError):
        suite.test_global_seam()


@pytest.mark.req("S0b-R07")
def test_uniform_weather_constructor_checks() -> None:
    """Missing variables, steps that do not divide the grid and bad times are rejected."""
    g = GRID
    args = ((g.lat_min_deg, g.lat_max_deg), (170.0, 175.0), g.times, RUN)
    with pytest.raises(MissingRequiredVariableError):
        UniformWeather({}, *args, 1.0, 1.0)
    with pytest.raises(InvalidInputError):
        UniformWeather(BASE, *args, 1.5, 1.0)
    with pytest.raises(InvalidInputError):
        UniformWeather(BASE, *args[:2], g.times[::-1], RUN, 1.0, 1.0)
    with pytest.raises(InvalidInputError):
        UniformWeather(BASE, *args[:2], g.times[:1], RUN, 1.0, 1.0)


@pytest.mark.req("S0b-R07")
def test_global_grid_wraps_last_column_to_first() -> None:
    """On a global linear grid the seam cell interpolates towards the first column's value."""
    g = TestUniformWeatherGlobal.grid
    lons = _f(*(wrap_lon(g.lon_west_deg + o) for o in (359.5, 359.0, 0.0)))
    s = make_uniform("linear", grid=g).sample(
        _f(41.0, 41.0, 41.0), lons, _t(g.start, g.start, g.start)
    )
    for var, values in s.values.items():
        if var not in DIRECTIONS:
            assert values[0] == pytest.approx((values[1] + values[2]) / 2)


@pytest.mark.req("S0b-R07")
def test_groups_report_their_own_coverage_source_and_run_time() -> None:
    """Wind is OK while current is out of coverage and waves out of time, at the same point."""
    g = GRID
    earlier = RUN - 6 * _HOUR
    windows = {
        WeatherGroup.CURRENT: GroupWindow(
            lat_range_deg=(40.0, 41.0), run_time=earlier, source="ocean"
        ),
        WeatherGroup.WAVES: GroupWindow(time_range=(g.times[0], g.times[2])),
    }
    p = make_uniform("uniform", group_windows=windows)
    lats, lons = _f(43.0, 40.5, 40.5), _f(175.0, 175.0, 175.0)
    s = p.sample(lats, lons, _t(g.times[3], g.times[1], g.times[3]))

    ooc, oot = SampleQuality.OUT_OF_COVERAGE.value, SampleQuality.OUT_OF_TIME_RANGE.value
    assert list(s.quality[WeatherGroup.WIND]) == [_OK, _OK, _OK]
    assert list(s.quality[WeatherGroup.CURRENT]) == [ooc, _OK, _OK]
    assert list(s.quality[WeatherGroup.WAVES]) == [oot, _OK, oot]
    nan = {v: bool(np.isnan(a[0])) for v, a in s.values.items()}
    assert not nan[WeatherVariable.WIND_U_MPS]
    assert nan[WeatherVariable.CURRENT_U_MPS]
    assert nan[WeatherVariable.TOTAL_SEA_HEIGHT_M]
    assert s.source[WeatherGroup.CURRENT] == "ocean"
    assert s.source[WeatherGroup.WIND] == "uniform"
    assert s.run_time[WeatherGroup.CURRENT][1] == to_datetime64(earlier)
    assert s.run_time[WeatherGroup.WIND][1] == to_datetime64(RUN)
    assert np.isnat(s.run_time[WeatherGroup.CURRENT][0])


@pytest.mark.req("S0b-R07")
def test_group_windows_must_fit_the_grid() -> None:
    """Windows outside the grid, or for groups that have no variables, are rejected."""
    g = GRID
    for window in (
        GroupWindow(lat_range_deg=(39.0, 44.0)),
        GroupWindow(time_range=(g.start - _HOUR, g.end)),
    ):
        with pytest.raises(InvalidInputError):
            make_uniform("uniform", group_windows={WeatherGroup.WIND: window})
    with pytest.raises(InvalidInputError):
        make_uniform("uniform", group_windows={WeatherGroup.SEA_ICE: GroupWindow()})


@pytest.mark.req("S0b-R07")
def test_optional_group_is_reported_when_provided() -> None:
    """An optional variable brings its own group; the others stay unavailable."""
    values = {**BASE, WeatherVariable.VISIBILITY_M: 10000.0}
    windows = {WeatherGroup.VISIBILITY: GroupWindow(lat_range_deg=(40.0, 41.0))}
    s = make_uniform("uniform", values=values, group_windows=windows).sample(
        _f(43.0), _f(175.0), _t(GRID.start)
    )

    assert s.quality[WeatherGroup.VISIBILITY][0] == SampleQuality.OUT_OF_COVERAGE
    assert s.quality[WeatherGroup.WIND][0] == SampleQuality.OK
    assert s.unavailable == {
        WeatherVariable.SEA_ICE_CONCENTRATION_RATIO,
        WeatherVariable.MEAN_SEA_LEVEL_PRESSURE_PA,
    }
