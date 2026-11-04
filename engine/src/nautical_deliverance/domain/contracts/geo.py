"""Positions and leg geometry on WGS84 (great circle and rhumb line)."""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from geographiclib.geodesic import Geodesic

from nautical_deliverance.domain.contracts.errors import (
    ContractError,
    InvalidInputError,
    InvalidPositionError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_GEOD = Geodesic.WGS84
_E2: float = float(_GEOD.f * (2.0 - _GEOD.f))
_POLE_DEG = 90.0
_NEWTON_RTOL = 1e-15
_NEWTON_MAX_ITER = 50
_HALF_MERIDIAN_M = 20_003_932.0  # just above half the WGS84 meridian: no rhumb goes further
_POLE_SLACK_DEG = 1e-9  # round-off allowed when a meridian leg lands exactly on a pole

# Rhumb integrals use adaptive composite Gauss-Legendre: a 16-point rule on the whole interval is
# compared with the sum of 16-point rules on its two halves; halving recurses until they agree to
# _QUAD_RTOL, relative to the interval's own value or to its width share of the first-level
# integral, whichever is looser (the second term is the absolute floor: the summed error stays
# within 2 * _QUAD_RTOL * integral, and an interval is never forced below the round-off of its own
# value). 16-point GL is exact for
# polynomials of degree 31 and the integrands are analytic away from the poles. The interval list
# is capped (_QUAD_MAX_INTERVALS): work is bounded, and exhausting it raises ContractError instead
# of returning a value of unknown accuracy. Integrals run over the offset t from the start
# latitude so tiny legs never subtract latitudes.
# The only ill-conditioned integrand is 1/cos(phi) near a pole: cos(phi1 + t) loses all relative
# precision there (phi near pi/2 carries an absolute error of 1e-16). _psi_increase therefore
# integrates over the colatitude (cos phi = sin c), held to full relative precision, inside the
# polar caps. This keeps the integrand well conditioned, so the quadrature converges instead of
# bisecting to full depth. (The closed form asinh(tan phi) - e atanh(e sin phi) is no better:
# tan phi suffers the same cancellation, and it subtracts two large values for short legs.)
_GL_NODES, _GL_WEIGHTS = (a.tolist() for a in np.polynomial.legendre.leggauss(16))
_QUAD_RTOL = 1e-14
_QUAD_MAX_INTERVALS = 4000


@dataclass(frozen=True, slots=True)
class Position:
    """A WGS84 position; longitude is normalized to [-180, 180)."""

    lat_deg: float
    lon_deg: float

    def __post_init__(self) -> None:
        """Validate finiteness and latitude range; normalize longitude."""
        if not (math.isfinite(self.lat_deg) and math.isfinite(self.lon_deg)):
            msg = f"position must be finite, got ({self.lat_deg}, {self.lon_deg})"
            raise InvalidPositionError(msg)
        if abs(self.lat_deg) > _POLE_DEG:
            msg = f"latitude must be within [-90, 90], got {self.lat_deg}"
            raise InvalidPositionError(msg)
        object.__setattr__(self, "lon_deg", _wrap_lon(self.lon_deg))


class LegGeometry(StrEnum):
    """How the path between two waypoints is drawn."""

    RHUMB_LINE = "rhumb_line"
    GREAT_CIRCLE = "great_circle"


def _wrap_lon(lon: float) -> float:
    if -180.0 <= lon < 180.0:  # noqa: PLR2004 - in range: keep exact (wrapping adds ulp noise)
        return lon
    wrapped = (lon + 180.0) % 360.0 - 180.0
    return -180.0 if wrapped >= 180.0 else wrapped  # noqa: PLR2004 - float rounding guard


def _gl(f: Callable[[float], float], t0: float, t1: float) -> float:
    half, mid = (t1 - t0) / 2.0, (t1 + t0) / 2.0
    return half * sum(w * f(mid + half * x) for x, w in zip(_GL_NODES, _GL_WEIGHTS, strict=True))


def _quad(f: Callable[[float], float], t0: float, t1: float) -> float:
    """Integrate ``f`` over [t0, t1] (adaptive Gauss-Legendre, see module constants)."""
    if t0 == t1:
        return 0.0
    width = abs(t1 - t0)
    todo = [(t0, t1)]
    total = scale = 0.0
    evaluated = 0
    while todo:
        a, b = todo.pop()
        mid = (a + b) / 2.0
        whole, left, right = _gl(f, a, b), _gl(f, a, mid), _gl(f, mid, b)
        halves = left + right
        if evaluated == 0:
            scale = abs(halves)
        evaluated += 1
        if abs(halves - whole) <= _QUAD_RTOL * max(abs(halves), scale * abs(b - a) / width):
            total += halves
        elif evaluated + len(todo) >= _QUAD_MAX_INTERVALS:
            msg = "rhumb integral did not converge within the interval budget"
            raise ContractError(msg)
        else:
            todo += [(a, mid), (mid, b)]
    return total


def _meridian_radius_m(phi: float) -> float:
    """Radius of curvature of the meridian, d(mu)/d(phi)."""
    return float(_GEOD.a * (1.0 - _E2) / (1.0 - _E2 * math.sin(phi) ** 2) ** 1.5)


def _dpsi_dphi(sin_phi: float, cos_phi: float) -> float:
    """Return d(psi)/d(phi), the isometric-latitude derivative."""
    return (1.0 - _E2) / ((1.0 - _E2 * sin_phi**2) * cos_phi)


def _psi_increase(lat_deg: float, delta: float, end_lat_deg: float | None = None) -> float:
    """Integral of d(psi)/d(phi) over [lat, lat + delta] (radians), well conditioned at poles.

    Away from the poles integrate over the offset t (no latitude subtraction). Within 45 degrees
    of a pole use the colatitude c (cos(phi) = sin(c) is then held to full relative precision,
    which phi1 + t cannot do): over c itself between exact endpoints for a long leg, or over the
    offset from the exact start colatitude for a leg short compared with its distance from the
    pole. ``end_lat_deg`` gives the exact far end when the caller has it.
    """
    end_deg = lat_deg + math.degrees(delta) if end_lat_deg is None else end_lat_deg
    sign = math.copysign(1.0, max(lat_deg, end_deg, key=abs))  # the pole this leg gets closest to
    c1, c2 = (math.radians(_POLE_DEG - sign * x) for x in (lat_deg, end_deg))  # exact near a pole
    near = min(c1, c2)  # c in (0, pi): the leg does not reach either pole
    if 0.0 < near < math.pi / 4.0 and max(c1, c2) < math.pi and abs(c1 - c2) > 0.1 * near:
        return sign * _quad(lambda c: _dpsi_dphi(math.cos(c), math.sin(c)), c2, c1)
    if near < math.pi / 4.0:  # short leg near a pole: offset from the exact start colatitude
        return _quad(
            lambda t: _dpsi_dphi(math.cos(c1 - sign * t), math.sin(c1 - sign * t)), 0.0, delta
        )
    phi1 = math.radians(lat_deg)
    return _quad(lambda t: _dpsi_dphi(math.sin(phi1 + t), math.cos(phi1 + t)), 0.0, delta)


def _parallel_radius_m(phi: float) -> float:
    """Radius of the parallel, N cos(phi)."""
    return float(_GEOD.a * math.cos(phi) / math.sqrt(1.0 - _E2 * math.sin(phi) ** 2))


@dataclass(frozen=True, slots=True)
class _Rhumb:
    """Solved rhumb inverse problem; all differences come from integrals, never subtraction."""

    phi1_deg: float
    dphi_deg: float
    dmu_m: float  # integral of the meridian radius over the leg
    dlon_deg: float  # shortest signed longitude difference
    dpsi_ratio: float  # integral of dpsi/dphi; infinite when the leg touches a pole
    lon_pole_deg: float | None  # fixed longitude when the leg touches a pole

    def psi_to(self, delta_rad: float) -> float:
        """Isometric-latitude increase over the first ``delta_rad`` of the leg."""
        return _psi_increase(self.phi1_deg, delta_rad)

    @property
    def length_m(self) -> float:
        if self.lon_pole_deg is not None:
            return abs(self.dmu_m)
        ratio = (
            self.dmu_m / self.dpsi_ratio
            if self.dphi_deg != 0.0
            else _parallel_radius_m(math.radians(self.phi1_deg))
        )
        return math.hypot(self.dmu_m, ratio * math.radians(self.dlon_deg))

    @property
    def course_deg(self) -> float:
        if self.lon_pole_deg is not None:
            return 0.0 if self.dphi_deg > 0.0 else 180.0
        return math.degrees(math.atan2(math.radians(self.dlon_deg), self.dpsi_ratio))


def _rhumb_solve(a: Position, b: Position) -> _Rhumb:
    phi1 = math.radians(a.lat_deg)
    dphi_deg = b.lat_deg - a.lat_deg
    dphi = math.radians(dphi_deg)
    dmu = _quad(lambda t: _meridian_radius_m(phi1 + t), 0.0, dphi)
    dlon = _wrap_lon(b.lon_deg - a.lon_deg)
    if abs(a.lat_deg) == _POLE_DEG or abs(b.lat_deg) == _POLE_DEG:
        pole_lon = b.lon_deg if abs(a.lat_deg) == _POLE_DEG else a.lon_deg
        return _Rhumb(a.lat_deg, dphi_deg, dmu, dlon, math.inf, pole_lon)
    dpsi = _psi_increase(a.lat_deg, dphi, b.lat_deg)
    return _Rhumb(a.lat_deg, dphi_deg, dmu, dlon, dpsi, None)


def _newton_delta(phi1: float, target_m: float, delta: float, scale: float) -> float:
    """Solve integral of the meridian radius over [phi1, phi1 + delta] == ``target_m`` for delta.

    ``delta`` is the starting guess; convergence is a step below ``_NEWTON_RTOL * scale``.
    """
    for _ in range(_NEWTON_MAX_ITER):
        err = target_m - _quad(lambda t: _meridian_radius_m(phi1 + t), 0.0, delta)
        step = err / _meridian_radius_m(phi1 + delta)
        delta += step
        if abs(step) <= _NEWTON_RTOL * scale:
            return delta
    msg = "rhumb point did not converge"
    raise ContractError(msg)


def _rhumb_point(a: Position, sol: _Rhumb, fraction: float) -> Position:
    """Point at ``fraction`` of the leg; Newton on the meridian-distance progress."""
    phi1 = math.radians(sol.phi1_deg)
    dphi = math.radians(sol.dphi_deg)
    delta = _newton_delta(phi1, fraction * sol.dmu_m, fraction * dphi, abs(dphi))
    lat = max(-_POLE_DEG, min(_POLE_DEG, a.lat_deg + math.degrees(delta)))
    if sol.lon_pole_deg is not None:
        return Position(lat, sol.lon_pole_deg)
    share = fraction if sol.dphi_deg == 0.0 else sol.psi_to(delta) / sol.dpsi_ratio
    return Position(lat, a.lon_deg + sol.dlon_deg * share)


def _course_components(course_deg: float) -> tuple[float, float]:
    """(cos, sin) of a course, exact for the cardinal courses (cos(90 deg) is not 0 in floats)."""
    cardinal = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    exact = cardinal.get(course_deg % 360.0)
    return exact or (math.cos(math.radians(course_deg)), math.sin(math.radians(course_deg)))


def _rhumb_destination(a: Position, course_deg: float, dist_m: float) -> Position:
    """Direct rhumb problem: the meridian progress is ``dist * cos(course)``, solved by Newton."""
    cos_c, sin_c = _course_components(course_deg)
    north_m, east_m = dist_m * cos_c, dist_m * sin_c
    phi1 = math.radians(a.lat_deg)
    if abs(north_m) > _HALF_MERIDIAN_M:
        msg = "the rhumb line passes the pole before the distance is used up"
        raise InvalidInputError(msg)
    if abs(a.lat_deg) == _POLE_DEG and east_m != 0.0:
        msg = "a rhumb line leaving a pole must follow a meridian"
        raise InvalidInputError(msg)
    guess = north_m / _meridian_radius_m(phi1)
    delta = _newton_delta(phi1, north_m, guess, abs(guess))
    lat = a.lat_deg + math.degrees(delta)
    if abs(lat) > _POLE_DEG:
        if abs(lat) > _POLE_DEG + _POLE_SLACK_DEG:
            msg = "the rhumb line passes the pole before the distance is used up"
            raise InvalidInputError(msg)
        lat = math.copysign(_POLE_DEG, lat)
    if abs(lat) == _POLE_DEG or abs(a.lat_deg) == _POLE_DEG:
        if east_m != 0.0:  # (a start at a pole was rejected above, so this is the arrival case)
            msg = "a rhumb line reaches a pole only along a meridian"
            raise InvalidInputError(msg)
        return Position(lat, a.lon_deg)
    if delta == 0.0:
        dlon = east_m / _parallel_radius_m(phi1)
    else:  # dlon = tan(course) * d(psi) = east * d(psi) / d(mu); both integrals are difference-free
        dpsi = _psi_increase(a.lat_deg, delta)
        dmu = _quad(lambda t: _meridian_radius_m(phi1 + t), 0.0, delta)
        dlon = east_m * dpsi / dmu
    return Position(lat, a.lon_deg + math.degrees(dlon))


def _is_zero_length(a: Position, b: Position) -> bool:
    return a == b or (abs(a.lat_deg) == _POLE_DEG and a.lat_deg == b.lat_deg)


def distance_m(a: Position, b: Position, geometry: LegGeometry) -> float:
    """Length of the leg from ``a`` to ``b`` in metres."""
    if _is_zero_length(a, b):
        return 0.0
    if geometry is LegGeometry.GREAT_CIRCLE:
        r = _GEOD.Inverse(a.lat_deg, a.lon_deg, b.lat_deg, b.lon_deg, Geodesic.DISTANCE)
        return float(r["s12"])
    return _rhumb_solve(a, b).length_m


def initial_course_deg(a: Position, b: Position, geometry: LegGeometry) -> float:
    """Return the initial course from ``a`` towards ``b`` in degrees, in [0, 360)."""
    if _is_zero_length(a, b):
        return 0.0
    if geometry is LegGeometry.GREAT_CIRCLE:
        r = _GEOD.Inverse(a.lat_deg, a.lon_deg, b.lat_deg, b.lon_deg, Geodesic.AZIMUTH)
        course = float(r["azi1"])
    else:
        course = _rhumb_solve(a, b).course_deg
    course %= 360.0
    return 0.0 if course >= 360.0 else course  # noqa: PLR2004 - float rounding guard


def point_along(a: Position, b: Position, geometry: LegGeometry, fraction: float) -> Position:
    """Point at ``fraction`` (0..1) of the leg's length from ``a`` towards ``b``."""
    if not (math.isfinite(fraction) and 0.0 <= fraction <= 1.0):
        msg = f"fraction must be within [0, 1], got {fraction}"
        raise InvalidInputError(msg)
    if _is_zero_length(a, b):
        return a
    if geometry is LegGeometry.GREAT_CIRCLE:
        r = _GEOD.Inverse(a.lat_deg, a.lon_deg, b.lat_deg, b.lon_deg)
        line = _GEOD.Line(a.lat_deg, a.lon_deg, r["azi1"])
        p = line.Position(fraction * r["s12"])
        return Position(p["lat2"], p["lon2"])
    return _rhumb_point(a, _rhumb_solve(a, b), fraction)


def destination(
    start: Position, course_deg: float, distance_m: float, geometry: LegGeometry
) -> Position:
    """Direct problem: the point reached from ``start`` after ``distance_m`` on ``course_deg``.

    For `GREAT_CIRCLE` the course is the initial course (it changes along the path, and the path
    may cross a pole); for `RHUMB_LINE` it is the constant course, and a path that would run past
    a pole raises `InvalidInputError`. The inverse of `distance_m` / `initial_course_deg`.
    """
    if not (math.isfinite(course_deg) and math.isfinite(distance_m) and distance_m >= 0.0):
        msg = (
            f"course must be finite and distance finite and >= 0, got ({course_deg}, {distance_m})"
        )
        raise InvalidInputError(msg)
    if distance_m == 0.0:
        return start
    if geometry is LegGeometry.GREAT_CIRCLE:
        p = _GEOD.Direct(start.lat_deg, start.lon_deg, course_deg, distance_m)
        return Position(p["lat2"], p["lon2"])
    return _rhumb_destination(start, course_deg, distance_m)
