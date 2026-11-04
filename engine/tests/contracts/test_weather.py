"""Weather contract unit tests (S0b-R07)."""

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    InvalidPositionError,
    MissingRequiredVariableError,
)
from nautical_deliverance.domain.contracts.time import to_datetime64
from nautical_deliverance.domain.contracts.weather import (
    GROUP_OF,
    REQUIRED,
    REQUIRED_GROUPS,
    SampleQuality,
    WeatherGroup,
    WeatherSample,
    WeatherVariable,
    has_values,
    interpolate_direction_deg,
    validate_query,
)
from tests.contracts.weather_fixtures import GRID, make_uniform

_T = np.array(["2026-11-04T00:00:00"], dtype="datetime64[s]")
_ONE = np.array([1.0])
_NAN = np.array([np.nan])
_OPTIONAL = frozenset(WeatherVariable) - REQUIRED


def _code(q: SampleQuality = SampleQuality.OK) -> np.ndarray:
    return np.array([q], dtype=np.uint8)


def _sample(  # noqa: PLR0913, PLR0917 - one keyword per field, to break each in turn
    quality: SampleQuality = SampleQuality.OK,
    values: dict[Any, Any] | None = None,
    quality_by_group: dict[Any, Any] | None = None,
    source: dict[Any, Any] | None = None,
    run_time: dict[Any, Any] | None = None,
    unavailable: frozenset[Any] | None = None,
) -> WeatherSample:
    """Return a valid one-point sample with the mandatory groups; keywords override parts."""
    val = dict.fromkeys(REQUIRED, _NAN if quality in (1, 2) else _ONE)
    groups = REQUIRED_GROUPS
    return WeatherSample(
        val if values is None else values,
        dict.fromkeys(groups, _code(quality)) if quality_by_group is None else quality_by_group,
        dict.fromkeys(groups, "s") if source is None else source,
        dict.fromkeys(groups, _T) if run_time is None else run_time,
        _OPTIONAL if unavailable is None else unavailable,
    )


@pytest.mark.req("S0b-R07")
def test_required_set_matches_decision() -> None:
    """13 required variables in three mandatory groups; every variable has a group."""
    assert len(REQUIRED) == 13  # noqa: PLR2004
    assert WeatherVariable.VISIBILITY_M not in REQUIRED
    assert GROUP_OF.keys() == set(WeatherVariable)
    assert {WeatherGroup.WIND, WeatherGroup.WAVES, WeatherGroup.CURRENT} == REQUIRED_GROUPS
    assert len(_OPTIONAL) == len({GROUP_OF[v] for v in _OPTIONAL})  # one group per optional


@pytest.mark.req("S0b-R07")
def test_quality_codes_are_readable_ints() -> None:
    """Qualities are small integer codes with names, and `SampleQuality(code)` works."""
    assert [q.value for q in SampleQuality] == [0, 1, 2, 3]
    assert SampleQuality(2) is SampleQuality.OUT_OF_TIME_RANGE
    assert list(has_values(np.array([0, 1, 2, 3], dtype=np.uint8))) == [True, False, False, True]


@pytest.mark.req("S0b-R07")
def test_sample_accepts_ok_stale_and_missing() -> None:
    """OK and STALE points carry values; coverage and time-range gaps are NaN."""
    ok = _sample()
    assert len(ok) == 1
    _sample(SampleQuality.STALE)
    _sample(SampleQuality.OUT_OF_COVERAGE)
    _sample(SampleQuality.OUT_OF_TIME_RANGE)
    assert ok.quality[WeatherGroup.WIND].dtype == np.uint8


@pytest.mark.req("S0b-R07")
def test_stale_keeps_values_and_missing_is_nan() -> None:
    """The NaN rule: STALE with NaN, and OUT_OF_COVERAGE without NaN, are both rejected."""
    nan = dict.fromkeys(REQUIRED, _NAN)
    with pytest.raises(InvalidInputError):
        _sample(SampleQuality.STALE, values=nan)
    with pytest.raises(InvalidInputError):
        _sample(SampleQuality.OUT_OF_COVERAGE, values=dict.fromkeys(REQUIRED, _ONE))
    with pytest.raises(InvalidInputError):
        _sample(SampleQuality.OUT_OF_TIME_RANGE, values=dict.fromkeys(REQUIRED, _ONE))


@pytest.mark.req("S0b-R07")
def test_nan_rule_applies_per_group() -> None:
    """One group out of coverage needs NaN only in its own variables."""
    quality = {g: _code() for g in REQUIRED_GROUPS}
    quality[WeatherGroup.CURRENT] = _code(SampleQuality.OUT_OF_COVERAGE)
    values = {v: (_NAN if GROUP_OF[v] is WeatherGroup.CURRENT else _ONE) for v in REQUIRED}
    s = _sample(values=values, quality_by_group=quality)
    assert np.isnan(s.values[WeatherVariable.CURRENT_U_MPS]).all()
    assert not np.isnan(s.values[WeatherVariable.WIND_U_MPS]).any()
    bad = dict.fromkeys(REQUIRED, _ONE)
    with pytest.raises(InvalidInputError):
        _sample(values=bad, quality_by_group=quality)


@pytest.mark.req("S0b-R07")
def test_sample_rejects_missing_and_vanished_variables() -> None:
    """Missing required variables and optional ones that vanish silently are rejected."""
    with pytest.raises(MissingRequiredVariableError):
        _sample(values={WeatherVariable.WIND_U_MPS: _ONE})
    with pytest.raises(MissingRequiredVariableError):
        _sample(unavailable=_OPTIONAL | {WeatherVariable.WIND_U_MPS})
    with pytest.raises(InvalidInputError, match="neither present nor"):
        _sample(unavailable=_OPTIONAL - {WeatherVariable.VISIBILITY_M})
    opt = WeatherVariable.VISIBILITY_M
    both = {**dict.fromkeys(REQUIRED, _ONE), opt: _ONE}
    with pytest.raises(InvalidInputError):
        _sample(values=both, unavailable=_OPTIONAL)


@pytest.mark.req("S0b-R07")
def test_optional_variable_needs_its_own_group() -> None:
    """A delivered optional variable adds its group to quality, source and run time."""
    opt = WeatherVariable.VISIBILITY_M
    group = WeatherGroup.VISIBILITY
    values = {**dict.fromkeys(REQUIRED, _ONE), opt: _ONE}
    quality = {g: _code() for g in REQUIRED_GROUPS}
    with pytest.raises(InvalidInputError):
        _sample(values=values, unavailable=_OPTIONAL - {opt}, quality_by_group=quality)
    ok = _sample(
        values=values,
        unavailable=_OPTIONAL - {opt},
        quality_by_group={**quality, group: _code()},
        source={**dict.fromkeys(REQUIRED_GROUPS, "s"), group: "vis"},
        run_time={**dict.fromkeys(REQUIRED_GROUPS, _T), group: _T},
    )
    assert ok.source[group] == "vis"


@pytest.mark.req("S0b-R07")
def test_sample_rejects_bad_arrays_and_keys() -> None:
    """dtype, dimension, length, key type, group set and source problems are rejected."""
    ok = {g: _code() for g in REQUIRED_GROUPS}
    cases: list[dict[str, Any]] = [
        {"values": dict.fromkeys(REQUIRED, np.array([1.0], dtype=np.float32))},
        {"values": dict.fromkeys(REQUIRED, np.ones((1, 1)))},
        {"values": dict.fromkeys(REQUIRED, np.array([1.0, 2.0]))},
        {"values": dict.fromkeys(REQUIRED, np.array([np.inf]))},
        {"values": {**dict.fromkeys(REQUIRED, _ONE), "bogus": _ONE}},
        {"quality_by_group": {g: np.array(["ok"]) for g in REQUIRED_GROUPS}},
        {"quality_by_group": {g: np.array([9], dtype=np.uint8) for g in REQUIRED_GROUPS}},
        {"quality_by_group": {g: np.array([0], dtype=np.int64) for g in REQUIRED_GROUPS}},
        {"quality_by_group": {WeatherGroup.WIND: _code()}},
        {"quality_by_group": {**ok, WeatherGroup.SEA_ICE: _code()}},
        {"quality_by_group": {"wind": _code(), "waves": _code(), "current": _code()}},
        {"run_time": dict.fromkeys(REQUIRED_GROUPS, np.array(["2026-11-04"], dtype="M8[D]"))},
        {"run_time": dict.fromkeys(REQUIRED_GROUPS, np.array(["NaT"], dtype="datetime64[s]"))},
        {"source": dict.fromkeys(REQUIRED_GROUPS, "")},
        {"source": dict.fromkeys(REQUIRED_GROUPS, "  ")},
        {"source": dict.fromkeys(REQUIRED_GROUPS, 3)},
        {"unavailable": _OPTIONAL | {"bogus"}},
    ]
    for case in cases:
        with pytest.raises(InvalidInputError):
            _sample(**case)


@pytest.mark.req("S0b-R07")
def test_run_time_may_be_nat_only_without_values() -> None:
    """NaT run time is fine at missing points, and wrong at STALE points that carry values."""
    nat = np.array(["NaT"], dtype="datetime64[s]")
    _sample(SampleQuality.OUT_OF_COVERAGE, run_time=dict.fromkeys(REQUIRED_GROUPS, nat))
    with pytest.raises(InvalidInputError):
        _sample(SampleQuality.STALE, run_time=dict.fromkeys(REQUIRED_GROUPS, nat))


@pytest.mark.req("S0b-R07")
def test_validate_query_rejects_bad_input() -> None:
    """Dimension, length, finiteness, dtype and NaT problems raise InvalidInputError."""
    validate_query(_ONE, _ONE, _T)
    bad_time = np.array(["2026-11-04"], dtype="datetime64[D]")
    for args in (
        (np.ones((1, 1)), _ONE, _T),
        (_ONE, np.ones(2), _T),
        (np.array([np.nan]), _ONE, _T),
        (_ONE, _ONE, bad_time),
        (_ONE, _ONE, np.array(["NaT"], dtype="datetime64[s]")),
    ):
        with pytest.raises(InvalidInputError):
            validate_query(*args)


@pytest.mark.req("S0b-R07")
def test_validate_query_latitude_range_and_longitude_wrapping() -> None:
    """|lat| > 90 is an InvalidPositionError; any finite longitude is accepted (wrapped)."""
    validate_query(np.array([90.0, -90.0]), np.array([1e6, -540.0]), np.repeat(_T, 2))
    for lat in (90.0000001, -91.0):
        with pytest.raises(InvalidPositionError):
            validate_query(np.array([lat]), _ONE, _T)


@pytest.mark.req("S0b-R07")
def test_interpolate_direction_wraps_and_stays_in_range() -> None:
    """350 and 10 average to 0; the result is always in [0, 360)."""
    w = np.array([[0.5, 0.5], [0.5, 0.5]])
    d = np.array([[350.0, 350.0 + 1e-13], [10.0, 10.0 - 1e-13]])
    out = interpolate_direction_deg(w, d)
    assert np.all((out >= 0.0) & (out < 360.0))  # noqa: PLR2004
    assert abs((out[0] + 180.0) % 360.0 - 180.0) < 1e-9  # noqa: PLR2004


@pytest.mark.req("S0b-R07")
def test_sample_is_immutable_after_construction() -> None:
    """Arrays and mappings are read-only copies; the caller's arrays are not aliased."""
    src = {v: np.array([1.0]) for v in REQUIRED}
    quality = {g: _code() for g in REQUIRED_GROUPS}
    s = _sample(values=src, quality_by_group=quality)
    wind = WeatherGroup.WIND
    with pytest.raises(ValueError, match="read-only"):
        s.values[WeatherVariable.WIND_U_MPS][0] = np.nan
    with pytest.raises(ValueError, match="read-only"):
        s.quality[wind][0] = 3
    with pytest.raises(ValueError, match="read-only"):
        s.run_time[wind][0] = np.datetime64("NaT", "s")
    for mapping in (s.values, s.quality, s.source, s.run_time):
        with pytest.raises(TypeError):
            mapping[next(iter(mapping))] = None  # type: ignore[index]
    src[WeatherVariable.WIND_U_MPS][0] = 5.0
    quality[wind][0] = 3
    assert s.values[WeatherVariable.WIND_U_MPS][0] == 1.0
    assert s.quality[wind][0] == 0


@pytest.mark.req("S0b-R07")
def test_sample_equality_is_identity_and_never_raises() -> None:
    """`==` on array-bearing samples compares identity instead of raising on arrays."""
    a, b = _sample(), _sample()
    assert a == a  # noqa: PLR0124 - identity is the documented policy
    assert a != b
    assert len({a, b}) == 2  # noqa: PLR2004


@pytest.mark.req("S0b-R07")
def test_validate_query_rejects_non_arrays() -> None:
    """Lists and scalars raise InvalidInputError rather than AttributeError."""
    with pytest.raises(InvalidInputError):
        validate_query([1.0], _ONE, _T)  # type: ignore[arg-type]
    with pytest.raises(InvalidInputError):
        validate_query(_ONE, _ONE, "2026")  # type: ignore[arg-type]


@pytest.mark.req("S0b-R07")
def test_out_of_coverage_takes_precedence_over_out_of_time() -> None:
    """A point outside both coverage and time range is OUT_OF_COVERAGE in every group."""
    late = to_datetime64(datetime(2030, 1, 1, tzinfo=UTC))
    s = make_uniform("uniform").sample(
        np.array([GRID.lat_max_deg + 10]),
        np.array([0.0]),
        np.array([late], dtype="datetime64[s]"),
    )
    assert all(list(q) == [SampleQuality.OUT_OF_COVERAGE] for q in s.quality.values())
