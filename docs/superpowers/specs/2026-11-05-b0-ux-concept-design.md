# B0 UX Concept — Specification

- **Status:** Approved by owner 2026-11-05
- **Traceability:** manual
- **Date:** 2026-11-05
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B0 (D-076)
- **Goal:** A clickable HTML prototype of the pilot 1 purchase flow, with demo data, that the brief's author reviews before anything is built. Design only — no backend, no persistence.

## 1. Decisions (confirmed by the owner)

| ID | Decision |
|---|---|
| B0-D1 | A new inquiry is created on **one page with sections** (vessel & voyage, port & timing, products, internal comments), not a step-by-step wizard. |
| B0-D2 | Offers are compared in a **table, one row per offer**, with a **detail panel** that opens for the selected row. The lowest total cost is highlighted. |
| B0-D3 | Besides product prices and fixed costs, an offer holds: **validity (valid until)** with an expiry warning, **payment terms**, **delivery window and method**, and **physical supplier / supplier comment** (for traders). |
| B0-D4 | A decision rationale is **required only when the selected offer is not the lowest total**: a reason from a list (flexibility, operational fit, availability, reliability, timing, payment terms, commercial judgement, other) plus free text. Optional otherwise. |
| B0-D5 | Inquiry status flow: Draft → RFQ sent → Offers received → Winner selected → Nominated; Cancelled reachable from every status. Pilot 2 adds Delivered → Invoiced → Closed after Nominated. |
| B0-D6 | Review format: a **clickable HTML prototype** with demo data, published as a private page the owner shares by link. |
| B0-D7 | The start page is a **work list** showing per inquiry: vessel, port, ETA; status and next step (e.g. "RFQ sent — 3 of 8 offers in"); deadline warnings (RFQ response deadline, offer validity, ETA near without nomination). |
| B0-D8 | Supplier selection pre-selects suppliers that, per master data, deliver **all** requested products in the inquiry's port; suppliers covering only some products, or not listed for the port, are shown unchecked. Each selected recipient gets its own RFQ draft. |

## 2. Assumptions to confirm with the brief's author

Marked **[ASSUMPTION]** until she confirms; the prototype is sized for them.

| ID | Assumption | Source |
|---|---|---|
| A1 | ~10 bunker inquiries per week. | Owner's estimate |
| A2 | ~15 suppliers/traders in total; RFQs per inquiry well below that. | Owner's estimate |
| A3 | ~10 inquiries open at the same time. | Owner's estimate |
| A4 | One buyer owns each inquiry; ownership need not be shown in the work list in pilot 1. | B0-D7 |
| A5 | A supplier offer covers some or all requested products; missing products are shown as "no offer" and excluded from that offer's total. | Owner-approved comparison preview |

## 3. Screens in the prototype

| # | Screen | Content | Roles |
|---|---|---|---|
| S1 | Work list (start page) | Per B0-D7; filter by status; "New inquiry". | All (Operator: no prices) |
| S2 | Inquiry (create/edit) | One page, sections per B0-D1: vessel (auto-filled particulars), voyage, operator, buyer, requester, entity; port, ETA, ETD, agent, bunkering reason; product lines (grade, quantity, unit, spec notes, ISO 8217 version); internal comments. | Create: Admin, Buyer, Operator. Edit: Admin, Buyer |
| S3 | Supplier selection | Per B0-D8. | Admin, Buyer |
| S4 | RFQ drafts and recipient log | One draft per recipient; "Open in e-mail" (`mailto:`), "Mark sent"; log per D-070 (recipient, contact, address, generated/sent time, status, response deadline, offer received). Draft preview shows exactly what the supplier will see. | Admin, Buyer |
| S5 | Offer entry | Manual entry per offer: product prices, fixed costs (barging, port call, agent, surveyor, other), and B0-D3 fields. Totals computed live. | Admin, Buyer |
| S6 | Offer comparison and decision | Per B0-D2; select winner; rationale per B0-D4. | Admin, Buyer (Viewer read-only) |
| S7 | Nomination | Nomination summary for the selected offer. | Admin, Buyer |
| S8 | Operator view | S1/S2 as seen by an Operator: status and selected supplier, **no prices, offers or rationale** (D-072). | Operator |

A role switcher in the prototype header lets the reviewer see each role's view.

## 4. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B0-R01 | Flow complete | The prototype lets a reviewer go S1 → S2 → S3 → S4 → S5 → S6 → S7 for one demo inquiry, and back to S1 with the status updated per B0-D5. |
| B0-R02 | Step budgets (E10) | From the work list: create an inquiry with 2 product lines ≤ 25 interactions; select suppliers and create RFQ drafts ≤ 5; enter one offer ≤ 15; select the lowest offer ≤ 3; select a non-lowest offer with rationale ≤ 6; create the nomination ≤ 3. An interaction is a click or a field entry. Budgets are measured on the prototype and listed in its notes. |
| B0-R03 | Correct totals | Demo totals follow the brief's formulas exactly (product line = quantity × price per mt; total = Σ lines + Σ fixed costs), shown in USD with 2 decimals; a worked example is visible in the detail panel. |
| B0-R04 | RFQ confidentiality visible | The RFQ draft preview contains only the recipient and inquiry details; it contains none of the D-070 forbidden items. |
| B0-R05 | Operator view | Switching to Operator hides every price, offer and rationale on every screen. |
| B0-R06 | Demo data anonymized (D-066) | Vessel, supplier, trader, person and company names are invented; e-mail addresses use `.example`; no real company names appear anywhere in the prototype. |
| B0-R07 | Craft (E11) and accessibility (E10) | Design tokens only (no ad-hoc colours/spacing), one icon set, no emoji icons, keyboard-operable, visible focus, WCAG 2.2 AA contrast, consistent units and formats (mt, USD, UTC with local port time). |
| B0-R08 | Review loop | The owner shares the link; her feedback is recorded as a list of findings in the repository (`docs/reviews/b0-review.md`, anonymized) and each finding is routed to the sub-project it affects (resolved there or explicitly deferred). Amended by D-078: her feedback is input, not a gate — B1 starts without it, and assumptions A1–A5 hold until she says otherwise. |

## 5. Out of scope
- Any backend, persistence, authentication, or real e-mail.
- Pilot 2 screens (delivery, invoice, claims, reports) — shown only as disabled menu items.
- Final visual design system (built in B1/B2 from this concept's tokens).

## 6. Risks

| Risk | Mitigation |
|---|---|
| Prototype mistaken for the real system | Persistent "Prototype — demo data" banner. |
| Assumptions A1–A5 wrong | Explicit list for her to confirm in the review (B0-R08). |
| Real company data slips into the prototype | B0-R06 checked before publishing. |
