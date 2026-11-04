"""Reusable weather conformance suite (S0b-R07).

Subclass `WeatherProviderConformance`, set `grid`, and implement `make_provider` and
`make_linear_provider`. The suite uses plain `assert` / numpy testing, so a broken provider fails
with `AssertionError`.

Contract for `make_linear_provider()` (returns provider plus an expected-value function):
every non-direction variable is linear in latitude, longitude offset from the west edge and time;
every `*_from_deg` variable is 350 degrees on the west longitude node, 10 degrees on the next
longitude node (any further nodes arbitrary) and constant in latitude and time.
`make_provider()` is any provider on the same grid.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta  # noqa: TC003 - dataclass field types

import numpy as np
import pytest
from numpy.typing import NDArray

from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.geo import Position
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.weather import (
    DIRECTIONS,
    REQUIRED,
    SampleQuality,
    WeatherProvider,
    WeatherSample,
    WeatherVariable,
)

type Expected = Callable[
    [NDArray[np.float64], NDArray[np.float64], NDArray[np.datetime64]],
    Mapping[WeatherVariable, NDArray[np.float64]],
]
_TOL = 1e-9
_FULL_CIRCLE = 360.0


@dataclass(frozen=True, slots=True)
class GridDescription:
    """Coverage of a provider. `lon_east_deg < lon_west_deg` means the grid crosses 180."""

    lat_min_deg: float
    lat_max_deg: float
    lon_west_deg: float
    lon_east_deg: float
    step_deg: float
    start: datetime
    end: datetime
    time_step: timedelta

    @property
    def is_global(self) -> bool:
        """True when the longitude span is the full circle (east edge == west node)."""
        return self.lon_east_deg - self.lon_west_deg == _FULL_CIRCLE


def wrap_lon(lon: float) -> float:
    """Normalize a longitude to [-180, 180); values already in range are returned unchanged."""
    if -180.0 <= lon < 180.0:  # noqa: PLR2004
        return lon
    return (lon + 180.0) % 360.0 - 180.0


def _f(*vals: float) -> NDArray[np.float64]:
    return np.array(vals, dtype=np.float64)


def _t(*vals: datetime) -> NDArray[np.datetime64]:
    return np.array([to_datetime64(v) for v in vals], dtype="datetime64[s]")


def _all_nan(sample: WeatherSample) -> bool:
    return all(bool(np.isnan(a).all()) for a in sample.values.values())


class WeatherProviderConformance:
    """Mixin of conformance tests; concrete subclasses supply the provider."""

    grid: GridDescription

    def make_provider(self) -> WeatherProvider:
        """Return a provider covering `grid`."""
        raise NotImplementedError

    def make_linear_provider(self) -> tuple[WeatherProvider, Expected]:
        """Return a linear-field provider on `grid` and its expected-value function."""
        raise NotImplementedError

    def _mid(self) -> tuple[float, float, datetime]:
        g = self.grid
        lat = g.lat_min_deg + g.step_deg
        lon = wrap_lon(g.lon_west_deg + g.step_deg)
        return lat, lon, g.start + g.time_step

    # -- input validation ------------------------------------------------------------------
    @pytest.mark.req("S0b-R07")
    def test_lengths_preserved(self) -> None:
        """Every output array has the input length, for in- and out-of-coverage points."""
        g = self.grid
        lat, lon, t = self._mid()
        lats = _f(lat, g.lat_max_deg + 5, lat, lat, lat, lat, lat)
        lons = _f(*([lon] * 7))
        times = _t(t, t, g.end + g.time_step, t, t, t, t)
        s = self.make_provider().sample(lats, lons, times)
        n = 7
        assert len(s.quality) == len(s.run_time) == n
        assert all(len(a) == n for a in s.values.values())

    @pytest.mark.req("S0b-R07")
    def test_mismatched_lengths_rejected(self) -> None:
        """Arrays of different lengths raise InvalidInputError, never broadcast."""
        lat, lon, t = self._mid()
        p = self.make_provider()
        for args in (
            (_f(lat, lat), _f(lon), _t(t, t)),
            (_f(lat), _f(lon, lon), _t(t)),
            (_f(lat, lat), _f(lon, lon), _t(t)),
        ):
            with pytest.raises(InvalidInputError):
                p.sample(*args)

    @pytest.mark.req("S0b-R07")
    def test_nan_coordinate_rejected(self) -> None:
        """NaN or infinite coordinates raise InvalidInputError."""
        lat, lon, t = self._mid()
        p = self.make_provider()
        for bad_lat, bad_lon in ((np.nan, lon), (lat, np.inf), (-np.inf, lon)):
            with pytest.raises(InvalidInputError):
                p.sample(_f(bad_lat), _f(bad_lon), _t(t))

    @pytest.mark.req("S0b-R07")
    def test_required_present(self) -> None:
        """All required variables are delivered and none is flagged unavailable."""
        lat, lon, t = self._mid()
        s = self.make_provider().sample(_f(lat), _f(lon), _t(t))
        assert s.values.keys() >= REQUIRED
        assert not (s.unavailable & REQUIRED)

    # -- coverage --------------------------------------------------------------------------
    @pytest.mark.req("S0b-R07")
    def test_no_extrapolation_space(self) -> None:
        """One grid step beyond each spatial edge is NaN with OUT_OF_COVERAGE."""
        g = self.grid
        lat, lon, t = self._mid()
        lats = [g.lat_min_deg - g.step_deg, g.lat_max_deg + g.step_deg]
        lons = [lon, lon]
        if not g.is_global:  # a global grid has no longitude edge
            lats += [lat, lat]
            lons += [wrap_lon(g.lon_west_deg - g.step_deg), wrap_lon(g.lon_east_deg + g.step_deg)]
        s = self.make_provider().sample(_f(*lats), _f(*lons), _t(*([t] * len(lats))))
        assert list(s.quality) == [SampleQuality.OUT_OF_COVERAGE.value] * len(lats)
        assert _all_nan(s)

    @pytest.mark.req("S0b-R07")
    def test_no_extrapolation_time(self) -> None:
        """One time step before the start or after the end is NaN with OUT_OF_TIME_RANGE."""
        g = self.grid
        lat, lon, _ = self._mid()
        s = self.make_provider().sample(
            _f(lat, lat), _f(lon, lon), _t(g.start - g.time_step, g.end + g.time_step)
        )
        assert list(s.quality) == [SampleQuality.OUT_OF_TIME_RANGE.value] * 2
        assert _all_nan(s)

    @pytest.mark.req("S0b-R07")
    def test_boundary_inclusive(self) -> None:
        """Points exactly on every edge, and at the last forecast step, are OK."""
        g = self.grid
        lats = _f(g.lat_min_deg, g.lat_max_deg, g.lat_min_deg, g.lat_max_deg, g.lat_min_deg)
        lons = _f(
            wrap_lon(g.lon_west_deg),
            wrap_lon(g.lon_east_deg),
            wrap_lon(g.lon_east_deg),
            wrap_lon(g.lon_west_deg),
            wrap_lon(g.lon_west_deg),
        )
        times = _t(g.start, g.end, g.end, g.end, g.start)
        s = self.make_provider().sample(lats, lons, times)
        assert list(s.quality) == [SampleQuality.OK.value] * 5
        assert all(bool(np.isfinite(a).all()) for a in s.values.values())

    # -- interpolation ---------------------------------------------------------------------
    @pytest.mark.req("S0b-R07")
    def test_exact_at_nodes(self) -> None:
        """At grid nodes the provider reproduces the node values exactly."""
        g = self.grid
        provider, expected = self.make_linear_provider()
        lat_n = round((g.lat_max_deg - g.lat_min_deg) / g.step_deg)
        lon_n = round(((g.lon_east_deg - g.lon_west_deg) % 360.0) / g.step_deg)
        t_n = round((g.end - g.start) / g.time_step)
        lats = _f(
            *(
                g.lat_max_deg if i == lat_n else g.lat_min_deg + g.step_deg * i
                for i in (0, lat_n, 1, lat_n // 2)
            )
        )
        lons = _f(
            *(
                wrap_lon(g.lon_east_deg if j == lon_n else g.lon_west_deg + g.step_deg * j)
                for j in (0, lon_n, 1, lon_n // 2)
            )
        )
        times = _t(*(g.start + g.time_step * k for k in (0, t_n, 1, t_n // 2)))
        s = provider.sample(lats, lons, times)
        assert list(s.quality) == [SampleQuality.OK.value] * 4
        for var, exp in expected(lats, lons, times).items():
            np.testing.assert_allclose(s.values[var], exp, rtol=0, atol=_TOL)

    @pytest.mark.req("S0b-R07")
    def test_linear_field_exact_between_nodes(self) -> None:
        """Bilinear/linear interpolation reproduces a linear field at off-node points."""
        g = self.grid
        provider, expected = self.make_linear_provider()
        rng = np.random.default_rng(7)
        n = 40
        width = (g.lon_east_deg - g.lon_west_deg) % 360.0
        lats = rng.uniform(g.lat_min_deg, g.lat_max_deg, n)
        lons = np.array([wrap_lon(g.lon_west_deg + o) for o in rng.uniform(0, width, n)])
        span = (g.end - g.start).total_seconds()
        offsets = rng.uniform(0, span, n).astype(np.int64)
        times = (to_datetime64(g.start) + offsets.astype("timedelta64[s]")).astype("datetime64[s]")
        s = provider.sample(lats, lons, times)
        assert list(s.quality) == [SampleQuality.OK.value] * n
        for var, exp in expected(lats, lons, times).items():
            np.testing.assert_allclose(s.values[var], exp, rtol=0, atol=_TOL)

    @pytest.mark.req("S0b-R07")
    def test_direction_unit_vector(self) -> None:
        """Between nodes at 350 and 10 degrees the direction is 0, not 180."""
        g = self.grid
        provider, _ = self.make_linear_provider()
        lon = wrap_lon(g.lon_west_deg + g.step_deg / 2)
        s = provider.sample(_f(g.lat_min_deg), _f(lon), _t(g.start))
        for var in DIRECTIONS:
            d = float(s.values[var][0])
            assert abs((d + 180.0) % _FULL_CIRCLE - 180.0) < _TOL, (var, d)
            assert 0.0 <= d < _FULL_CIRCLE

    @pytest.mark.req("S0b-R07")
    def test_source_and_run_time_set_for_ok_points(self) -> None:
        """OK points carry a non-empty source and a valid run time."""
        lat, lon, t = self._mid()
        s = self.make_provider().sample(_f(lat), _f(lon), _t(t))
        assert s.source
        assert not np.isnat(s.run_time).any()
        assert s.run_time.dtype == np.dtype("datetime64[s]")

    @pytest.mark.req("S0b-R07")
    def test_sample_point_matches_vectorized(self) -> None:
        """sample_point equals the length-1 vectorized result."""
        lat, lon, t = self._mid()
        p = self.make_provider()
        a = p.sample_point(Position(lat, lon), t)
        b = p.sample(_f(lat), _f(lon), _t(t))
        assert a.values.keys() == b.values.keys()
        for var in a.values:
            np.testing.assert_array_equal(a.values[var], b.values[var])
        np.testing.assert_array_equal(a.quality, b.quality)
        np.testing.assert_array_equal(a.run_time, b.run_time)
        assert (a.source, a.unavailable) == (b.source, b.unavailable)

    @pytest.mark.req("S0b-R07")
    def test_antimeridian_query(self) -> None:
        """A grid spanning 170E-170W is interpolated correctly at 179.5 and -179.5."""
        g = self.grid
        if g.lon_east_deg >= g.lon_west_deg:
            pytest.skip("grid does not cross the antimeridian")
        provider, expected = self.make_linear_provider()
        lats = _f(g.lat_min_deg + g.step_deg * 0.5, g.lat_min_deg + g.step_deg * 1.5)
        lons = _f(179.5, -179.5)
        times = _t(g.start + g.time_step / 3, g.start + g.time_step / 2)
        s = provider.sample(lats, lons, times)
        assert list(s.quality) == [SampleQuality.OK.value] * 2
        for var, exp in expected(lats, lons, times).items():
            np.testing.assert_allclose(s.values[var], exp, rtol=0, atol=_TOL)
