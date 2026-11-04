"""Positions and leg geometry on WGS84 (great circle and rhumb line)."""

import math
from dataclasses import dataclass
from enum import StrEnum

from geographiclib.geodesic import Geodesic

from nautical_deliverance.domain.contracts.errors import InvalidInputError, InvalidPositionError

_GEOD = Geodesic.WGS84
_E2 = _GEOD.f * (2.0 - _GEOD.f)
_E = math.sqrt(_E2)
_POLE_DEG = 90.0
_NEWTON_TOL_RAD = 1e-15


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
    wrapped = (lon + 180.0) % 360.0 - 180.0
    return -180.0 if wrapped >= 180.0 else wrapped  # noqa: PLR2004 - float rounding guard


def _meridian_m(lat_deg: float) -> float:
    """Signed meridian distance from the equator."""
    s = float(_GEOD.Inverse(0.0, 0.0, abs(lat_deg), 0.0, Geodesic.DISTANCE)["s12"])
    return math.copysign(s, lat_deg)


def _lat_from_meridian(mu_m: float, guess_deg: float) -> float:
    """Invert ``_meridian_m`` by Newton iteration (dmu/dphi is the meridian radius)."""
    lat = guess_deg
    for _ in range(30):
        sin2 = math.sin(math.radians(lat)) ** 2
        radius = _GEOD.a * (1.0 - _E2) / (1.0 - _E2 * sin2) ** 1.5
        step = (mu_m - _meridian_m(lat)) / radius
        lat += math.degrees(step)
        if abs(step) < _NEWTON_TOL_RAD:
            break
    return max(-_POLE_DEG, min(_POLE_DEG, lat))


def _isometric(lat_deg: float) -> float:
    """Isometric latitude (radians); callers handle the poles, where it diverges."""
    phi = math.radians(lat_deg)
    return math.asinh(math.tan(phi)) - _E * math.atanh(_E * math.sin(phi))


@dataclass(frozen=True, slots=True)
class _Rhumb:
    """Solved rhumb inverse problem; ``dmu_m`` is the meridian-distance difference."""

    dmu_m: float
    dlon_deg: float  # shortest signed longitude difference
    dpsi_ratio: float
    lon_pole_deg: float | None  # fixed longitude when the leg touches a pole

    @property
    def course_rad(self) -> float:
        return (
            0.0
            if self.lon_pole_deg is not None
            else math.atan2(math.radians(self.dlon_deg), self.dpsi_ratio)
        )

    @property
    def length_m(self) -> float:
        return abs(self.dmu_m / math.cos(self.course_rad))


def _rhumb_solve(a: Position, b: Position) -> _Rhumb:
    dmu = _meridian_m(b.lat_deg) - _meridian_m(a.lat_deg)
    dlon = _wrap_lon(b.lon_deg - a.lon_deg)
    if abs(a.lat_deg) == _POLE_DEG or abs(b.lat_deg) == _POLE_DEG:
        pole_lon = b.lon_deg if abs(a.lat_deg) == _POLE_DEG else a.lon_deg
        return _Rhumb(dmu, dlon, math.inf, pole_lon)
    return _Rhumb(dmu, dlon, _isometric(b.lat_deg) - _isometric(a.lat_deg), None)


def _east_west_length_m(a: Position, dlon_deg: float) -> float:
    sin2 = math.sin(math.radians(a.lat_deg)) ** 2
    return abs(
        float(
            _GEOD.a
            * math.cos(math.radians(a.lat_deg))
            / math.sqrt(1.0 - _E2 * sin2)
            * math.radians(dlon_deg)
        )
    )


def _is_zero_length(a: Position, b: Position) -> bool:
    return a == b or (abs(a.lat_deg) == _POLE_DEG and a.lat_deg == b.lat_deg)


def distance_m(a: Position, b: Position, geometry: LegGeometry) -> float:
    """Length of the leg from ``a`` to ``b`` in metres."""
    if _is_zero_length(a, b):
        return 0.0
    if geometry is LegGeometry.GREAT_CIRCLE:
        r = _GEOD.Inverse(a.lat_deg, a.lon_deg, b.lat_deg, b.lon_deg, Geodesic.DISTANCE)
        return float(r["s12"])
    sol = _rhumb_solve(a, b)
    if abs(sol.dpsi_ratio) < 1e-12 and sol.lon_pole_deg is None:  # noqa: PLR2004
        return _east_west_length_m(a, sol.dlon_deg)
    return sol.length_m


def initial_course_deg(a: Position, b: Position, geometry: LegGeometry) -> float:
    """Return the initial course from ``a`` towards ``b`` in degrees, in [0, 360)."""
    if _is_zero_length(a, b):
        return 0.0
    if geometry is LegGeometry.GREAT_CIRCLE:
        r = _GEOD.Inverse(a.lat_deg, a.lon_deg, b.lat_deg, b.lon_deg, Geodesic.AZIMUTH)
        course = float(r["azi1"])
    else:
        sol = _rhumb_solve(a, b)
        if sol.lon_pole_deg is not None:
            course = 0.0 if b.lat_deg > a.lat_deg else 180.0
        else:
            course = math.degrees(sol.course_rad)
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
    sol = _rhumb_solve(a, b)
    lat = _lat_from_meridian(_meridian_m(a.lat_deg) + fraction * sol.dmu_m, a.lat_deg)
    if sol.lon_pole_deg is not None:
        return Position(lat, sol.lon_pole_deg)
    if abs(sol.dpsi_ratio) < 1e-12:  # noqa: PLR2004 - east-west leg
        return Position(a.lat_deg, a.lon_deg + fraction * sol.dlon_deg)
    tan_c = math.radians(sol.dlon_deg) / sol.dpsi_ratio
    return Position(
        lat, a.lon_deg + math.degrees(tan_c * (_isometric(lat) - _isometric(a.lat_deg)))
    )
