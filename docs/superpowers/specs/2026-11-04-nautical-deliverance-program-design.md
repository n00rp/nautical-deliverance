# Nautical Deliverance — Program Specification

- **Status:** Approved by owner 2026-11-04. **Goal, scope and build order superseded on 2026-11-05 by D-065** — see [2026-11-05-bunker-procurement-program-design.md](2026-11-05-bunker-procurement-program-design.md); weather routing parked, not discarded.
- **Date:** 2026-11-04
- **Scope of this document:** Program level. Defines goals, confirmed decisions, evaluation criteria, decomposition into sub-projects and build order. It does **not** specify any sub-project in detail; each sub-project gets its own spec → plan → implementation cycle.

## 1. Goal

Build a commercial weather-routing and voyage-optimization product for deep-sea commercial shipping, of a quality that allows a paying customer to replace incumbent systems (StormGeo, ZeroStorm, Nereus and similar). Incumbents serve as inspiration and reference; complexity they carry without user value is deliberately removed. A simpler, user-focused UI is an explicit competitive advantage.

## 2. Decision log

All decisions below are confirmed by the owner. A decision changes only through a new, explicitly confirmed decision that supersedes it.

| ID | Decision |
|---|---|
| D-000 | Communication with the owner is in Swedish. All code, identifiers, UI text and repository documentation are in English. |
| D-001 | Evaluation criteria E1–E10 (section 3) apply to the project. |
| D-002 | The project is a commercial product for shipping companies and vessel operators, good enough to replace incumbent systems at a paying customer. |
| D-003 | Until a pilot customer exists, requirements are derived from public sources: incumbents' published material, regulation (IMO, SOLAS, MARPOL, CII, EU ETS etc.), weather data standards (GRIB, WMO) and open data sources. Every requirement states its source. |
| D-004 | The product is pilot-ready when P1–P8 (section 6) are all met. |
| D-005 | Primary segment: deep-sea commercial shipping (bulk, tanker, container). Other segments are out of scope until explicitly decided. |
| D-006 | Incumbent systems are inspiration and reference. Every adopted feature is justified by user value; unnecessary complexity is removed deliberately. |
| D-007 | Pilot-ready scope includes C1–C9 (section 4) in full. |
| D-008 | UI simplicity is a product requirement. E10 is sharpened with measurable step/click budgets for core flows (at minimum: plan route, compare alternatives, export to ECDIS). Budgets are defined in the S0c and C4 specs. |
| D-009 | The computation engine (C1–C3, later C5–C7) is a standalone, UI-agnostic engine. All functionality is exposed through a versioned API. The first client is a web application with its own design system. |
| D-010 | No logic that affects computation results lives in a client. Every computation is callable and testable through the API without a UI. |
| D-011 | Pilot scope is shore-only (route analysts and operators). The vessel receives routes via RTZ export and recommendations. Offline mode, sync and an onboard client are out of scope and are not pre-built. |
| D-012 | Team: the owner and Claude, no deadline. Quality drives the schedule, not dates. |
| D-013 | Automated quality gates replace human code review. Nothing merges without green CI (type check, lint, tests, traceability and coverage per E2/E7). Each sub-project ends with a review against its spec before the next one starts. |
| D-014 | Engine and API in Python (latest stable at project start, pinned). Base stack: NumPy, xarray, cfgrib/ecCodes, Shapely, FastAPI, Hypothesis, mypy strict. Rust is introduced only for a specific component when a measurement against E6 shows Python cannot meet the requirement. Exact versions and tooling are fixed in the S0 spec. |
| D-015 | UX flows and the design system are specified and approved as their own sub-project before C4 is implemented. |
| D-016 | Web client: TypeScript, React, MapLibre GL, own design system, Storybook. No pre-styled component library. Headless accessibility/behaviour libraries (e.g. Radix, React Aria) are allowed. |
| D-017 | E11 (section 3) applies. |
| D-018 | The system is a planning tool, not a navigation system. Routes keep a configurable safety margin to land and shallow water. Every export is marked "Not for navigation – verify in ECDIS". Final route verification is the responsibility of the vessel's ECDIS and master, stated clearly in the UI. |
| D-019 | The pilot uses only open data licensed for commercial use. Each data type (weather, ocean, coastline, depth, zones) is accessed through its own data-source interface; a new source (free or commercial) is added as a new implementation without engine changes. License terms and attribution requirements are documented per source and shown in the UI where required. |
| D-020 | Authentication via OpenID Connect (e.g. self-hosted Keycloak). No custom password handling. Role-based authorization per organization, at minimum Admin, Route Analyst, Viewer; final role list fixed in its spec. |
| D-021 | All data carries an organization identifier from day one; every API call and data query is filtered by organization, verified by tests proving a user can never read or modify another organization's data. The pilot runs as one installation; multi-tenant vs single-tenant is decided when the first customer exists. |
| D-022 | Every service (engine/API, web client, database, Keycloak, weather ingestion) runs as its own Docker container. `docker compose up` starts the whole system locally. CI builds and tests the same images; production runs the exact images tested in CI. No cloud-provider-specific services until explicitly decided. |
| D-023 | Build order A+ (section 5). Each step has its own spec; the next step starts only when the previous one is complete and verified. |
| D-024 | Validation on three levels (section 7). The level-3 cases are a versioned reference suite in the repository (data or fetch scripts plus source per case). Every change to C1–C3 runs against the full suite in CI; a regression beyond a per-metric tolerance blocks the merge. |
| D-025 | Absolute calibration of the fuel model against real operating data is a pilot activity. Before the pilot, the product makes no claims of absolute fuel savings, in UI or sales material. |
| D-026 | Working name: Nautical Deliverance. Package/identifier form: `nautical_deliverance` (Python), `nautical-deliverance` (npm scope, Docker images). The product display name may change later; it is defined in exactly one place per client so a rename only touches UI text. |

## 3. Evaluation criteria

Numeric thresholds are not set here. Each sub-project spec sets the thresholds for the criteria it touches; a sub-project spec without them fails E1.

| ID | Criterion | Measured by |
|---|---|---|
| E1 | Testable spec | Every requirement has a measurable acceptance criterion. No "TBD", no vague terms ("fast", "good"). |
| E2 | Traceability | Every requirement has ≥ 1 automated test. A requirement → test matrix lives in the repository and is checked in CI. |
| E3 | Domain correctness | Navigation computations match reference implementations within a stated tolerance; decoded weather data matches a reference GRIB decoder. |
| E4 | Safety limits always hold | No proposed route crosses land, prohibited zones or vessel weather limits. Verified by property-based tests over thousands of generated cases. |
| E5 | Competitive comparability | Feature parity against an agreed list; benchmark on historical voyages (fuel, ETA error) against a baseline. |
| E6 | Performance | Computation time and memory per operation, with limits set per sub-project. |
| E7 | Code quality | CI runs static typing, lint and tests on every commit; core-logic test coverage ≥ the threshold set in S0; reproducible builds. |
| E8 | Robustness | Defined behaviour for missing, stale or corrupt weather data and invalid input. Never a silently wrong result. |
| E9 | Security & data | Threat model per sub-project; no secrets in code; validation of all input at system boundaries. |
| E10 | Usability | English UI meeting WCAG 2.2 AA; core flows verified against defined tasks and step budgets (D-008). |
| E11 | Craft, not generic | See below. |

**E11 — Craft, not generic.**

Visual & UX:
1. No hard-coded colours, spacing, fonts or shadows outside design-system tokens (lint-enforced).
2. No generic "AI look": no decorative gradients, no emoji as icons, no stock template themes. One icon set.
3. Information density suited to professionals — a workspace, not a marketing page.
4. Every component defines loading, empty, error, disabled and focus states, documented in Storybook.
5. No dead buttons, placeholder text or "coming soon" in anything delivered.
6. Consistent units and formats everywhere (kn, nm, m, °, UTC/local time, decimal precision).
7. Fully keyboard-operable, with shortcuts for core flows.
8. Visual regression tests on all components and views.

Code:

9. One architecture rule per layer, enforced by automated dependency rules.
10. No duplicated logic and no dead code, checked in CI.
11. Every screen has an approved mockup before implementation (D-015).

## 4. Capabilities

| ID | Capability | Content |
|---|---|---|
| C1 | Weather & ocean data | Fetch and decode GRIB2 forecasts (wind, waves, swell, current, optionally ice) from open sources (e.g. NOAA GFS/WW3, ECMWF Open Data, Copernicus Marine). |
| C2 | Vessel performance model | Speed, power and fuel as a function of weather, draft and trim. |
| C3 | Route optimization | Optimal route by fuel, ETA or RTA under hard safety limits: land, depth, ECA zones, high-risk areas, vessel wave limits. |
| C4 | Voyage planning UI | Map, editable routes, comparison of alternatives. |
| C5 | Voyage monitoring | Position (AIS and/or noon reports), deviation from plan, alerts, re-planning. |
| C6 | Charter party & performance analysis | Good-weather speed/consumption compliance; claims support. |
| C7 | Emissions & compliance | CII, EU ETS, FuelEU Maritime, IMO DCS. |
| C8 | Fleet overview | All vessels and voyages in one view. |
| C9 | Export & integration | RTZ export to ECDIS (IEC 61174), API for third-party systems. |

## 5. Build order (A+)

Each row is one sub-project with its own spec → plan → implementation → review cycle.

| # | Sub-project | Purpose | Done when |
|---|---|---|---|
| 1 | **S0 Foundation** | Repository layout, Docker Compose skeleton, CI, quality gates for E1–E11, traceability tooling. | CI enforces every gate on a trivial service; `docker compose up` starts it. |
| 2 | **S0b Contracts** | Interface contracts between C1, C2 and C3: data types, units, coordinate system, time handling, access patterns. No implementation. | Contracts written, approved, and covered by contract tests. |
| 3 | **S0c UX concept** | User flows and mockups for core flows; step budgets (D-008). Design only, no code. | Mockups and budgets approved by the owner. |
| 4 | **C1** | Weather & ocean data. | Spec acceptance criteria met. |
| 5 | **C2** | Vessel performance model. | Spec acceptance criteria met. |
| 6 | **C3** | Route optimization. | Spec acceptance criteria met, plus an end-to-end test C1→C2→C3 through the API. |
| 7 | **Design system** | Tokens, components, Storybook, visual regression (E11). | Spec acceptance criteria met. |
| 8 | **C4** | Voyage planning UI. | Spec acceptance criteria met. |
| 9 | **C9** | Export & integration. | Spec acceptance criteria met. |
| 10 | **C5** | Voyage monitoring. | Spec acceptance criteria met. |
| 11 | **C7** | Emissions & compliance. | Spec acceptance criteria met. |
| 12 | **C6** | Charter party & performance analysis. | Spec acceptance criteria met. |
| 13 | **C8** | Fleet overview. | Spec acceptance criteria met. |

Cross-cutting concerns (authentication D-020, organization isolation D-021) are introduced in S0 as minimal, tested infrastructure and extended by each sub-project that touches them.

## 6. Pilot-readiness (D-004)

The product is pilot-ready when **all** of the following hold:

| ID | Condition | Verified by |
|---|---|---|
| P1 | C1–C9 implemented; every sub-project meets all acceptance criteria of its spec. | Green traceability matrix (E2). |
| P2 | E1–E11 met at the thresholds set per sub-project. | CI report and per-sub-project review. |
| P3 | Core scenario end-to-end: an analyst creates a voyage for a reference vessel, gets an optimized route on the current forecast, compares ≥ 2 alternatives, exports RTZ that validates against the IEC 61174 schema, monitors the voyage with position data, and sees CII/ETS figures and a charter-party report — within the step budgets of D-008. | Automated browser end-to-end test. |
| P4 | Reference suite (D-024) passes on all three levels. | CI run. |
| P5 | Weather pipeline (C1) runs unattended for ≥ 14 consecutive days with no manual intervention and no silent failures (E8). | Logs and monitoring from an endurance run. |
| P6 | Operations: install from scratch with one command (D-022); backup and restore tested; logging and monitoring in place. | Documented install and restore run. |
| P7 | Security: threat model per sub-project; no known high/critical dependency vulnerabilities; organization-isolation tests (D-021) green. | CI security scan and review. |
| P8 | English user guide and API documentation; data-license attributions (D-019) and navigation disclaimer (D-018) in place. | Review. |

## 7. Validation strategy (D-024)

1. **Analytical cases (exact answer).** Distances and courses (great circle, rhumb line) against GeographicLib (Karney). Synthetic weather scenarios with known optimum (e.g. uniform current → closed-form route and time; storm cell at a known position → avoided with the prescribed margin). Property-based tests for safety limits (E4).
2. **Reference tools.** GRIB decoding matches ecCodes tools value for value. The performance model (C2) matches published worked examples of the empirical methods chosen in the C2 spec (candidates: Holtrop–Mennen for resistance, ISO 15016 for added resistance in waves).
3. **Historical voyages.** Real voyages from open AIS archives (e.g. Danish Maritime Authority, NOAA MarineCadastre) with weather from reanalysis (ERA5). Compare the actual track with our optimized route under the same weather.

**Known limit:** level 3 shows only *relative* improvement (our route vs. the actual track under the same model), not absolute fuel consumption. Absolute calibration requires pilot-customer noon reports (D-025).

## 8. Out of scope until explicitly decided

- Segments other than deep-sea commercial (D-005).
- Onboard use, offline mode, ship–shore sync (D-011).
- Native clients (D-009 keeps the door open).
- Paid data sources (D-019 keeps the door open).
- Multi-tenant vs single-tenant deployment model (D-021).
- Rust components (D-014).
- Cloud-provider-specific services (D-022).

## 9. Assumptions

- Development host is Windows 11 with Docker Desktop on WSL2.
- License terms of the open data sources named in this document reflect general knowledge and are verified and documented in the C1 spec before any source is used.

## 10. Next step

After owner approval of this document: write the **S0 Foundation** spec.
