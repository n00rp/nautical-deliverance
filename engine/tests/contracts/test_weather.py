"""Weather contract unit tests (S0b-R07)."""

import numpy as np
import pytest

from nautical_deliverance.domain.contracts.errors import (
    InvalidInputError,
    MissingRequiredVariableError,
)
from nautical_deliverance.domain.contracts.weather import (
    REQUIRED,
    SampleQuality,
    WeatherSample,
    WeatherVariable,
    interpolate_direction_deg,
    validate_query,
)

_T = np.array(["2026-11-04T00:00:00"], dtype="datetime64[s]")
_ONE = np.array([1.0])


def _sample(
    values: dict[WeatherVariable, np.ndarray] | None = None,
    quality: str = "ok",
    unavailable: frozenset[WeatherVariable] = frozenset(),
) -> WeatherSample:
    vals = dict.fromkeys(REQUIRED, _ONE) if values is None else values
    return WeatherSample(vals, np.array([quality]), "s", _T, unavailable)


@pytest.mark.req("S0b-R07")
def test_required_set_matches_decision() -> None:
    """13 required variables; the 3 optional ones are not required."""
    assert len(REQUIRED) == 13  # noqa: PLR2004
    assert WeatherVariable.VISIBILITY_M not in REQUIRED


@pytest.mark.req("S0b-R07")
def test_sample_accepts_valid_and_not_ok_with_nan() -> None:
    """A valid sample constructs; non-OK points must be NaN."""
    _sample()
    nan = dict.fromkeys(REQUIRED, np.array([np.nan]))
    _sample(nan, SampleQuality.STALE.value)


@pytest.mark.req("S0b-R07")
def test_sample_rejects_inconsistent() -> None:
    """NaN/quality mismatch, length mismatch and missing required variables are rejected."""
    with pytest.raises(InvalidInputError):
        _sample(quality=SampleQuality.STALE.value)
    with pytest.raises(InvalidInputError):
        _sample(dict.fromkeys(REQUIRED, np.array([1.0, 2.0])))
    with pytest.raises(MissingRequiredVariableError):
        _sample({WeatherVariable.WIND_U_MPS: _ONE})
    with pytest.raises(MissingRequiredVariableError):
        _sample(unavailable=frozenset({WeatherVariable.WIND_U_MPS}))


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
def test_interpolate_direction_wraps_and_stays_in_range() -> None:
    """350 and 10 average to 0; the result is always in [0, 360)."""
    w = np.array([[0.5, 0.5], [0.5, 0.5]])
    d = np.array([[350.0, 350.0 + 1e-13], [10.0, 10.0 - 1e-13]])
    out = interpolate_direction_deg(w, d)
    assert np.all((out >= 0.0) & (out < 360.0))  # noqa: PLR2004
    assert abs((out[0] + 180.0) % 360.0 - 180.0) < 1e-9  # noqa: PLR2004


@pytest.mark.req("S0b-R07")
def test_sample_is_immutable_after_construction() -> None:
    """Arrays and mapping are read-only copies; the caller's arrays are not aliased."""
    src = {v: np.array([1.0]) for v in REQUIRED}
    s = WeatherSample(src, np.array(["ok"]), "s", _T.copy(), frozenset())
    with pytest.raises(ValueError, match="read-only"):
        s.values[WeatherVariable.WIND_U_MPS][0] = np.nan
    with pytest.raises(ValueError, match="read-only"):
        s.quality[0] = "stale"
    with pytest.raises(ValueError, match="read-only"):
        s.run_time[0] = np.datetime64("NaT", "s")
    with pytest.raises(TypeError):
        s.values[WeatherVariable.WIND_U_MPS] = _ONE  # type: ignore[index]
    src[WeatherVariable.WIND_U_MPS][0] = 5.0
    assert s.values[WeatherVariable.WIND_U_MPS][0] == 1.0


@pytest.mark.req("S0b-R07")
def test_sample_rejects_bad_quality_run_time_and_overlap() -> None:
    """Unknown quality, NaT run time at an OK point and present+unavailable are rejected."""
    with pytest.raises(InvalidInputError):
        _sample(quality="bogus")
    with pytest.raises(InvalidInputError):
        WeatherSample(
            dict.fromkeys(REQUIRED, _ONE),
            np.array(["ok"]),
            "s",
            np.array(["NaT"], dtype="datetime64[s]"),
            frozenset(),
        )
    opt = WeatherVariable.VISIBILITY_M
    with pytest.raises(InvalidInputError):
        _sample({**dict.fromkeys(REQUIRED, _ONE), opt: _ONE}, unavailable=frozenset({opt}))


@pytest.mark.req("S0b-R07")
def test_validate_query_rejects_non_arrays() -> None:
    """Lists and scalars raise InvalidInputError rather than AttributeError."""
    with pytest.raises(InvalidInputError):
        validate_query([1.0], _ONE, _T)  # type: ignore[arg-type]
    with pytest.raises(InvalidInputError):
        validate_query(_ONE, _ONE, "2026")  # type: ignore[arg-type]


@pytest.mark.req("S0b-R07")
def test_out_of_coverage_takes_precedence_over_out_of_time() -> None:
    """A point outside both coverage and time range is OUT_OF_COVERAGE."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from nautical_deliverance.domain.contracts.time import to_datetime64  # noqa: PLC0415
    from tests.contracts.test_weather_conformance import GRID, _make  # noqa: PLC0415

    late = to_datetime64(datetime(2030, 1, 1, tzinfo=UTC))
    s = _make("uniform").sample(
        np.array([GRID.lat_max_deg + 10]),
        np.array([0.0]),
        np.array([late], dtype="datetime64[s]"),
    )
    assert list(s.quality) == [SampleQuality.OUT_OF_COVERAGE.value]
