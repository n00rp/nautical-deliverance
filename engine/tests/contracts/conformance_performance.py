"""Reusable performance-model conformance suite (S0b-R08).

Subclass `PerformanceModelConformance` and implement `make_model`, `make_vessel` and
`make_condition(n)` (a condition with `n` points and OK weather). The suite uses plain `assert`
/ numpy testing, so a broken model fails with `AssertionError`.
"""

from typing import TYPE_CHECKING

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.performance import (
    Consumer,
    OperatingCondition,
    PerformanceModel,
    PerformanceResult,
    VesselSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

_ROUND_TRIP_RTOL = 1e-6
_FUEL_RTOL = 1e-12


def _f(*vals: float) -> NDArray[np.float64]:
    return np.array(vals, dtype=np.float64)


def _assert_rejected(call: Callable[..., object], *args: object) -> None:
    """Fail with AssertionError unless `call(*args)` raises InvalidInputError."""
    try:
        call(*args)
    except InvalidInputError:
        return
    msg = "invalid input was accepted"
    raise AssertionError(msg)


def total_fuel_kgps(result: PerformanceResult) -> NDArray[np.float64]:
    """Fuel rate summed over all consumers."""
    return np.sum([result.fuel_rate_kgps[c] for c in Consumer], axis=0)


class PerformanceModelConformance:
    """Mixin of conformance tests; concrete subclasses supply the model and fixtures."""

    def make_model(self) -> PerformanceModel:
        """Return the model under test."""
        raise NotImplementedError

    def make_vessel(self) -> VesselSpec:
        """Return a valid vessel."""
        raise NotImplementedError

    def make_condition(self, n: int) -> OperatingCondition:
        """Return a condition of `n` points with OK weather."""
        raise NotImplementedError

    def make_bad_weather_condition(self, n: int) -> OperatingCondition:
        """Return a condition of `n` points whose weather quality is not OK."""
        raise NotImplementedError

    def _powers(self, *fractions: float) -> NDArray[np.float64]:
        return _f(*fractions) * self.make_vessel().mcr_w

    def _all_results(self) -> list[PerformanceResult]:
        m, v, c = self.make_model(), self.make_vessel(), self.make_condition(5)
        p = self._powers(0.05, 0.3, 0.6, 0.85, 1.0)
        by_power = m.speed_for_power(v, c, p)
        return [by_power, m.power_for_speed(v, c, by_power.speed_through_water_mps)]

    @pytest.mark.req("S0b-R08")
    @settings(max_examples=50, deadline=None)
    @given(fractions=st.lists(st.floats(0.05, 1.0), min_size=1, max_size=6))
    def test_round_trip_power(self, fractions: list[float]) -> None:
        """power_for_speed(speed_for_power(P)) returns P."""
        self.check_round_trip(fractions)

    def check_round_trip(self, fractions: list[float]) -> None:
        """Check the round-trip property for one batch (callable without Hypothesis)."""
        m, v = self.make_model(), self.make_vessel()
        c = self.make_condition(len(fractions))
        p = self._powers(*fractions)
        speed = m.speed_for_power(v, c, p).speed_through_water_mps
        back = m.power_for_speed(v, c, speed).shaft_power_w
        np.testing.assert_allclose(back, p, rtol=_ROUND_TRIP_RTOL)

    @pytest.mark.req("S0b-R08")
    def test_outputs_finite_non_negative(self) -> None:
        """Every output array is finite and non-negative."""
        for r in self._all_results():
            arrays = [
                r.speed_through_water_mps,
                r.shaft_power_w,
                r.motion_risk_ratio,
                *r.fuel_rate_kgps.values(),
            ]
            assert all(bool(np.isfinite(a).all() and (a >= 0.0).all()) for a in arrays)

    @pytest.mark.req("S0b-R08")
    def test_fuel_reported_non_negative_and_point_independent(self) -> None:
        """Every consumer is reported, finite, non-negative, and each point is independent."""
        m, v = self.make_model(), self.make_vessel()
        p = self._powers(0.4, 0.9)
        both = m.speed_for_power(v, self.make_condition(2), p)
        assert set(both.fuel_rate_kgps) == set(Consumer)
        assert all(
            bool(np.isfinite(a).all() and (a >= 0.0).all()) for a in both.fuel_rate_kgps.values()
        )
        singles = [
            m.speed_for_power(v, self.make_condition(1), p[i : i + 1]).fuel_rate_kgps
            for i in range(2)
        ]
        for c in Consumer:
            np.testing.assert_allclose(
                both.fuel_rate_kgps[c], [s[c][0] for s in singles], rtol=_FUEL_RTOL
            )
        np.testing.assert_allclose(
            total_fuel_kgps(both).sum(),
            sum(float(np.sum(list(s.values()))) for s in singles),
            rtol=_FUEL_RTOL,
        )

    @pytest.mark.req("S0b-R08")
    def test_motion_risk_in_unit_interval(self) -> None:
        """motion_risk_ratio lies in [0, 1]."""
        for r in self._all_results():
            assert bool(((r.motion_risk_ratio >= 0.0) & (r.motion_risk_ratio <= 1.0)).all())

    @pytest.mark.req("S0b-R08")
    def test_lengths_preserved(self) -> None:
        """Every output array has the input length."""
        n = 4
        m, v, c = self.make_model(), self.make_vessel(), self.make_condition(n)
        r = m.speed_for_power(v, c, self._powers(0.2, 0.4, 0.6, 0.8))
        r2 = m.power_for_speed(v, c, r.speed_through_water_mps)
        for res in (r, r2):
            arrays = [
                res.speed_through_water_mps,
                res.shaft_power_w,
                res.motion_risk_ratio,
                *res.fuel_rate_kgps.values(),
            ]
            assert all(len(a) == n for a in arrays)

    @pytest.mark.req("S0b-R08")
    def test_mismatched_lengths_rejected(self) -> None:
        """Input and condition of different lengths raise InvalidInputError."""
        m, v, c = self.make_model(), self.make_vessel(), self.make_condition(3)
        for bad in (_f(1.0, 2.0), _f(1.0, 2.0, 3.0, 4.0)):
            _assert_rejected(m.speed_for_power, v, c, bad * 1e6)
            _assert_rejected(m.power_for_speed, v, c, bad)

    @pytest.mark.req("S0b-R08")
    def test_nan_speed_rejected(self) -> None:
        """NaN or infinite speeds (and powers) raise InvalidInputError."""
        m, v, c = self.make_model(), self.make_vessel(), self.make_condition(1)
        for bad in (np.nan, np.inf, -np.inf):
            _assert_rejected(m.power_for_speed, v, c, _f(bad))
            _assert_rejected(m.speed_for_power, v, c, _f(bad))

    @pytest.mark.req("S0b-R08")
    def test_negative_power_rejected(self) -> None:
        """Negative power (and speed) raises InvalidInputError."""
        m, v, c = self.make_model(), self.make_vessel(), self.make_condition(1)
        _assert_rejected(m.speed_for_power, v, c, _f(-1.0))
        _assert_rejected(m.power_for_speed, v, c, _f(-1.0))

    @pytest.mark.req("S0b-R08")
    def test_non_ok_weather_rejected(self) -> None:
        """Points without valid weather are rejected, never computed on NaN."""
        m, v, c = self.make_model(), self.make_vessel(), self.make_bad_weather_condition(2)
        _assert_rejected(m.power_for_speed, v, c, _f(5.0, 5.0))
        _assert_rejected(m.speed_for_power, v, c, self._powers(0.5, 0.5))
