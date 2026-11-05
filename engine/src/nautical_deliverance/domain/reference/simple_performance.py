"""Analytical reference performance model: cubic power law plus a wave add-on.

Shaft power: P(v) = k * v^3 + C_WAVE * Hs^2 * v, with k chosen so the calm-water term equals
0.85 * MCR at the design speed. Hs is the total sea height of the condition's weather sample.
Fuel: main engine = SFOC(P / MCR) * P with the main-engine curve; auxiliary = SFOC(aux / MCR) * aux
with the auxiliary curve and the at-sea load; SFOC is linearly interpolated and clamped at the
curve ends, also for loads above MCR. Curves are at the ISO reference LCV; the mass of the chosen
fuel is the reference mass times REFERENCE_LCV_J_PER_KG / LCV of that fuel (equal energy).
Draft and heading are unused. `speed_for_power` raises for power above P(2 * design speed).
"""

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

import numpy as np

from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.performance import (
    Consumer,
    FuelType,
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

# Lower calorific values in J/kg. ILLUSTRATIVE round figures from typical marine-fuel data
# (ISO 3046-1 reference 42.7 MJ/kg for distillate fuel; residual fuels about 40 MJ/kg; LNG about
# 49 MJ/kg), NOT calibrated and not a source for C2. C2 owns the real values and their sources.
REFERENCE_LCV_J_PER_KG: Final = 42.7e6
LCV_J_PER_KG: Final = MappingProxyType(
    {
        FuelType.HFO: 40.2e6,
        FuelType.VLSFO: 41.0e6,
        FuelType.ULSFO: 41.5e6,
        FuelType.MGO: 42.7e6,
        FuelType.LNG: 49.1e6,
    }
)


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
        fuel_type: FuelType,
    ) -> PerformanceResult:
        """Invert the power law by bisection on [0, 2 * design speed] (power rises with speed)."""
        validate_performance_input(condition, shaft_power_w, "shaft_power_w", fuel_type)
        hs = condition.weather.values[WeatherVariable.TOTAL_SEA_HEIGHT_M]
        lo = np.zeros_like(shaft_power_w)
        hi = np.full_like(shaft_power_w, 2.0 * self._design)
        for _ in range(_BISECTION_STEPS):
            mid = 0.5 * (lo + hi)
            below = self._power(vessel, hs, mid) < shaft_power_w
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        reachable = self._power(vessel, hs, np.full_like(shaft_power_w, 2.0 * self._design))
        if (too_high := shaft_power_w > reachable).any():
            msg = (
                f"power unreachable at points {np.flatnonzero(too_high).tolist()}; "
                f"maximum {reachable[too_high].tolist()} W"
            )
            raise InvalidInputError(msg)
        speed = np.where(shaft_power_w == 0.0, 0.0, 0.5 * (lo + hi))
        return self._result(vessel, hs, speed, shaft_power_w, fuel_type)

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        """Evaluate the power law at the given speeds."""
        validate_performance_input(
            condition, speed_through_water_mps, "speed_through_water_mps", fuel_type
        )
        hs = condition.weather.values[WeatherVariable.TOTAL_SEA_HEIGHT_M]
        power = self._power(vessel, hs, speed_through_water_mps)
        return self._result(vessel, hs, speed_through_water_mps, power, fuel_type)

    @staticmethod
    def _result(
        vessel: VesselSpec,
        hs_m: NDArray[np.float64],
        speed: NDArray[np.float64],
        power: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        def sfoc(consumer: Consumer, load_w: NDArray[np.float64]) -> NDArray[np.float64]:
            loads, curve = zip(*vessel.sfoc_curve_kg_per_j[consumer], strict=True)
            return np.asarray(np.interp(load_w / vessel.mcr_w, loads, curve))

        to_fuel = REFERENCE_LCV_J_PER_KG / LCV_J_PER_KG[fuel_type]
        aux_w = np.full_like(power, vessel.auxiliary_load_w[OperatingState.AT_SEA])
        fuel = {
            Consumer.MAIN_ENGINE: sfoc(Consumer.MAIN_ENGINE, power) * power * to_fuel,
            Consumer.AUXILIARY: sfoc(Consumer.AUXILIARY, aux_w) * aux_w * to_fuel,
        }
        risk = np.minimum(1.0, hs_m / vessel.safety_limits.max_significant_wave_height_m)
        return PerformanceResult(speed, power, fuel, risk)
