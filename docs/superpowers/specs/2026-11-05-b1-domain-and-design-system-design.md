# B1 Domain Model, Master Data and Design System — Specification

- **Status:** Draft for owner review
- **Date:** 2026-11-05
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B1 (D-076); UX per [B0](2026-11-05-b0-ux-concept-design.md)
- **Goal:** The data foundation every later step builds on — roles, legal entities, vessels, ports, counterparties with contacts and coverage, product catalogue, audit log, admin pages — and the complete design system for pilot 1.

B1 has two parts with separate implementation plans: **Part A, design system** (web only) and **Part B, domain model and master data** (engine + admin pages, using Part A's components). Part B's engine work does not depend on Part A and may run in parallel; Part B's pages start once Part A's components exist.

## 1. Decisions

Confirmed by the owner in the interview:

| ID | Decision |
|---|---|
| B1-D1 | Suppliers and traders are one **Counterparty** with a type: `physical_supplier`, `trader` or `both`. A counterparty has many contacts and a **coverage** (port × product) that drives B0-D8 suggestions. |
| B1-D2 | Ports are identified by **UN/LOCODE**; real ports may appear in demo data (public, non-confidential). |
| B1-D3 | Product-line quantities are in **metric tons** by default; **m³** is selectable, but an m³ line enters total cost only once a density is given (density belongs to the inquiry line, B2). |
| B1-D4 | Master data is maintained through **admin pages** in the UI. Records are **deactivated, never hard-deleted**, so history is preserved. |
| B1-D5 | A vessel has name, IMO (check digit validated), type, DWT, flag, owning legal entity, default operator, and **approved fuels** (used later to warn when an inquiry requests a product the vessel cannot take). |
| B1-D6 | The audit log records **who, when and which fields changed (before/after)** for every create, update and deactivation, shown as history on the record (implements D-067). |
| B1-D7 | S0's roles are **replaced** by the bunker roles `admin`, `bunker_buyer`, `operator`, `viewer` (D-072) in the Keycloak realm, engine and tests; `route_analyst` is removed (weather routing is parked and can re-add it). |
| B1-D8 | B1 builds the **complete design system for pilot 1** (tokens and every component the B0 screens need), not only what the admin pages use. |

**Proposed — confirmed by the owner's approval of this spec:**

| ID | Decision | Rationale |
|---|---|---|
| B1-D9 | Styling: **CSS Modules with design tokens as CSS custom properties** (light and dark), no CSS-in-JS runtime; Radix primitives only for behaviour-heavy widgets (select, dialog, popover) per D-016. Fonts (IBM Plex Sans, Condensed, Mono) are **self-hosted** in the web image, not loaded from Google. | No runtime cost; tokens shared by CSS and tests; self-hosting keeps the CSP strict and works offline in the company's environment later. |
| B1-D10 | Every port has an **IANA time zone**; the UI shows instants as UTC plus the port's local time (e.g. `12 Nov 06:00 UTC · 07:00 local`). | ETA/ETD are planned in port local time; storing UTC (D-049 spirit) and displaying both avoids ambiguity. |
| B1-D11 | Master-data API: versioned REST under `/api/v1/master/…`; **all roles read, only `admin` writes** (D-072 matrix). | Matches §4 of the program spec. |
| B1-D12 | The audit log is **append-only**: the application DB role has `INSERT` and `SELECT` only on it (no `UPDATE`/`DELETE`), and entries are written in the same transaction as the change. | A log the application can rewrite is not an audit log. |
| B1-D13 | `tools/trace.py` recognizes requirement IDs `B<n>-R<nn>` (and `B<n><letter>-R<nn>`) in addition to `S…`/`C…`. | B-step requirements must be traceable (E2). |

## 2. Part A — Design system

### 2.1 Tokens
Colour (light and dark, as in the B0 prototype), typography (display, body, mono; one type scale), spacing scale, radius, focus ring, and semantic colours `ok`, `warn`, `crit`, `info`. Tokens live in one file; no component uses a literal colour, size or font (E11 #1).

### 2.2 Components (pilot 1)
AppShell (header with role-aware user menu, side navigation, prototype/environment banner slot) · Button (primary, secondary, ghost; loading, disabled) · TextField · NumberField (decimal string in, decimal string out — never a float, D-074) · Select (Radix) · Checkbox · DateTimeField (UTC with port-local hint, B1-D10) · Table (sortable columns, row selection, sticky header, horizontal scroll container, empty and loading states) · StatusPill (the B0-D5 statuses + semantic variants) · Panel · DetailPanel (side panel, collapses below on narrow screens) · Toast · InlineConfirm (no `window.confirm`) · EmptyState · FieldError / FormSummary · HistoryList (audit entries) · RoleGate (renders nothing or a "hidden for your role" note) · LockedNote.

Every component has loading, empty, error, disabled and focus states where applicable, documented in **Storybook** (E11 #4), and is keyboard operable with visible focus (E10).

## 3. Part B — Domain model and master data

### 3.1 Entities (all organization-scoped with RLS, D-021/D-034; all with `active` flag and audit)

| Entity | Fields |
|---|---|
| LegalEntity | name, short code (unique per org) |
| Vessel | name, IMO (7 digits, check digit), vessel type, DWT (integer t), flag, legal entity, default operator (user), approved fuels (set of products) |
| Port | UN/LOCODE (`^[A-Z]{2}[A-Z2-9]{3}$`, unique), name, country (ISO 3166-1 alpha-2), IANA time zone |
| Counterparty | name, type (B1-D1), notes |
| Contact | counterparty, name, e-mail, phone (optional), is_primary |
| Coverage | counterparty × port × product (unique triple) |
| Product | name (catalogue per the brief: HSFO 3.5%, VLSFO 0.5%, DMA 0.1%, Biofuel, B24, B30, B100, Bio diesel FAME), default unit |
| IsoSpecVersion | ISO 8217:2005, :2010, :2012, :2017, :2024 |
| BunkeringReason | Bunkers only, Working cargo, Debunkering |
| AuditEntry | org, actor (user id), timestamp (UTC), entity type, entity id, action (create/update/deactivate/reactivate), changes (field → before/after) |

Products, ISO versions and bunkering reasons are seeded reference data, editable by Admin (B1-D4).

### 3.2 Admin pages
One page per master-data type: list (search, filter active/inactive), create/edit form, deactivate/reactivate with inline confirm, history panel from the audit log. Counterparty page includes contacts and a coverage matrix (ports × products).

## 4. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B1-R01 | Roles migrated (B1-D7) | Realm, engine `Role` enum, web and tests use exactly `admin`, `bunker_buyer`, `operator`, `viewer`; no reference to `route_analyst` remains outside parked S0b code; the dev realm has one test user per role in each of two organizations; smoke test signs in as each role. |
| B1-R02 | Entities and constraints | Every field in §3.1 exists with its constraint enforced in the database (unique keys, checks for LOCODE/IMO format, foreign keys) and in the API (422 with a field error); tests cover each constraint's accept and reject case. |
| B1-R03 | IMO check digit | Valid IMOs (e.g. 9074729) are accepted and invalid check digits rejected, in API and UI; property test over generated 7-digit numbers. |
| B1-R04 | Organization isolation | Every master-data table is RLS-protected; a test per table proves another organization's rows are invisible and immutable (as S0-R04). |
| B1-R05 | Read/write permissions (B1-D11) | For every master-data endpoint and role: reads succeed for all four roles, writes succeed only for `admin` and return 403 otherwise; one parametrized test covers the full matrix. |
| B1-R06 | Soft deactivation (B1-D4) | No DELETE endpoint exists; deactivated records are excluded from selection lists (`?active=true` default) but returned when explicitly requested and still resolvable by id; DB grants deny `DELETE` to the application role on master-data tables. |
| B1-R07 | Audit log (B1-D6, B1-D12) | Every create/update/deactivate/reactivate writes exactly one AuditEntry in the same transaction with actor, time and per-field before/after; a failed change writes none; the application role cannot UPDATE or DELETE audit rows (tested); the history panel shows entries newest first. |
| B1-R08 | Port time zones (B1-D10) | Every port has a valid IANA zone; a formatting helper renders an instant as `DD Mon HH:MM UTC · HH:MM local` with correct DST handling, tested across a DST change. |
| B1-R09 | Coverage drives suggestions | An API query "counterparties covering port P for all of products X" returns exactly those with every (P, x) in coverage, and "covering some" returns the partial ones (feeds B0-D8 in B3); tested on demo data. |
| B1-R10 | Demo data (D-066) | Seed creates ≥ 2 legal entities, ≥ 6 vessels with valid IMOs, ≥ 10 real bunker ports with LOCODE and time zone, ≥ 8 counterparties of all three types with contacts on `.example` and realistic coverage; no real company or person names; a test asserts every contact e-mail ends in `.example` and the seed is idempotent. |
| B1-R11 | Admin pages | Each master-data type has list, create/edit, deactivate/reactivate and history; non-admins see the pages read-only (no edit controls); step budget: create a counterparty with one contact and three coverage rows ≤ 15 interactions. |
| B1-R12 | Design tokens (Part A) | All tokens defined once with light and dark values; a lint rule fails on literal colours, font families or spacing values in component styles; proven to fail on a fixture. |
| B1-R13 | Components (Part A) | Every component in §2.2 exists with Storybook stories for each applicable state; visual regression runs in CI over all stories (light and dark) and fails on unintended change; axe accessibility check passes on every story. |
| B1-R14 | Decimal input (D-074) | NumberField never converts to a JS number: typing, pasting and locale separators produce a normalized decimal string; tested with values that lose precision as floats (e.g. `0.1`, `12345678901234.56`). |
| B1-R15 | Traceability (B1-D13) | `tools/trace.py` collects `B…-R..` IDs; all B1 requirements covered; `--check` green. |
| B1-R16 | Gates inherited | All S0 gates green; coverage ≥ 90 % line and branch for engine and web. |

## 5. Out of scope
Inquiries, RFQs, offers, nomination (B2–B5); user management beyond Keycloak's own admin console (pilot users are created in Keycloak); deployment (B6); importing real master data.

## 6. Risks

| Risk | Mitigation |
|---|---|
| B1 is large | Split into Part A and Part B with separate plans; Part B engine work parallel to Part A. |
| Visual regression is flaky across platforms | Run it only in CI's Linux container with pinned browser; local runs are advisory. |
| Self-hosted fonts' licence | IBM Plex is SIL OFL 1.1 — add `OFL-1.1` to the licence allow-list only for font files (owner decision if needed at plan time). |
