# S0b Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Typed, tested in-engine contracts between C1 (weather), C2 (performance) and C3 (routing), with reusable conformance suites and analytical reference implementations.

**Architecture:** Pure domain code under `engine/src/nautical_deliverance/domain/contracts/` (frozen dataclasses + `typing.Protocol`) using only stdlib, NumPy and GeographicLib. Reusable conformance suites in `engine/tests/contracts/` are parametrized by an implementation factory; `domain/reference/` holds analytical implementations that prove the suites and later serve D-024 level-1 tests.

**Tech Stack:** Python 3.14, NumPy, geographiclib, pytest, Hypothesis, import-linter (all existing except geographiclib).

**Spec:** [docs/superpowers/specs/2026-11-04-s0b-contracts-design.md](../specs/2026-11-04-s0b-contracts-design.md) (parent: [program spec](../specs/2026-11-04-nautical-deliverance-program-design.md)).

## Global Constraints

- English only. mypy `--strict`, Ruff, vulture, import-linter, jscpd, traceability — all S0 gates must stay green (S0b-R12).
- Coverage ≥ 90 % line and ≥ 90 % branch, checked separately by `tools/check_coverage.py` (D-035).
- Requirement tests tagged `@pytest.mark.req("S0b-Rnn")` (double quotes).
- SI internally; every float / float-array / float-mapping dataclass field ends with a suffix from `UNIT_SUFFIXES` = `_m`, `_s`, `_mps`, `_kg`, `_kgps`, `_w`, `_kg_per_j`, `_deg`, `_from_deg`, `_ratio`, `_pa` (D-050). Identifiers are `str`.
- Instants: aware UTC `datetime`; arrays `datetime64[s]` in UTC; naive → `NaiveDatetimeError` (D-049, D-058).
- Positions WGS84; longitude normalized to [−180, 180); latitude [−90, 90] (D-048).
- Arrays `float64`, 1-D, equal length per call.
- `domain.contracts` and `domain.reference` import only stdlib, `numpy`, `geographiclib` (S0b-R11).
- All dataclasses `frozen=True, slots=True`; Protocols are not `runtime_checkable` unless a test needs it.
- New dependency `geographiclib` pinned exactly in `engine/pyproject.toml` / `uv.lock`; release ≥ 14 days old.
- Work on branch `feat/s0b-contracts`; commit messages Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Arrays of different lengths passed to `sample()` / performance calls** → `InvalidInputError`, never broadcasting silently. Test in Tasks 3 and 4.
2. **NaN or ±inf in input coordinates/speeds/powers** → `InvalidInputError`. Test in Tasks 2 and 4.
3. **Query exactly on the coverage boundary or exactly at the last forecast step** → treated as inside (OK), one step beyond → flagged. Test in Task 3.
4. **Latitude ±90 (poles) for both leg geometries** → finite distance and no exception for both geometries (GeographicLib defines a rhumb line to a pole with finite length); course at the pole itself is reported as GeographicLib returns it. Test in Task 2.
5. **Zero-length leg (same start and end)** → distance 0, course defined as 0.0, `point_along` returns the start. Test in Task 2.

## File Structure

```
engine/src/nautical_deliverance/domain/contracts/
  __init__.py  units.py  time.py  errors.py  geo.py  weather.py  performance.py  route.py
engine/src/nautical_deliverance/domain/reference/
  __init__.py  uniform_weather.py  simple_performance.py
engine/tests/contracts/
  __init__.py
  conformance_weather.py        reusable suite: weather_conformance(factory)
  conformance_performance.py    reusable suite: performance_conformance(factory)
  test_units.py  test_time.py  test_errors.py  test_suffixes.py  test_geo.py
  test_weather_conformance.py   test_performance_conformance.py  test_route.py
engine/pyproject.toml           + geographiclib, + import-linter contract 3
```

---

### Task 1: Units, time, errors and the suffix gate

**Files:** Create `contracts/__init__.py`, `units.py`, `time.py`, `errors.py`; tests `test_units.py`, `test_time.py`, `test_errors.py`, `test_suffixes.py`.

**Interfaces — Produces:**
- `errors.py`: `class ContractError(Exception)`; `class InvalidInputError(ContractError)`; `class NaiveDatetimeError(InvalidInputError)`; `class InvalidPositionError(InvalidInputError)`; `class MissingRequiredVariableError(ContractError)` with attribute `variables: frozenset[str]`; `class DataBlockedError(ContractError)` with attribute `reasons: tuple[str, ...]`.
- `units.py`: `UNIT_SUFFIXES: Final[tuple[str, ...]]` (exact list above, longest-match order so `_from_deg` is checked before `_deg`); `knots_to_mps(x)`, `mps_to_knots(x)`, `nm_to_m(x)`, `m_to_nm(x)`, `tonnes_to_kg(x)`, `kg_to_tonnes(x)`, `kw_to_w(x)`, `w_to_kw(x)`, `g_per_kwh_to_kg_per_j(x)`, `kg_per_j_to_g_per_kwh(x)`, `hours_to_s(x)`, `s_to_hours(x)` — each `(float | NDArray[float64]) -> same`. Constants: `M_PER_NM = 1852.0`, `MPS_PER_KNOT = 1852.0 / 3600.0`, `KG_PER_J_PER_G_PER_KWH = 1.0 / 3.6e9`.
- `time.py`: `to_datetime64(dt: datetime) -> np.datetime64`; `from_datetime64(t: np.datetime64) -> datetime`; `to_datetime64_array(dts: Sequence[datetime]) -> NDArray[np.datetime64]`; `require_utc(dt: datetime) -> datetime` (raises `NaiveDatetimeError` if `tzinfo is None`, else returns `dt.astimezone(UTC)`).
- `test_suffixes.py` helper used by later tasks: `contract_dataclasses() -> list[type]` discovering every dataclass in `nautical_deliverance.domain.contracts.*`; `unsuffixed_numeric_fields(cls) -> list[str]`.

- [ ] **Step 1: Write failing tests**
  - `test_units.py` (`req("S0b-R02")`): `test_exact_constants` (`knots_to_mps(1.0) == 1852/3600`, `nm_to_m(1.0) == 1852.0`, `g_per_kwh_to_kg_per_j(3.6e9) == 1.0`); `test_round_trips` (Hypothesis, `max_examples=1000`, finite floats in [−1e9, 1e9], each pair round-trips within `rel=1e-12`, abs 1e-12 near 0); `test_array_inputs_preserve_shape`.
  - `test_time.py` (`req("S0b-R03")`): `test_naive_rejected` (each helper raises `NaiveDatetimeError`); `test_non_utc_converted` (`datetime(2026,1,1,12,tzinfo=timezone(timedelta(hours=2)))` → `2026-01-01T10:00:00`); `test_round_trip` (Hypothesis aware datetimes, second precision, 1000 examples).
  - `test_errors.py`: hierarchy assertions (`issubclass` chain), `MissingRequiredVariableError(frozenset({"wind_u_mps"})).variables`, `DataBlockedError(("stale",)).reasons`.
  - `test_suffixes.py` (`req("S0b-R01")`): `test_all_contract_fields_suffixed` (`unsuffixed_numeric_fields(cls) == []` for every discovered class — trivially true now, grows with later tasks); `test_gate_rejects_unsuffixed_fixture` (a local `@dataclass class Bad: speed: float` → `["speed"]`); `test_from_deg_not_confused_with_deg`.
- [ ] **Step 2: Run** `uv run pytest tests/contracts -v` (from `engine/`) → FAIL (import errors).
- [ ] **Step 3: Implement** the four modules. Numeric detection in the helper: annotation is `float`, `NDArray[np.float64]`, `npt.NDArray[np.float64]`, or `Mapping[..., float]` (resolve with `typing.get_type_hints`).
- [ ] **Step 4: Run** → PASS; full engine gate list + `tools/check_coverage.py` → green.
- [ ] **Step 5: Commit** `feat(engine): add contract units, time and error types`.

---

### Task 2: Geometry and the dependency rule

**Files:** Create `contracts/geo.py`, `tests/contracts/test_geo.py`; modify `engine/pyproject.toml` (+ `geographiclib==<pinned>`, + import-linter contract 3), `engine/tests/unit/test_layers.py` (+ violation fixture for contract 3).

**Interfaces — Consumes:** `InvalidPositionError`, `InvalidInputError` (Task 1). **Produces:**
- `@dataclass(frozen=True, slots=True) class Position: lat_deg: float; lon_deg: float` with `__post_init__` validating finite, latitude in [−90, 90], normalizing longitude to [−180, 180) via `object.__setattr__`.
- `class LegGeometry(StrEnum): RHUMB_LINE = "rhumb_line"; GREAT_CIRCLE = "great_circle"`.
- `distance_m(a: Position, b: Position, geometry: LegGeometry) -> float`; `initial_course_deg(a, b, geometry) -> float` in [0, 360); `point_along(a, b, geometry, fraction: float) -> Position` (`fraction` in [0, 1] else `InvalidInputError`). GeographicLib `Geodesic.WGS84.Inverse/Line` and `Rhumb.WGS84.Inverse/Line`.
- import-linter contract 3 (forbidden): `nautical_deliverance.domain.contracts` and `nautical_deliverance.domain.reference` ✗ every installed top-level package except `numpy` and `geographiclib` — implement as `forbidden_modules` listing `fastapi`, `starlette`, `pydantic`, `pydantic_settings`, `sqlalchemy`, `psycopg`, `alembic`, `jwt`, `xarray`, `nautical_deliverance.api`, `nautical_deliverance.persistence`.

- [ ] **Step 1: Write failing tests** in `test_geo.py`:
  - `req("S0b-R04")`: `test_longitude_normalized` (Hypothesis 1000 finite lons in [−1e4, 1e4] → result in [−180, 180) and congruent mod 360 within 1e-9); `test_invalid_latitude_rejected` (91, −90.0001, nan, inf); `test_nan_longitude_rejected`.
  - `req("S0b-R05")`: `test_geodesic_matches_reference_cases` — ≥ 10 cases from GeographicLib's `GeodTest` dataset (cite the dataset URL and line numbers in a module docstring; embed the numbers), distance within 1e-3 m, azimuth within 1e-9°; `test_rhumb_matches_reference_cases` — ≥ 10 cases from GeographicLib's rhumb test values (cite source), same tolerances.
  - `req("S0b-R06")`: `test_antimeridian_leg_short` — for both geometries, `distance_m(Position(10, 179), Position(10, -179), g)` equals `distance_m(Position(10, -1), Position(10, 1), g)` within 1e-3 m; `test_antimeridian_midpoint` — `point_along(..., 0.5).lon_deg == -180.0` within 1e-9 (normalized form of ±180).
  - Review Focus: `test_pole_legs_finite` (both geometries, start at 60° N → end at 90° N), `test_zero_length_leg` (distance 0, course 0.0, `point_along` returns start for 0, 0.5, 1).
  - `test_layers.py` (`req("S0b-R11")`): add contract 3 to the parametrized violation list (fixture: `import pydantic` in `domain/contracts/__init__.py`) — expect "BROKEN" for that contract; clean tree "3 kept, 0 broken".
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `geo.py`; add geographiclib with `uv add geographiclib==<version>` (record version + release date in `docs/versions.md`); add contract 3. Note in Task 2's report whether the "1 broken" assertion from S0 (ledger minor) needed adjustment.
- [ ] **Step 4: Run** → PASS; full gates; license check passes (`uv run pip-licenses --format=json | python tools/check_licenses.py ...` as in ci.yml).
- [ ] **Step 5: Commit** `feat(engine): add geodetic contract helpers`.

---

### Task 3: Weather contract, conformance suite, uniform reference

**Files:** Create `contracts/weather.py`, `reference/__init__.py`, `reference/uniform_weather.py`, `tests/contracts/conformance_weather.py`, `tests/contracts/test_weather_conformance.py`.

**Interfaces — Consumes:** Task 1 errors/time, Task 2 `Position`. **Produces:**
- `class WeatherVariable(StrEnum)` members with value = field name and a module-level `REQUIRED: frozenset[WeatherVariable]`:
  required — `WIND_U_MPS="wind_u_mps"`, `WIND_V_MPS="wind_v_mps"`, `TOTAL_SEA_HEIGHT_M`, `TOTAL_SEA_PERIOD_S`, `TOTAL_SEA_DIRECTION_FROM_DEG`, `WIND_SEA_HEIGHT_M`, `WIND_SEA_PERIOD_S`, `WIND_SEA_DIRECTION_FROM_DEG`, `SWELL_HEIGHT_M`, `SWELL_PERIOD_S`, `SWELL_DIRECTION_FROM_DEG`, `CURRENT_U_MPS`, `CURRENT_V_MPS`; optional — `SEA_ICE_CONCENTRATION_RATIO`, `VISIBILITY_M`, `MEAN_SEA_LEVEL_PRESSURE_PA` (values = lower-case names).
- `class SampleQuality(StrEnum): OK="ok"; OUT_OF_COVERAGE="out_of_coverage"; OUT_OF_TIME_RANGE="out_of_time_range"; STALE="stale"`.
- `@dataclass(frozen=True, slots=True) class WeatherSample: values: Mapping[WeatherVariable, NDArray[np.float64]]; quality: NDArray[np.str_]` (SampleQuality values); `source: str; run_time: NDArray[np.datetime64]; unavailable: frozenset[WeatherVariable]` with `__post_init__` checking equal lengths, NaN exactly where quality ≠ OK, `unavailable ∩ REQUIRED == ∅` else `MissingRequiredVariableError`. (`values` is a mapping keyed by variables whose names carry the unit suffix — the suffix test must accept this: document that the mapping keys carry the suffix and add this case to the S0b-R01 helper.)
- `class WeatherProvider(Protocol)`: `def sample(self, lat_deg: NDArray[np.float64], lon_deg: NDArray[np.float64], valid_time: NDArray[np.datetime64]) -> WeatherSample`; `def sample_point(self, position: Position, valid_time: datetime) -> WeatherSample`.
- `validate_query(lat_deg, lon_deg, valid_time) -> None` (equal length, 1-D, finite coords, `datetime64[s]`) — raises `InvalidInputError`.
- `interpolate_direction_deg(weights: NDArray, directions_from_deg: NDArray) -> NDArray` (unit-vector average, result in [0, 360)).
- `reference/uniform_weather.py`: `class UniformWeather` — constructor `(values: Mapping[WeatherVariable, float], lat_range_deg: tuple[float, float], lon_range_deg: tuple[float, float], time_range: tuple[datetime, datetime], run_time: datetime, grid_step_deg: float, time_step: timedelta, field: Literal["uniform", "linear"] = "uniform")` — a gridded field (uniform values, or linear in lat/lon/time for the interpolation checks) sampled with the contract's interpolation rules; outside → NaN + flag.
- `conformance_weather.py`: `def weather_conformance(factory: Callable[[], WeatherProvider], grid: GridDescription) -> list[Callable[[], None]]` — or idiomatic pytest: a mixin class `WeatherProviderConformance` with an abstract `make_provider()` fixture; concrete test classes subclass it. Use the mixin pattern.

- [ ] **Step 1: Write the suite** (`WeatherProviderConformance`, every test `req("S0b-R07")`): `test_lengths_preserved`; `test_mismatched_lengths_rejected`; `test_nan_coordinate_rejected`; `test_required_present`; `test_no_extrapolation_space` (one grid step beyond each edge → NaN + `OUT_OF_COVERAGE`); `test_no_extrapolation_time` (`OUT_OF_TIME_RANGE`); `test_boundary_inclusive` (exactly on edges and last step → OK); `test_exact_at_nodes`; `test_linear_field_exact_between_nodes` (linear provider); `test_direction_unit_vector` (nodes 350° and 10° → midpoint 0° within 1e-9, not 180°); `test_source_and_run_time_set_for_ok_points`; `test_sample_point_matches_vectorized`; `test_antimeridian_query` (grid spanning 170°E–170°W queried at 179.5° and −179.5°).
- [ ] **Step 2: Write** `test_weather_conformance.py`: `class TestUniformWeather(WeatherProviderConformance)` and, `req("S0b-R09")`, `test_suite_fails_on_extrapolating_provider` and `test_suite_fails_on_naive_direction_average` — run the suite's test methods against a deliberately broken subclass (overrides extrapolation / averages degrees arithmetically) and assert at least the targeted test raises `AssertionError`.
- [ ] **Step 3: Run** → FAIL. **Step 4: Implement** `weather.py` and `uniform_weather.py`. **Step 5: Run** → PASS; gates green.
- [ ] **Step 6: Commit** `feat(engine): add weather contract and conformance suite`.

---

### Task 4: Performance contract, conformance suite, simple reference

**Files:** Create `contracts/performance.py`, `reference/simple_performance.py`, `tests/contracts/conformance_performance.py`, `tests/contracts/test_performance_conformance.py`.

**Interfaces — Consumes:** Tasks 1–3. **Produces:**
- `class FuelType(StrEnum): HFO; VLSFO; ULSFO; MGO; LNG` (values lower-case); `class Consumer(StrEnum): MAIN_ENGINE="main_engine"; AUXILIARY="auxiliary"`; `class OperatingState(StrEnum): AT_SEA="at_sea"; IN_PORT="in_port"`.
- `SafetyLimits(max_significant_wave_height_m: float, max_wind_speed_mps: float, min_under_keel_clearance_m: float)` — all > 0 else `InvalidInputError`.
- `VesselSpec(imo_number: str, length_m: float, beam_m: float, design_draft_m: float, mcr_w: float, sfoc_curve_kg_per_j: tuple[tuple[float, float], ...], auxiliary_load_w: Mapping[OperatingState, float], safety_limits: SafetyLimits)` — `imo_number` 7 digits with valid IMO check digit; `sfoc_curve_kg_per_j` = (load fraction 0–1, kg/J) pairs, strictly increasing load, ≥ 2 points.
- `OperatingCondition(draft_fwd_m: NDArray, draft_aft_m: NDArray, heading_deg: NDArray, weather: WeatherSample)` — equal lengths.
- `PerformanceResult(speed_through_water_mps: NDArray, shaft_power_w: NDArray, fuel_rate_kgps: Mapping[Consumer, NDArray], motion_risk_ratio: NDArray)`.
- `class PerformanceModel(Protocol)`: `speed_for_power(self, vessel: VesselSpec, condition: OperatingCondition, shaft_power_w: NDArray[np.float64]) -> PerformanceResult`; `power_for_speed(self, vessel, condition, speed_through_water_mps: NDArray[np.float64]) -> PerformanceResult`.
- `reference/simple_performance.py`: `class SimplePerformance` — cubic law `P = k·v³` with `k` derived so `P(design_speed) = 0.85·MCR` (constructor `design_speed_mps: float`), a weather add-on `ΔP = c·Hs²·v` with documented constant, SFOC by linear interpolation of the curve, auxiliary from `auxiliary_load_w[AT_SEA]`, `motion_risk_ratio = min(1, Hs / max_significant_wave_height_m)`. `speed_for_power` inverts numerically (bisection to 1e-9 relative, bracket [0, 2·design]).
- `conformance_performance.py`: mixin `PerformanceModelConformance` with abstract `make_model()` / `make_vessel()` / `make_condition(n)` fixtures.

- [ ] **Step 1: Write the suite** (each `req("S0b-R08")`): `test_round_trip_power` (Hypothesis power in [5 %, 100 %] MCR, `power_for_speed(speed_for_power(P)).shaft_power_w ≈ P` rel 1e-6); `test_outputs_finite_non_negative`; `test_fuel_split_sums` (per-consumer fuel sums equal total fuel within 1e-12 relative); `test_motion_risk_in_unit_interval`; `test_lengths_preserved`; `test_mismatched_lengths_rejected`; `test_nan_speed_rejected`; `test_negative_power_rejected`.
- [ ] **Step 2: Write** `test_performance_conformance.py`: `class TestSimplePerformance(PerformanceModelConformance)`; `req("S0b-R09")` `test_suite_fails_on_inconsistent_model` (broken subclass whose two directions disagree by 1 %) and `test_suite_fails_on_risk_out_of_range`; plus `VesselSpec` validation tests (bad IMO check digit, non-increasing SFOC curve) and the suffix gate now covering performance classes.
- [ ] **Step 3: Run** → FAIL. **Step 4: Implement**. **Step 5: Run** → PASS; gates green.
- [ ] **Step 6: Commit** `feat(engine): add performance contract and conformance suite`.

---

### Task 5: Route contract, final gates, PR

**Files:** Create `contracts/route.py`, `tests/contracts/test_route.py`; regenerate `docs/traceability.md`.

**Interfaces — Consumes:** Tasks 1–4. **Produces:**
- `class OperatingMode(StrEnum): CONSTANT_POWER; CONSTANT_SPEED; FIXED_ARRIVAL`; `class DataQuality(StrEnum): OK="ok"; DEGRADED="degraded"`.
- `Waypoint(position: Position, eta: datetime)` — `eta` via `require_utc`.
- `RouteLeg(start: Waypoint, end: Waypoint, geometry: LegGeometry, speed_through_water_mps: float, speed_over_ground_mps: float, fuel_type: FuelType, fuel_kg: Mapping[Consumer, float], worst_significant_wave_height_m: float, worst_wind_speed_mps: float, limit_violations: frozenset[str])` — `end.eta > start.eta`, non-negative numbers.
- `ForecastRun(source: str, run_time: datetime)`.
- `Route(legs: tuple[RouteLeg, ...], mode: OperatingMode, forecast_runs: tuple[ForecastRun, ...], data_quality: DataQuality, quality_reasons: tuple[str, ...])` — ≥ 1 leg; `legs[i].end == legs[i+1].start`; `DEGRADED` ⇔ `quality_reasons` non-empty.

- [ ] **Step 1: Write failing tests** (`req("S0b-R10")`): `test_valid_route`; `test_gap_between_legs_rejected`; `test_non_increasing_eta_rejected`; `test_degraded_without_reasons_rejected`; `test_ok_with_reasons_rejected`; `test_naive_eta_rejected`; `test_empty_route_rejected`; suffix gate now covering route classes.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**. **Step 4: Run** → PASS.
- [ ] **Step 5: Final verification** (`req("S0b-R12")` is covered by CI jobs; add `S0b-R12` to the `# req:` comment of the `engine` job in `.github/workflows/ci.yml`): full engine gate list with DB tests (`ND_REQUIRE_DB=1`), `tools/check_coverage.py`, tools tests, web gates, `python tools/trace.py` then `--check` (zero uncovered for S0 and S0b), license check, jscpd.
- [ ] **Step 6: Commit** `feat(engine): add route contract` and push `feat/s0b-contracts`; open PR titled `feat: add S0b contracts` (the controller asks the owner before opening it).

---

## Spec coverage

| Req | Task |
|---|---|
| S0b-R01 | 1 (gate), 2–5 (classes join automatically) |
| S0b-R02, R03 | 1 |
| S0b-R04, R05, R06, R11 | 2 |
| S0b-R07 | 3 |
| S0b-R08 | 4 |
| S0b-R09 | 3, 4 |
| S0b-R10 | 5 |
| S0b-R12 | 5 |
