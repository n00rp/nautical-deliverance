# B5 Nomination and Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Versioned nomination e-mail drafts to the winner (completing pilot 1's purchase flow) and a role-filtered dashboard as the start page.

**Architecture:**
- `domain/nomination.py` holds the allow-listed `NominationContext`, `render_nomination` and the nomination transitions. It reuses `domain/rfq.build_mailto` and `format_instant`, and `domain/offer.evaluate_offer` and `format_qty_mt`.
- Migration `0006_nomination` adds the table and its trigger.
- `persistence/nomination_repo.py` contains `build_nomination_context`, which is the only DB→context mapper.
- The routers are `api/nominations.py` and `api/dashboard.py`, with `persistence/dashboard_repo.py` behind the dashboard.
- On the web side, `web/src/nominations/` holds S7, `web/src/dashboard/` holds the dashboard, and `nominationApi.ts` and `dashboardApi.ts` are the API clients.

**Tech Stack:** as B4.

**Spec:** [docs/superpowers/specs/2026-11-06-b5-nomination-dashboard-design.md](../specs/2026-11-06-b5-nomination-dashboard-design.md), covering all of B5-D1–D12 and B5-R01–R13. Patterns follow the [B3](2026-11-05-b3-supplier-selection-rfq.md) and [B4](2026-11-06-b4-offers-decision.md) plans.

## Global Constraints

- **Repo path:** exactly `C:\Programing\nautical deliverence` ("deliverence" with an e; the path contains a space). Never use the sibling folder `nautical deliverance`.
- **Gates:** all S0–B4 gates stay green.
  - Engine runs with the DB and `ND_REQUIRE_DB=1`, with coverage ≥ 90 % line and branch.
  - The web gates include jscpd at threshold 0 (it also scans `engine/src`) and the ESLint no-float rule on money paths.
  - Visual tests run in the pinned container.
  - Smoke runs from a cold start, and the licence check must pass.
- **Requirement tags:** use `req("B5-Rnn")` / `[B5-Rnn]`. At the end, `python tools/trace.py --check` exits 0 and `docs/traceability.md` is regenerated.
- **Layers:** `domain` imports no FastAPI or SQLAlchemy, and `persistence` imports no `api`.
- **Table rules:** `nomination` follows the B3 `rfq` rules. FORCE RLS, composite org FKs, `nd_app` gets `SELECT, INSERT, UPDATE` with no DELETE, and the sent fields are set exactly when `sent`, with an immutability trigger.
- **Money:** Decimal / `numeric` in the engine and decimal strings in JSON. Display as `USD 1,234,567.89`. qty_mt is exact (B4 R3).
- **Nomination statuses:** `draft`, `sent`, `withdrawn`. The allowed transitions are draft→sent and draft→withdrawn.
- **Subjects:**
  - first version: `Nomination <reference> – <vessel> – <port>`;
  - versions ≥ 2: `Amended nomination (<n>) <reference> – <vessel> – <port>`, using an en dash with spaces.
- **mailto rules:** as in B3. One address, only `subject` and `body` (≤ 1800 characters), never `cc`/`bcc`/`to`.
- **Permissions (B5-D11):**
  - Nominations: Admin and Bunker Buyer write; Admin, Bunker Buyer and Viewer read; Operator gets 403.
  - Dashboard: all roles. The Operator's response holds only `status_counts`, plus attention items of kind `eta_unnominated` without any money or offer data.
- **Errors:** as in B1–B4.
- **Demo data:** demo only (D-066).
- **Branch and commits:** work on `feat/b5-nomination`, which already holds the spec. Use Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.

## Review Focus

1. **The winner's contact is deactivated before nominating.** The draft defaults to another active contact of the same counterparty. If there is none, the API returns 422 on `contact_id` with the message "No active contact with e-mail". Task 3.
2. **ETA changes after a nomination was sent.** The frozen text stays unchanged, and `changed_since_sent` becomes true (same mechanism as B3). The amendment draft renders the new ETA. Tasks 3 and 6.
3. **An inquiry is cancelled while a nomination draft exists.** The draft can no longer be sent and gets 409. The dashboard drops the inquiry's attention items. Tasks 3 and 4.
4. **Month boundary.** A nomination first sent at 23:59:59 UTC on 30 Nov counts for November. An amendment sent in December does not move the inquiry to December. Task 4.
5. **Ties and m³ lines without density in the volume figure.** The volume is exact, the excluded-lines count is correct, and nothing is silently wrong. Task 4.

## File Structure

```
engine/src/nautical_deliverance/domain/nomination.py
engine/src/nautical_deliverance/persistence/migrations/versions/0006_nomination.py
engine/src/nautical_deliverance/persistence/{models.py,nomination_repo.py,dashboard_repo.py,seed.py}
engine/src/nautical_deliverance/api/{nomination_models.py,nominations.py,dashboard.py}
engine/tests/unit/test_nomination_domain.py, engine/tests/db/test_nomination_*.py, test_dashboard.py
web/src/{nominationApi.ts,dashboardApi.ts}, web/src/nominations/*, web/src/dashboard/*
```

---

### Task 1: Nomination rendering (B5-R04 domain, B5-R05)

**Files:** Create `domain/nomination.py` and `tests/unit/test_nomination_domain.py`.

**Interfaces — Produces:**
- `NominationStatus(StrEnum)` with the three values, plus `NOMINATION_TRANSITIONS` and `can_nomination_transition`.
- `NominationLine` is a frozen dataclass with fields `product`, `quantity`, `unit`, `density | None`, `qty_mt | None`, `price_per_mt`, `line_cost | None`, `in_total`.
- `NominationContext` is a frozen dataclass. It holds exactly the spec §3 allowed fields:
  - `reference`, `vessel_name`, `vessel_imo`, `port_name`, `port_locode`, `port_time_zone`;
  - `eta`, `etd`, `agent_name`;
  - `lines: tuple[NominationLine, ...]`;
  - `barging_cost`, `port_call_cost`, `agent_cost`, `surveyor_cost`, `other_cost`, `total`, `currency`;
  - `delivery_from`, `delivery_to`, `delivery_method`, `physical_supplier`, `payment_terms`;
  - `recipient_name`, `recipient_email`, `buyer_name`, `sequence`.
- `render_nomination(ctx) -> tuple[str, str]`:
  - Uses the subject rules above.
  - The body is a plain English confirmation: "We confirm the following nomination …".
  - Each line shows qty_mt (`format_qty_mt`), `USD x.xxx/mt` and its line cost. Then the fixed costs and the total in the `USD 1,234,567.89` format.
  - The delivery window is shown in UTC · local. Then the physical supplier and payment terms. Fields that are not given are printed as "to be advised".
  - It is signed with the buyer name and "Bunker desk". If there is no buyer name, it is signed "Bunker desk" alone.
- `format_usd(d: Decimal) -> str` gives `USD 1,234,567.89` with a leading `-` for negatives. Put it in `domain/offer.py` if it is missing there, and reuse it everywhere.

- [ ] **Step 1: Write the failing tests.**
  - `req("B5-R05")`: two golden texts written as literals in the test, one for version 1 and one for version 2 (amended). They must include an m³ line with an exact qty_mt such as `850.5008505`, a line not in total, and a DST-sensitive local time.
  - `req("B5-R04")`:
    - A field pin: the `dataclasses.fields` names of `NominationContext` and `NominationLine` are exactly the expected sets, and are disjoint from a FORBIDDEN list. The list contains `decision_reason`, `decision_note`, `internal_comments`, `cancel_reason`, `operator_name`, `requester_name`, `legal_entity_name`, `other_offers`, `offer_count`, `delta_to_lowest` and `lowest`.
    - A positive control: a marker placed in `physical_supplier` is found in the body.
    - The mailto has a single address, as in B3.
  - The transition table is exact.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_nomination_domain.py`. It should FAIL. **Step 3: Implement.** **Step 4:** run the tests and the gates. They should PASS.
- [ ] **Step 5: Commit** as `feat(engine): add nomination rendering`.

### Task 2: Schema (B5-R01 DB, B5-R02)

**Files:** Create `migrations/versions/0006_nomination.py` and `tests/db/test_nomination_schema.py`. Modify `persistence/models.py`.

**Interfaces — Produces:**
- The `nomination` table follows spec §2:
  - `offer_id` is a composite FK whose target ensures the offer belongs to the inquiry.
  - `contact_id` is a composite FK to the counterparty of the offer's RFQ. Use a trigger if a composite FK cannot reach it.
  - `status` has a check constraint.
  - `sequence` is an int, not null exactly when `sent`.
  - The five sent fields (`sent_at`, `sent_to_email`, `sent_subject`, `sent_body`, `inquiry_version_at_send`) are set exactly when status is `sent`. Use a biconditional check, as in B3 R4.
  - An immutability trigger protects the sent fields.
  - A partial unique index `nomination_one_draft_idx` on `(inquiry_id)` where status = `draft`.
  - A unique `(inquiry_id, sequence)` where `sent`.
  - Grants: `SELECT, INSERT, UPDATE`.
- Widen the audit action check with `nominate` if it is a closed list. Use the existing `send` and `withdraw` verbs, or add new ones, and record the choice.

- [ ] **Step 1: Write the failing tests.**
  - `req("B5-R01")`: accept and reject for every constraint and trigger. Commit fixtures first, run each negative in isolation and assert the constraint name (B4 lesson).
  - `req("B5-R02")`: RLS isolation.
  - No DELETE.
- [ ] **Step 2: Run the tests.** They should FAIL. **Step 3: Implement.** Check that upgrade and downgrade round-trip.
- [ ] **Step 4: Run the full suite.** It should PASS. **Step 5: Commit** as `feat(engine): add nomination schema with RLS`.

### Task 3: Nomination API (B5-R01 API, R02, R03 part, R04 API, R06, R10)

**Files:**
- Create `persistence/nomination_repo.py`, `api/nomination_models.py`, `api/nominations.py` and `tests/db/test_nomination_api.py`.
- Modify `main.py`.
- Modify `api/offers.py` so that select-winner after Nominated returns 409, if B4 does not already do so.

**Interfaces — Produces:** the routes from spec §4.
- `build_nomination_context(session, nomination) -> NominationContext` is the only mapper. It uses `offer_repo.inputs_for` and `evaluate_offer` for the line costs and the total.
- Preview of a draft is live. Preview of a sent version returns the frozen text.
- The list item is `{id, status, sequence, contact_name, email, sent_at, changed_since_sent, version}`. `changed_since_sent` uses re-render comparison, as in B3.

**Rules:**
- **Create** is allowed only when the inquiry is in `winner_selected` or `nominated`. Otherwise it returns 409.
  - The winner must exist.
  - If a draft already exists, return 422 on `inquiry_id` with "A nomination draft already exists".
  - The contact defaults to the winning RFQ's contact if it is active and has an e-mail. Otherwise use the first active contact with an e-mail of that counterparty. Otherwise return 422 on `contact_id` (Review Focus #1).
- **Mark-sent:**
  - Freeze the text, set `sequence = max(sent sequence) + 1`, and set `sent_at` from `get_now`.
  - If the inquiry is in `winner_selected`, move it to `nominated` through `_transition`, with the inquiry row locked and an inquiry audit entry.
  - Mark-sent on a cancelled inquiry returns 409 (Review Focus #3).
- **Select-winner** on a nominated inquiry returns 409 (B5-D10).

- [ ] **Step 1: Write the failing tests.**
  - `req("B5-R01")`: every 422 and 409 response.
  - `req("B5-R02")`: foreign ids.
  - `req("B5-R03")`: a role matrix covering every nomination route. The Operator gets 403.
  - `req("B5-R04")`: an API-level marker test. Put markers in every FORBIDDEN field that has a DB counterpart: the other offers' prices and texts, other counterparties and contacts, the decision reason and note, internal comments, the cancel reason, and the operator, requester and legal-entity names. None may appear in the live or the frozen subject, body or mailto. Iterate over the domain FORBIDDEN list.
  - `req("B5-R06")`:
    - the first send transitions the inquiry, an amendment keeps `nominated` and gets sequence 2 with the amended subject, and a second draft returns 422;
    - re-select after nominated returns 409;
    - frozen texts stay unchanged after an ETA edit, and `changed_since_sent` becomes true (Review Focus #2).
  - `req("B5-R10")`: one audit entry each for create, patch, send and withdraw, plus the transition.
- [ ] **Step 2: Run the tests.** They should FAIL. **Step 3: Implement.** Keep the router at about 300 lines or fewer, and keep jscpd clean by reusing the B3/B4 helpers in `api/access.py`.
- [ ] **Step 4: Run the full suite and the gates.** They should PASS. **Step 5: Commit** as `feat(engine): add nominations`.

### Task 4: Dashboard API and Operator safety (B5-R03 dashboard, R07, R08, R09)

**Files:** Create `persistence/dashboard_repo.py`, `api/dashboard.py` and `tests/db/test_dashboard.py`. Modify `main.py` and `tests/db/test_operator_never_sees_prices.py`.

**Interfaces — Produces:** `GET /api/v1/dashboard` with the shape from spec §4.
- `period` is `YYYY-MM`.
- The amounts are strings.
- `avg_offers` is a decimal string with 2 places, rounded half-up. It is null when there are no decided inquiries.

**Rules:**
- **The month** is the UTC calendar month of each inquiry's first sent nomination (sequence 1), taken from `get_now`.
- **Volume** sums `quantity_mt` of the winning offer's lines that are in total. `mt_excluded_lines` counts the winner's m³ lines that have no density.
- **Spend** is the sum of `decided_total` over those inquiries.
- **avg_offers** averages the offer count over the inquiries decided this month. Decided means `decided_at` falls in the month.
- **`open_by_status`** counts every status except `nominated` and `cancelled`. `status_counts` counts all statuses.
- **Attention kinds:**
  - `rfq_deadline`: an RFQ that is sent, has no offer, and whose response deadline is within 24 h.
  - `offer_validity`: the selected offer, or the lowest selectable offer when there is no winner, has `valid_until` within 24 h and the inquiry is not nominated.
  - `eta_unnominated`: the B2 rule. ETA is within 48 h, including an ETA that has already passed, and the inquiry is not nominated or cancelled.
  - `rfq_drafts_unsent`: the inquiry is in draft, rfq_sent or offers_received and has draft RFQs.
  - Cancelled inquiries never appear.
- **The Operator** gets `{attention: [only eta_unnominated items, with no detail beyond reference/vessel/port/due_at], status_counts}`. `month` is null.

- [ ] **Step 1: Write the failing tests.**
  - `req("B5-R07")`:
    - each kind appears exactly at its threshold, tested at boundary ± 1 s with a pinned clock;
    - each disappears when resolved;
    - a cancelled inquiry produces no items (Review Focus #3).
  - `req("B5-R08")`:
    - a fixed data set gives exact mt, including an m³ conversion with an exact non-3-decimal value and an excluded line;
    - exact spend, counts and avg_offers;
    - the month boundary from Review Focus #4.
  - `req("B5-R03")`: the dashboard per role. The Operator response contains only `status_counts` and `eta_unnominated` items.
  - `req("B5-R09")`: extend the B4-R09 property test. Add nomination text markers and KPI values, and keep the enumeration of every API operation through `app.openapi()`, which must include `/dashboard` and the nomination routes. Assert that no marker appears in any Operator response, including the dashboard.
- [ ] **Step 2: Run the tests.** They should FAIL. **Step 3: Implement.** **Step 4: Run the full suite and the gates.** They should PASS.
- [ ] **Step 5: Commit** as `feat(engine): add dashboard`.

### Task 5: Demo nominations (B5-R12)

**Files:** Modify `persistence/seed.py`, the seed tests and `tools/smoke.sh`.

- [ ] **Step 1: Write the failing tests**, tagged `req("B5-R12")`.
  - The nominated demo inquiry (DEMO-6) has sent nominations 1 and 2. Version 2 follows an ETA change, and its frozen text must equal `render_nomination(build_nomination_context(...))` at seed time.
  - On fresh demo data the dashboard has at least one item of each attention kind (the ETAs and deadlines are relative to seed time).
  - The seed is idempotent.
  - The denylist and `.example` checks still pass.
- [ ] **Step 2: Run the tests.** They should FAIL. **Step 3: Implement.**
- [ ] **Step 4: Smoke.** As the buyer, `GET /dashboard` returns `month` non-null and at least 1 attention item. As the operator, it returns `month` null. Run a cold smoke. It should PASS.
- [ ] **Step 5: Commit** as `feat(engine): seed demo nominations`.

### Task 6: Web nomination screen, S7 (B5-R11 part)

**Files:**
- Create `web/src/nominationApi.ts` and its test.
- Create `web/src/nominations/Nomination.tsx` with a test and stories.
- Add the route `#/inquiries/<id>/nomination`.
- Add the inquiry page actions "Create nomination" and "Amend nomination".
- Change the work-list next step to "Nominated (v<n>)".
- Show the Operator "Nominated: <supplier>".

**Screen:** reuse the RFQ preview, actions and mail-handoff components where possible, without jscpd clones. Extract shared ones if needed. The screen has:
- the exact preview;
- the contact select;
- Open in e-mail and Copy text;
- Mark sent through InlineConfirm, protected by an in-flight guard;
- Withdraw draft;
- the list of sent versions with their frozen text and a "Changed since sent" pill.

- [ ] **Step 1: Write the failing tests.**
  - `[B5-R11]`:
    - action visibility per status and role;
    - the mailto href equals the API value;
    - Copy text writes exactly the body;
    - the amended subject is shown;
    - after the first send the inquiry status shows "Nominated";
    - the Operator has no route access.
  - Budget test from the inquiry page: Create nomination → Mark sent → confirm takes ≤ 3 interactions. Use a counting `userEvent` wrapper, not a hand-incremented counter (B4 lesson).
  - Stories in light and dark, with axe.
- [ ] **Step 2: Run the tests.** They should FAIL. **Step 3: Implement.** **Step 4: Run the web gates.** They should PASS.
- [ ] **Step 5: Commit** as `feat(web): add nomination screen`.

### Task 7: Web dashboard and final verification (B5-R11, R13)

**Files:**
- Create `web/src/dashboardApi.ts` and `web/src/dashboard/Dashboard.tsx` with a test and stories.
- Change routing so that `#/` and an empty hash show the dashboard and the work list is at `#/inquiries`. Update the AppShell navigation with Dashboard, Inquiries and Master data.
- Regenerate `docs/traceability.md`.
- Add `# req: … B5-R13` to the ci.yml engine and web jobs.

**Screen:**
- **"Needs attention" list:** each item has a kind pill (warn or crit), its due time in UTC · local, and a link to the inquiry. Show EmptyState when there is nothing.
- **Status count tiles.**
- **Month figures:** `USD …` and `… mt` with "excl. n lines without density" when n > 0, plus avg offers. These are hidden when `month` is null (Operator).

- [ ] **Step 1: Write the failing tests.**
  - `[B5-R11]`:
    - the dashboard renders each attention kind;
    - the figures use exact strings, with no float (the ESLint rule covers `dashboard/**`);
    - the Operator view shows only counts and ETA items;
    - links navigate;
    - the start route is the dashboard.
  - Stories in light and dark with axe: full, empty, and Operator.
- [ ] **Step 2: Run the tests.** They should FAIL. **Step 3: Implement.**
- [ ] **Step 4: Final verification:**
  - engine gates with the DB, coverage ≥ 90;
  - all web gates, including jscpd exit 0, coverage ≥ 90/90, build and build-storybook;
  - visual tests in the container, regenerating only new or intended baselines, with a clean second run;
  - cold smoke;
  - licence check;
  - `python tools/trace.py`, then `--check`, which must exit 0 with B5-R01–R13 covered.
- [ ] **Step 5: Commit** as `feat(web): add dashboard start page`, including traceability.md.

## Spec coverage

| Requirement | Tasks |
|---|---|
| B5-R01 | 2, 3 |
| B5-R02 | 2, 3 |
| B5-R03 | 3, 4 |
| B5-R04 | 1, 3 |
| B5-R05 | 1 |
| B5-R06 | 3 |
| B5-R07 | 4 |
| B5-R08 | 4 |
| B5-R09 | 4 |
| B5-R10 | 3 |
| B5-R11 | 6, 7 |
| B5-R12 | 5 |
| B5-R13 | 7 |
