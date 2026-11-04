"""Reusable weather conformance suite (S0b-R07).

Subclass `WeatherProviderConformance`, set `grid`, and implement `make_provider` and
`make_linear_provider`. The suite uses plain `assert` / numpy testing, so a broken provider fails
with `AssertionError`.

Contract for `make_linear_provider()` (returns provider plus an expected-value function):
every non-direction variable is linear in latitude, longitude offset from the west edge and time
(seconds since the first valid time); every `*_from_deg` variable is 350 degrees on the west
longitude node, 10 degrees on the next longitude node (any further nodes arbitrary) and constant
in latitude and time. On a global grid the linear field is only checked for longitude offsets in
[0, 360 - lon_step]: past the last column it wraps to the first, so it cannot stay linear.
`make_provider()` is a provider on the same grid whose fields are constant in longitude (a
uniform field qualifies); the global-seam test relies on that.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta  # noqa: TC003 - dataclass field types

import numpy as np
import pytest
from numpy.typing import NDArray

from nautical_deliverance.domain.contracts.errors import InvalidInputError, InvalidPositionError
from nautical_deliverance.domain.contracts.geo import Position
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.weather import (
    DIRECTIONS,
    GROUP_OF,
    REQUIRED,
    REQUIRED_GROUPS,
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
_MAX_LAT_DEG = 90.0
_OK = SampleQuality.OK.value


@dataclass(frozen=True, slots=True)
class GridDescription:
    """Coverage of a provider. `lon_east_deg < lon_west_deg` means the grid crosses 180.

    `times` are the valid times in increasing order (at least two); their spacing may vary.
    """

    lat_min_deg: float
    lat_max_deg: float
    lon_west_deg: float
    lon_east_deg: float
    lat_step_deg: float
    lon_step_deg: float
    times: tuple[datetime, ...]

    @property
    def is_global(self) -> bool:
        """True when the longitude span is the full circle (east edge == west node)."""
        return self.lon_east_deg - self.lon_west_deg == _FULL_CIRCLE

    @property
    def lon_width_deg(self) -> float:
        """Longitude span of the grid, 360 for a global grid."""
        return _FULL_CIRCLE if self.is_global else (self.lon_east_deg - self.lon_west_deg) % 360.0

    @property
    def linear_width_deg(self) -> float:
        """Longitude span in which a linear field stays linear (a global grid wraps at the end)."""
        return self.lon_width_deg - (self.lon_step_deg if self.is_global else 0.0)

    @property
    def start(self) -> datetime:
        """First valid time."""
        return self.times[0]

    @property
    def end(self) -> datetime:
        """Last valid time."""
        return self.times[-1]

    @property
    def first_interval(self) -> timedelta:
        """Spacing of the first two valid times."""
        return self.times[1] - self.times[0]

    @property
    def last_interval(self) -> timedelta:
        """Spacing of the last two valid times."""
        return self.times[-1] - self.times[-2]


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


def _all_groups(sample: WeatherSample, code: int, n: int) -> bool:
    """Return True when every group of the sample has quality `code` at all `n` points."""
    return all(list(q) == [code] * n for q in sample.quality.values())


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % _FULL_CIRCLE - 180.0)


class WeatherProviderConformance:
    """Mixin of conformance tests; concrete subclasses supply the provider."""

    grid: GridDescription

    def make_provider(self) -> WeatherProvider:
        """Return a provider covering `grid`, constant in longitude."""
        raise NotImplementedError

    def make_linear_provider(self) -> tuple[WeatherProvider, Expected]:
        """Return a linear-field provider on `grid` and its expected-value function."""
        raise NotImplementedError

    def _mid(self) -> tuple[float, float, datetime]:
        g = self.grid
        lat = g.lat_min_deg + g.lat_step_deg
        lon = wrap_lon(g.lon_west_deg + g.lon_step_deg)
        return lat, lon, g.times[1]

    # -- input validation ------------------------------------------------------------------
    @pytest.mark.req("S0b-R07")
    def test_lengths_preserved(self) -> None:
        """Every output array has the input length, for in- and out-of-coverage points."""
        g = self.grid
        lat, lon, t = self._mid()
        lats = _f(lat, min(g.lat_max_deg + 5, _MAX_LAT_DEG), lat, lat, lat, lat, lat)
        lons = _f(*([lon] * 7))
        times = _t(t, t, g.end + g.last_interval, t, t, t, t)
        s = self.make_provider().sample(lats, lons, times)
        n = 7
        assert len(s) == n
        assert all(len(a) == n for a in s.values.values())
        assert all(len(a) == n for a in (*s.quality.values(), *s.run_time.values()))

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
    def test_latitude_beyond_pole_rejected(self) -> None:
        """A latitude beyond +-90 is an InvalidPositionError; any finite longitude is accepted."""
        lat, lon, t = self._mid()
        p = self.make_provider()
        for bad_lat in (90.5, -91.0):
            with pytest.raises(InvalidPositionError):
                p.sample(_f(bad_lat), _f(lon), _t(t))
        assert len(p.sample(_f(lat), _f(lon + 720.0), _t(t))) == 1

    @pytest.mark.req("S0b-R07")
    def test_required_present(self) -> None:
        """All required variables and groups are delivered and none is flagged unavailable."""
        lat, lon, t = self._mid()
        s = self.make_provider().sample(_f(lat), _f(lon), _t(t))
        assert s.values.keys() >= REQUIRED
        assert not (s.unavailable & REQUIRED)
        assert s.quality.keys() >= REQUIRED_GROUPS

    @pytest.mark.req("S0b-R07")
    def test_optional_variables_cannot_vanish(self) -> None:
        """Every variable is either delivered or reported unavailable."""
        lat, lon, t = self._mid()
        s = self.make_provider().sample(_f(lat), _f(lon), _t(t))
        assert s.values.keys() | s.unavailable == set(WeatherVariable)
        assert not (s.values.keys() & s.unavailable)

    @pytest.mark.req("S0b-R07")
    def test_every_variable_has_its_group(self) -> None:
        """Quality, source and run time exist for exactly the groups of the delivered variables."""
        lat, lon, t = self._mid()
        s = self.make_provider().sample(_f(lat), _f(lon), _t(t))
        groups = {GROUP_OF[v] for v in s.values}
        assert set(s.quality) == set(s.source) == set(s.run_time) == groups
        assert all(q.dtype == np.dtype("uint8") for q in s.quality.values())

    # -- coverage --------------------------------------------------------------------------
    @pytest.mark.req("S0b-R07")
    def test_no_extrapolation_space(self) -> None:
        """One grid step beyond each spatial edge is NaN with OUT_OF_COVERAGE."""
        g = self.grid
        lat, lon, t = self._mid()
        lats = [g.lat_min_deg - g.lat_step_deg, g.lat_max_deg + g.lat_step_deg]
        lons = [lon, lon]
        if not g.is_global:  # a global grid has no longitude edge
            lats += [lat, lat]
            lons += [
                wrap_lon(g.lon_west_deg - g.lon_step_deg),
                wrap_lon(g.lon_east_deg + g.lon_step_deg),
            ]
        keep = [i for i, la in enumerate(lats) if abs(la) <= _MAX_LAT_DEG]  # lat 90 has no beyond
        lats, lons = [lats[i] for i in keep], [lons[i] for i in keep]
        s = self.make_provider().sample(_f(*lats), _f(*lons), _t(*([t] * len(lats))))
        assert _all_groups(s, SampleQuality.OUT_OF_COVERAGE.value, len(lats))
        assert _all_nan(s)

    @pytest.mark.req("S0b-R07")
    def test_no_extrapolation_time(self) -> None:
        """One time step before the start or after the end is NaN with OUT_OF_TIME_RANGE."""
        g = self.grid
        lat, lon, _ = self._mid()
        s = self.make_provider().sample(
            _f(lat, lat), _f(lon, lon), _t(g.start - g.first_interval, g.end + g.last_interval)
        )
        assert _all_groups(s, SampleQuality.OUT_OF_TIME_RANGE.value, 2)
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
        assert _all_groups(s, _OK, 5)
        assert all(bool(np.isfinite(a).all()) for a in s.values.values())

    # -- interpolation ---------------------------------------------------------------------
    @pytest.mark.req("S0b-R07")
    def test_exact_at_nodes(self) -> None:
        """At grid nodes the provider reproduces the node values exactly."""
        g = self.grid
        provider, expected = self.make_linear_provider()
        lat_n = round((g.lat_max_deg - g.lat_min_deg) / g.lat_step_deg)
        lon_n = round(g.lon_width_deg / g.lon_step_deg)
        t_n = len(g.times) - 1
        lats = _f(
            *(
                g.lat_max_deg if i == lat_n else g.lat_min_deg + g.lat_step_deg * i
                for i in (0, lat_n, 1, lat_n // 2)
            )
        )
        lons = _f(
            *(
                wrap_lon(g.lon_east_deg if j == lon_n else g.lon_west_deg + g.lon_step_deg * j)
                for j in (0, lon_n, 1, lon_n // 2)
            )
        )
        times = _t(*(g.times[k] for k in (0, t_n, 1, t_n // 2)))
        s = provider.sample(lats, lons, times)
        assert _all_groups(s, _OK, 4)
        for var, exp in expected(lats, lons, times).items():
            np.testing.assert_allclose(s.values[var], exp, rtol=0, atol=_TOL)

    @pytest.mark.req("S0b-R07")
    def test_linear_field_exact_between_nodes(self) -> None:
        """Bilinear/linear interpolation reproduces a linear field at off-node points."""
        g = self.grid
        provider, expected = self.make_linear_provider()
        rng = np.random.default_rng(7)
        n = 40
        lats = rng.uniform(g.lat_min_deg, g.lat_max_deg, n)
        lons = np.array(
            [wrap_lon(g.lon_west_deg + o) for o in rng.uniform(0, g.linear_width_deg, n)]
        )
        span = (g.end - g.start).total_seconds()
        offsets = rng.uniform(0, span, n).astype(np.int64)
        times = (to_datetime64(g.start) + offsets.astype("timedelta64[s]")).astype("datetime64[s]")
        s = provider.sample(lats, lons, times)
        assert _all_groups(s, _OK, n)
        for var, exp in expected(lats, lons, times).items():
            np.testing.assert_allclose(s.values[var], exp, rtol=0, atol=_TOL)

    @pytest.mark.req("S0b-R07")
    def test_direction_unit_vector(self) -> None:
        """Between nodes at 350 and 10 degrees the direction is 0, not 180."""
        g = self.grid
        provider, _ = self.make_linear_provider()
        lon = wrap_lon(g.lon_west_deg + g.lon_step_deg / 2)
        s = provider.sample(_f(g.lat_min_deg), _f(lon), _t(g.start))
        for var in DIRECTIONS:
            d = float(s.values[var][0])
            assert abs((d + 180.0) % _FULL_CIRCLE - 180.0) < _TOL, (var, d)
            assert 0.0 <= d < _FULL_CIRCLE

    @pytest.mark.req("S0b-R07")
    def test_source_and_run_time_set_for_ok_points(self) -> None:
        """OK points carry a non-empty source and a valid run time, per group."""
        lat, lon, t = self._mid()
        s = self.make_provider().sample(_f(lat), _f(lon), _t(t))
        for group in s.quality:
            assert s.source[group]
            assert not np.isnat(s.run_time[group]).any()
            assert s.run_time[group].dtype == np.dtype("datetime64[s]")

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
        assert a.quality.keys() == b.quality.keys()
        for group in a.quality:
            np.testing.assert_array_equal(a.quality[group], b.quality[group])
            np.testing.assert_array_equal(a.run_time[group], b.run_time[group])
        assert (dict(a.source), a.unavailable) == (dict(b.source), b.unavailable)

    @pytest.mark.req("S0b-R07")
    def test_antimeridian_query(self) -> None:
        """A grid covering 180 is interpolated correctly at 179.5 and -179.5."""
        g = self.grid
        if not (g.is_global or g.lon_east_deg < g.lon_west_deg):
            pytest.skip("grid does not cover the antimeridian")
        provider, expected = self.make_linear_provider()
        # on a global grid a query in the wrap cell cannot be checked against a linear field
        queries = [
            (la, lo, t)
            for la, lo, t in (
                (g.lat_min_deg + g.lat_step_deg * 0.5, 179.5, g.start + g.first_interval / 3),
                (g.lat_min_deg + g.lat_step_deg * 1.5, -179.5, g.start + g.first_interval / 2),
            )
            if (lo - g.lon_west_deg) % _FULL_CIRCLE <= g.linear_width_deg
        ]
        assert queries
        lats, lons, times = (
            _f(*(q[0] for q in queries)),
            _f(*(q[1] for q in queries)),
            _t(*(q[2] for q in queries)),
        )
        s = provider.sample(lats, lons, times)
        assert _all_groups(s, _OK, len(queries))
        for var, exp in expected(lats, lons, times).items():
            np.testing.assert_allclose(s.values[var], exp, rtol=0, atol=_TOL)

    @pytest.mark.req("S0b-R07")
    def test_global_seam(self) -> None:
        """On a global grid the cell between the last and the first column is covered and wraps."""
        g = self.grid
        if not g.is_global:
            pytest.skip("grid is not global")
        p = self.make_provider()
        lat, lon_mid, t = self._mid()
        offsets = (
            _FULL_CIRCLE - 0.5 * g.lon_step_deg,
            _FULL_CIRCLE - 0.01 * g.lon_step_deg,
            _FULL_CIRCLE - g.lon_step_deg,
        )
        lons = _f(*(wrap_lon(g.lon_west_deg + o) for o in offsets))
        s = p.sample(_f(*([lat] * 3)), lons, _t(*([t] * 3)))
        ref = p.sample(_f(lat), _f(lon_mid), _t(t))
        assert _all_groups(s, _OK, 3)
        for var in s.values:
            for k in range(3):
                a, b = float(s.values[var][k]), float(ref.values[var][0])
                diff = _angle_diff(a, b) if var in DIRECTIONS else abs(a - b)
                assert diff < _TOL, (var, k, a, b)

    @pytest.mark.req("S0b-R09")
    def test_global_grid_interpolates_across_the_seam(self) -> None:
        """On a global linear grid the seam cell blends the last column into the first."""
        g = self.grid
        if not g.is_global:
            pytest.skip("grid is not global")
        provider, _ = self.make_linear_provider()
        lat, _, t = self._mid()
        fractions = (
            0.0,
            0.25,
            0.5,
            0.75,
        )  # of the seam cell, from the last column towards the first
        lons = _f(
            *(
                wrap_lon(g.lon_west_deg + _FULL_CIRCLE - g.lon_step_deg * (1.0 - f))
                for f in fractions
            ),
            g.lon_west_deg,
        )
        s = provider.sample(_f(*([lat] * 5)), lons, _t(*([t] * 5)))
        assert _all_groups(s, _OK, 5)
        for var, values in s.values.items():
            if var in DIRECTIONS:
                continue
            last, first = float(values[0]), float(values[4])
            for f, got in zip(fractions, values[:4], strict=True):
                assert abs(float(got) - ((1.0 - f) * last + f * first)) < _TOL, (var, f)
