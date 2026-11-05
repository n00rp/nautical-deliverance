"""Run the performance conformance suite on the reference model and prove it can fail (S0b-R09)."""

import functools
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
from nautical_deliverance.domain.contracts.weather import (
    REQUIRED,
    SampleQuality,
    WeatherGroup,
    WeatherSample,
    WeatherVariable,
)
from nautical_deliverance.domain.reference.simple_performance import (
    C_WAVE,
    LCV_J_PER_KG,
    REFERENCE_LCV_J_PER_KG,
    SimplePerformance,
)
from nautical_deliverance.domain.reference.uniform_weather import GroupWindow, UniformWeather
from tests.contracts.conformance_performance import PerformanceModelConformance
from tests.contracts.weather_fixtures import uniform_times

if TYPE_CHECKING:
    from numpy.typing import NDArray

_START = datetime(2026, 11, 4, tzinfo=UTC)
_DESIGN_SPEED_MPS = 7.0
_MCR_W = 10e6
_LIMITS = SafetyLimits(8.0, 25.0, 2.0)
_MAIN_CURVE_G = ((0.1, 230.0), (0.5, 180.0), (1.0, 190.0))
_AUX_CURVE_G = ((0.0, 260.0), (0.1, 220.0), (1.0, 205.0))
_FUEL = FuelType.VLSFO


def _curve(points_g_per_kwh: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    return tuple((load, g_per_kwh_to_kg_per_j(g)) for load, g in points_g_per_kwh)


def make_vessel(**overrides: Any) -> VesselSpec:  # noqa: ANN401 - forwarded to `replace`
    """Build a valid vessel; keyword overrides replace fields."""
    spec = VesselSpec(
        imo_number="9074729",
        length_m=200.0,
        beam_m=32.0,
        design_draft_m=10.0,
        mcr_w=_MCR_W,
        sfoc_curve_kg_per_j={
            Consumer.MAIN_ENGINE: _curve(_MAIN_CURVE_G),
            Consumer.AUXILIARY: _curve(_AUX_CURVE_G),
        },
        auxiliary_load_w={OperatingState.AT_SEA: 500e3, OperatingState.IN_PORT: 300e3},
        safety_limits=_LIMITS,
    )
    return replace(spec, **overrides)


def make_weather(  # noqa: PLR0913, PLR0917 - a test builder with one knob per concern
    n: int,
    hs_m: float = 2.0,
    lon_deg: float = 1.0,
    extra: dict[WeatherVariable, float] | None = None,
    windows: dict[WeatherGroup, GroupWindow] | None = None,
    lat_deg: float = 41.0,
) -> WeatherSample:
    """`n` points of uniform weather with the given significant wave height."""
    base = dict.fromkeys(REQUIRED, 1.0) | {WeatherVariable.TOTAL_SEA_HEIGHT_M: hs_m} | (extra or {})
    provider = UniformWeather(
        base,
        (40.0, 44.0),
        (0.0, 4.0),
        uniform_times(_START, _START + timedelta(hours=6), timedelta(hours=3)),
        _START,
        1.0,
        1.0,
        group_windows=windows,
    )
    return provider.sample(
        np.full(n, lat_deg),
        np.full(n, lon_deg),
        np.full(n, to_datetime64(_START), dtype="datetime64[s]"),
    )


def condition_from(weather: WeatherSample) -> OperatingCondition:
    """Wrap a weather sample into a condition with fixed draft and heading."""
    ones = np.ones(len(weather))
    return OperatingCondition(10.0 * ones, 10.0 * ones, 90.0 * ones, weather)


def make_condition(n: int, hs_m: float = 2.0, lon_deg: float = 1.0) -> OperatingCondition:
    """`n` points of uniform weather; `lon_deg` outside 0..4 makes the weather out of coverage."""
    return condition_from(make_weather(n, hs_m, lon_deg))


def restamp(weather: WeatherSample, quality: SampleQuality) -> WeatherSample:
    """Return the same weather with every group set to `quality` (values unchanged)."""
    return WeatherSample(
        dict(weather.values),
        {g: np.full_like(q, quality) for g, q in weather.quality.items()},
        dict(weather.source),
        dict(weather.run_time),
        weather.unavailable,
    )


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

    def make_stale_weather_condition(self, n: int) -> OperatingCondition:
        """Return the moderate sea state with every group STALE."""
        return condition_from(restamp(make_weather(n), SampleQuality.STALE))

    def make_bad_weather_condition(self, n: int) -> OperatingCondition:
        """Return points outside weather coverage."""
        return make_condition(n, lon_deg=100.0)


class _Inconsistent(SimplePerformance):
    """Broken: the two directions disagree by 1 %."""

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().power_for_speed(vessel, condition, speed_through_water_mps, fuel_type)
        return replace(r, shaft_power_w=r.shaft_power_w * 1.01)


class _RiskOutOfRange(SimplePerformance):
    """Broken: risk is not clamped to 1."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
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
    """P(design) = 0.85 MCR in calm water; wave add-on, risk clamp and per-consumer SFOC follow."""
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    v = np.array([_DESIGN_SPEED_MPS])
    calm = model.power_for_speed(vessel, make_condition(1, hs_m=1e-12), v, FuelType.MGO)
    assert calm.shaft_power_w[0] == pytest.approx(0.85 * _MCR_W)
    rough = model.power_for_speed(vessel, make_condition(1, hs_m=20.0), v, FuelType.MGO)
    assert rough.shaft_power_w[0] == pytest.approx(
        0.85 * _MCR_W + C_WAVE * 20.0**2 * _DESIGN_SPEED_MPS
    )
    assert rough.motion_risk_ratio[0] == 1.0
    g_to_kg_per_j = 1e-3 / 3.6e6
    main_sfoc = np.interp(0.85, [0.5, 1.0], [180.0, 190.0]) * g_to_kg_per_j
    aux_sfoc = np.interp(0.05, [0.0, 0.1, 1.0], [260.0, 220.0, 205.0]) * g_to_kg_per_j
    assert calm.fuel_rate_kgps[Consumer.MAIN_ENGINE][0] == pytest.approx(
        main_sfoc * calm.shaft_power_w[0]
    )
    assert calm.fuel_rate_kgps[Consumer.AUXILIARY][0] == pytest.approx(aux_sfoc * 500e3)
    main_aux_curve = np.interp(0.05, [0.1, 0.5, 1.0], [230.0, 180.0, 190.0]) * g_to_kg_per_j
    assert calm.fuel_rate_kgps[Consumer.AUXILIARY][0] != pytest.approx(main_aux_curve * 500e3)


@pytest.mark.req("S0b-R08")
def test_fuel_mass_scales_with_calorific_value() -> None:
    """The reference converts equal energy: mass = reference mass * reference LCV / fuel LCV."""
    model, vessel, cond = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel(), make_condition(2)
    p = np.array([0.3 * _MCR_W, 0.9 * _MCR_W])
    reference = model.speed_for_power(vessel, cond, p, FuelType.MGO)
    assert LCV_J_PER_KG[FuelType.MGO] == REFERENCE_LCV_J_PER_KG
    assert set(LCV_J_PER_KG) == set(FuelType)
    for fuel in FuelType:
        r = model.speed_for_power(vessel, cond, p, fuel)
        for c in Consumer:
            np.testing.assert_allclose(
                r.fuel_rate_kgps[c],
                reference.fuel_rate_kgps[c] * REFERENCE_LCV_J_PER_KG / LCV_J_PER_KG[fuel],
            )
    lng = model.speed_for_power(vessel, cond, p, FuelType.LNG)
    hfo = model.speed_for_power(vessel, cond, p, FuelType.HFO)
    assert bool(
        (lng.fuel_rate_kgps[Consumer.MAIN_ENGINE] < hfo.fuel_rate_kgps[Consumer.MAIN_ENGINE]).all()
    )


@pytest.mark.req("S0b-R08")
def test_bad_design_speed_and_dtype_rejected() -> None:
    """Non-positive design speed and non-float64 input raise InvalidInputError."""
    with pytest.raises(InvalidInputError):
        SimplePerformance(0.0)
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    with pytest.raises(InvalidInputError):
        model.power_for_speed(vessel, make_condition(1), np.array([5], dtype=np.int64), _FUEL)
    with pytest.raises(InvalidInputError):
        model.power_for_speed(vessel, make_condition(1), [5.0], _FUEL)  # type: ignore[arg-type]


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
    good_aux = _curve(_AUX_CURVE_G)
    bad_curves = (
        ((0.1, 1e-7),),
        ((0.5, 1e-7), (0.5, 1e-7)),
        ((0.8, 1e-7), (0.2, 1e-7)),
        ((0.1, 1e-7), (1.5, 1e-7)),
        ((0.1, 1e-7), (0.9, 0.0)),
    )
    for curve in bad_curves:
        for consumer in Consumer:
            curves = {Consumer.MAIN_ENGINE: good_aux, Consumer.AUXILIARY: good_aux}
            curves[consumer] = curve
            with pytest.raises(InvalidInputError):
                make_vessel(sfoc_curve_kg_per_j=curves)
    for missing in ({Consumer.MAIN_ENGINE: good_aux}, {}, {"boiler": good_aux}):
        with pytest.raises(InvalidInputError):
            make_vessel(sfoc_curve_kg_per_j=missing)
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
    """Missing consumers, unequal lengths and non-1-D arrays are rejected."""
    a = np.ones(2)
    both = {Consumer.MAIN_ENGINE: a, Consumer.AUXILIARY: a}
    with pytest.raises(InvalidInputError):
        PerformanceResult(a, a, {Consumer.MAIN_ENGINE: a}, a)
    with pytest.raises(InvalidInputError):
        PerformanceResult(a, a, {Consumer.MAIN_ENGINE: a, Consumer.AUXILIARY: np.ones(3)}, a)
    with pytest.raises(InvalidInputError):
        PerformanceResult(np.ones((2, 1)), a, both, a)
    with pytest.raises(InvalidInputError):
        PerformanceResult(a, a, {Consumer.MAIN_ENGINE: a, Consumer.AUXILIARY: np.ones((2, 1))}, a)


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
    vessel = make_vessel()
    with pytest.raises(TypeError):
        vessel.auxiliary_load_w[OperatingState.AT_SEA] = 0.0  # type: ignore[index]
    with pytest.raises(TypeError):
        vessel.sfoc_curve_kg_per_j[Consumer.MAIN_ENGINE] = ()  # type: ignore[index]


@pytest.mark.req("S0b-R08")
def test_vessel_equality_and_hash_by_value() -> None:
    """Equal specs are equal and hash alike (dict key, lru_cache); different ones differ."""
    a, b = make_vessel(), make_vessel()
    assert a is not b
    assert a == b
    assert hash(a) == hash(b)
    assert {a: 1}[b] == 1
    assert len({a, b}) == 1

    calls: list[VesselSpec] = []

    @functools.cache
    def cached(spec: VesselSpec) -> float:
        calls.append(spec)
        return spec.mcr_w

    assert cached(a) == cached(b)
    assert len(calls) == 1

    reordered = make_vessel(
        sfoc_curve_kg_per_j={
            Consumer.AUXILIARY: _curve(_AUX_CURVE_G),
            Consumer.MAIN_ENGINE: _curve(_MAIN_CURVE_G),
        },
        auxiliary_load_w={OperatingState.IN_PORT: 300e3, OperatingState.AT_SEA: 500e3},
    )
    assert reordered == a
    assert hash(reordered) == hash(a)

    other_curve = _curve(((0.1, 230.0), (0.5, 181.0), (1.0, 190.0)))
    variants = (
        make_vessel(mcr_w=_MCR_W * 2),
        make_vessel(imo_number="9074729", beam_m=33.0),
        make_vessel(safety_limits=SafetyLimits(9.0, 25.0, 2.0)),
        make_vessel(auxiliary_load_w={OperatingState.AT_SEA: 1.0, OperatingState.IN_PORT: 300e3}),
        make_vessel(
            sfoc_curve_kg_per_j={
                Consumer.MAIN_ENGINE: other_curve,
                Consumer.AUXILIARY: _curve(_AUX_CURVE_G),
            }
        ),
    )
    for v in variants:
        assert v != a
        assert len({a, v}) == 2  # noqa: PLR2004
    assert a != "vessel"
    assert a != 3  # noqa: PLR2004


@pytest.mark.req("S0b-R08")
def test_array_types_compare_by_identity_without_raising() -> None:
    """`==` on array-bearing types never raises; equal-looking instances are distinct."""
    cond, other = make_condition(2), make_condition(2)
    a = np.ones(2)
    result = PerformanceResult(a, a, dict.fromkeys(Consumer, a), a)
    for x, y in ((cond, other), (cond.weather, other.weather), (result, replace(result))):
        assert x == x  # noqa: PLR0124 - identity is the documented policy
        assert x != y
        assert len({x, y}) == 2  # noqa: PLR2004


@pytest.mark.req("S0b-R08")
def test_enums() -> None:
    """Enum values are lower-case."""
    assert [f.value for f in FuelType] == ["hfo", "vlsfo", "ulsfo", "mgo", "lng"]
    assert len(make_condition(4)) == len(make_condition(4).heading_deg)


@pytest.mark.req("S0b-R08")
def test_weather_groups_need_ok_or_stale_per_group() -> None:
    """Each needed group may be OK or STALE; a group without values rejects, others do not help."""
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    p = np.array([0.5 * _MCR_W])
    ok = make_condition(1)
    for quality in (SampleQuality.OK, SampleQuality.STALE):
        cond = condition_from(restamp(ok.weather, quality))
        assert model.speed_for_power(vessel, cond, p, _FUEL).speed_through_water_mps[0] > 0.0
    # wind is fine at this point, but current is outside its coverage
    current_out = {WeatherGroup.CURRENT: GroupWindow(lat_range_deg=(40.0, 40.5))}
    cond = condition_from(make_weather(1, windows=current_out))
    assert cond.weather.quality[WeatherGroup.WIND][0] == SampleQuality.OK
    assert cond.weather.quality[WeatherGroup.CURRENT][0] == SampleQuality.OUT_OF_COVERAGE
    with pytest.raises(InvalidInputError, match="current"):
        model.speed_for_power(vessel, cond, p, _FUEL)
    # the same point with the group STALE would be accepted only if it kept its values
    visibility_out = {WeatherGroup.VISIBILITY: GroupWindow(lat_range_deg=(40.0, 40.5))}
    optional = make_weather(1, extra={WeatherVariable.VISIBILITY_M: 9000.0}, windows=visibility_out)
    assert optional.quality[WeatherGroup.VISIBILITY][0] == SampleQuality.OUT_OF_COVERAGE
    result = model.speed_for_power(vessel, condition_from(optional), p, _FUEL)
    assert result.speed_through_water_mps[0] > 0.0  # an optional group is not needed


def _loose(r: PerformanceResult, **changes: Any) -> Any:  # noqa: ANN401
    """Copy a result without PerformanceResult validation (for broken models)."""
    fields = {
        "speed_through_water_mps": r.speed_through_water_mps,
        "shaft_power_w": r.shaft_power_w,
        "fuel_rate_kgps": dict(r.fuel_rate_kgps),
        "motion_risk_ratio": r.motion_risk_ratio,
    }
    return SimpleNamespace(**(fields | changes))


def replace_len(condition: OperatingCondition) -> OperatingCondition:
    """Return a condition with OK weather of the same length."""
    return make_condition(len(condition))


class _NoValidation(SimplePerformance):
    """Broken: coerces bad input instead of rejecting it."""

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
        fuel_type: FuelType,  # noqa: ARG002 - the broken model ignores it
    ) -> PerformanceResult:
        x = np.nan_to_num(np.abs(speed_through_water_mps), posinf=1.0)
        return super().power_for_speed(
            vessel, replace_len(condition), np.resize(x, len(condition)), FuelType.VLSFO
        )

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,  # noqa: ARG002 - the broken model ignores it
    ) -> PerformanceResult:
        x = np.nan_to_num(np.abs(shaft_power_w), posinf=1.0)
        return super().speed_for_power(
            vessel, replace_len(condition), np.resize(x, len(condition)), FuelType.VLSFO
        )


class _NegativeFuel(SimplePerformance):
    """Broken: auxiliary fuel is negative."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
        fuel = dict(r.fuel_rate_kgps)
        fuel[Consumer.AUXILIARY] = -fuel[Consumer.AUXILIARY]
        return _loose(r, fuel_rate_kgps=fuel)  # type: ignore[no-any-return]


class _MissingConsumer(SimplePerformance):
    """Broken: no auxiliary fuel reported."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
        main = r.fuel_rate_kgps[Consumer.MAIN_ENGINE]
        return _loose(r, fuel_rate_kgps={Consumer.MAIN_ENGINE: main})  # type: ignore[no-any-return]


class _Coupled(SimplePerformance):
    """Broken: fuel of each point depends on the mean power of the batch."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
        scale = 1.0 + shaft_power_w.mean() / vessel.mcr_w
        return _loose(r, fuel_rate_kgps={c: a * scale for c, a in r.fuel_rate_kgps.items()})  # type: ignore[no-any-return]


class _InvertedLcv(SimplePerformance):
    """Broken: converts to the wrong direction, so a higher-LCV fuel needs more mass."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
        k = (LCV_J_PER_KG[fuel_type] / REFERENCE_LCV_J_PER_KG) ** 2
        return replace(r, fuel_rate_kgps={c: a * k for c, a in r.fuel_rate_kgps.items()})


class _IgnoresFuel(SimplePerformance):
    """Broken: the fuel type is validated but never used, so every fuel burns the same mass."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,  # noqa: ARG002 - ignoring it is the defect
    ) -> PerformanceResult:
        return super().speed_for_power(vessel, condition, shaft_power_w, FuelType.VLSFO)


class _FuelChangesSpeed(SimplePerformance):
    """Broken: speed depends on the fuel type."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
        k = LCV_J_PER_KG[fuel_type] / REFERENCE_LCV_J_PER_KG
        return replace(r, speed_through_water_mps=r.speed_through_water_mps * k)


class _NoFuelValidation(SimplePerformance):
    """Broken: any fuel type is accepted and replaced by a default."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        known = fuel_type if isinstance(fuel_type, FuelType) else FuelType.VLSFO
        return super().speed_for_power(vessel, condition, shaft_power_w, known)

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        known = fuel_type if isinstance(fuel_type, FuelType) else FuelType.VLSFO
        return super().power_for_speed(vessel, condition, speed_through_water_mps, known)


class _NonMonotone(SimplePerformance):
    """Broken: speed falls again at high power."""

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        r = super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)
        k = 1.5 - shaft_power_w / vessel.mcr_w
        return replace(r, speed_through_water_mps=r.speed_through_water_mps * k)


class _RejectsStale(SimplePerformance):
    """Broken: refuses STALE weather, although D-063 says to compute on it."""

    def _check(self, condition: OperatingCondition) -> None:
        if any((q != SampleQuality.OK).any() for q in condition.weather.quality.values()):
            msg = "weather must be ok"
            raise InvalidInputError(msg)

    def speed_for_power(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        shaft_power_w: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        self._check(condition)
        return super().speed_for_power(vessel, condition, shaft_power_w, fuel_type)

    def power_for_speed(
        self,
        vessel: VesselSpec,
        condition: OperatingCondition,
        speed_through_water_mps: NDArray[np.float64],
        fuel_type: FuelType,
    ) -> PerformanceResult:
        self._check(condition)
        return super().power_for_speed(vessel, condition, speed_through_water_mps, fuel_type)


def _suite(model: type[SimplePerformance]) -> TestSimplePerformance:
    class Broken(TestSimplePerformance):
        def make_model(self) -> PerformanceModel:
            return model(_DESIGN_SPEED_MPS)

    return Broken()


@pytest.mark.req("S0b-R09")
def test_suite_fails_when_validation_skipped() -> None:
    """A model that coerces bad input fails the length, NaN, negative and weather checks."""
    suite = _suite(_NoValidation)
    for check in (
        suite.test_mismatched_lengths_rejected,
        suite.test_nan_speed_rejected,
        suite.test_negative_power_rejected,
        suite.test_non_ok_weather_rejected,
    ):
        with pytest.raises(AssertionError):
            check()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_negative_fuel() -> None:
    """Negative fuel is rejected."""
    with pytest.raises(AssertionError):
        _suite(_NegativeFuel).test_outputs_finite_non_negative()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_missing_consumer() -> None:
    """A result without every consumer is rejected."""
    with pytest.raises(AssertionError):
        _suite(_MissingConsumer).test_fuel_reported_non_negative_and_point_independent()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_coupled_points() -> None:
    """A model whose result for a point depends on the other points is rejected."""
    with pytest.raises(AssertionError):
        _suite(_Coupled).test_fuel_reported_non_negative_and_point_independent()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_fuel_rising_with_calorific_value() -> None:
    """A model whose fuel mass rises with the calorific value fails the monotonic property."""
    with pytest.raises(AssertionError):
        _suite(_InvertedLcv).test_fuel_mass_does_not_rise_with_calorific_value()


@pytest.mark.req("S0b-R09")
def test_suite_fails_when_the_model_ignores_the_fuel_type() -> None:
    """Equal fuel mass for fuels of different calorific value fails the strict LCV property."""
    with pytest.raises(AssertionError):
        _suite(_IgnoresFuel).test_fuel_mass_does_not_rise_with_calorific_value()


@pytest.mark.req("S0b-R09")
def test_suite_fails_when_fuel_changes_speed() -> None:
    """A model whose speed depends on the fuel type fails the independence check."""
    with pytest.raises(AssertionError):
        _suite(_FuelChangesSpeed).test_speed_and_power_do_not_depend_on_fuel()


@pytest.mark.req("S0b-R09")
def test_suite_fails_when_fuel_type_not_validated() -> None:
    """A model that accepts any fuel type is rejected."""
    with pytest.raises(AssertionError):
        _suite(_NoFuelValidation).test_invalid_fuel_type_rejected()


@pytest.mark.req("S0b-R09")
def test_suite_fails_on_speed_falling_with_power() -> None:
    """A model whose speed falls as power rises is rejected."""
    with pytest.raises(AssertionError):
        _suite(_NonMonotone).test_speed_rises_with_power()


@pytest.mark.req("S0b-R09")
def test_suite_fails_when_stale_weather_rejected() -> None:
    """A model that refuses STALE weather fails the D-063 check."""
    with pytest.raises(AssertionError):
        _suite(_RejectsStale).test_stale_weather_accepted()


@pytest.mark.req("S0b-R08")
def test_unreachable_and_zero_power() -> None:
    """Power above P(2 * design) raises (no silent clamp); zero power gives speed exactly 0."""
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    with pytest.raises(InvalidInputError, match="unreachable"):
        model.speed_for_power(vessel, make_condition(2), np.array([1e6, 1e12]), _FUEL)
    r = model.speed_for_power(vessel, make_condition(1), np.array([0.0]), _FUEL)
    assert r.speed_through_water_mps[0] == 0.0


@pytest.mark.req("S0b-R08")
def test_sfoc_clamped_below_first_point_and_above_mcr() -> None:
    """Below the first curve point and above MCR the SFOC end values apply (MGO: no LCV scale)."""
    model, vessel = SimplePerformance(_DESIGN_SPEED_MPS), make_vessel()
    curve = vessel.sfoc_curve_kg_per_j[Consumer.MAIN_ENGINE]
    first = curve[0][1]
    low = model.speed_for_power(vessel, make_condition(1), np.array([0.05 * _MCR_W]), FuelType.MGO)
    assert low.fuel_rate_kgps[Consumer.MAIN_ENGINE][0] == pytest.approx(first * 0.05 * _MCR_W)
    last = curve[-1][1]
    high = model.speed_for_power(vessel, make_condition(1), np.array([1.2 * _MCR_W]), FuelType.MGO)
    assert high.fuel_rate_kgps[Consumer.MAIN_ENGINE][0] == pytest.approx(last * 1.2 * _MCR_W)
