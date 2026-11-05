"""SI unit conversions and the unit-suffix list for contract field names."""

from typing import TYPE_CHECKING, Final, overload

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

# A name is accepted when it ends with any of these (the check is `str.endswith(tuple)`).
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


@overload
def knots_to_mps(x: float) -> float: ...
@overload
def knots_to_mps(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def knots_to_mps(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Knots to metres per second."""
    return x * MPS_PER_KNOT


@overload
def mps_to_knots(x: float) -> float: ...
@overload
def mps_to_knots(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def mps_to_knots(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Metres per second to knots."""
    return x / MPS_PER_KNOT


@overload
def nm_to_m(x: float) -> float: ...
@overload
def nm_to_m(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def nm_to_m(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Nautical miles to metres."""
    return x * M_PER_NM


@overload
def m_to_nm(x: float) -> float: ...
@overload
def m_to_nm(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def m_to_nm(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Metres to nautical miles."""
    return x / M_PER_NM


@overload
def tonnes_to_kg(x: float) -> float: ...
@overload
def tonnes_to_kg(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def tonnes_to_kg(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Tonnes to kilograms."""
    return x * _KG_PER_TONNE


@overload
def kg_to_tonnes(x: float) -> float: ...
@overload
def kg_to_tonnes(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def kg_to_tonnes(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Kilograms to tonnes."""
    return x / _KG_PER_TONNE


@overload
def kw_to_w(x: float) -> float: ...
@overload
def kw_to_w(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def kw_to_w(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Kilowatts to watts."""
    return x * _W_PER_KW


@overload
def w_to_kw(x: float) -> float: ...
@overload
def w_to_kw(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def w_to_kw(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Watts to kilowatts."""
    return x / _W_PER_KW


@overload
def g_per_kwh_to_kg_per_j(x: float) -> float: ...
@overload
def g_per_kwh_to_kg_per_j(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def g_per_kwh_to_kg_per_j(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Specific fuel consumption, g/kWh to kg/J."""
    return x * KG_PER_J_PER_G_PER_KWH


@overload
def kg_per_j_to_g_per_kwh(x: float) -> float: ...
@overload
def kg_per_j_to_g_per_kwh(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def kg_per_j_to_g_per_kwh(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Specific fuel consumption, kg/J to g/kWh."""
    return x / KG_PER_J_PER_G_PER_KWH


@overload
def hours_to_s(x: float) -> float: ...
@overload
def hours_to_s(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def hours_to_s(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Hours to seconds."""
    return x * _S_PER_HOUR


@overload
def s_to_hours(x: float) -> float: ...
@overload
def s_to_hours(x: NDArray[np.float64]) -> NDArray[np.float64]: ...
def s_to_hours(x: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Seconds to hours."""
    return x / _S_PER_HOUR
