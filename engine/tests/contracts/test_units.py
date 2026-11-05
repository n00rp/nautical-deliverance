"""Unit conversion tests."""

from typing import TYPE_CHECKING

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nautical_deliverance.domain.contracts import units as u

if TYPE_CHECKING:
    from collections.abc import Callable

PAIRS: list[tuple[Callable[[float], float], Callable[[float], float]]] = [
    (u.knots_to_mps, u.mps_to_knots),
    (u.nm_to_m, u.m_to_nm),
    (u.tonnes_to_kg, u.kg_to_tonnes),
    (u.kw_to_w, u.w_to_kw),
    (u.g_per_kwh_to_kg_per_j, u.kg_per_j_to_g_per_kwh),
    (u.hours_to_s, u.s_to_hours),
]


@pytest.mark.req("S0b-R02")
def test_exact_constants() -> None:
    """Defining constants convert exactly."""
    assert u.knots_to_mps(1.0) == 1852 / 3600
    assert u.nm_to_m(1.0) == u.M_PER_NM == 1852.0  # noqa: PLR2004
    assert u.g_per_kwh_to_kg_per_j(3.6e9) == 1.0


@pytest.mark.req("S0b-R02")
@pytest.mark.parametrize(("fwd", "back"), PAIRS)
@settings(max_examples=1000)
@given(x=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_round_trips(
    fwd: Callable[[float], float], back: Callable[[float], float], x: float
) -> None:
    """Every pair round-trips."""
    assert back(fwd(x)) == pytest.approx(x, rel=1e-12, abs=1e-12)


@pytest.mark.req("S0b-R02")
@pytest.mark.parametrize(("fwd", "back"), PAIRS)
def test_array_inputs_preserve_shape(
    fwd: Callable[[float], float], back: Callable[[float], float]
) -> None:
    """Arrays in, same-shaped float64 arrays out."""
    x = np.linspace(-5.0, 5.0, 7)
    for f in (fwd, back):
        y = f(x)  # type: ignore[arg-type]
        assert isinstance(y, np.ndarray)
        assert y.shape == x.shape
        assert y.dtype == np.float64
