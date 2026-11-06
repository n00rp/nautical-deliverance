# B5 Nomination and Dashboard — Specification

- **Status:** Draft for owner review
- **Date:** 2026-11-06
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B5 (D-076); D-070 (mail handoff pattern), D-072 (roles), D-074 (exact money), E4; B0-D5, B0-D7, B0 screen S7; builds on [B2](2026-11-05-b2-inquiries-design.md), [B3](2026-11-05-b3-supplier-selection-rfq-design.md) and [B4](2026-11-06-b4-offers-decision-design.md).
- **Goal:** The buyer nominates the selected supplier with an individual nomination e-mail draft (amendable while nominated), completing the pilot 1 purchase flow; a dashboard becomes the start page and shows what needs attention and the month's key figures.

## 1. Decisions

Confirmed by the owner in the B5 interview:

| ID | Decision |
|---|---|
| B5-D1 | The nomination is an **e-mail draft to the winning counterparty's contact**, handled like an RFQ: Open in e-mail (`mailto:`) / Copy text, then **Mark sent**, which freezes the text and moves the inquiry Winner selected → Nominated. |
| B5-D2 | Losing suppliers are **not** informed by the system in pilot 1. |
| B5-D3 | While the inquiry is Nominated the buyer can create an **amended nomination** (e.g. after an ETA change); every sent version is frozen and kept, the latest sent is current. |
| B5-D4 | A **dashboard is the start page**: "Needs attention", status counts and the month's figures, with a link to the full work list. |
| B5-D5 | Dashboard figures (calendar month, UTC, by first nomination sent): **nominated volume (mt)**, **nominated spend (USD)**, **open inquiries by status**, **average offers per decided inquiry**. |
| B5-D6 | "Needs attention" thresholds: RFQ response deadline within **24 h** with RFQs still unanswered; selected (or, without a winner, lowest selectable) offer validity ending within **24 h** without nomination; ETA within **48 h** without nomination (B2 rule, incl. passed ETA); plus RFQ drafts not yet sent. |

Proposed — confirmed by the owner's approval of this spec:

| ID | Decision | Rationale |
|---|---|---|
| B5-D7 | Nomination text is rendered by one pure function from an allow-listed **`NominationContext`** (§3); forbidden data never reaches it. Reuses `build_mailto`, `format_instant`, `format_qty_mt`, `formatUsd` rules. | Same confidentiality-by-construction as B3-D9. |
| B5-D8 | **One draft at a time** per inquiry; a draft can be withdrawn; version numbers 1, 2, … count sent versions; the subject of version ≥ 2 reads `Amended nomination …`. | Clear history, no parallel drafts. |
| B5-D9 | The nomination recipient defaults to the winning RFQ's contact; another active contact with e-mail of the same counterparty may be chosen. | As B3-D1. |
| B5-D10 | Once Nominated, the winner can no longer be re-selected (B4-D7 ends at nomination) and the winning offer stays locked. | B0-D5 flow; decision is final once communicated. |
| B5-D11 | Permissions: create/edit/send/withdraw nominations — Admin, Bunker Buyer; read nominations — Admin, Bunker Buyer, Viewer; **Operator: 403** on nomination endpoints (they contain prices). Dashboard: all roles; the Operator's dashboard contains **only status counts and the ETA-without-nomination item** — no money, volumes, RFQ, offer or validity information. | D-072. |
| B5-D12 | Volume counts mt lines and m³ lines converted with a known density; m³ lines without density are excluded and the figure is marked "excl. n lines without density". Spend is the sum of frozen `decided_total`s. | Exactness (D-074); never a silently wrong figure (E8). |

## 2. Data model (organization-scoped, FORCE RLS, composite org FKs, audit, version; no DELETE grant)

| Entity | Fields |
|---|---|
| Nomination | inquiry, offer (must be the inquiry's winner when created), contact (must belong to the offer's counterparty; active; has e-mail), status (`draft`, `sent`, `withdrawn`), sequence (sent version number, set at Mark sent), sent_at, sent_to_email, sent_subject, sent_body, inquiry_version_at_send (all five sent fields set exactly when `sent`, immutable afterwards — trigger as B3), version, created_at, created_by, updated_at. Partial unique: one `draft` per inquiry; unique (inquiry, sequence) where sent. |

## 3. Nomination content

**Allowed** (the complete `NominationContext`): inquiry reference; vessel name and IMO; port name and UN/LOCODE; ETA and ETD (`DD Mon HH:MM UTC · HH:MM local`); agent name; per line: product, quantity, unit, density if any, qty_mt (exact, B4 R3), price per mt, line cost; the five fixed costs and the total in USD; delivery window and method; physical supplier; payment terms; recipient contact name; buyer name; sequence (amendment number).

**Never:** other counterparties, offers or prices; the number of offers or RFQs; lowest/delta information; decision reason or note; internal comments; cancel reason; operator, requester, legal entity; any e-mail address other than the recipient's.

Subject: `Nomination <reference> – <vessel> – <port>` (version ≥ 2: `Amended nomination (<n>) <reference> – <vessel> – <port>`). `mailto:` rules as B3-D7.

## 4. API (under `/api/v1/`)

`GET /inquiries/{id}/nominations` (all versions, newest first) · `POST /inquiries/{id}/nominations` `{contact_id?}` (draft; inquiry Winner selected or Nominated; 201) · `GET /nominations/{id}/preview` → `{to, subject, body, mailto, body_in_link}` · `PATCH /nominations/{id}` `{version, contact_id}` (draft only) · `POST /nominations/{id}/mark-sent|withdraw` (`version`) · `GET /nominations/{id}/history` · `GET /dashboard` → `{attention:[{inquiry_id, reference, vessel_name, port_name, kind, due_at, detail}], status_counts:{…}, month:{period, nominated_mt, mt_excluded_lines, nominated_spend, currency, open_by_status, avg_offers}}` (role-filtered per B5-D11). Errors as before.

## 5. UI

- **Dashboard (start page `#/`)**: "Needs attention" list (kind pill, due time in UTC · local, link to the inquiry), status count tiles, month figures (`USD 1,234,567.89`, `12,345.678 mt`); work list moves to `#/inquiries`, still in the navigation.
- **S7 Nomination** (inquiry page → "Create nomination" when Winner selected; "Amend nomination" when Nominated): exact preview, contact select, Open in e-mail, Copy text, Mark sent (InlineConfirm), Withdraw draft; list of sent versions with their frozen text.
- Work list next step: "Nominated" (with version when > 1); inquiry page shows the current nomination for Admin/Buyer/Viewer, "Nominated: <supplier>" for the Operator.

## 6. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B5-R01 | Entities and constraints | Every field and constraint in §2 is enforced in DB and API (422 with field error), incl. one draft per inquiry, offer is the winner, contact belongs to the counterparty, sent-field consistency and immutability; accept and reject test each. |
| B5-R02 | Organization isolation | `nomination` RLS-protected; other organization's rows invisible and immutable; foreign ids 404/422. |
| B5-R03 | Permissions (B5-D11) | One parametrized test over every nomination and dashboard endpoint × four roles; Operator 403 on nomination endpoints; Operator dashboard has only status counts and ETA items. |
| B5-R04 | Confidentiality of nomination text | Property test with unique markers in other offers, other counterparties and contacts, decision reason/note, internal comments, cancel reason, operator/requester/legal entity: none appears in subject, body or `mailto:` (live or frozen); the field set of `NominationContext` is pinned; exactly one recipient. |
| B5-R05 | Render correctness | Golden test: a fixed inquiry/offer renders exactly the expected subject and body for version 1 and an amendment (qty_mt exact, money `USD 1,234,567.89`). |
| B5-R06 | Status flow and amendments (B5-D1, D3, D8, D10) | First Mark sent moves Winner selected → Nominated through `can_transition`; later sends keep Nominated and increment the sequence; drafts only in Winner selected/Nominated; re-select winner after Nominated gives 409; a second draft gives 422; frozen texts unchanged after inquiry edits. |
| B5-R07 | Dashboard attention (B5-D6) | Each kind appears exactly at its threshold boundary (tested at boundary ± 1 s) and disappears when resolved (RFQs answered, nomination sent, inquiry cancelled). |
| B5-R08 | Dashboard figures (B5-D5, D12) | Exact expected values on a fixed data set: mt (incl. m³ conversion and excluded lines), spend (Σ decided_total), counts, average offers (exact decimal, 2 places half-up); month boundary at UTC midnight. |
| B5-R09 | Operator never sees commercial data (E4) | The B4-R09 property test is extended to the dashboard and nomination endpoints with nomination and KPI markers; still enumerates every API operation. |
| B5-R10 | Audit | Create, edit, send, withdraw and the inquiry transition write exactly one AuditEntry each, same transaction; history newest first. |
| B5-R11 | Screens and step budget (B0-R02) | Dashboard and S7 per §5; create and send a nomination ≤ 3 interactions from the inquiry page; scripted test; Storybook/visual and axe. |
| B5-R12 | Demo data (D-066) | Seed: the nominated demo inquiry has a sent nomination (one with an amendment); dashboard shows at least one item of each attention kind on fresh demo data; idempotent. |
| B5-R13 | Gates inherited | All S0–B4 gates green; coverage ≥ 90 %; `tools/trace.py --check` green. |

## 7. Out of scope

Informing losing suppliers; delivery tracking, invoices, claims, reports (pilot 2); charts; e-mail sending by the system.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Prices leak into an Operator view through the dashboard | B5-D11 role filter; B5-R09 property test over every operation. |
| Nomination text drifts from the decided offer | Rendered from the winning offer at send time; frozen; golden test. |
| Dashboard figures disagree with the comparison | Spend uses frozen `decided_total`; volume uses the same `quantity_mt` rule. |
