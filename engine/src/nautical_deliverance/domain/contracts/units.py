"""SI unit conversions and the unit-suffix list for contract field names."""

from typing import Final, cast

import numpy as np
from numpy.typing import NDArray

type Num = float | NDArray[np.float64]

# Longest match first: `_from_deg` must be checked before `_deg`.
UNIT_SUFFIXES: Final[tuple[str, ...]] = (
    "_from_deg",
    "_kg_per_j",
    "_kgps",
    "_ratio",
    "_deg",
    "_mps",
    "_kg",
    "_pa",
    "_m",
    "_s",
    "_w",
)

M_PER_NM: Final = 1852.0
MPS_PER_KNOT: Final = 1852.0 / 3600.0
KG_PER_J_PER_G_PER_KWH: Final = 1.0 / 3.6e9
_KG_PER_TONNE: Final = 1000.0
_W_PER_KW: Final = 1000.0
_S_PER_HOUR: Final = 3600.0


def _scale[T: Num](x: T, k: float) -> T:
    return cast("T", x * k)


def _unscale[T: Num](x: T, k: float) -> T:
    return cast("T", x / k)


def knots_to_mps[T: Num](x: T) -> T:
    """Knots to metres per second."""
    return _scale(x, MPS_PER_KNOT)


def mps_to_knots[T: Num](x: T) -> T:
    """Metres per second to knots."""
    return _unscale(x, MPS_PER_KNOT)


def nm_to_m[T: Num](x: T) -> T:
    """Nautical miles to metres."""
    return _scale(x, M_PER_NM)


def m_to_nm[T: Num](x: T) -> T:
    """Metres to nautical miles."""
    return _unscale(x, M_PER_NM)


def tonnes_to_kg[T: Num](x: T) -> T:
    """Tonnes to kilograms."""
    return _scale(x, _KG_PER_TONNE)


def kg_to_tonnes[T: Num](x: T) -> T:
    """Kilograms to tonnes."""
    return _unscale(x, _KG_PER_TONNE)


def kw_to_w[T: Num](x: T) -> T:
    """Kilowatts to watts."""
    return _scale(x, _W_PER_KW)


def w_to_kw[T: Num](x: T) -> T:
    """Watts to kilowatts."""
    return _unscale(x, _W_PER_KW)


def g_per_kwh_to_kg_per_j[T: Num](x: T) -> T:
    """Specific fuel consumption, g/kWh to kg/J."""
    return _scale(x, KG_PER_J_PER_G_PER_KWH)


def kg_per_j_to_g_per_kwh[T: Num](x: T) -> T:
    """Specific fuel consumption, kg/J to g/kWh."""
    return _unscale(x, KG_PER_J_PER_G_PER_KWH)


def hours_to_s[T: Num](x: T) -> T:
    """Hours to seconds."""
    return _scale(x, _S_PER_HOUR)


def s_to_hours[T: Num](x: T) -> T:
    """Seconds to hours."""
    return _unscale(x, _S_PER_HOUR)
