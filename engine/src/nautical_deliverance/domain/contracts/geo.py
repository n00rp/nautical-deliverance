"""Positions and leg geometry on WGS84 (great circle and rhumb line)."""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from geographiclib.geodesic import Geodesic

from nautical_deliverance.domain.contracts.errors import InvalidInputError, InvalidPositionError

if TYPE_CHECKING:
    from collections.abc import Callable

_GEOD = Geodesic.WGS84
_E2: float = float(_GEOD.f * (2.0 - _GEOD.f))
_POLE_DEG = 90.0
_NEWTON_RTOL = 1e-15
_NEWTON_MAX_ITER = 50

# Rhumb integrals use adaptive composite Gauss-Legendre: a 16-point rule on the whole interval is
# compared with the sum of 16-point rules on its two halves; halving recurses until they agree to
# _QUAD_RTOL relative. 16-point GL is exact for polynomials of degree 31 and the integrands are
# analytic away from the poles, so the accepted (halved) result is accurate to well below 1e-14.
# Integrals run over the offset t from the start latitude so tiny legs never subtract latitudes.
_GL_NODES, _GL_WEIGHTS = (a.tolist() for a in np.polynomial.legendre.leggauss(16))
_QUAD_RTOL = 1e-14
_QUAD_MAX_DEPTH = 40


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


def _quad(f: Callable[[float], float], t0: float, t1: float, depth: int = 0) -> float:
    """Integrate ``f`` over [t0, t1] (adaptive Gauss-Legendre, see module constants)."""
    whole = _gl(f, t0, t1)
    mid = (t0 + t1) / 2.0
    halves = _gl(f, t0, mid) + _gl(f, mid, t1)
    if depth >= _QUAD_MAX_DEPTH or abs(halves - whole) <= _QUAD_RTOL * abs(halves):
        return halves
    return _quad(f, t0, mid, depth + 1) + _quad(f, mid, t1, depth + 1)


def _meridian_radius_m(phi: float) -> float:
    """Radius of curvature of the meridian, d(mu)/d(phi)."""
    return float(_GEOD.a * (1.0 - _E2) / (1.0 - _E2 * math.sin(phi) ** 2) ** 1.5)


def _dpsi_dphi(phi: float) -> float:
    """Return d(psi)/d(phi), the isometric-latitude derivative."""
    return (1.0 - _E2) / ((1.0 - _E2 * math.sin(phi) ** 2) * math.cos(phi))


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
        phi1 = math.radians(self.phi1_deg)
        return _quad(lambda t: _dpsi_dphi(phi1 + t), 0.0, delta_rad)

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
    dpsi = _quad(lambda t: _dpsi_dphi(phi1 + t), 0.0, dphi)
    return _Rhumb(a.lat_deg, dphi_deg, dmu, dlon, dpsi, None)


def _rhumb_point(a: Position, sol: _Rhumb, fraction: float) -> Position:
    """Point at ``fraction`` of the leg; Newton on the meridian-distance progress."""
    phi1, target = math.radians(sol.phi1_deg), fraction * sol.dmu_m
    dphi = math.radians(sol.dphi_deg)
    delta = fraction * dphi
    for _ in range(_NEWTON_MAX_ITER):
        err = target - _quad(lambda t: _meridian_radius_m(phi1 + t), 0.0, delta)
        step = err / _meridian_radius_m(phi1 + delta)
        delta += step
        if abs(step) <= _NEWTON_RTOL * abs(dphi):
            break
    lat = max(-_POLE_DEG, min(_POLE_DEG, a.lat_deg + math.degrees(delta)))
    if sol.lon_pole_deg is not None:
        return Position(lat, sol.lon_pole_deg)
    share = fraction if sol.dphi_deg == 0.0 else sol.psi_to(delta) / sol.dpsi_ratio
    return Position(lat, a.lon_deg + sol.dlon_deg * share)


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
