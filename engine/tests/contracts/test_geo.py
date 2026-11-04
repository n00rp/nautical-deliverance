"""Geodetic helper tests (S0b-R04, S0b-R05, S0b-R06).

Reference data
--------------
Geodesic cases: the first 12 entries of ``testcases`` in
``geographiclib/test/test_geodesic.py`` (lines 11-60) of the geographiclib 2.1 Python package
(PyPI wheel, https://pypi.org/project/geographiclib/2.1/). Each row is a GeodTest-format line
(lat1, lon1, azi1, lat2, lon2, azi2, s12, ...) from Karney's GeodTest dataset
(https://geographiclib.sourceforge.io/C++/doc/geodesic.html#testgeod).

Rhumb cases: geographiclib 2.1 for Python ships NO rhumb code or rhumb test values, so the
values are the worked examples of the RhumbSolve(1) manual page of GeographicLib C++ 2.x
(https://geographiclib.sourceforge.io/C++/doc/RhumbSolve.1.html): the JFK -> Changi inverse
example (azimuth 103:34:58.2, 18523563 m) and the 9 intermediate waypoints of the "-L" example
at 2000 km intervals. Those are printed to 0.1 arc-second and 1 m, so the rhumb tolerances are
looser than the geodesic ones. Further exact checks: along the equator and along a meridian a
rhumb line coincides with the geodesic.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nautical_deliverance.domain.contracts.errors import InvalidInputError, InvalidPositionError
from nautical_deliverance.domain.contracts.geo import (
    LegGeometry,
    Position,
    distance_m,
    initial_course_deg,
    point_along,
)

GEOMETRIES = list(LegGeometry)
ANGLE_TOL = 1e-9
HALF_TURN = 180.0
FULL_TURN = 360.0

# Columns: lat1, lon1, azi1, lat2, lon2, azi2, s12 in metres
GEODESIC_CASES = [
    (
        35.60777,
        -139.44815,
        111.098748429560326,
        -11.17491,
        -69.95921,
        129.289270889708762,
        8935244.5604818305,
    ),
    (
        55.52454,
        106.05087,
        22.020059880982801,
        77.03196,
        197.18234,
        109.112041110671519,
        4105086.1713924406,
    ),
    (
        -21.97856,
        142.59065,
        -32.44456876433189,
        41.84138,
        98.56635,
        -41.84359951440466,
        8394328.894657671,
    ),
    (
        -66.99028,
        112.2363,
        173.73491240878403,
        -12.70631,
        285.90344,
        2.512956620913668,
        11150344.2312080241,
    ),
    (
        -17.42761,
        173.34268,
        -159.033557661192928,
        -15.84784,
        5.93557,
        -20.787484651536988,
        16076603.1631180673,
    ),
    (
        32.84994,
        48.28919,
        150.492927788121982,
        -56.28556,
        202.29132,
        48.113449399816759,
        16727068.9438164461,
    ),
    (
        6.96833,
        52.74123,
        92.581585386317712,
        -7.39675,
        206.17291,
        90.721692165923907,
        17102477.2496958388,
    ),
    (
        -50.56724,
        -16.30485,
        -105.439679907590164,
        -33.56571,
        -94.97412,
        -47.348547835650331,
        6455670.5118668696,
    ),
    (
        -58.93002,
        -8.90775,
        140.965397902500679,
        -8.91104,
        133.13503,
        19.255429433416599,
        11756066.0219864627,
    ),
    (
        -68.82867,
        -74.28391,
        93.774347763114881,
        -50.63005,
        -8.36685,
        34.65564085411343,
        3956936.926063544,
    ),
    (
        -10.62672,
        -32.0898,
        -86.426713286747751,
        5.883,
        -134.31681,
        -80.473780971034875,
        11470869.3864563009,
    ),
    (
        -21.76221,
        166.90563,
        29.319421206936428,
        48.72884,
        213.97627,
        43.508671946410168,
        9098627.3986554915,
    ),
]

RHUMB_START = ("40:38:23N", "073:46:44W")
RHUMB_AZIMUTH = "103:34:58.2"
RHUMB_TOTAL_M = 18523563.0
# (distance along the rhumb in m, latitude, longitude) from the RhumbSolve -L example
RHUMB_WAYPOINTS = [
    (2_000_000, "36:24:30.3N", "051:28:26.4W"),
    (4_000_000, "32:10:26.8N", "030:20:57.3W"),
    (6_000_000, "27:56:13.2N", "010:10:54.2W"),
    (8_000_000, "23:41:50.1N", "009:12:45.5E"),
    (10_000_000, "19:27:18.7N", "027:59:22.1E"),
    (12_000_000, "15:12:40.2N", "046:17:01.1E"),
    (14_000_000, "10:57:55.9N", "064:12:52.8E"),
    (16_000_000, "06:43:07.3N", "081:53:28.8E"),
    (18_000_000, "02:28:16.2N", "099:24:54.5E"),
]
RHUMB_END = ("01:21:33N", "103:59:22E")
RHUMB_DEG_TOL = 5e-5  # 0.1 arc-second rounding of the manual page is 1.4e-5 deg
RHUMB_DIST_TOL_M = 2.0  # manual prints whole metres; line points are rounded to 0.1 arc-second


def dms(text: str) -> float:
    """Parse ``DD:MM:SS.s`` with a trailing hemisphere letter into signed degrees."""
    sign = -1.0 if text[-1] in "SW" else 1.0
    parts = [float(p) for p in text.rstrip("NSEW").split(":")]
    return sign * float(sum(p / 60**i for i, p in enumerate(parts)))


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two angles in degrees."""
    return abs((a - b + HALF_TURN) % FULL_TURN - HALF_TURN)


@pytest.mark.req("S0b-R04")
@settings(max_examples=1000)
@given(lon=st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False))
def test_longitude_normalized(lon: float) -> None:
    """Any finite longitude lands in [-180, 180) and stays congruent modulo 360."""
    result = Position(0.0, lon).lon_deg

    assert -HALF_TURN <= result < HALF_TURN
    assert angle_diff_deg(result, lon) < ANGLE_TOL


@pytest.mark.req("S0b-R04")
@pytest.mark.parametrize("lat", [91.0, -90.0001, math.nan, math.inf, -math.inf])
def test_invalid_latitude_rejected(lat: float) -> None:
    """Latitude outside [-90, 90] or not finite is rejected."""
    with pytest.raises(InvalidPositionError):
        Position(lat, 0.0)


@pytest.mark.req("S0b-R04")
@pytest.mark.parametrize("lon", [math.nan, math.inf, -math.inf])
def test_nan_longitude_rejected(lon: float) -> None:
    """A non-finite longitude is rejected."""
    with pytest.raises(InvalidPositionError):
        Position(0.0, lon)


@pytest.mark.req("S0b-R05")
@pytest.mark.parametrize(("lat1", "lon1", "azi1", "lat2", "lon2", "_azi2", "s12"), GEODESIC_CASES)
def test_geodesic_matches_reference_cases(  # noqa: PLR0913, PLR0917
    lat1: float, lon1: float, azi1: float, lat2: float, lon2: float, _azi2: float, s12: float
) -> None:
    """Great-circle distance, course and endpoint agree with GeodTest rows."""
    a, b = Position(lat1, lon1), Position(lat2, lon2)
    g = LegGeometry.GREAT_CIRCLE

    assert distance_m(a, b, g) == pytest.approx(s12, abs=1e-3)
    assert angle_diff_deg(initial_course_deg(a, b, g), azi1) < ANGLE_TOL
    end = point_along(a, b, g, 1.0)
    assert end.lat_deg == pytest.approx(lat2, abs=ANGLE_TOL)
    assert angle_diff_deg(end.lon_deg, lon2) < ANGLE_TOL


@pytest.mark.req("S0b-R05")
def test_rhumb_matches_reference_cases() -> None:
    """Rhumb distance, course and waypoints agree with the RhumbSolve manual examples."""
    a = Position(dms(RHUMB_START[0]), dms(RHUMB_START[1]))
    b = Position(dms(RHUMB_END[0]), dms(RHUMB_END[1]))
    g = LegGeometry.RHUMB_LINE
    total = distance_m(a, b, g)

    assert total == pytest.approx(RHUMB_TOTAL_M, abs=RHUMB_DIST_TOL_M)
    assert angle_diff_deg(initial_course_deg(a, b, g), dms(RHUMB_AZIMUTH)) < RHUMB_DEG_TOL
    for dist, lat, lon in RHUMB_WAYPOINTS:
        p = point_along(a, b, g, dist / total)
        assert p.lat_deg == pytest.approx(dms(lat), abs=RHUMB_DEG_TOL)
        assert angle_diff_deg(p.lon_deg, dms(lon)) < RHUMB_DEG_TOL
        assert distance_m(a, p, g) == pytest.approx(dist, abs=RHUMB_DIST_TOL_M)


@pytest.mark.req("S0b-R05")
def test_rhumb_equals_geodesic_on_equator_and_meridian() -> None:
    """Along the equator and along a meridian both geometries agree."""
    for a, b in [(Position(0, 10), Position(0, 70)), (Position(-20, 33), Position(55, 33))]:
        rh, gc = LegGeometry.RHUMB_LINE, LegGeometry.GREAT_CIRCLE
        assert distance_m(a, b, rh) == pytest.approx(distance_m(a, b, gc), abs=1e-6)
        assert (
            angle_diff_deg(initial_course_deg(a, b, rh), initial_course_deg(a, b, gc)) < ANGLE_TOL
        )


@pytest.mark.req("S0b-R06")
@pytest.mark.parametrize("g", GEOMETRIES)
def test_antimeridian_leg_short(g: LegGeometry) -> None:
    """A leg crossing +-180 takes the short way round."""
    across = distance_m(Position(10, 179), Position(10, -179), g)
    plain = distance_m(Position(10, -1), Position(10, 1), g)

    assert across == pytest.approx(plain, abs=1e-3)


@pytest.mark.req("S0b-R06")
@pytest.mark.parametrize("g", GEOMETRIES)
def test_antimeridian_midpoint(g: LegGeometry) -> None:
    """The midpoint of a leg crossing +-180 is normalized to -180."""
    mid = point_along(Position(10, 179), Position(10, -179), g, 0.5)

    assert mid.lon_deg == pytest.approx(-HALF_TURN, abs=ANGLE_TOL)


@pytest.mark.req("S0b-R04")
@pytest.mark.parametrize("g", GEOMETRIES)
def test_pole_legs_finite(g: LegGeometry) -> None:
    """A leg ending at the pole has finite length and a defined course."""
    a, b = Position(60, 20), Position(90, 0)

    d = distance_m(a, b, g)
    assert math.isfinite(d)
    assert d == pytest.approx(3_347_892.91, abs=1e-2)  # WGS84 meridian arc 60N-90N, same for both
    assert 0.0 <= initial_course_deg(a, b, g) < FULL_TURN
    assert point_along(a, b, g, 1.0).lat_deg == pytest.approx(90.0, abs=ANGLE_TOL)


@pytest.mark.req("S0b-R04")
@pytest.mark.parametrize("g", GEOMETRIES)
def test_zero_length_leg(g: LegGeometry) -> None:
    """Same start and end: distance 0, course 0.0, every point is the start."""
    p = Position(12.5, -40.0)

    assert distance_m(p, p, g) == 0.0
    assert initial_course_deg(p, p, g) == 0.0
    for f in (0.0, 0.5, 1.0):
        assert point_along(p, p, g, f) == p


@pytest.mark.req("S0b-R04")
@pytest.mark.parametrize("fraction", [-0.1, 1.1, math.nan, math.inf])
@pytest.mark.parametrize("g", GEOMETRIES)
def test_fraction_out_of_range_rejected(g: LegGeometry, fraction: float) -> None:
    """Fractions outside [0, 1] or non-finite are rejected."""
    with pytest.raises(InvalidInputError):
        point_along(Position(0, 0), Position(1, 1), g, fraction)
