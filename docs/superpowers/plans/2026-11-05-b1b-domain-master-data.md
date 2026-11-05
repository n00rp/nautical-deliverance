# B1 Part B — Domain Model and Master Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bunker roles, all master-data entities with RLS and an append-only audit log, a versioned master-data API with the role matrix, demo seed data, and admin pages built on Part A's components.

**Architecture:** Follows S0 patterns exactly: SQLAlchemy 2 models in `persistence/`, Alembic migrations with RLS policies and grants (see `0001_identity_rls.py` and `infra/db/init/01-roles.sh`), per-transaction org context via `org_session`, FastAPI routers in `api/` using `get_principal`, pure validation in `domain/`. Audit entries are written by one persistence helper inside the same transaction as the change.

**Tech Stack:** as S0 (Python 3.14, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/PostGIS, Keycloak; React/TS for pages).

**Spec:** [docs/superpowers/specs/2026-11-05-b1-domain-and-design-system-design.md](../specs/2026-11-05-b1-domain-and-design-system-design.md) §3, B1-D1–D7, B1-D10–D12, B1-R01–R11, R15, R16. Depends on Part A ([plan](2026-11-05-b1a-design-system.md)) only for Task B6.

## Global Constraints

- All S0 gates green (engine gate list with DB, `ND_REQUIRE_DB=1`; coverage ≥ 90 % line and branch via `tools/check_coverage.py`; traceability; licences; smoke).
- Requirement tests tagged `@pytest.mark.req("B1-Rnn")` / `[B1-Rnn]`.
- Layer rules: `domain` imports no FastAPI/SQLAlchemy; `persistence` imports no `api`.
- Every master-data table: `organization_id` + RLS policy (USING + WITH CHECK, FORCE), `active boolean not null default true`, `created_at/updated_at timestamptz`; application role `nd_app` gets `SELECT, INSERT, UPDATE` — **never DELETE**. `audit_entry`: `SELECT, INSERT` only.
- No real company/person names in seed; e-mails end in `.example` (D-066).
- Errors: JSON `{"detail": ...}`; validation errors 422 with `{"detail": [{"field": ..., "message": ...}]}`.
- Branch: `feat/b1b-domain-master-data`; Conventional Commits ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; no push without the controller.

## Review Focus

1. **Two admins edit the same record concurrently** → optimistic concurrency: every update carries the record's `updated_at` (or a `version` integer); a stale write returns 409 and writes no audit entry. Task B4.
2. **Deactivated counterparty still referenced by coverage or a future inquiry** → stays resolvable by id, excluded from suggestion queries and default lists. Tasks B3, B4.
3. **Duplicate LOCODE / IMO / coverage triple within an org** → 422 field error, not 500. Tasks B2, B4.
4. **Audit "changes" for a no-op update (same values)** → no audit entry and 200 with unchanged record. Task B3.
5. **Org without seeded reference data (products, ISO, reasons)** → API returns empty lists, UI shows EmptyState; seed is idempotent per org. Task B5.

## File Structure

```
engine/src/nautical_deliverance/domain/master.py          validators: imo_valid, locode_valid, tz_valid; enums CounterpartyType, Unit
engine/src/nautical_deliverance/domain/identity.py         Role enum → admin, bunker_buyer, operator, viewer
engine/src/nautical_deliverance/persistence/models.py      + master-data models, AuditEntry
engine/src/nautical_deliverance/persistence/audit.py       record_change(...)
engine/src/nautical_deliverance/persistence/master_repo.py queries incl. coverage
engine/src/nautical_deliverance/persistence/migrations/versions/0002_master_data.py
engine/src/nautical_deliverance/persistence/seed.py        + demo master data
engine/src/nautical_deliverance/api/master.py              /api/v1/master/* router
engine/tests/{unit,db}/test_master_*.py
infra/keycloak/realm-dev.json                               roles + users per role × 2 orgs
web/src/admin/<Type>Page.tsx (+ tests)                      admin pages
```

---

### Task B1: Bunker roles (B1-R01)

**Files:** `domain/identity.py`, `api/auth.py` (role parsing), `infra/keycloak/realm-dev.json`, `tools/smoke.sh`, web `Role` usage, all tests referencing `route_analyst`.

**Interfaces — Produces:** `class Role(StrEnum): ADMIN="admin"; BUNKER_BUYER="bunker_buyer"; OPERATOR="operator"; VIEWER="viewer"`; dev users `<role>@acme.test` / `<role>@borealis.test` for the 4 roles (passwords = username, test-only).

- [ ] **Step 1: Failing tests:** `test_roles_are_bunker_roles` (`req("B1-R01")`): enum values exactly the four; a repo grep test asserts `route_analyst` appears nowhere under `engine/src`, `web/src`, `infra/`, `tools/` (S0b branch excluded by definition); token with role `route_analyst` → role ignored (unknown roles ignored as before).
- [ ] **Step 2: Implement**; update realm (roles, mappers unchanged, 8 users), smoke signs in as each role and checks `/me` roles.
- [ ] **Step 3: Run** engine gates + `bash tools/smoke.sh` → green. **Commit** `feat: switch to bunker procurement roles`.

### Task B2: Schema, RLS, grants, audit table (B1-R02, R04, R06 grants, R07 grants)

**Files:** `persistence/models.py`, `migrations/versions/0002_master_data.py`, `domain/master.py`, tests `db/test_master_schema.py`, `unit/test_master_validators.py`.

**Interfaces — Produces:** tables `legal_entity, vessel, vessel_approved_fuel, port, counterparty, contact, coverage, product, iso_spec_version, bunkering_reason, audit_entry` per spec §3.1 (FKs, uniques per org: `legal_entity(org, code)`, `vessel(org, imo)`, `port(org, locode)`, `coverage(org, counterparty_id, port_id, product_id)`; checks: IMO `^\d{7}$`, LOCODE `^[A-Z]{2}[A-Z2-9]{3}$`, DWT > 0); `domain.master.imo_valid(imo: str) -> bool`, `locode_valid(code: str) -> bool`, `tz_valid(name: str) -> bool` (via `zoneinfo`); `class CounterpartyType(StrEnum): PHYSICAL_SUPPLIER, TRADER, BOTH`; `class Unit(StrEnum): MT="mt"; M3="m3"`.

- [ ] **Step 1: Failing tests:** `unit`: IMO property test (`req("B1-R03")`, Hypothesis 1000 cases: generated 6 digits + computed check digit → True; any other 7th digit → False; 9074729 True); LOCODE accept/reject table; tz valid/invalid. `db` (`req("B1-R04")`): for every new table, org A cannot see/modify org B rows (parametrize over tables, reuse S0 RLS test helpers); (`req("B1-R06")`) `nd_app` has no DELETE privilege on master tables (`has_table_privilege`); (`req("B1-R07")`) `nd_app` has no UPDATE/DELETE on `audit_entry`; (`req("B1-R02")`) each DB constraint rejects a bad row.
- [ ] **Step 2: Implement** models + migration (RLS policies like 0001, grants), validators.
- [ ] **Step 3: Run** → green; `alembic downgrade -1` and `upgrade head` both work. **Commit** `feat(engine): add master-data schema with RLS and append-only audit table`.

### Task B3: Audit helper and repository queries (B1-R07, R09)

**Files:** `persistence/audit.py`, `persistence/master_repo.py`, tests `db/test_audit.py`, `db/test_coverage_queries.py`.

**Interfaces — Produces:**
- `record_change(session, *, actor: UUID, entity_type: str, entity_id: UUID, action: Literal["create","update","deactivate","reactivate"], before: Mapping[str, object] | None, after: Mapping[str, object]) -> AuditEntry | None` — computes per-field diff (values serialized to strings; Decimals as canonical strings, datetimes ISO UTC); returns None and writes nothing when the diff is empty (Review Focus 4).
- `counterparties_covering(session, port_id: UUID, product_ids: Sequence[UUID], *, mode: Literal["all","some"]) -> list[Counterparty]` — active counterparties only (Review Focus 2); "some" excludes those matching "all".

- [ ] **Step 1: Failing tests** (`req("B1-R07")`): create/update/deactivate each write exactly one entry with correct before/after; failure mid-transaction (raise after change) leaves no entry and no change; no-op update writes none. (`req("B1-R09")`): fixture with 4 counterparties and mixed coverage → exact sets for all/some; deactivated excluded.
- [ ] **Step 2: Implement.** **Step 3: Run** → green. **Commit** `feat(engine): add audit helper and coverage queries`.

### Task B4: Master-data API (B1-R02, R05, R06, R07)

**Files:** `api/master.py`, `main.py` (include router), tests `db/test_master_api.py`.

**Interfaces — Produces:** for each type `T` in `legal-entities, vessels, ports, counterparties, products, iso-spec-versions, bunkering-reasons`: `GET /api/v1/master/T?active=true|false|all&q=` (default `true`), `GET /api/v1/master/T/{id}`, `POST /api/v1/master/T`, `PATCH /api/v1/master/T/{id}` (body includes `version: int`; stale → 409), `POST /api/v1/master/T/{id}/deactivate`, `POST …/reactivate`, `GET …/{id}/history`; nested: `counterparties/{id}/contacts` (CRUD-without-delete), `counterparties/{id}/coverage` (PUT replaces the set; audited as one update with before/after sets); `GET /api/v1/master/counterparties/suggest?port_id=&product_id=…` → `{all: [...], some: [...]}`. Pydantic request/response models; writes require `Role.ADMIN`.

- [ ] **Step 1: Failing tests:** (`req("B1-R05")`) parametrized matrix: 4 roles × every endpoint × read/write → expected status (200/201 vs 403); (`req("B1-R02")`) 422 field errors for duplicate LOCODE/IMO/coverage triple and invalid formats (Review Focus 3); (`req("B1-R06")`) no DELETE routes registered (introspect `app.routes`), deactivated hidden by default, returned with `active=false|all`, resolvable by id; (`req("B1-R07")`) history endpoint newest first; Review Focus 1: concurrent PATCH with stale `version` → 409, no audit entry.
- [ ] **Step 2: Implement.** **Step 3: Run** → green. **Commit** `feat(engine): add master-data API with role matrix`.

### Task B5: Demo seed (B1-R10)

**Files:** `persistence/seed.py`, tests `db/test_seed_master.py`.

**Interfaces — Produces:** seeding per dev organization (idempotent): reference data (8 products, 5 ISO versions, 3 reasons), ≥ 2 legal entities, ≥ 6 vessels (valid IMOs, approved fuels), ≥ 10 real bunker ports with LOCODE + IANA zone (e.g. NLRTM Europe/Amsterdam, SGSIN Asia/Singapore, GIGIB Europe/Gibraltar, USHOU America/Chicago, AEFJR Asia/Dubai, BEANR Europe/Brussels, ESALG Europe/Madrid, plus two more major bunker ports of the implementer's choice — every LOCODE and zone verified against the official UN/LOCODE list and the IANA tz database, with the source recorded in the seed module docstring), ≥ 8 counterparties across the three types with contacts and coverage. Names invented (`Alpha Fuels`, …), e-mails `*.example`.

- [ ] **Step 1: Failing tests** (`req("B1-R10")`): counts ≥ minima; all contact e-mails end with `.example`; all IMOs valid; all LOCODEs/zones valid; running seed twice yields identical counts; a denylist test asserts no seed string contains configured real-company names (list in test: the pilot company's name and the major incumbent platform names).
- [ ] **Step 2: Implement.** **Step 3: Run** + smoke → green. **Commit** `feat(engine): seed demo master data`.

### Task B6: Admin pages (B1-R11, R08 display) — after Part A

**Files:** `web/src/admin/{LegalEntities,Vessels,Ports,Counterparties,Products,IsoVersions,Reasons}Page.tsx` + tests; `web/src/api.ts` (typed client for master endpoints); route wiring in `App.tsx` (hash or simple router — no new router dependency unless needed).

**Interfaces — Consumes:** Part A components (`AppShell`, `Table`, form fields, `DetailPanel`, `HistoryList`, `InlineConfirm`, `RoleGate`, `StatusPill`, `useToast`, `formatInstant`), master API (Task B4).

- [ ] **Step 1: Failing tests:** (`[B1-R11]`) each page lists, creates, edits, deactivates/reactivates and shows history (mocked API); non-admin roles see no edit controls (RoleGate); counterparty page edits contacts and coverage matrix; step budget test: scripted user-event run creating a counterparty with one contact and three coverage rows counts ≤ 15 interactions; 409 conflict shows a clear message and reloads the record; (`[B1-R08]`) port page shows local time hint via `formatInstant`.
- [ ] **Step 2: Implement** pages with Part A components only (no new styles outside tokens).
- [ ] **Step 3: Final verification:** engine gates with DB, web gates, stylelint, visual (new page stories if added), `bash tools/smoke.sh`, `python tools/trace.py --check` (all B1-R01–R16 covered), licence check. **Commit** `feat(web): add master-data admin pages`.

## Spec coverage
B1-R01 → B1 · R02 → B2, B4 · R03 → B2 · R04 → B2 · R05 → B4 · R06 → B2, B4 · R07 → B2, B3, B4 · R08 → (helper Part A) B6 · R09 → B3, B4 · R10 → B5 · R11 → B6 · R15/R16 → B6 final verification.
