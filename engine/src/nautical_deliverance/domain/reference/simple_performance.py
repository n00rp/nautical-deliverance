"""Analytical reference performance model: cubic power law plus a wave add-on.

Shaft power: P(v) = k * v^3 + C_WAVE * Hs^2 * v, with k chosen so the calm-water term equals
0.85 * MCR at the design speed. Hs is the total sea height of the condition's weather sample.
Fuel: main engine = SFOC(P / MCR) * P; auxiliary = SFOC(aux / MCR) * aux (at-sea load); SFOC is
linearly interpolated (clamped at the curve ends).
"""

from typing import TYPE_CHECKING

import numpy as np

from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.performance import (
    Consumer,
    OperatingCondition,
    OperatingState,
    PerformanceResult,
    VesselSpec,
    validate_performance_input,
)
from nautical_deliverance.domain.contracts.weather import WeatherVariable

if TYPE_CHECKING:
    from numpy.typing import NDArray

DESIGN_LOAD_RATIO = 0.85
# Added wave resistance coefficient, W per (m^2 * m/s) of Hs^2 * v. Illustrative, not calibrated.
C_WAVE = 2000.0
_BISECTION_STEPS = 64  # the bracket 2 * design halves to ~1e-19 relative


class SimplePerformance:
    """Implements `PerformanceModel` with analytical formulas."""

    def __init__(self, design_speed_mps: float) -> None:
        """Set the speed at which calm-water power is 85 % of MCR."""
        if not (design_speed_mps > 0.0 and np.isfinite(design_speed_mps)):
            msg = "design_speed_mps must be positive and finite"
            raise InvalidInputError(msg)
        self._design = design_speed_mps

    def _power(
        self, vessel: VesselSpec, hs_m: NDArray[np.float64], v: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        k = DESIGN_LOAD_RATIO * vessel.mcr_w / self._design**3
        return np.asarray(k * v**3 + C_WAVE * hs_m**2 * v)

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
    ) -> PerformanceResult:
        """Invert the power law by bisection on [0, 2 * design speed] (power rises with speed)."""
        validate_performance_input(condition, shaft_power_w, "shaft_power_w")
        hs = condition.weather.values[WeatherVariable.TOTAL_SEA_HEIGHT_M]
        lo = np.zeros_like(shaft_power_w)
        hi = np.full_like(shaft_power_w, 2.0 * self._design)
        for _ in range(_BISECTION_STEPS):
            mid = 0.5 * (lo + hi)
            below = self._power(vessel, hs, mid) < shaft_power_w
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        return self._result(vessel, hs, 0.5 * (lo + hi), shaft_power_w)

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
    ) -> PerformanceResult:
        """Evaluate the power law at the given speeds."""
        validate_performance_input(condition, speed_through_water_mps, "speed_through_water_mps")
        hs = condition.weather.values[WeatherVariable.TOTAL_SEA_HEIGHT_M]
        power = self._power(vessel, hs, speed_through_water_mps)
        return self._result(vessel, hs, speed_through_water_mps, power)

    @staticmethod
    def _result(
        vessel: VesselSpec,
        hs_m: NDArray[np.float64],
        speed: NDArray[np.float64],
        power: NDArray[np.float64],
    ) -> PerformanceResult:
        loads, sfoc = zip(*vessel.sfoc_curve_kg_per_j, strict=True)
        aux_w = vessel.auxiliary_load_w[OperatingState.AT_SEA]
        main = np.interp(power / vessel.mcr_w, loads, sfoc) * power
        aux = np.full_like(power, np.interp(aux_w / vessel.mcr_w, loads, sfoc) * aux_w)
        risk = np.minimum(1.0, hs_m / vessel.safety_limits.max_significant_wave_height_m)
        return PerformanceResult(
            speed, power, {Consumer.MAIN_ENGINE: main, Consumer.AUXILIARY: aux}, risk
        )
