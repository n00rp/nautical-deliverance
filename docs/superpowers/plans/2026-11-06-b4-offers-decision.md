# B4 Offers and Decision — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manual offer entry against sent RFQs, exact total-cost comparison, winner selection with rationale, and a guarantee that no commercial data ever reaches the Operator.

**Architecture:**
- **Calculation.** The cost rules are pure functions in `domain/offer.py`.
- **Test vectors.** One shared file, `contracts/offer-cost-vectors.json` at the repo root, is read by both the engine tests and the web tests.
- **Migration.** `0005_offers` adds `offer` and `offer_line` and the decision columns on `inquiry`.
- **API.** The routers are `api/offers.py` with `api/offer_models.py`. Queries live in `persistence/offer_repo.py`.
- **Status changes.** Inquiry status changes reuse `api/inquiries._transition` and `can_transition`, as B3 does.
- **Web.** The web client does exact money arithmetic in `web/src/money.ts` using BigInt. The screens go in `web/src/offers/`.

**Tech Stack:** as B3.

**Spec:** [docs/superpowers/specs/2026-11-06-b4-offers-decision-design.md](../specs/2026-11-06-b4-offers-decision-design.md), covering all of B4-D1–D14 and B4-R01–R14. Patterns follow the [B3 plan](2026-11-05-b3-supplier-selection-rfq.md).

## Global Constraints

- **Repo path:** exactly `C:\Programing\nautical deliverence` ("deliverence" with an e; the path contains a space). Never use the sibling folder `nautical deliverance`.
- **Gates:** all S0–B3 gates stay green.
  - Engine runs with the DB and `ND_REQUIRE_DB=1`, coverage ≥ 90 % line and branch.
  - Web gates include jscpd.
  - Visual tests run in the pinned container.
  - Smoke runs cold, and the licence check passes.
- **Requirement tags:** `@pytest.mark.req("B4-Rnn")` / `[B4-Rnn]`. At the end, `python tools/trace.py --check` exits 0 and `docs/traceability.md` is regenerated.
- **Layers:** `domain` imports no FastAPI or SQLAlchemy, and `persistence` imports no `api`.
- **New tables:** `organization_id`, FORCE RLS (USING + WITH CHECK), composite `(organization_id, id)` FKs, and `nd_app` `SELECT, INSERT, UPDATE` only. `offer_line` may also get DELETE (lines are replaced as a set, as `inquiry_line` was in B2).
- **Money:**
  - Decimal / `numeric` in the engine, and decimal strings in JSON.
  - BigInt scaled integers in the web. Never `float`, `Number(...)` or `parseFloat` on money, quantity or density.
  - Display format is `USD 1,234,567.89`.
- **Rounding (B4-D1):** each line cost is rounded half-up to 2 decimals. The total is the sum of the rounded lines plus the fixed costs.
- **Precision (B4-D10):**
  - price per mt `numeric(12,3)`, > 0;
  - fixed costs `numeric(12,2)`, ≥ 0, default 0;
  - density `numeric(6,1)`, 600–1100;
  - `decided_total` `numeric(14,2)`.
- **Delivery methods:** `barge`, `truck`, `pipeline`, `ex_wharf`.
- **Decision reasons:** `flexibility`, `operational_fit`, `availability`, `reliability`, `timing`, `payment_terms`, `commercial_judgement`, `other`.
- **Permissions (B4-D14):**
  - write: Admin and Bunker Buyer;
  - read: Admin, Bunker Buyer and Viewer;
  - Operator gets 403 on every offer, comparison and decision endpoint, and sees only `winner_counterparty_name` on the inquiry.
- **Errors:** as in B1–B3.
- **Demo data:** demo only (D-066).
- **Branch and commits:**
  - Work on `feat/b4-offers`, which already holds the spec.
  - Use Conventional Commits ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - No push.

## Review Focus

1. **The RFQ is withdrawn or declined after its offer was entered.** The offer stays in the comparison, marked with the RFQ status, and can still be selected only if the RFQ is `sent`. A declined RFQ's offer cannot be selected and gets 422 on `offer_id`. Tasks 3 and 4.
2. **An inquiry line is inactive or its product is deactivated after offers exist.** Totals stay computable from the stored data, and nothing breaks. Tasks 1 and 4.
3. **The quantity × price product is huge** (999,999,999.999 mt × 99,999.999). It must not overflow silently. The API returns 422 when a line cost or total would exceed `numeric(14,2)`. Tasks 1 and 3.
4. **Two buyers select different winners at the same time.** One succeeds, the other gets 409. There is exactly one decision and one audit entry. Task 4.
5. **The selected offer's RFQ contact or counterparty becomes inactive before nomination.** The decision stands, and the name still shows. Task 4.

## File Structure

```
contracts/offer-cost-vectors.json                         shared cases: inputs → exact expected strings
engine/src/nautical_deliverance/domain/offer.py           DeliveryMethod, DecisionReason, LineInput, OfferInput, LineResult, OfferResult, quantity_mt, line_cost, evaluate_offer, lowest, rationale_required, MAX_TOTAL
engine/src/nautical_deliverance/persistence/migrations/versions/0005_offers.py
engine/src/nautical_deliverance/persistence/models.py     + Offer, OfferLine, Inquiry decision columns
engine/src/nautical_deliverance/persistence/offer_repo.py comparison query, inputs builder
engine/src/nautical_deliverance/api/offer_models.py, api/offers.py
engine/tests/unit/test_offer_domain.py, engine/tests/db/test_offer_*.py
web/src/money.ts (+ test using the shared vectors), web/src/offerApi.ts
web/src/offers/{OfferEntry,Comparison,DecisionForm}.tsx (+ tests, stories)
```

---

### Task 1: Cost rules and shared vectors (B4-R04 engine, R05, R06 rule)

**Files:** Create `contracts/offer-cost-vectors.json`, `domain/offer.py` and `tests/unit/test_offer_domain.py`.

**Interfaces — Produces:**
- `DeliveryMethod` and `DecisionReason` are StrEnums with the Global Constraints values.
- `@dataclass(frozen=True) LineInput(line_id: str, unit: Literal["mt","m3"], quantity: Decimal, inquiry_density: Decimal | None, price_per_mt: Decimal | None, offer_density: Decimal | None)`.
- `@dataclass(frozen=True) OfferInput(offer_id: str, lines: tuple[LineInput, ...], fixed: tuple[Decimal, Decimal, Decimal, Decimal, Decimal])`.
- `quantity_mt(line) -> Decimal | None` is exact. It returns None for m³ with no density.
- `line_cost(qty_mt, price) -> Decimal` uses `quantize(Decimal("0.01"), ROUND_HALF_UP)`.
- `evaluate_offer(o) -> OfferResult(offer_id, lines: tuple[LineResult(line_id, qty_mt, line_cost, in_total)], total: Decimal, complete: bool)`. It raises `ValueError("total too large")` when `|total| > MAX_TOTAL = Decimal("999999999999.99")`.
- `lowest(results) -> frozenset[str]` returns the offer ids with the minimum total among complete offers. It is empty when no offer is complete.
- `rationale_required(selected_id, results) -> bool`.
- **Vector file:** `{"cases":[{"name", "offer": {lines:[{line_id, unit, quantity, inquiry_density, price_per_mt, offer_density}], fixed:[...]}, "expected": {lines:[{line_id, qty_mt, line_cost, in_total}], total, complete}}]}`.
  - All numbers are strings, and null is allowed.
  - Include at least:
    - the spec §3 worked example;
    - half-up boundaries (`0.005 → 0.01`, `0.004999 → 0.00`, a cost ending in exactly `5` at the 3rd decimal);
    - an m³ line with inquiry density;
    - an m³ line with offer density;
    - an m³ line with no density (not in total, incomplete);
    - a missing price (incomplete);
    - zero fixed costs;
    - 3-decimal prices;
    - a large total just under `MAX_TOTAL`.

- [ ] **Step 1: Write the failing tests.**
  - `req("B4-R04")`: every vector case gives exactly the expected strings, compared with `str()` after quantize.
  - `req("B4-R04")`: the worked example gives total `394413.50`.
  - `req("B4-R04")`: an over-limit total raises (Review Focus #3).
  - `req("B4-R05")`: a Hypothesis property over generated offer sets.
    - `lowest` equals `{o | complete and total == min(total of complete)}`.
    - Partial offers are never in it.
    - Ties are all included.
  - `req("B4-R06")`: `rationale_required` is False for every member of `lowest` and True otherwise, including partial offers.
  - A static test asserts that `domain/offer.py` source contains no `float(`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_offer_domain.py`. It should FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests and the gates. They should PASS.
- [ ] **Step 5: Commit** with `feat(engine): add exact offer cost rules`.

### Task 2: Schema (B4-R01 DB, B4-R02)

**Files:** Create `migrations/versions/0005_offers.py` and `tests/db/test_offer_schema.py`. Modify `persistence/models.py`.

**Interfaces — Produces:** the §2 tables with these constraints:
- `offer`:
  - `rfq_id` is unique and a composite FK to `rfq`;
  - `inquiry_id` is a composite FK, with a check or trigger that it equals the RFQ's inquiry;
  - `currency = 'USD'`;
  - text length checks;
  - `delivery_from <= delivery_to` when both are set;
  - the method check;
  - each cost ≥ 0.
- `offer_line`:
  - unique `(offer_id, inquiry_line_id)`;
  - the inquiry line must belong to the offer's inquiry, using a composite FK or trigger, following B3's contact pattern;
  - price > 0;
  - density range check.
  - The rule "density only when the inquiry line is m³ without density" is enforced by a trigger (it needs the other table) or by the API plus a DB trigger. Prefer the trigger.
- Inquiry columns:
  - `winner_offer_id` (composite FK to offer, with the offer's inquiry equal to this inquiry);
  - `decision_reason` (check against the reason values);
  - `decision_note` (≤ 2000);
  - `decided_at`, `decided_by` and `decided_total`;
  - a check that all of them are set or all are null, apart from reason and note, which are optional when a winner is set.
- Audit: widen `audit_entry.action` with `select_winner` if it is a closed list.

- [ ] **Step 1: Write the failing tests.**
  - `req("B4-R01")`: an accept case and a reject case per constraint.
  - `req("B4-R02")`: RLS isolation for `offer` and `offer_line`, and for the inquiry decision columns via the inquiry.
  - No DELETE on `offer`.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement**, following `0004_rfq.py`. Check that upgrade and downgrade round-trip.
- [ ] **Step 4: Run** the full suite. It should PASS. **Step 5: Commit** with `feat(engine): add offer schema with RLS`.

### Task 3: Offer entry API (B4-R01 API, R02, R03 part, R07 first offer, R10, R11)

**Files:** Create `persistence/offer_repo.py`, `api/offer_models.py`, `api/offers.py` and `tests/db/test_offer_api.py`. Modify `main.py`, and `persistence/rfq_repo.py` so that the log's `offer_received` reflects existence.

**Interfaces — Produces:**
- `POST /rfqs/{id}/offer`, with this body:
  - `{valid_until, payment_terms?, delivery_from?, delivery_to?, delivery_method?, physical_supplier?, supplier_comment?, barging_cost?, port_call_cost?, agent_cost?, surveyor_cost?, other_cost?, lines:[{inquiry_line_id, price_per_mt, density?}]}`
  - It returns 201 and `OfferOut`, which includes the computed `lines[].{qty_mt, line_cost, in_total}`, `total` and `complete` from `evaluate_offer`.
- `GET /offers/{id}`.
- `PATCH /offers/{id}`, with `version` and a partial body, where `lines` replaces the set.
- `GET /offers/{id}/history`.
- `offer_repo.inputs_for(session, offer) -> OfferInput` is the only mapper from DB rows to the domain.

**Rules:**
- **RFQ status.** The RFQ must be `sent`, otherwise 409 "RFQ is not sent". One offer per RFQ, otherwise 422 on `rfq_id` "Offer already entered".
- **Inquiry status.** The inquiry status must be `rfq_sent`, `offers_received` or `winner_selected`, otherwise 409.
- **First offer.** The first offer on an inquiry moves it from `rfq_sent` to `offers_received` through `_transition`, with an inquiry audit entry, in the same transaction, with the inquiry row locked.
- **Density.** Density on a line is allowed only for an m³ inquiry line without density, otherwise 422 on `lines[i].density`.
- **Totals.** A total over `MAX_TOTAL` gives 422 on `lines` (Review Focus #3).
- **Locking.** Editing the selected offer gives 409 "Selected offer is locked" (B4-D12).

- [ ] **Step 1: Write the failing tests.**
  - `req("B4-R01")`: each 422 and 409, with exact field paths.
  - `req("B4-R02")`: another org's RFQ or offer id gives 404, and another org's inquiry line id gives 422.
  - `req("B4-R03")`: start the parametrized role matrix for this task's routes. Operator gets 403, and Viewer can read but not write.
  - `req("B4-R07")`: the first offer transitions the inquiry, and a second one does not.
  - `req("B4-R10")`: after offers with marker values are entered, every RFQ's live preview and frozen text are byte-identical to before.
  - `req("B4-R11")`: create, update and the transition each write one audit entry. A no-op patch writes none.
  - The RFQ log shows `offer_received: true` after an offer exists.
  - Review Focus #1: an offer whose RFQ was later marked declined stays readable.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement**, keeping the router at about 400 lines or fewer.
- [ ] **Step 4: Run** the full suite and the gates. They should PASS. **Step 5: Commit** with `feat(engine): add offer entry`.

### Task 4: Comparison, selection, Operator safety (B4-R03, R05 API, R06, R07, R08, R09, R11)

**Files:** Modify `api/offers.py`, `persistence/offer_repo.py`, `api/inquiries.py` and `api/inquiry_models.py` (to add `winner_counterparty_name` and the decision fields with role filtering). Create `tests/db/test_offer_decision.py` and `tests/db/test_operator_never_sees_prices.py`.

**Interfaces — Produces:**
- `GET /inquiries/{id}/comparison` returns `{rows: [...per spec §4], decision: {winner_offer_id, reason, note, decided_at, decided_by_name, decided_total} | null}`. Rows are ordered by complete first, then total ascending, then counterparty name.
  - `expired` means `valid_until < now`.
  - `expiring_soon` means `now <= valid_until < now + 24 h`.
  - `delta_to_lowest` is `total − min complete total` for complete rows and null otherwise.
  - `rfq_status` is the RFQ's status.
- `POST /inquiries/{id}/select-winner` takes `{version, offer_id, reason?, note?}` and needs Editor role.
  - The status must be `offers_received` or `winner_selected`. The first selection transitions to `winner_selected` through `_transition`, and a re-selection keeps the status.
  - The offer must belong to the inquiry, its RFQ must be `sent`, and it must not be expired. Otherwise 422 on `offer_id`.
  - Rationale per `rationale_required`: a missing reason gives 422 on `reason`. Reason `other` with an empty note gives 422 on `note`.
  - Store `decided_total` from `evaluate_offer`, set `decided_at` and `decided_by`, and write one audit entry with action `select_winner`.
- Inquiry `GET`/list for each role:
  - The Operator gets `winner_counterparty_name` and nothing else about the decision.
  - The Viewer, Buyer and Admin also get `decision` (reason, note, decided_total).
  - The inquiry history for the Operator strips the decision fields (reason, note, decided_total, winner_offer_id), keeping only a "winner selected" entry with the counterparty name. Follow how B3 R6 filtered `rfq_deadline`.

- [ ] **Step 1: Write the failing tests.**
  - `req("B4-R05")`: the comparison API's `lowest` flags and deltas match `domain.offer.lowest` on a world that has a tie, a partial offer and an expired offer.
  - `req("B4-R06")`: lowest needs no reason. A non-lowest selection without a reason gives 422. `other` with no note gives 422. The stored reason and note appear in history.
  - `req("B4-R07")`:
    - selection transitions the inquiry, and re-selection keeps the status;
    - Draft, Nominated (set in DB) and Cancelled give 409 for both offer entry and selection.
  - `req("B4-R08")`:
    - an expired offer gives 422, and after extending its validity it is accepted;
    - the selected offer is locked;
    - `decided_total` is unchanged after another offer is edited.
  - Review Focus #4: concurrent selections give one 200, one 409 and one audit entry.
  - Review Focus #5: the decision still shows after the counterparty is deactivated.
  - `req("B4-R09")`: a property test using Hypothesis with a small `max_examples`.
    - Generate offers and a decision with unique marker values in every price, cost, note and offer text field, and pick decimal markers that are unlikely to collide.
    - As the Operator, call every route the Operator can reach: the inquiry list, the inquiry get and history, `/users`, `/me`, and every RFQ, offer and comparison route (403 bodies included).
    - Assert that no marker appears in any response body, and that the winner's counterparty name does appear in the inquiry get.
  - `req("B4-R03")`: complete the role matrix over every B4 route.
  - `req("B4-R11")`: one audit entry per selection.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite and the gates. They should PASS. **Step 5: Commit** with `feat(engine): add offer comparison and winner selection`.

### Task 5: Demo offers (B4-R13)

**Files:** Modify `persistence/seed.py`, the seed tests and `tools/smoke.sh`.

- [ ] **Step 1: Write the failing tests**, tagged `req("B4-R13")`.
  - The seed adds offers to the demo inquiries in `offers_received`, `winner_selected` and `nominated`. Include:
    - at least 1 complete offer;
    - at least 1 partial offer;
    - at least 1 expired offer;
    - one decided inquiry with a non-lowest winner and its rationale.
  - Use plausible invented prices: about USD 500–900/mt for fuels and about USD 700–1,200/mt for gasoil and biofuels.
  - `decided_total` must equal `evaluate_offer` of the winner.
  - Each RFQ with an offer must be `sent`.
  - The seed must be idempotent.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement**, reusing `offer_repo.inputs_for` and `evaluate_offer`.
- [ ] **Step 4:** Smoke: as the buyer, `GET /inquiries/{id}/comparison` returns at least 1 row, and as the operator it returns 403. Run a cold smoke. It should PASS.
- [ ] **Step 5: Commit** with `feat(engine): seed demo offers`.

### Task 6: Web money and offer entry, S5 (B4-R04 web, R12 part)

**Files:**
- Create `web/src/money.ts` and its test, which reads `../../contracts/offer-cost-vectors.json`.
- Create `web/src/offerApi.ts`.
- Create `web/src/offers/OfferEntry.tsx` with a test and stories.
- Add a route `#/inquiries/<id>/rfqs/<rfqId>/offer`.
- Add "Enter offer" / "Edit offer" actions in `RfqLog` for sent RFQs, for writers.

**Interfaces — Produces:**
- `money.ts`, all exact, built on BigInt scaled by 10^n:
  - `parseDecimal(s: string, scale: number): bigint` throws on invalid input or too many decimals;
  - `formatDecimal(v: bigint, scale: number): string`;
  - `quantityMt(line)`, `lineCost(qtyMt, price)` (half-up to cents) and `evaluateOffer(input)`, with the same semantics as the engine;
  - `formatUsd(s: string) -> "USD 1,234,567.89"`.
- `offerApi.ts`: `createOffer`, `getOffer`, `patchOffer`, `offerHistory`, `getComparison` and `selectWinner`.
- **Screen:**
  - one price field per requested line, labelled with product, quantity and unit, where blank means no offer;
  - a density field only where B4-D6 allows it;
  - five fixed-cost fields, valid until (DateTimeField with a port hint), delivery from/to, a delivery method Select, payment terms, physical supplier and comment;
  - live line costs and total from `evaluateOffer`, with a "Partial" note when the offer is incomplete;
  - Save maps 422 errors to fields.

- [ ] **Step 1: Write the failing tests.**
  - `[B4-R04]`: every shared vector case gives exactly the expected strings in TypeScript.
  - A static test asserts that `money.ts` and `OfferEntry.tsx` contain no `parseFloat(`, `Number(` or `toFixed(`.
  - `[B4-R12]`:
    - live totals update;
    - the density field appears only when allowed;
    - 422 mapping;
    - an Operator has no route access;
    - budget: entering one offer with 2 lines, 2 fixed costs and valid-until, then saving, takes ≤ 15 interactions. Assert the exact count.
  - Stories in light and dark, with axe.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement.** **Step 4: Run** the web gates. They should PASS.
- [ ] **Step 5: Commit** with `feat(web): add offer entry with exact totals`.

### Task 7: Comparison and decision, S6, plus final verification (B4-R12, R14)

**Files:**
- Create `web/src/offers/Comparison.tsx` and `DecisionForm.tsx`, with tests and stories.
- Add a route `#/inquiries/<id>/offers`.
- Add the inquiry page action "Compare offers".
- Change the work-list next steps.
- Show the Operator "Selected supplier: <name>".
- Regenerate `docs/traceability.md`.
- Add `# req: … B4-R14` to the ci.yml engine and web jobs.

**Screen:**
- **Table.** One row per offer: Counterparty (physical supplier underneath), Coverage ("Complete" / "Partial n of m"), Total, Δ to lowest, Valid until (warn when less than 24 h remain, crit when expired), Delivery window and Status.
  - The lowest row is highlighted with a token-based style plus a "Lowest" pill.
  - The selected row carries a "Selected" pill.
- **Detail panel.** A per-line worked calculation, `102.000 mt × USD 845.500 = USD 86,241.00`, then the fixed costs, then the total.
- **Selecting the winner.**
  - "Select winner" on a lowest row asks for confirmation through InlineConfirm.
  - On any other row it opens DecisionForm: reason Select and note TextArea. The note is required when the reason is "other".
  - Expired and declined rows cannot be selected.
  - An in-flight guard applies.
- **Inquiry page and work list.**
  - The next step is "Compare n offers" when the inquiry is in offers_received, and "Create nomination" when it is in winner_selected.
  - The Operator sees only "Selected supplier: <name>".
  - The Viewer sees everything, read-only.

- [ ] **Step 1: Write the failing tests.**
  - `[B4-R12]`:
    - lowest highlight, partial tag and validity tones;
    - the worked calculation in the panel;
    - lowest selection without a form;
    - a non-lowest selection requires a reason, and "other" requires a note;
    - expired rows are not selectable;
    - Operator and Viewer views.
  - Budgets: selecting the lowest takes ≤ 3 interactions, and selecting a non-lowest offer with rationale takes ≤ 6. Assert the exact counts.
  - Stories in light and dark with axe, covering: complete only, a tie, partial plus expired, and decided.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement.**
- [ ] **Step 4: Final verification:**
  - engine gates with the DB, coverage ≥ 90;
  - all web gates, coverage ≥ 90/90, build and build-storybook;
  - visual in the container, regenerating only new or intended baselines, with a clean second run;
  - cold smoke;
  - licence check;
  - `python tools/trace.py`, then `--check`, which must exit 0 with B4-R01–R14 covered.
- [ ] **Step 5: Commit** with `feat(web): add offer comparison and winner selection`, including traceability.md.

## Spec coverage

| Requirement | Tasks |
|---|---|
| B4-R01 | 2, 3 |
| B4-R02 | 2, 3 |
| B4-R03 | 3, 4 |
| B4-R04 | 1, 6 |
| B4-R05 | 1, 4 |
| B4-R06 | 1, 4 |
| B4-R07 | 3, 4 |
| B4-R08 | 4 |
| B4-R09 | 4 |
| B4-R10 | 3 |
| B4-R11 | 3, 4 |
| B4-R12 | 6, 7 |
| B4-R13 | 5 |
| B4-R14 | 7 |
