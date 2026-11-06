# B4 Offers and Decision — Specification

- **Status:** Approved by owner 2026-11-06 (including proposed decisions B4-D9–B4-D14)
- **Date:** 2026-11-06
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B4 (D-076); D-071 (USD), D-072 (roles), D-074 (exact money), E3, E4; B0-D2, B0-D3, B0-D4, A5; B0 screens S5/S6; builds on [B2](2026-11-05-b2-inquiries-design.md) and [B3](2026-11-05-b3-supplier-selection-rfq-design.md).
- **Goal:** The buyer enters each supplier's offer manually against its sent RFQ, compares offers by exact total cost, and selects a winner — with a rationale whenever the choice is not the lowest complete offer.

## 1. Decisions

Confirmed by the owner in the B4 interview:

| ID | Decision |
|---|---|
| B4-D1 | **Rounding:** each product line cost is rounded **half-up to 2 decimals**; the total is the sum of the rounded line costs plus the fixed costs. Intermediate values are exact. |
| B4-D2 | **Lowest** is chosen among **complete** offers only (every requested line priced and in total). Partial offers are tagged "Partial", can be selected, and always require a rationale. Lowest is taken among complete offers that are currently selectable (RFQ sent, not expired). |
| B4-D3 | **One current offer per sent RFQ**, edited in place; every change is audited with before/after. |
| B4-D4 | An **expired** offer (valid until in the past) cannot be selected; the buyer first records the supplier's extended validity (an audited edit). |
| B4-D5 | Offers exist **only for sent RFQs** (at most one each). Entering the first offer marks the RFQ "offer received" and moves the inquiry RFQ sent → Offers received through `can_transition`. |
| B4-D6 | An m³ line takes its density from the inquiry line; when the inquiry has none, the **offer line** may carry the supplier's density. Without any density the line is not in total and the offer is partial. |
| B4-D7 | The winner can be **re-selected while the inquiry is Winner selected** (until nominated); rationale rules apply each time; every selection stays in history. |
| B4-D8 | **Payment terms** are free text; **delivery method** is one of Barge, Truck, Pipeline, Ex-wharf; the **delivery window** is two instants (from ≤ to). |

Proposed — confirmed by the owner's approval of this spec:

| ID | Decision | Rationale |
|---|---|---|
| B4-D9 | The cost rules live in one pure engine module; the engine is the authority. The web shows live totals with the same algorithm in **integer arithmetic (BigInt, scaled)**; one shared **test-vector file** is run by both the engine and web test suites. | Exactness without a decimal dependency; divergence fails a test. |
| B4-D10 | Precision: price per mt `numeric(12,3)` (> 0); fixed costs `numeric(12,2)` (≥ 0, default 0); density as B2 (`numeric(6,1)`, 600–1100); quantity in mt for m³ lines = quantity × density / 1000, exact; qty_mt is never rounded: it is shown and sent as the shortest exact decimal with at least 3 decimals, so the shown quantity × price always yields the shown line cost before rounding. All money displayed as `USD 1,234,567.89`. | Bunker prices are quoted to at most 3 decimals; costs to cents. |
| B4-D11 | Ties: all complete offers with the lowest total are "lowest"; selecting any of them needs no rationale. | Deterministic and fair. |
| B4-D12 | The **selected offer is locked** (no edits) while selected; to change it, select another offer first. At selection, the offer's total is **frozen** on the decision for audit. | The decision record must match what was decided. |
| B4-D13 | Rationale reasons: flexibility, operational fit, availability, reliability, timing, payment terms, commercial judgement, other (B0-D4); free text required when the reason is "other", optional otherwise (max 2000). | B0-D4. |
| B4-D14 | Permissions: enter/edit offers and select winner — Admin, Bunker Buyer; read offers, comparison, decision — Admin, Bunker Buyer, Viewer; **Operator: 403** on every offer, comparison and decision endpoint, and sees on the inquiry only the **selected counterparty's name** (program §4) — never prices, totals, offers or rationale. | D-072. |

## 2. Data model (organization-scoped, FORCE RLS, composite org FKs, audit, version; no DELETE grant)

| Entity | Fields |
|---|---|
| Offer | rfq (unique), inquiry, currency (`USD` only, check), valid_until (timestamptz, required), payment_terms (text ≤ 200, optional), delivery_from, delivery_to (timestamptz, optional, from ≤ to), delivery_method (`barge`, `truck`, `pipeline`, `ex_wharf`, optional), physical_supplier (text ≤ 200, optional), supplier_comment (text ≤ 2000, optional), barging_cost, port_call_cost, agent_cost, surveyor_cost, other_cost (`numeric(12,2)` ≥ 0, default 0), received_at, version, created_at, created_by, updated_at |
| OfferLine | offer, inquiry_line (same inquiry; unique per offer), price_per_mt (`numeric(12,3)` > 0), density (`numeric(6,1)` 600–1100, allowed only when the inquiry line is m³ without density) |
| Inquiry (added) | winner_offer (optional; must belong to the inquiry), decision_reason (enum per B4-D13, optional), decision_note (≤ 2000, optional), decided_at, decided_by, decided_total (`numeric(14,2)`) — set together at selection |

Rfq `offer_received` (B3) becomes true exactly when an offer exists for it.

## 3. Calculation (pure, `domain/offer.py`)

For each requested inquiry line *i* with offer line price *p*:

- quantity in mt *q* = quantity when unit is mt; quantity × density / 1000 when m³ (inquiry density, else offer-line density, else not in total).
- line cost = round_half_up(*q* × *p*, 2).
- Offer total = Σ line costs of in-total lines + barging + port call + agent + surveyor + other.
- Complete ⇔ every inquiry line has an offer line and is in total.
- Lowest = the minimum total among complete offers (all ties).
- Rationale required ⇔ the selected offer is not lowest (incl. partial).

Worked example (must be reproduced exactly by tests and shown in the detail panel): line A 500 mt × 612.345 = 306,172.50; line B 120 m³ × density 850.0 → 102.000 mt × 845.5 = 86,241.00; fixed 1,200.00 + 0 + 350.00 + 450.00 + 0 → total USD 394,413.50.

## 4. API (under `/api/v1/`)

`POST /rfqs/{id}/offer` (sent RFQ only; 201) · `GET /offers/{id}` · `PATCH /offers/{id}` (`version`; lines replaced as a set) · `GET /inquiries/{id}/comparison` → rows `{offer_id, rfq_id, counterparty_name, physical_supplier, lines:[{inquiry_line_id, product, qty_mt|null, price_per_mt|null, line_cost|null, in_total}], fixed costs, total, complete, lowest, delta_to_lowest|null, valid_until, expired, expiring_soon (< 24 h), delivery fields, payment_terms, selected}` plus the inquiry's decision · `POST /inquiries/{id}/select-winner` `{version, offer_id, reason?, note?}` · `GET /offers/{id}/history`. Amounts are JSON strings. Errors as B1–B3.

## 5. UI

- **S5 Offer entry** (from an RFQ log row "Enter offer" / "Edit offer"): one price field per requested line (blank = no offer), density field only where B4-D6 allows, the five fixed costs, B0-D3 fields; live line costs and total (exact, B4-D9); "Partial" note when incomplete.
- **S6 Comparison** (inquiry page → "Compare offers"): table one row per offer with counterparty (and physical supplier), coverage, total, delta to lowest, validity (warn < 24 h, crit expired), delivery window; lowest row highlighted, partial tagged; detail panel with per-line worked calculation; "Select winner" — direct for a lowest offer, with a rationale form otherwise; expired rows not selectable.
- Inquiry page and work list: next step "Compare n offers" (Offers received), "Create nomination" (Winner selected); Operator sees "Selected supplier: <name>" only.

## 6. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B4-R01 | Entities and constraints | Every field and constraint in §2 is enforced in DB and API (422 with a field error); accept and reject test each, incl. one offer per RFQ, offer only for a sent RFQ, line of the same inquiry, density rule, USD only, winner belongs to the inquiry. |
| B4-R02 | Organization isolation | Offer, offer line and decision fields are RLS-protected; another organization's rows are invisible and immutable; foreign ids give 404/422. |
| B4-R03 | Permissions (B4-D14) | One parametrized test covers every offer/comparison/decision endpoint × four roles; Operator 403 on all. |
| B4-R04 | Exact cost calculation (E3, D-074) | The §3 worked example and a set of shared test vectors (incl. half-up boundaries like x.xx5, m³ conversion, zero fixed costs, 3-decimal prices, large totals near `numeric(14,2)` limits) produce exactly the expected strings in engine and web; no float anywhere (static check: no `float(` / `Number(` / `parseFloat` on money paths). |
| B4-R05 | Lowest and completeness (B4-D2, B4-D11) | Property test over generated offer sets: lowest is exactly the set of minimum-total complete offers; partial offers are never lowest; deltas are exact. |
| B4-R06 | Rationale (B0-D4, B4-D13) | Selecting a lowest offer needs no rationale; any other selection without a reason gives 422; "other" without note gives 422; reason and note are stored and shown in history. |
| B4-R07 | Status flow (B4-D5, B4-D7) | First offer moves RFQ sent → Offers received; select-winner moves Offers received → Winner selected; re-selection keeps Winner selected; all through `can_transition`; offers cannot be entered or selected in Draft, Nominated or Cancelled (409). |
| B4-R08 | Validity and locking (B4-D4, B4-D12) | An expired offer cannot be selected (422 on `offer_id`); after extending validity it can; the selected offer cannot be edited (409); `decided_total` equals the offer's total at selection and does not change if another offer is edited. |
| B4-R09 | Operator never sees commercial data (E4, D-072) | Property test over generated inquiries with offers and decisions, with unique marker values in every price, cost, total, rationale and offer field: no marker appears in any response an Operator can obtain (inquiry list, get, history, users, RFQ and offer endpoints); the selected counterparty name is visible. |
| B4-R10 | RFQ text unaffected | Entering offers and decisions leaves every RFQ's live and frozen text unchanged (B3-R06 extended with offer markers). |
| B4-R11 | Audit | Offer create/update, first-offer inquiry transition and every selection write exactly one AuditEntry each in the same transaction; histories newest first. |
| B4-R12 | Screens and step budgets (B0-R02, E10) | S5 and S6 per §5 with Part A components; enter one offer with 2 lines and 2 fixed costs ≤ 15 interactions; select the lowest offer ≤ 3; select a non-lowest offer with rationale ≤ 6; asserted by scripted tests; Storybook/visual and axe as before. |
| B4-R13 | Demo data (D-066) | The seed adds offers for the demo inquiries with plausible invented prices (complete, partial, expired, and one decided inquiry with rationale); idempotent; totals consistent with §3. |
| B4-R14 | Gates inherited | All S0–B3 gates green; coverage ≥ 90 % line and branch; `tools/trace.py --check` green with all B4 requirements covered. |

## 7. Out of scope

Nomination (B5); currencies other than USD; price indices or formulas; attachments; automatic import of offers from e-mail.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Web and engine totals diverge | Shared test vectors run by both suites (B4-D9). |
| Operator sees prices through a new field later | B4-R09 property test scans every Operator-reachable response for markers. |
| Rounding disputes | One stated rule (B4-D1), worked example in the UI (B0-R03). |
