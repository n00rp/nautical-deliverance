"""Run the performance conformance suite on the reference model and prove it can fail (S0b-R09)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from nautical_deliverance.domain.contracts.errors import InvalidInputError
from nautical_deliverance.domain.contracts.performance import (
    Consumer,
    FuelType,
    OperatingCondition,
    OperatingState,
    PerformanceModel,
    PerformanceResult,
    SafetyLimits,
    VesselSpec,
    is_valid_imo,
)
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.units import g_per_kwh_to_kg_per_j
from nautical_deliverance.domain.contracts.weather import REQUIRED, WeatherVariable
from nautical_deliverance.domain.reference.simple_performance import C_WAVE, SimplePerformance
from nautical_deliverance.domain.reference.uniform_weather import UniformWeather
from tests.contracts.conformance_performance import PerformanceModelConformance

if TYPE_CHECKING:
    from numpy.typing import NDArray

_START = datetime(2026, 11, 4, tzinfo=UTC)
_DESIGN_SPEED_MPS = 7.0
_MCR_W = 10e6
_LIMITS = SafetyLimits(8.0, 25.0, 2.0)


def make_vessel(**overrides: Any) -> VesselSpec:  # noqa: ANN401 - forwarded to `replace`
    """Build a valid vessel; keyword overrides replace fields."""
    spec = VesselSpec(
        imo_number="9074729",
        length_m=200.0,
        beam_m=32.0,
        design_draft_m=10.0,
        mcr_w=_MCR_W,
        sfoc_curve_kg_per_j=tuple(
            (load, g_per_kwh_to_kg_per_j(g))
            for load, g in ((0.1, 230.0), (0.5, 180.0), (1.0, 190.0))
        ),
        auxiliary_load_w={OperatingState.AT_SEA: 500e3, OperatingState.IN_PORT: 300e3},
        safety_limits=_LIMITS,
    )
    return replace(spec, **overrides)


def make_condition(n: int, hs_m: float = 2.0, offset_deg: float = 0.0) -> OperatingCondition:
    """`n` points of uniform weather with the given significant wave height."""
    base = dict.fromkeys(REQUIRED, 1.0) | {WeatherVariable.TOTAL_SEA_HEIGHT_M: hs_m}
    provider = UniformWeather(
        base, (40.0, 44.0), (0.0, 4.0), (_START, _START + timedelta(hours=6)), _START, 1.0,
        timedelta(hours=3),
    )  # fmt: skip
    weather = provider.sample(
        np.full(n, 41.0 + offset_deg),
        np.full(n, 1.0),
        np.full(n, to_datetime64(_START), dtype="datetime64[s]"),
    )
    ones = np.ones(n)
    return OperatingCondition(10.0 * ones, 10.0 * ones, 90.0 * ones, weather)


class TestSimplePerformance(PerformanceModelConformance):
    """The reference model passes the suite."""

    def make_model(self) -> PerformanceModel:
        """Return the reference model."""
        return SimplePerformance(_DESIGN_SPEED_MPS)

    def make_vessel(self) -> VesselSpec:
        """Return the fixture vessel."""
        return make_vessel()

    def make_condition(self, n: int) -> OperatingCondition:
        """Return a moderate sea state."""
        return make_condition(n)


class _Inconsistent(SimplePerformance):
    """Broken: the two directions disagree by 1 %."""

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
    ) -> PerformanceResult:
        r = super().power_for_speed(vessel, condition, speed_through_water_mps)
        return replace(r, shaft_power_w=r.shaft_power_w * 1.01)


class _RiskOutOfRange(SimplePerformance):
    """Broken: risk is not clamped to 1."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w)
        return replace(r, motion_risk_ratio=r.motion_risk_ratio * 10.0)


class _InconsistentSuite(TestSimplePerformance):
    def make_model(self) -> PerformanceModel:
        return _Inconsistent(_DESIGN_SPEED_MPS)


class _RiskSuite(TestSimplePerformance):
    def make_model(self) -> PerformanceModel:
        return _RiskOutOfRange(_DESIGN_SPEED_MPS)


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_inconsistent_model() -> None:
    """A model whose directions disagree by 1 % fails the round trip."""
    with pytest.raises(AssertionError):
        _InconsistentSuite().check_round_trip([0.05, 0.5, 1.0])


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_risk_out_of_range() -> None:
    """A model reporting risk above 1 fails the unit-interval check."""
    with pytest.raises(AssertionError):
        _RiskSuite().test_motion_risk_in_unit_interval()


@pytest.mark.req("S0b-R08")
def test_simple_performance_equations() -> None:
    """P(design) = 0.85 MCR in calm water; wave add-on and risk clamp follow the formulas."""
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    v = np.array([_DESIGN_SPEED_MPS])
    calm = model.power_for_speed(vessel, make_condition(1, hs_m=1e-12), v)
    assert calm.shaft_power_w[0] == pytest.approx(0.85 * _MCR_W)
    rough = model.power_for_speed(vessel, make_condition(1, hs_m=20.0), v)
    assert rough.shaft_power_w[0] == pytest.approx(
        0.85 * _MCR_W + C_WAVE * 20.0**2 * _DESIGN_SPEED_MPS
    )
    assert rough.motion_risk_ratio[0] == 1.0
    sfoc_at_85 = np.interp(0.85, [0.5, 1.0], [180.0, 190.0]) * 1e-3 / 3.6e6  # g/kWh -> kg/J
    assert calm.fuel_rate_kgps[Consumer.MAIN_ENGINE][0] == pytest.approx(
        sfoc_at_85 * calm.shaft_power_w[0]
    )


@pytest.mark.req("S0b-R08")
def test_non_ok_weather_rejected() -> None:
    """A point without valid weather is rejected, never computed on NaN."""
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    cond = make_condition(2, offset_deg=100.0)
    assert (cond.weather.quality != "ok").all()
    with pytest.raises(InvalidInputError):
        model.power_for_speed(vessel, cond, np.array([5.0, 5.0]))


@pytest.mark.req("S0b-R08")
def test_bad_design_speed_and_dtype_rejected() -> None:
    """Non-positive design speed and non-float64 input raise InvalidInputError."""
    with pytest.raises(InvalidInputError):
        SimplePerformance(0.0)
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    with pytest.raises(InvalidInputError):
        model.power_for_speed(vessel, make_condition(1), np.array([5], dtype=np.int64))
    with pytest.raises(InvalidInputError):
        model.power_for_speed(vessel, make_condition(1), [5.0])  # type: ignore[arg-type]


@pytest.mark.req("S0b-R08")
def test_imo_check_digit() -> None:
    """Valid IMO numbers pass; wrong check digit, length or characters fail."""
    assert is_valid_imo("9074729")
    assert not is_valid_imo("9074728")
    assert not is_valid_imo("907472")
    assert not is_valid_imo("90747a9")
    with pytest.raises(InvalidInputError):
        make_vessel(imo_number="9074728")


@pytest.mark.req("S0b-R08")
def test_vessel_validation() -> None:
    """Bad curves, loads and dimensions are rejected."""
    bad_curves = (
        ((0.1, 1e-7),),
        ((0.5, 1e-7), (0.5, 1e-7)),
        ((0.8, 1e-7), (0.2, 1e-7)),
        ((0.1, 1e-7), (1.5, 1e-7)),
        ((0.1, 1e-7), (0.9, 0.0)),
    )
    for curve in bad_curves:
        with pytest.raises(InvalidInputError):
            make_vessel(sfoc_curve_kg_per_j=curve)
    with pytest.raises(InvalidInputError):
        make_vessel(auxiliary_load_w={OperatingState.AT_SEA: 1.0})
    with pytest.raises(InvalidInputError):
        make_vessel(auxiliary_load_w={OperatingState.AT_SEA: -1.0, OperatingState.IN_PORT: 1.0})
    with pytest.raises(InvalidInputError):
        make_vessel(mcr_w=float("nan"))
    with pytest.raises(InvalidInputError):
        SafetyLimits(0.0, 25.0, 2.0)


@pytest.mark.req("S0b-R08")
def test_condition_validation() -> None:
    """Length mismatch, 2-D and non-finite condition arrays are rejected."""
    c = make_condition(3)
    ones = np.ones(3)
    with pytest.raises(InvalidInputError):
        OperatingCondition(np.ones(2), ones, ones, c.weather)
    with pytest.raises(InvalidInputError):
        OperatingCondition(ones, ones, np.array([1.0, np.nan, 1.0]), c.weather)


@pytest.mark.req("S0b-R08")
def test_result_validation() -> None:
    """Missing consumers and unequal lengths are rejected."""
    a = np.ones(2)
    with pytest.raises(InvalidInputError):
        PerformanceResult(a, a, {Consumer.MAIN_ENGINE: a}, a)
    with pytest.raises(InvalidInputError):
        PerformanceResult(a, a, {Consumer.MAIN_ENGINE: a, Consumer.AUXILIARY: np.ones(3)}, a)


@pytest.mark.req("S0b-R08")
def test_immutability() -> None:
    """Result, condition and vessel hold read-only copies."""
    a = np.ones(2)
    r = PerformanceResult(a, a, {Consumer.MAIN_ENGINE: a, Consumer.AUXILIARY: a}, a)
    a[0] = 99.0
    assert r.shaft_power_w[0] == 1.0
    for arr in (r.shaft_power_w, r.speed_through_water_mps, r.motion_risk_ratio,
                r.fuel_rate_kgps[Consumer.MAIN_ENGINE]):  # fmt: skip
        assert not arr.flags.writeable
    with pytest.raises(TypeError):
        r.fuel_rate_kgps[Consumer.MAIN_ENGINE] = a  # type: ignore[index]
    cond = make_condition(2)
    for arr in (cond.draft_fwd_m, cond.draft_aft_m, cond.heading_deg):
        assert not arr.flags.writeable
    with pytest.raises(TypeError):
        make_vessel().auxiliary_load_w[OperatingState.AT_SEA] = 0.0  # type: ignore[index]


@pytest.mark.req("S0b-R08")
def test_enums() -> None:
    """Enum values are lower-case."""
    assert [f.value for f in FuelType] == ["hfo", "vlsfo", "ulsfo", "mgo", "lng"]
    assert len(make_condition(4)) == len(make_condition(4).heading_deg)
