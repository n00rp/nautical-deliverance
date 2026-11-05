# B2 Inquiries — Specification

- **Status:** Approved by owner 2026-11-05 (including proposed decisions B2-D9–B2-D12)
- **Date:** 2026-11-05
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B2 (D-076); UX per [B0](2026-11-05-b0-ux-concept-design.md) S1, S2, S8; builds on [B1](2026-11-05-b1-domain-and-design-system-design.md)
- **Goal:** Bunker inquiries can be created, edited, owned, cancelled, duplicated and listed, with product lines and the inquiry status flow, as the first working part of the purchase flow.

## 1. Decisions

Confirmed by the owner in the B2 interview:

| ID | Decision |
|---|---|
| B2-D1 | A **user directory** in the engine: each authenticated request upserts the caller (Keycloak subject, name, e-mail, roles, organization) into `app_user`; dev users are seeded. Operator, buyer and requester are picked from it; the buyer defaults to the signed-in user when that user is a buyer or admin. |
| B2-D2 | The port **agent** is free text on the inquiry (name, optional e-mail); not master data in pilot 1. |
| B2-D3 | Inquiry reference is `INQ-YYMM-NNN`, sequential per organization and calendar month (UTC) of creation, starting at 001; `NNN` widens to four digits after 999. Never reused, also not after cancellation. |
| B2-D4 | A product line for a product not in the vessel's **approved fuels** shows a warning and may still be saved. |
| B2-D5 | After **Draft**, the core fields lock: vessel, legal entity, port, bunkering reason and all product lines. ETA, ETD, agent, buyer and internal comments stay editable (audited). A changed scope is handled by cancelling and duplicating. |
| B2-D6 | **Cancel** requires a free-text reason (stored internally, shown in history) and goes through InlineConfirm. Cancelled inquiries are read-only. |
| B2-D7 | The buyer is **optional** at creation; an inquiry without one shows "Unassigned". An Admin or Bunker Buyer can **Take** it (become buyer). |
| B2-D8 | The **inquiry work list** (B0-D7) is the start page from B2, with the data available now; RFQ and offer warnings are added by B3/B4. |

Proposed — confirmed by the owner's approval of this spec:

| ID | Decision | Rationale |
|---|---|---|
| B2-D9 | Statuses are the full B0-D5 set (`draft`, `rfq_sent`, `offers_received`, `winner_selected`, `nominated`, `cancelled`); transitions are defined in **one pure function** in the domain layer. B2 exposes only create (→ draft) and cancel (any non-cancelled → cancelled); later steps add their transitions through the same function. | One place to test the whole flow; no ad-hoc status writes. |
| B2-D10 | **Duplicate** creates a new Draft with the same vessel, legal entity, voyage, operator, requester, port, agent, bunkering reason and product lines; ETA/ETD, buyer, internal comments and cancel reason are not copied. Allowed from any status. | Supports B2-D5's "cancel and duplicate" with one click. |
| B2-D11 | An **m³ line** takes an optional density (kg/m³ at 15 °C, 600–1100). Without density it is flagged "not in total" (B1-D3); the total is computed in B4. | Density belongs to the line (B1-D3); no cost calculation exists yet. |
| B2-D12 | Permissions: create — Admin, Bunker Buyer, Operator; edit, take, cancel, duplicate — Admin, Bunker Buyer; read — all four roles. Internal comments are a commercially sensitive field (D-067), readable by the same roles as the inquiry in pilot 1. | Program spec §4; Operator never sees prices, none exist in B2. |

## 2. Data model (all organization-scoped with FORCE RLS, composite org FKs, audit; as B1)

| Entity | Fields |
|---|---|
| AppUser | id (Keycloak `sub`), organization, name, e-mail, roles (array), last_seen_at. Upsert writes only when name, e-mail or roles changed, or `last_seen_at` is older than 1 h. Not deactivated; a user that loses all roles is excluded from pickers. |
| Inquiry | reference (unique per org), status, vessel, legal entity (defaults from the vessel), voyage (text, optional, ≤ 40), operator (user, required; defaults from the vessel's default operator, else the creator if an operator), buyer (user, optional), requester (user, required, defaults to creator), port, ETA, ETD (timestamptz, UTC; ETD ≥ ETA; both required), agent name (optional), agent e-mail (optional, valid address), bunkering reason, internal comments (optional, ≤ 4000), cancel reason, version, created_at, created_by, updated_at |
| InquiryLine | inquiry, position, product, quantity (`numeric(12,3)`, > 0), unit (`mt` or `m3`), density (`numeric(6,1)`, optional, only for `m3`, 600–1100), spec notes (optional, ≤ 500), ISO 8217 version (required). 1–10 lines per inquiry; a product appears at most once per inquiry. |
| InquiryReferenceCounter | organization, year-month, next value; incremented with a row lock in the creating transaction. |

Inactive master data (B1-D4) cannot be chosen for a new or edited inquiry, but existing inquiries that reference it still display it, marked "inactive".

## 3. API (versioned under `/api/v1/`)

`GET /users?role=` · `GET /inquiries?status=&q=&mine=` · `GET /inquiries/{id}` (with lines, warnings, display names) · `POST /inquiries` · `PATCH /inquiries/{id}` (with `version`; lines replaced as a set while Draft) · `POST /inquiries/{id}/take|cancel|duplicate` (with `version`) · `GET /inquiries/{id}/history`. Errors as B1: 422 `{"detail":[{field,message}]}`, 409 on a stale version, 403 by role, 404 across organizations.

## 4. UI

- **Work list (start page, S1):** reference, vessel, port, ETA (UTC · port local), status pill, next step (B2: Draft → "Select suppliers", Cancelled → "—"), buyer or "Unassigned", warning "ETA in < 48 h, not nominated" (crit). Filter by status (default: all except cancelled), search on reference/vessel/port, sort by ETA (default) or reference, "Mine" toggle for buyers. "New inquiry" for roles that may create.
- **Inquiry page (S2):** one page with sections per B0-D1 — Vessel & voyage (vessel select auto-fills IMO, type, DWT, legal entity, operator), Port & timing (DateTimeField with port-local hint), Products (add/remove lines, unit, density for m³, approved-fuel warning), Internal comments (marked internal). Actions: Save, Take, Cancel (with reason), Duplicate; history panel. Locked fields per B2-D5 show LockedNote; Operator sees the page read-only after creating (S8).

## 5. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B2-R01 | User directory (B2-D1) | An authenticated request upserts the caller; repeated requests within an hour with unchanged claims write nothing; `GET /users?role=` returns only the caller's organization's users with that role; users without a bunker role are excluded; tested including two organizations. |
| B2-R02 | Entities and constraints | Every field and constraint in §2 is enforced in the database and the API (422 with a field error); each constraint has an accept and a reject test. |
| B2-R03 | Organization isolation | Every new table is RLS-protected; a test per table proves another organization's rows are invisible and immutable. |
| B2-R04 | Permissions (B2-D12) | One parametrized test covers every inquiry endpoint × the four roles: allowed calls succeed, others return 403. |
| B2-R05 | References (B2-D3) | References follow `INQ-YYMM-NNN`, restart each month per organization, never repeat; 20 concurrent creates in one organization produce 20 distinct, gap-free references. |
| B2-R06 | Status flow (B2-D9) | The transition function accepts exactly the B0-D5 transitions (incl. cancel from every non-cancelled status) and rejects all others; property test over all status pairs; the API rejects edits, take and cancel on a cancelled inquiry with 409. |
| B2-R07 | Edit lock (B2-D5) | After Draft, changes to a core field return 422 with a field error; ETA, ETD, agent, buyer and comments still save; tested per field. |
| B2-R08 | Cancel and duplicate (B2-D6, B2-D10) | Cancel without a reason is rejected; with one, the status is cancelled and the reason appears in history. Duplicate creates a Draft with a new reference and exactly the B2-D10 fields copied. |
| B2-R09 | Product lines (B2-D11) | Quantities and densities are exact decimals end to end (no float; tested with `0.1` and `999999999.999`); density allowed only on m³ lines and within range; m³ lines without density are flagged "not in total" in the API and UI; 1–10 lines, no duplicate product. |
| B2-R10 | Approved-fuel warning (B2-D4) | A line whose product is not approved for the vessel returns a warning in the API and shows it on the line; the inquiry still saves. |
| B2-R11 | Audit | Create, every update (including line changes as before/after), take, cancel and duplicate write exactly one AuditEntry each in the same transaction; the inquiry history shows them newest first. |
| B2-R12 | Work list (B2-D8) | Shows the §4 columns; filter, search, sort and "Mine" behave as specified; the ETA warning appears for a non-nominated inquiry with ETA < 48 h ahead and not otherwise (tested at the boundary); the list for 200 inquiries responds in < 300 ms in the CI environment (E6). |
| B2-R13 | Inquiry page and step budget (E10, B0-R02) | Create an inquiry with 2 product lines from the work list in ≤ 25 interactions, asserted by a scripted test; vessel selection auto-fills per §4; locked fields and the Operator read-only view render per §4; Storybook/visual and axe as B1-R13. |
| B2-R14 | Demo data (D-066) | The seed adds ≥ 6 inquiries per organization covering Draft, Cancelled and Unassigned cases, with references in the B2-D3 format, idempotent, only demo master data. |
| B2-R15 | Gates inherited | All S0/B1 gates green; coverage ≥ 90 % line and branch; `tools/trace.py --check` green with all B2 requirements covered. |

## 6. Out of scope

Supplier selection and RFQs (B3), offers and totals (B4), nomination and the full dashboard (B5); notifications; attachments; agent master data; editing locked fields by reopening an inquiry.

## 7. Risks

| Risk | Mitigation |
|---|---|
| User directory diverges from Keycloak | Upsert on every request with changed claims; pickers show only users with a current bunker role. |
| Reference counter contention | Row lock per org-month; ~10 inquiries/week (A1) is far below any contention limit; concurrency test (B2-R05). |
| Lock rules too strict for real work | Duplicate is one click; the brief's author's feedback (D-078) may relax B2-D5 later. |
