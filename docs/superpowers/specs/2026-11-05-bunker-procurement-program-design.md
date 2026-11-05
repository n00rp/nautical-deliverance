# Bunker Procurement — Program Specification

- **Status:** Approved by owner 2026-11-05
- **Date:** 2026-11-05
- **Supersedes:** the goal, scope and build order of [2026-11-04-nautical-deliverance-program-design.md](2026-11-04-nautical-deliverance-program-design.md) (see §7 for which earlier decisions still apply).
- **Requirements source:** the bunker procurement MVP brief written by a bunker buyer at the pilot company (`text.md`, owner-provided). Every requirement in later sub-project specs traces to a line of that brief or to a decision below.

## 1. Goal

Build an internal web application for bunker (marine fuel) procurement that supports the workflow end to end — inquiry → RFQ → offer comparison → supplier/trader selection → nomination → delivery tracking → invoice matching → claims → reporting — first as a pilot used by the brief's author and colleagues, with demo data only. Weather routing (former C1–C9) is parked as a possible later extension; its code is preserved (§8).

## 2. Decisions (all confirmed by the owner)

| ID | Decision |
|---|---|
| D-065 | The first product is the internal bunker procurement system described in the brief. Weather routing is parked as a possible later extension. S0 is kept as the platform. S0b is parked on its branch and reused in part. **Nothing of the weather/performance contracts or the rhumb solver is discarded** (draft PR #7, branch `feat/s0b-contracts`, tag `archive/s0b-contracts`). |
| D-066 | The first delivery is a **pilot** used in real work by the brief's author and a few colleagues. Until an explicit new decision, it contains **demo data only**: no real prices, suppliers, contracts, invoices, claims or internal comments of the pilot company. Demo data is realistic but anonymized (invented suppliers and vessel names, plausible price levels). |
| D-067 | Built so that real data can be introduced later without rewrites: role-based permissions, an audit log of changes, and commercially sensitive fields (prices, decision rationale, internal comments) marked as such. |
| D-068 | The pilot runs in a **free cloud environment** controlled by the owner, reached via browser over HTTPS, signing in through our Keycloak with accounts we create. If no free environment suffices, the owner gets alternatives and costs before anything is bought. The system stays portable to the company's own environment (D-022). |
| D-069 | Two pilot steps. **Pilot 1 (the purchase):** dashboard, inquiry list, create/edit inquiry, supplier/trader selection with suggestions per port, individual RFQ per supplier with recipient log, manual offer entry, total-cost comparison, winner selection with rationale, nomination, master data. **Pilot 2 (after the purchase):** delivery tracking, invoice matching, claims, reporting. |
| D-070 | Each RFQ is created as a draft with **exactly one recipient**; the user opens it in their own e-mail client (`mailto:` with recipient, subject and body prefilled), sends it themselves and marks it sent; the time is logged. The system never sends e-mail itself in the pilot. All demo e-mail addresses use the `.example` domain. Every draft obeys the brief's confidentiality rules (no other suppliers, no number contacted, no internal comments, no price expectations, no other offers, no decision rationale), verified by automated tests. |
| D-071 | Pilot 1 handles USD only for prices and costs; every amount carries a currency field so more currencies can be added without data migration. |
| D-072 | Roles and permissions per §4. **Operator** may create inquiries and see status and the selected supplier, but **never** prices, offers or decision rationale; enforced in the API and tested per role. Accounting/AP is added in pilot 2. |
| D-073 | S0's stack is reused unchanged: Python/FastAPI, React/TypeScript, PostgreSQL with Row-Level Security, Keycloak, Docker. |
| D-074 | Money is exact: amounts are `Decimal` in Python and `numeric` in PostgreSQL, never floats; rounding only for display with a stated rule. The brief's formulas are tested with exact expected values. |
| D-075 | Evaluation criteria per §3 (E3, E4, E5 redefined). |
| D-076 | Build order per §5 (replaces D-023). |
| D-077 | Pilot 1 is ready per §6. |
| D-078 | The build proceeds on our own judgment without waiting for the brief author's feedback; her feedback is input to whichever sub-project it affects, not a gate (amends B0-R08). Assumptions recorded in sub-project specs hold until she says otherwise. |
| D-079 | License allow-list extended with CC-BY-4.0 (build-time data packages such as caniuse-lite), with attribution in THIRD_PARTY_NOTICES.md. D-061 (0BSD, Zlib) applies on main too. GPL/AGPL remain blocked. |

## 3. Evaluation criteria

| ID | Criterion | Measured by |
|---|---|---|
| E1 | Testable spec | Every requirement has a measurable acceptance criterion; no "TBD". |
| E2 | Traceability | Every requirement has ≥ 1 automated test; matrix checked in CI (`tools/trace.py`). |
| E3 | **Commercial correctness** | Cost calculations (product line, fixed costs, total offer cost) match exact expected values; no float arithmetic on money (D-074). |
| E4 | **Confidentiality always holds** | No RFQ draft ever contains forbidden content (D-070) and no role ever receives data it may not see (D-072), verified by property-based tests over generated inquiries, offers and users. |
| E5 | **Coverage of the brief** | Every item in the brief maps to a requirement in a sub-project spec or is explicitly listed as out of scope with a reason. |
| E6 | Performance | Response-time limits per sub-project (e.g. list and comparison views). |
| E7 | Code quality | As S0 (CI gates, coverage ≥ 90 % line and branch). |
| E8 | Robustness | Defined behaviour for invalid input and missing data; never a silently wrong result. |
| E9 | Security & data | Threat model per sub-project; no secrets in code; validation at boundaries; audit log (D-067). |
| E10 | Usability | English UI, WCAG 2.2 AA; core flows within step budgets set in B0. |
| E11 | Craft, not generic | As defined in the earlier program spec (D-017). |

## 4. Roles and permissions (D-072)

| Permission | Admin | Bunker Buyer | Operator | Viewer / Management |
|---|---|---|---|---|
| Manage users and master data (vessels, ports, suppliers/traders) | ✅ | Read | Read | Read |
| Create inquiry (bunker request) | ✅ | ✅ | ✅ | – |
| Edit inquiry, select suppliers, create RFQs | ✅ | ✅ | – | – |
| Enter and compare offers, select winner with rationale | ✅ | ✅ | – | – |
| Create nomination | ✅ | ✅ | – | – |
| See inquiry status | ✅ | ✅ | ✅ | ✅ |
| See prices, offers and decision rationale | ✅ | ✅ | ❌ | ✅ |

## 5. Build order (D-076)

| # | Sub-project | Content |
|---|---|---|
| ✅ | S0 Foundation | Done (merged). |
| B0 | UX concept | Screens and flows for pilot 1; mockups reviewed by the brief's author; step budgets (E10). Design only. |
| B1 | Domain model and master data | Vessels, ports, suppliers/traders, contact persons, products (brief §Bunker Products), ISO 8217 versions 2005–2024, bunkering reasons, legal entities; demo data. |
| B2 | Inquiries | List, create/edit, product lines, status flow. |
| B3 | Supplier selection and RFQ | Suggestions per port, one RFQ draft per recipient, recipient log. |
| B4 | Offers and decision | Manual offer entry, comparison, winner with rationale. |
| B5 | Nomination and dashboard | Nomination, dashboard. |
| B6 | Deployment | Free cloud environment (D-068), HTTPS, backups, accounts — **pilot 1 goes live**. |
| B7+ | Pilot 2 | Delivery, invoice matching, claims, reporting, Accounting/AP role. |

Each step has its own spec → plan → implementation → review cycle; the next starts when the previous is complete and verified.

## 6. Pilot 1 readiness (D-077)

| ID | Condition | Verified by |
|---|---|---|
| P1 | The brief's author can run the full purchase flow for a demo inquiry — create inquiry, select suppliers, generate individual RFQs, enter offers, compare, select winner with rationale, nominate — in the deployed environment. | Automated end-to-end test in the deployed environment, plus her own walkthrough. |
| P2 | All confidentiality tests (E4) green. | CI. |
| P3 | All S0 quality gates green. | CI. |
| P4 | Backup and restore tested. | Documented restore run. |
| P5 | Short English user guide. | Review. |

## 7. Earlier decisions that still apply

From the earlier program spec: D-000, D-006 (adapted: reference systems are the workflow in the brief and commercial bunker platforms), D-008, D-009/D-010 (engine is UI-agnostic; all logic behind the versioned API), D-012, D-013, D-014, D-015, D-016, D-017, D-020 (roles now per D-072), D-021, D-022, D-026, and all S0 decisions (D-027–D-046).

Parked with weather routing: D-005, D-007, D-011, D-018, D-019, D-023 (replaced by D-076), D-024, D-025, D-047–D-064 (S0b).

## 8. Parked: weather routing

The S0b contracts (units, time, errors, geometry incl. the rhumb solver, weather and performance contracts with conformance suites) live on branch `feat/s0b-contracts` (draft PR #7, tag `archive/s0b-contracts`). Parts that the bunker product needs (e.g. units, UTC time helpers, fuel types, vessel particulars) are brought in by the sub-project that first needs them; the rest stays parked until an explicit decision revives weather routing.

## 9. Out of scope until explicitly decided

Real company data; automatic e-mail sending; currencies other than USD; integrations with ERP, accounting or e-mail systems; the company's own SSO; weather routing.
