# B2 Inquiries — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user directory, inquiries with product lines, the status-flow function, the inquiry API, and the work list and inquiry pages, with demo data.

**Architecture:** This step follows the B1 patterns:
- Pure rules live in `domain/inquiry.py`: transitions, references and lock fields.
- Migration `0003` adds the new tables and the `app_user` columns, with RLS, grants and composite FKs as in `0002`.
- The router is `api/inquiries.py`. It reuses helpers that are moved out of `api/master.py` into `api/common.py`, with no change in behaviour.
- Audit goes through `record_change`.
- The web side adds `web/src/inquiries/` on top of the Part A components and the hash routing from `web/src/admin/routes.ts`.

**Tech Stack:** as B1.

**Spec:** [docs/superpowers/specs/2026-11-05-b2-inquiries-design.md](../specs/2026-11-05-b2-inquiries-design.md) covers all of B2-D1 to D12 and B2-R01 to R15. The patterns to follow are in [B1 Part B plan](2026-11-05-b1b-domain-master-data.md).

## Global Constraints

- **Gates:** all S0 and B1 gates stay green.
  - Engine gates run with the DB and `ND_REQUIRE_DB=1`.
  - Coverage is ≥ 90 % line and branch, checked by `tools/check_coverage.py`.
  - Web gates: typecheck, eslint, prettier, stylelint, depcruise, knip, jscpd.
  - Visual tests run in the pinned container. Smoke tests and the licence check must pass.
- **Requirement tags:** tag tests `@pytest.mark.req("B2-Rnn")` or `[B2-Rnn]`. `python tools/trace.py --check` exits 0 at the end, and `docs/traceability.md` is regenerated.
- **Layers:** `domain` imports no FastAPI or SQLAlchemy, and `persistence` imports no `api`.
- **Tables:**
  - Every new table has `organization_id` plus FORCE RLS (USING + WITH CHECK) and composite `(organization_id, id)` FKs.
  - `nd_app` gets `SELECT, INSERT, UPDATE` on `inquiry` and `inquiry_reference_counter`, and `SELECT, INSERT, UPDATE, DELETE` on `inquiry_line` only. Lines are part of the inquiry aggregate and their changes are audited on the inquiry.
- **Money and quantity:** values are `Decimal` and `numeric`, sent as JSON strings, and never floats (D-074).
- **Status values:** `draft`, `rfq_sent`, `offers_received`, `winner_selected`, `nominated`, `cancelled`.
- **Errors:** as B1. A 422 returns `{"detail":[{"field","message"}]}`. A stale `version` returns 409 `{"detail":"Record was changed by someone else"}`. A role that may not write gets 403. Another organization's id gets 404.
- **Demo data:** demo only. No real company or person names, and e-mails end in `.example` (D-066).
- **Branch and commits:**
  - Work on branch `feat/b2-inquiries`, which already holds the spec.
  - Use Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Do not push without the controller.
- **Host:** the host is Windows, so DB URLs use `127.0.0.1`. DB tests wipe the dev DB, so run smoke from a cold stack (`docker compose down -v`).

## Review Focus

1. **Two buyers Take the same unassigned inquiry at the same moment.** One succeeds, the other gets 409, and exactly one audit entry is written. Task 5.
2. **A reference is created at a month boundary.** An inquiry created at 23:59:59 UTC on 31 Oct gets `INQ-2610-…`, and one created at 00:00:00 UTC on 1 Nov gets `INQ-2611-001`. Task 4, by injecting the clock.
3. **A Draft line switches from m³ to mt while it still has a density.** The API returns 422 on `lines[i].density`, and the UI clears the density when the unit changes to mt. Tasks 4 and 8.
4. **The vessel is changed on a Draft after lines were entered.** Approved-fuel warnings are recomputed. The legal entity and operator are refilled only if they still hold the previous vessel's defaults. Tasks 4 and 8.
5. **A user later loses all roles but is still the buyer or requester on old inquiries.** Their name still displays on those inquiries, but they no longer appear in pickers. Tasks 3 and 7.

## File Structure

```
engine/src/nautical_deliverance/domain/inquiry.py            Status, TRANSITIONS, can_transition, format_reference, LOCKED_AFTER_DRAFT, line rules
engine/src/nautical_deliverance/api/common.py                helpers moved from master.py (scope, field errors, _Strict, check, email_ok, unprocessable, conflict)
engine/src/nautical_deliverance/api/users.py                 current_user dependency (upsert) + GET /users
engine/src/nautical_deliverance/api/inquiries.py             /api/v1/inquiries router
engine/src/nautical_deliverance/persistence/models.py        + AppUser columns, Inquiry, InquiryLine, InquiryReferenceCounter
engine/src/nautical_deliverance/persistence/inquiry_repo.py  next_reference, list query, warnings
engine/src/nautical_deliverance/persistence/migrations/versions/0003_inquiries.py
engine/src/nautical_deliverance/persistence/seed.py          + users, + inquiries
engine/tests/unit/test_inquiry_domain.py, engine/tests/db/test_inquir*.py, test_users.py
web/src/inquiryApi.ts                                        typed client
web/src/inquiries/{WorkList,InquiryPage,LinesEditor}.tsx (+ tests, stories), routes in web/src/admin/routes.ts
```

---

### Task 1: Inquiry domain rules (B2-R05 format, B2-R06, B2-R07 field set)

**Files:** Create `domain/inquiry.py` and `tests/unit/test_inquiry_domain.py`.

**Interfaces — Produces:**
- `class Status(StrEnum)`, with the six values.
- `TRANSITIONS: Mapping[Status, frozenset[Status]]`, holding exactly:
  - draft→{rfq_sent, cancelled};
  - rfq_sent→{offers_received, cancelled};
  - offers_received→{winner_selected, cancelled};
  - winner_selected→{nominated, cancelled};
  - nominated→{cancelled};
  - cancelled→∅.
- `can_transition(a: Status, b: Status) -> bool`.
- `format_reference(created_at: datetime, n: int) -> str`, which gives `f"INQ-{yymm}-{n:03d}"` with yymm taken from the UTC `created_at`. It rejects a naive datetime and n < 1.
- `LOCKED_AFTER_DRAFT: frozenset[str]`, which is `{"vessel_id", "legal_entity_id", "port_id", "bunkering_reason_id", "lines", "voyage", "operator_id", "requester_id"}`. The spec does not name voyage, operator or requester, so they lock too: only the B2-D5 editable list stays editable.
- `EDITABLE_AFTER_DRAFT = {"eta", "etd", "agent_name", "agent_email", "buyer_id", "internal_comments"}`.
- `class LineUnit(StrEnum)`, with `mt` and `m3`. Reuse `domain.master.Unit` if it has the same values.
- `DENSITY_MIN = Decimal("600")`, `DENSITY_MAX = Decimal("1100")`, `MAX_LINES = 10`.

- [ ] **Step 1: Write the failing tests.** All are tagged `req("B2-R06")` unless noted.
  - `test_transitions_exact`: compares against a literal copy of the table.
  - `test_cancel_from_every_non_cancelled`.
  - `test_cancelled_is_terminal`.
  - A Hypothesis property over all 36 status pairs: `can_transition(a, b) == (b in TRANSITIONS[a])`, and no self-transitions.
  - `req("B2-R05")`: `format_reference(datetime(2026,10,31,23,59,59,tzinfo=UTC),1) == "INQ-2610-001"`, `format_reference(datetime(2026,11,1,tzinfo=UTC),14) == "INQ-2611-014"`, `n=1000 → "INQ-2611-1000"`, a naive datetime raises `ValueError`, and n=0 raises `ValueError`.
  - `req("B2-R07")`: the two field sets are disjoint, and their union is every patchable inquiry field.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_inquiry_domain.py`. It should FAIL with an import error.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. It should PASS.
- [ ] **Step 5: Commit** as `feat(engine): add inquiry status and reference rules`.

### Task 2: Schema and RLS (B2-R02 DB, B2-R03)

**Files:** Create `migrations/versions/0003_inquiries.py`, modify `persistence/models.py`, and create `tests/db/test_inquiry_schema.py`. Follow `0002_master_data.py` for the RLS, grant and composite-FK helpers.

**Interfaces — Produces:** models with these columns:
- `AppUser` gains `name text not null default ''`, `email text not null default ''` and `roles text[] not null default '{}'`.
- `Inquiry` has:
  - `id`, `organization_id`, `reference text`, with `unique(organization_id, reference)`;
  - `status text`, with a check against the six values;
  - `vessel_id`, `legal_entity_id`, `port_id`, `bunkering_reason_id`, all composite FKs;
  - `voyage text null`, with a check `length ≤ 40`;
  - `operator_id`, `requester_id` (not null) and `buyer_id` (null), all FKs to `app_user`;
  - `eta`, `etd timestamptz not null`, with a check `etd >= eta`;
  - `agent_name text null`, `agent_email text null`;
  - `internal_comments text null`, with a check `length ≤ 4000`;
  - `cancel_reason text null`, with a check that `status='cancelled'` ⇔ `cancel_reason` is not null and non-blank;
  - `version int`, `created_at`, `created_by` and `updated_at`.
- `InquiryLine` has:
  - `id`, `organization_id`, `inquiry_id` (composite FK, on delete cascade), `position smallint` (1..10);
  - `product_id` (composite FK), with `unique(inquiry_id, product_id)` and `unique(inquiry_id, position)`;
  - `quantity numeric(12,3) > 0`;
  - `unit text`, with a check in `(mt, m3)`;
  - `density numeric(6,1) null`, with a check that it is between 600 and 1100 and only when `unit='m3'`;
  - `spec_notes text null`, with a check `≤ 500`;
  - `iso_spec_version_id not null`.
- `InquiryReferenceCounter` has `(organization_id, year_month char(4))` as the PK and `next_value int not null`.

- [ ] **Step 1: Write the failing tests.**
  - `req("B2-R02")`: each check and unique constraint has one accept case and one reject case, parametrized. A reject raises `IntegrityError` and names the constraint.
  - `req("B2-R03")`: for each of the 3 new tables, rows belonging to another organization are invisible and immutable, following the pattern in `test_rls.py`.
  - Grants: `nd_app` cannot DELETE from `inquiry` or `inquiry_reference_counter`.
- [ ] **Step 2: Run** `uv run pytest tests/db/test_inquiry_schema.py` with `ND_REQUIRE_DB=1`. It should FAIL.
- [ ] **Step 3: Implement** the migration (upgrade and downgrade) and the models. Then run `uv run alembic upgrade head`.
- [ ] **Step 4: Run** the tests again. They should PASS. The existing `test_master_schema` and `test_rls` must stay green.
- [ ] **Step 5: Commit** as `feat(engine): add inquiry schema with RLS`.

### Task 3: Shared API helpers and user directory (B2-R01)

**Files:**
- Create `api/common.py` and `api/users.py`.
- Modify `api/master.py` (import the moved helpers and drop their copies), `api/me.py` (reuse the upsert), `api/auth.py` and `domain/identity.py`.
- Modify `main.py`.
- Create `tests/db/test_users.py`.

**Interfaces — Produces:**
- `Principal` gains `name: str` and `email: str`. They come from the claims `name` (falling back to `preferred_username`) and `email`, and default to `""`.
- `api.users.current_user(principal, engine) -> Principal` is the dependency that upserts. It writes only if a field (name, email, roles) differs, or if `last_seen_at < now() - 1 h`. An org that is not accessible gives 403, as in `me.py`.
- `api.common` exports these with unchanged behaviour: `scope(principal, engine) -> Iterator[Session]`, `field_errors`, `validation_handler`, `unprocessable(field, message)`, `conflict()`, `Strict`, `check(ok, message)` and `email_ok(value)`.
- `GET /api/v1/users?role=<role>` returns `[{id, name, email, roles}]` sorted by name. It covers only the caller's org, only users whose `roles` contain a bunker role, and filters by `role` when one is given. All four roles may read it.
- The inquiry router (Task 4) puts `current_user` on every route.

- [ ] **Step 1: Write the failing tests**, all tagged `req("B2-R01")`.
  - The first request inserts the user with name, email and roles.
  - A second request within 1 h with the same claims writes nothing. Assert that `xmin` or `last_seen_at` is unchanged.
  - Changed roles are updated.
  - `GET /users?role=bunker_buyer` returns only that org's buyers.
  - A user whose roles became `[]` is excluded.
  - A second org's users are invisible.
  - Every existing master and me test passes unchanged, which shows the refactor is behaviour-neutral.
- [ ] **Step 2: Run** `uv run pytest tests/db/test_users.py`. It should FAIL.
- [ ] **Step 3: Implement.** Move the helpers into `common.py` without behaviour change, then add the dependency and the route.
- [ ] **Step 4: Run** the full engine suite and gates (ruff, mypy, lint-imports, vulture). Everything should PASS.
- [ ] **Step 5: Commit** as `feat(engine): add user directory`.

### Task 4: Inquiry create, read, list, edit (B2-R02 API, R04, R05, R07, R09, R10, R11, R12 perf)

**Files:** Create `api/inquiries.py`, `persistence/inquiry_repo.py` and `tests/db/test_inquiry_api.py`. Modify `main.py`.

**Interfaces:**
- **Consumes:** Task 1 rules, Task 2 models, Task 3 helpers and `current_user`, `record_change` from `persistence/audit.py`.
- **Produces:**
  - `InquiryIn` contains:
    - `vessel_id`, `legal_entity_id | None`, `voyage | None`;
    - `operator_id | None`, `buyer_id | None`, `requester_id | None`;
    - `port_id`, `eta`, `etd`, `agent_name | None`, `agent_email | None`;
    - `bunkering_reason_id`, `internal_comments | None`;
    - `lines: list[LineIn]` with 1–10 entries.
  - `LineIn` contains `product_id`, `quantity: str` (a decimal string), `unit`, `density: str | None`, `spec_notes | None` and `iso_spec_version_id`.
  - `InquiryOut` is the full record. It adds:
    - `reference`, `status` and `version`;
    - display names: `vessel_name`, `port_name`, `port_locode`, `port_time_zone`, `operator_name`, `buyer_name`, `requester_name`;
    - an `inactive` flag on each referenced master record;
    - `lines[]` with `not_in_total: bool`;
    - `warnings: [{field, code, message}]`, where the code is `not_approved_fuel`, the field is `lines[i].product_id` and the message is `"<product> is not an approved fuel for <vessel>"`.
  - `InquiryListItem` contains `id`, `reference`, `status`, `vessel_name`, `port_name`, `port_time_zone`, `eta`, `buyer_name | None` and `eta_warning: bool`.
  - Routes:
    - `GET /inquiries?status=<s>&q=<text>&mine=<bool>&sort=eta|reference`. The default excludes cancelled. `status=all` includes everything.
    - `GET /inquiries/{id}`.
    - `POST /inquiries`, returning 201.
    - `PATCH /inquiries/{id}`, with `version` and a partial body. When `lines` is present the lines are replaced as a set.
  - `inquiry_repo.next_reference(session, org_id, now) -> str` uses `INSERT … ON CONFLICT (organization_id, year_month) DO UPDATE SET next_value = counter.next_value + 1 RETURNING next_value - 1`, or an equivalent row-locked upsert that yields 1, 2, 3, …
  - The clock is injected as a dependency, `get_now() -> datetime`, so that tests can override it.

**Rules:**
- **Defaults on create:**
  - `legal_entity_id` comes from the vessel.
  - `operator_id` comes from the vessel's `default_operator`. Failing that, it is the caller, if the caller is an operator. Failing that, it is a 422 on `operator_id`.
  - `requester_id` is the caller.
  - `buyer_id` is the caller if the caller is a bunker_buyer or admin, otherwise null.
- **Validation:**
  - Inactive master data is rejected on create and edit with a 422 on that field. An unchanged inactive reference on PATCH is allowed.
  - `operator_id`, `buyer_id` and `requester_id` must be users of the org. An operator must have the operator or admin role, and a buyer must have bunker_buyer or admin.
  - A PATCH on a locked field when the status is not draft gives a 422 on that field with the message `"Locked after Draft"`.
  - A PATCH on a cancelled inquiry gives 409 with `{"detail":"Inquiry is cancelled"}`.
- **List warning:** `eta_warning` is true when the status is not nominated or cancelled and `now <= eta < now + 48 h`.

- [ ] **Step 1: Write the failing tests.**
  - `req("B2-R02")`: each API constraint returns a 422 with the right `field`:
    - `lines[0].quantity` set to `"0"` or `"abc"`;
    - `lines[0].density` sent on an mt line, or set to `"599.9"`;
    - an empty `lines`, 11 lines, or a duplicate product;
    - `etd` < `eta`;
    - an invalid `agent_email`;
    - `voyage` of 41 characters.
  - `req("B2-R04")`: one parametrized matrix of 4 roles × (list, get, create, patch). Create is allowed for admin, buyer and operator. Patch is allowed for admin and buyer.
  - `req("B2-R05")`:
    - 20 concurrent creates, using a thread pool and separate connections, yield `{INQ-2611-001 … INQ-2611-020}`;
    - a second org starts its own sequence at 001;
    - with a clock at 2026-10-31T23:59:59Z the reference is `INQ-2610-…`, and at the next second it is `INQ-2611-001`;
    - a cancelled inquiry's number is not reused.
  - `req("B2-R07")`: after the status is set to `rfq_sent` through the transition helper, each locked field gives 422 `Locked after Draft`, and each editable field saves.
  - `req("B2-R09")`:
    - `"0.1"` and `"999999999.999"` round-trip exactly as strings;
    - an m³ line without density has `not_in_total` true, and one with density has it false;
    - the Review Focus #3 case gives a 422.
  - `req("B2-R10")`:
    - a product the vessel is not approved for gives a 201 with the warning;
    - changing the vessel on a Draft recomputes the warnings (Review Focus #4, API side).
  - `req("B2-R11")`:
    - create writes 1 audit entry and patch writes 1;
    - a line change records `lines` with before and after;
    - a no-op patch writes 0;
    - a failed patch writes 0.
  - `req("B2-R12")`:
    - the eta_warning boundary at exactly 48 h is false, and at 47 h 59 m it is true;
    - the filters `status`, `q` (reference, vessel or port name) and `mine` (buyer = caller) work;
    - sorting works;
    - with 200 seeded inquiries, the list responds in under 300 ms, measured with `time.perf_counter` around the TestClient call and taking the median of 5 runs.
- [ ] **Step 2: Run** `uv run pytest tests/db/test_inquiry_api.py`. It should FAIL.
- [ ] **Step 3: Implement.** Keep the router under about 500 lines. The query and warning logic go in `inquiry_repo.py`.
- [ ] **Step 4: Run** the full engine suite and gates. Everything should PASS, with coverage ≥ 90.
- [ ] **Step 5: Commit** as `feat(engine): add inquiry API`.

### Task 5: Take, cancel, duplicate, history (B2-R06 API, R08, R11)

**Files:** Modify `api/inquiries.py` and create `tests/db/test_inquiry_actions.py`.

**Interfaces — Produces:**
- `POST /inquiries/{id}/take` with `{version}` sets the buyer to the caller. It is allowed for admin and buyer, and the inquiry must not be cancelled.
- `POST /inquiries/{id}/cancel` with `{version, reason}`. The reason is required, stripped, and 1–500 characters. The status change goes through `can_transition`.
- `POST /inquiries/{id}/duplicate` with `{version}` returns 201 with the new `InquiryOut`. It copies exactly the B2-D10 fields and gets a new reference and status draft. The buyer follows the create default.
- `GET /inquiries/{id}/history` follows the B1 history shape, newest first.
- The audit actions are `create`, `update`, `take`, `cancel` and `duplicate`. Extend the action enum or check constraint in `0003` if it is closed.

- [ ] **Step 1: Write the failing tests.**
  - `req("B2-R08")`:
    - a cancel without a reason, or with a blank one, gives 422 on `reason`;
    - a cancel with a reason sets the status to cancelled, and the reason shows in history;
    - duplicate copies exactly the B2-D10 field set, asserted field by field, including line contents, and leaves ETA/ETD, buyer and comments not copied.
  - `req("B2-R06")`:
    - take, cancel and patch on a cancelled inquiry each give 409;
    - duplicate on a cancelled inquiry is allowed.
  - Review Focus #1: two concurrent takes with the same version give exactly one 200, one 409 and one audit entry.
  - `req("B2-R11")`: each action writes exactly one entry, and history comes back newest first.
  - `req("B2-R04")`: extend the matrix with the three actions and history.
- [ ] **Step 2: Run** the tests. They should FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests. They should PASS, and the full suite stays green.
- [ ] **Step 5: Commit** as `feat(engine): add inquiry take, cancel and duplicate`.

### Task 6: Demo data (B2-R14)

**Files:** Modify `persistence/seed.py`, `tests/db/test_seed_master.py` (or create `test_seed_inquiries.py`) and `tools/smoke.sh`.

- [ ] **Step 1: Write the failing tests**, all tagged `req("B2-R14")`.
  - The seed inserts the 8 realm users into `app_user` with their name, email and roles, matching `infra/keycloak/realm-dev.json`.
  - Per org there are ≥ 6 inquiries:
    - ≥ 3 draft, at least 1 of them unassigned;
    - ≥ 1 cancelled with a reason;
    - ≥ 1 with an m³ line that has a density;
    - ≥ 1 with ETA within 48 h;
    - ≥ 1 with a not-approved-fuel warning.
  - ETAs are relative to the seed time.
  - References are in the B2-D3 format and the counters are consistent.
  - A second seed run changes nothing (idempotent).
  - The existing denylist and `.example` assertions still pass.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** the tests. They should PASS. Extend `tools/smoke.sh` so that it checks that `GET /api/v1/inquiries` as the buyer returns ≥ 1 item. Run the smoke test from cold. It should PASS.
- [ ] **Step 5: Commit** as `feat(engine): seed demo inquiries`.

### Task 7: Web client and work list (B2-R12 UI, B2-D8)

**Files:**
- Create `web/src/inquiryApi.ts` (+ test).
- Create `web/src/inquiries/WorkList.tsx` (+ `WorkList.test.tsx` and `WorkList.stories.tsx`).
- Modify `web/src/admin/routes.ts` to add `#/inquiries` and `#/inquiries/new|<id>`, and make the default route `#/inquiries`.
- Modify `App.tsx` to add an "Inquiries" nav item first, followed by "Master data".

**Interfaces:**
- **Consumes:** the Task 4 and 5 shapes, `ApiError`, the token handling in `api.ts` and `masterApi.ts` (one request helper; do not duplicate it), Part A `Table`, `StatusPill`, `Select`, `TextField`, `Checkbox`, `EmptyState`, `formatInstant`, and `RoleGate`.
- **Produces:** `listInquiries(params)`, `getInquiry(id)`, `createInquiry(body)`, `patchInquiry(id, version, body)`, `takeInquiry`, `cancelInquiry(id, version, reason)`, `duplicateInquiry`, `inquiryHistory` and `listUsers(role?)`, all typed. Decimals stay strings throughout.

**Work list:**
- **Columns:** Reference, Vessel, Port, ETA (`formatInstant(eta, port_time_zone)`), Status (StatusPill), Next step, and Buyer (shown as "Unassigned" when null).
- **Next step:** draft shows "Select suppliers", cancelled shows "—", and any other status shows the status label.
- **Warnings:** a row with `eta_warning` shows a crit "ETA in < 48 h, not nominated".
- **Filter:** status, with the default "Open" meaning everything except cancelled.
- **Search:** debounced 250 ms.
- **Sort:** ETA or reference.
- **Mine:** a toggle visible to buyers and admins.
- **New inquiry:** for admin, buyer and operator.
- **Empty state:** EmptyState.

- [ ] **Step 1: Write the failing tests**, all tagged `[B2-R12]` and using mocked fetch.
  - The columns render.
  - The status, search, Mine and sort filters send the right query.
  - The warning shows only when `eta_warning` is set.
  - The viewer sees no "New inquiry", and the operator does.
  - "Unassigned" shows when there is no buyer.
  - Review Focus #5: a buyer with no roles still displays by name, because the name comes from the API.
- [ ] **Step 2: Run** `pnpm -C web test --run`. It should FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** the web gates. They should PASS.
- [ ] **Step 5: Commit** as `feat(web): add inquiry work list`.

### Task 8: Inquiry page, step budget, final verification (B2-R13, R10 UI, R09 UI, R15)

**Files:**
- Create `web/src/inquiries/InquiryPage.tsx`, `LinesEditor.tsx` and `CancelAction.tsx` if needed.
- Add tests, `inquiryBudget.test.tsx` and `InquiryPage.stories.tsx`.
- Add visual baselines.
- Regenerate `docs/traceability.md`.

**Interfaces — Consumes:** Task 7 client and routes, the Part A form components (`NumberField` for quantity and density), `DateTimeField` with the port-zone hint, `DetailPanel`/`Panel`, `HistoryList`, `InlineConfirm`, `LockedNote`, `useToast`, and the 409/422 handling in `web/src/admin/errors.ts`. Reuse it; do not copy it.

**Page:**
- **Sections:** one page with the B0-D1 sections.
- **Vessel selection:** shows IMO, type and DWT. It fills the legal entity and operator only if they are empty or still equal to the previous vessel's defaults (Review Focus #4).
- **Lines:**
  - They can be added and removed, up to 10.
  - The density field is shown only for m³. Switching to mt clears it (Review Focus #3).
  - An m³ line without density shows "Not in total until density is given".
  - Warnings from the API show on their line, with a warn tone.
- **Internal comments:** the section is labelled "Internal — never sent to suppliers".
- **Actions:**
  - Save.
  - Take, shown when there is no buyer and the role is admin or buyer.
  - Cancel, through InlineConfirm with a required reason field.
  - Duplicate, which navigates to the new Draft.
  - A history panel.
- **Locked fields:** after Draft they render disabled with a LockedNote saying "Locked after Draft — duplicate to change scope".
- **Operator:** after creating, the operator sees the page read-only.
- **Viewer:** read-only.

- [ ] **Step 1: Write the failing tests.**
  - `[B2-R13]`:
    - vessel selection auto-fills, and the Review Focus #4 case;
    - locked fields after Draft;
    - the operator view is read-only after creating, and the viewer view is read-only;
    - a 422 maps to fields, including `lines[1].quantity`;
    - a 409 shows a toast and reloads;
    - Cancel requires a reason;
    - Duplicate navigates.
  - `[B2-R09]`: density is shown and cleared, and the not-in-total note appears.
  - `[B2-R10]`: the warning renders on the right line.
  - `[B2-R13]` budget: a scripted user-event run from the work list creates an inquiry with 2 product lines, with a counted click or field entry per interaction. Assert the count is ≤ 25 and record it.
  - Stories for Draft, Locked (rfq_sent) and Operator in light and dark, with axe.
- [ ] **Step 2: Run** the tests. They should FAIL. **Step 3: Implement**, using Part A components and tokens only.
- [ ] **Step 4: Final verification:**
  - engine gates with the DB, coverage ≥ 90;
  - all web gates, coverage ≥ 90/90, build and build-storybook;
  - visual in the container, regenerating only the new or intentionally changed baselines, with a clean second run;
  - `docker compose down -v`, then `bash tools/smoke.sh`, which should PASS;
  - the licence check;
  - `python tools/trace.py`, then `python tools/trace.py --check`, which should exit 0 with B2-R01 to R15 covered.
- [ ] **Step 5: Commit** as `feat(web): add inquiry page`, together with `docs/traceability.md`.

## Spec coverage

| Requirement | Tasks |
|---|---|
| B2-R01 | 3 |
| B2-R02 | 2, 4 |
| B2-R03 | 2 |
| B2-R04 | 4, 5 |
| B2-R05 | 1, 4 |
| B2-R06 | 1, 5 |
| B2-R07 | 1, 4 |
| B2-R08 | 5 |
| B2-R09 | 4, 8 |
| B2-R10 | 4, 8 |
| B2-R11 | 4, 5 |
| B2-R12 | 4 (API and perf), 7 |
| B2-R13 | 8 |
| B2-R14 | 6 |
| B2-R15 | 8 (final verification) |
