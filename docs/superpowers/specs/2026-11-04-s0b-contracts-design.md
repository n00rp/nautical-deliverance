# S0b Contracts — Specification

- **Status:** Approved by owner 2026-11-04
- **Date:** 2026-11-04
- **Parent:** [Program specification](2026-11-04-nautical-deliverance-program-design.md), build step 2 (D-023)
- **Goal:** Define, implement and test the in-engine contracts between weather data (C1), vessel performance (C2) and route optimization (C3) — types, conventions and provider interfaces — so the three can be built one after another without rework. No C1/C2/C3 implementation.

## 1. Decisions (all confirmed by the owner)

| ID | Decision |
|---|---|
| D-047 | S0b covers K1 coordinates, K2 time, K3 units, K4 weather fields, K5 vessel performance, K6 route and results, K7 errors and data quality. Out of scope: data sources (C1), physical models (C2), optimization algorithm (C3), persistence. |
| D-048 | Positions are WGS84 latitude/longitude in decimal degrees. Longitude is always normalized to [−180, 180); latitude valid in [−90, 90]. A leg is computed exactly on the WGS84 ellipsoid for its geometry type with GeographicLib (`Geodesic` or `Rhumb`), never by linear interpolation in degrees. Courses are degrees true, [0, 360). |
| D-049 | All instants are timezone-aware UTC; a naive datetime is rejected at the boundary. Durations are `timedelta`. Every forecast value carries its **run time** and **valid time**; consumers query by valid time. Local time is used only for display (UI, RTZ). |
| D-050 | SI units inside the engine (m, s, m/s, kg, kg/s, W, kg/J, degrees for angles). Conversion to kn, nm, h, t, kW, g/kWh only at boundaries. Every numeric contract field carries a unit suffix from one registry; a contract test fails on any numeric field without an allowed suffix. |
| D-051 | Required weather variables: 10 m wind (u, v), total sea, wind sea and swell (height, period, direction each), surface current (u, v). Optional: sea-ice concentration, visibility, mean sea-level pressure. A missing required variable stops the computation with an explicit error; an optional one is reported unavailable, never guessed. Wind and current are (u, v) components pointing **towards**; wave directions are **from**, suffix `_from_deg`. |
| D-052 | Weather access is a vectorized `sample(lat_deg, lon_deg, valid_time)` over arrays returning all variables. Bilinear in space, linear in time; directions via unit vectors. No extrapolation: out-of-coverage / out-of-time-range is flagged per value. Every result states source and run time. A scalar convenience query wraps the vectorized one. C3 never touches C1 storage. |
| D-053 | Operating modes M1 constant power, M2 constant speed through water, M3 fixed arrival time (RTA) at minimum fuel; M4 arrival window later without contract change. The performance model offers `speed_for_power` and `power_for_speed`, both taking draft, trim, heading and weather, both returning speed through water, shaft power, fuel rate and a motion-risk indicator. C3 derives speed over ground. |
| D-054 | Fuel consumption split per consumer (`main_engine`, `auxiliary`); auxiliary load is a constant per vessel and operating state; fuel type chosen per leg by C3 (ECA). Fuel types are a fixed enumeration HFO, VLSFO, ULSFO, MGO, LNG. Emission factors belong to C7. Further consumers (boiler) can be added without breaking the contract. |
| D-055 | Each leg declares `rhumb_line` or `great_circle`; choice per route, default rhumb line. C3 densifies waypoints so the deviation from the optimized path stays below a tolerance set in the C3 spec. Each leg carries waypoint times (UTC), speed through water and over ground, fuel per consumer and fuel type, worst weather along the leg, and safety-limit violation flags (empty in a valid route). |
| D-056 | Two thresholds per quality measure — *warn* and *block* — values set in the C1/C3 specs. Hard errors are typed exceptions from one hierarchy and are never swallowed. Every `sample()` result carries per-point quality `ok`, `out_of_coverage`, `out_of_time_range`, `stale`. Every route records its forecast runs and a `data_quality: ok \| degraded` summary with reasons, which the UI must show. |
| D-057 | A `VesselSpec` contract: IMO number, length, beam, design draft (m), main-engine MCR (W), specific fuel oil consumption curve (kg/J, converted at the boundary from g/kWh), auxiliary load per operating state (W), and **safety limits**: max significant wave height (m), max wind speed (m/s), min under-keel clearance (m). E4 tests against these. |
| D-058 | Contracts live in `nautical_deliverance.domain.contracts`, one module per area (`geo`, `time`, `units`, `weather`, `performance`, `route`, `errors`). Data types are frozen dataclasses; providers (`WeatherProvider`, `PerformanceModel`) are `typing.Protocol`. Only stdlib, NumPy and GeographicLib. Arrays are `float64`; time arrays are `datetime64[s]` in UTC, with a helper converting to/from aware `datetime` that rejects naive values (clarifies D-049). |
| D-059 | Each Protocol has a reusable conformance test suite every future implementation must pass. S0b ships an analytical reference implementation (uniform fields, a simple performance model) that proves the suites work and later serves C3's level-1 analytical tests (D-024). |
| D-061 | License allow-list (D-037/D-044) extended with 0BSD and Zlib (bundled components of NumPy). GPL/AGPL remain blocked. |
| D-062 | Amends D-052: `WeatherSample` carries `source`, `run_time` and `quality` per **variable group** — `WIND` (u, v), `WAVES` (total sea, wind sea, swell), `CURRENT` (u, v), and one group per optional variable. The NaN rule applies per group. |
| D-063 | Amends D-056: values are kept at `STALE` points; NaN only for `OUT_OF_COVERAGE` and `OUT_OF_TIME_RANGE`. Performance models accept `STALE` input; C3 decides warn vs block from the thresholds. |
| D-064 | Amends D-054/D-057: `speed_for_power` and `power_for_speed` take a `fuel_type`; returned fuel rates are the mass of that fuel. `VesselSpec` holds one SFOC curve per `Consumer` at the ISO reference lower calorific value; conversion between fuel types happens in C2. |
| D-060 | Contracts are internal to the engine; no separate version numbering. A change needs a new confirmed decision and an updated spec; the conformance suites catch implementations that drift. |

## 2. Module layout

```
engine/src/nautical_deliverance/domain/contracts/
  __init__.py
  units.py        suffix registry, boundary conversions
  time.py         UTC helpers (datetime <-> datetime64[s])
  geo.py          Position, LegGeometry, distance/course/point-along-leg
  errors.py       ContractError hierarchy
  weather.py      WeatherVariable, SampleQuality, WeatherSample, WeatherProvider
  performance.py  FuelType, Consumer, OperatingState, SafetyLimits, VesselSpec,
                  OperatingCondition, PerformanceResult, PerformanceModel
  route.py        OperatingMode, Waypoint, RouteLeg, Route, DataQuality
engine/src/nautical_deliverance/domain/reference/
  __init__.py
  uniform_weather.py      analytical WeatherProvider (D-059)
  simple_performance.py   analytical PerformanceModel (D-059)
engine/tests/contracts/
  conformance_weather.py      reusable suite (parametrized by a provider factory)
  conformance_performance.py  reusable suite
  test_*.py                   unit tests + suites run against the reference implementations
```

New dependency: `geographiclib` (pure Python, MIT — on the D-037 allow-list).

## 3. Contract content

### 3.1 Units (K3)
- `UNIT_SUFFIXES`: the single registry of allowed suffixes: `_m`, `_s`, `_mps`, `_kg`, `_kgps`, `_w`, `_kg_per_j`, `_deg`, `_from_deg`, `_ratio` (dimensionless 0–1), `_pa`.
- Boundary conversions with exact constants: knots ↔ m/s (1 kn = 1852/3600 m/s), nautical miles ↔ m (1852 m), tonnes ↔ kg, kW ↔ W, g/kWh ↔ kg/J (1 g/kWh = 1/3.6e9 kg/J), hours ↔ s.

### 3.2 Time (K2)
- `to_datetime64(dt: datetime) -> np.datetime64` and `from_datetime64(t: np.datetime64) -> datetime`; naive input raises `NaiveDatetimeError`; non-UTC aware input is converted to UTC.
- Array variant for sequences.

### 3.3 Geometry (K1)
- `Position(lat_deg, lon_deg)`: validates latitude, normalizes longitude to [−180, 180).
- `LegGeometry` enum: `RHUMB_LINE`, `GREAT_CIRCLE`.
- `distance_m(a, b, geometry)`, `initial_course_deg(a, b, geometry)`, `point_along(a, b, geometry, fraction)`, all via GeographicLib on WGS84.

### 3.4 Errors (K7)
`ContractError` ← `InvalidInputError` ← { `NaiveDatetimeError`, `InvalidPositionError` }; `ContractError` ← `MissingRequiredVariableError`; `ContractError` ← `DataBlockedError` (carries the reasons).

### 3.5 Weather (K4)
- `WeatherVariable` enum with a `required: bool` attribute per member (D-051 set).
- `SampleQuality` enum: `OK`, `OUT_OF_COVERAGE`, `OUT_OF_TIME_RANGE`, `STALE`.
- `WeatherSample`: one `float64` array per available variable (NaN where quality ≠ OK), a `quality` array, `source: str`, `run_time` (`datetime64[s]` array, one per point), and `unavailable: frozenset[WeatherVariable]` for optional variables the provider lacks.
- `WeatherProvider` Protocol: `sample(lat_deg, lon_deg, valid_time) -> WeatherSample` (equal-length 1-D arrays) and `sample_point(position, valid_time: datetime) -> WeatherSample`.
- Interpolation rules (§1 D-052) are part of the contract and verified by the conformance suite.

### 3.6 Performance (K5)
- `FuelType` enum (D-054), `Consumer` enum (`MAIN_ENGINE`, `AUXILIARY`), `OperatingState` enum (`AT_SEA`, `IN_PORT`).
- `SafetyLimits(max_significant_wave_height_m, max_wind_speed_mps, min_under_keel_clearance_m)`, `VesselSpec` (D-057).
- `OperatingCondition`: arrays `draft_fwd_m`, `draft_aft_m`, `heading_deg`, plus the `WeatherSample` at those points.
- `PerformanceResult`: arrays `speed_through_water_mps`, `shaft_power_w`, `fuel_rate_kgps` per `Consumer`, `motion_risk_ratio` (0 = calm, 1 = at the vessel's limit).
- `PerformanceModel` Protocol: `speed_for_power(vessel, condition, shaft_power_w) -> PerformanceResult` and `power_for_speed(vessel, condition, speed_through_water_mps) -> PerformanceResult`.

### 3.7 Route (K6)
- `OperatingMode` enum: `CONSTANT_POWER`, `CONSTANT_SPEED`, `FIXED_ARRIVAL`.
- `Waypoint(position, eta: datetime)`.
- `RouteLeg`: `start`, `end` (`Waypoint`), `geometry`, `speed_through_water_mps`, `speed_over_ground_mps`, `fuel_type`, `fuel_kg` per `Consumer`, `worst_significant_wave_height_m`, `worst_wind_speed_mps`, `limit_violations: frozenset[str]`.
- `Route`: `legs`, `mode`, `forecast_runs` (source + run time pairs), `data_quality` (`OK` / `DEGRADED`), `quality_reasons: tuple[str, ...]`. Invariants: consecutive legs share waypoints; ETAs strictly increase.

## 4. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| S0b-R01 | Unit suffixes enforced (D-050) | A test inspects every dataclass in `domain.contracts` and fails if any field typed `float`, a float `np.ndarray`, or a mapping to those lacks a suffix from `UNIT_SUFFIXES`; it is proven to fail on a deliberately unsuffixed fixture class. Identifiers are `str` (e.g. `imo_number: str`, 7 digits validated), so no numeric field is unit-less. |
| S0b-R02 | Boundary conversions exact | Round-trip kn↔m/s, nm↔m, t↔kg, kW↔W, g/kWh↔kg/J, h↔s for ≥ 1000 Hypothesis-generated values agrees within 1e-12 relative; 1 kn = 0.514444… m/s and 1 nm = 1852 m exactly. |
| S0b-R03 | UTC enforced (D-049) | Naive `datetime` → `NaiveDatetimeError` in every contract constructor and helper taking an instant; aware non-UTC input is converted to the same UTC instant; `datetime` ↔ `datetime64[s]` round-trips exactly for ≥ 1000 generated instants. |
| S0b-R04 | Longitude normalization and validation | `Position` maps any finite longitude to [−180, 180) (Hypothesis, ≥ 1000 cases); latitude outside [−90, 90] or non-finite values → `InvalidPositionError`. |
| S0b-R05 | Geodesic correctness | `distance_m` and `initial_course_deg` for `GREAT_CIRCLE` and `RHUMB_LINE` match GeographicLib's published test cases (≥ 10 from its test set, documented source) within 1 mm and 1e-9°. |
| S0b-R06 | Antimeridian | A leg 179° E → 179° W at equal latitude has distance equal to the 2° leg (not 358°) within 1 mm for both geometries; `point_along(…, 0.5)` lies at ±180° longitude. |
| S0b-R07 | Weather conformance suite | A reusable suite checks for any `WeatherProvider`: output arrays match input length; required variables present or `MissingRequiredVariableError`; no extrapolation (points outside coverage/time → NaN + the right `SampleQuality`); directional interpolation via unit vectors (350° and 10° → 0°, not 180°); bilinear/linear interpolation reproduces values exactly at grid nodes and linear fields exactly in between; `run_time` and `source` set for every OK point; `sample_point` equals the vectorized result. |
| S0b-R08 | Performance conformance suite | A reusable suite checks for any `PerformanceModel`: `power_for_speed(speed_for_power(P)) ≈ P` within 1e-6 relative over the valid range; outputs are finite and non-negative; fuel split per `Consumer` sums to the total; `motion_risk_ratio` in [0, 1]; array lengths preserved; invalid input → `InvalidInputError`. |
| S0b-R09 | Reference implementations pass | The analytical `uniform_weather` and `simple_performance` implementations pass their conformance suites; the suites are proven to fail on a deliberately broken variant of each (e.g. extrapolating provider, inconsistent model). |
| S0b-R10 | Route invariants | Constructing a `Route` with non-shared consecutive waypoints, non-increasing ETAs, or a `DEGRADED` quality without reasons raises `InvalidInputError`. |
| S0b-R11 | Layer rules hold | `domain.contracts` and `domain.reference` import only stdlib, NumPy and geographiclib (import-linter contract proven to fail on a violating fixture). |
| S0b-R12 | Gates inherited | Coverage ≥ 90 % line and branch (D-035); mypy strict, Ruff, vulture, traceability all green; no change to S0 behaviour (existing tests pass unchanged). |

## 5. Out of scope
- Any real data source, GRIB decoding, caching (C1).
- Any physical resistance/propulsion model beyond the analytical reference (C2).
- Optimization, densification algorithm and its tolerance value (C3).
- Persistence of routes, API endpoints, UI (C3/C4).
- Threshold values for warn/block (C1/C3).
- Performance budgets (E6) for `sample()` — set in C1 against a real provider.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Contract too abstract for C3's hot loop | Vectorized interfaces from day one (D-052, D-053); C1/C3 specs measure E6 against them. |
| Reference implementation leaks into production | It lives in `domain.reference`, is named analytical, and is only used by tests and level-1 validation. |
| Conformance suites too lenient | S0b-R09 proves each suite fails on a broken implementation. |
