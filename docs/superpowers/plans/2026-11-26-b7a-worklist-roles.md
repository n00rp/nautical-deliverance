# B7a Work List, Operator Name and Two-Role Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship B7 part a. The work list gets three phase tabs and a prominent search. Duplicate is removed. The operator becomes a free-text name. Pilot buyers can hold the bunker buyer and admin roles on one login.

**Architecture:**
- The engine gets a `phase` filter, `phase_counts` and an Alembic migration `0007` that replaces two user-id columns with name columns. The Duplicate endpoint is deleted.
- The web replaces the status Select with tabs, makes the operator fields text inputs, and links the dashboard tiles.
- `tools/pilot_user.py` takes repeated `--role` and an `--add-role` mode.
- `tools/trace.py` learns a `Planned:` header so that the B7b and B7c requirements can sit in the approved spec before their tests exist.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Alembic, PostgreSQL 17 with RLS, pytest (`@pytest.mark.req`); React and TypeScript, Vitest with Testing Library (`[ID]` in test names), Storybook with Playwright visual and axe.

**Spec:** `docs/superpowers/specs/2026-11-26-b7-pilot1-feedback-design.md`, approved 2026-11-26.

## Global Constraints

- UI copy is English. The tab labels are exactly `On the list`, `In the market` and `Stemmed`, followed by the count in parentheses, for example `In the market (5)`. The toggle is labelled `Show cancelled`. The search hint is `Reference, vessel or port`.
- Phases:
  - `list` = `draft`
  - `market` = `rfq_sent`, `offers_received`, `winner_selected`
  - `stemmed` = `nominated`
  - `cancelled` = `cancelled`
- The default tab is `market` (B7-D18).
- The operator name is optional, at most 120 characters, trimmed, with an empty string stored as null. It applies to both `inquiry.operator_name` and `vessel.default_operator_name` (B7-D10).
- The D-072 Operator role, its permissions and its confidentiality tests stay unchanged (B7-D7).
- The commit footer is `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit locally only. Push and the PR happen when the owner approves.
- Gates stay as before:
  - coverage ≥ 90 % line and branch
  - `python tools/trace.py --check` green
  - ruff, mypy and the web lint, typecheck, unit and visual suites
- Engine tests run from `engine/` with `uv run pytest`. Web tests run from `web/` with `pnpm exec vitest run`.

## Review Focus

1. **Existing live data without an operator user.** After `0007`, an inquiry whose `operator_id` points to a user without a name keeps the user's e-mail as `operator_name`, the same fallback as `_shown`. This is tested in Task 3.
2. **Search across tabs.** A search that matches only cancelled inquiries shows `(0)` in all three tabs. It does not show a blank list with no hint, and the empty state reads `Nothing matches this search in this tab.`. This is tested in Task 4.
3. **Locked operator name after Draft.** `operator_name` stays in `LOCKED_AFTER_DRAFT`, as `operator_id` was, so a PATCH after Draft gives 422 "Locked after Draft". This is tested in Task 3.
4. **Whitespace-only operator name.** `"   "` is stored as null, not as an empty or blank string. This is tested in Task 3.
5. **`--add-role` for an e-mail that does not exist.** It exits 2 with `no user with e-mail …` and changes nothing. It must not create the user. This is tested in Task 6.

---

### Task 1: Spec requirement ids per part and a `Planned:` marker in trace.py

**Files:**
- Modify: `tools/trace.py`
- Test: `tools/test_trace.py`. Add to it if it exists. If not, create it next to the other `tools/test_*.py`, and check how the current trace tests are named with `grep -rn "trace" tools/test_*.py`.
- Modify: `docs/superpowers/specs/2026-11-26-b7-pilot1-feedback-design.md` (§6 and the header)
- Modify: `docs/traceability.md`, regenerated

**Interfaces:**
- Produces: the spec header line `- **Planned:** B7b, B7c`. Requirements whose id starts with a listed prefix followed by `-R` are exempt from the `no test` error and are rendered in the matrix as `| B7b-R01 | planned |`. A referenced planned id is not "unknown". Tasks in B7b and B7c remove their prefix from this line.

- [ ] **Step 1: Write the failing tests.** Build a temporary `--root` with one spec whose first 20 lines contain `- **Planned:** B9b`, with rows `| B9a-R01 |` and `| B9b-R01 |`, and one test that references `req("B9a-R01")`.
  - `test_planned_requirement_needs_no_test`: `main(["--root", tmp])` returns 0, and the matrix contains `| B9b-R01 | planned |`.
  - `test_unplanned_requirement_still_needs_a_test`: removing the `Planned` line makes `main` return 1, with `B9b-R01: no test` on stderr.
- [ ] **Step 2: Run them.** Run `uv run --project engine pytest tools/test_trace.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Add `_planned(spec: Path) -> tuple[str, ...]` in `tools/trace.py`. It reads the head lines with the same 20-line window as `_is_manual`, parses `- **Planned:** a, b`, and returns the prefixes.
  - In `main`, a requirement `r` is exempt when `r.split("-R")[0]` is among the planned prefixes of its spec.
  - `render` writes `planned` for an exempt row with no refs.
- [ ] **Step 4: Renumber the B7 requirements in the spec.**
  - The single §6 table becomes three tables (`### B7a`, `### B7b`, `### B7c`). Keep each row's text, and renumber as follows:
    - B7a-R01 = old R01, B7a-R02 = R02, B7a-R03 = R03, B7a-R04 = R04, B7a-R05 = R11
    - B7a-R06 = R12 (B7a screens), B7a-R07 = R13
    - B7b-R01 = R05, B7b-R02 = R06, B7b-R03 = R07, B7b-R04 = R08
    - B7b-R05 = R12 (B7b screens), B7b-R06 = R13
    - B7c-R01 = R09, B7c-R02 = R10, B7c-R03 = R12 (B7c screens), B7c-R04 = R13
  - Update the §7 "Requirements" column to the new ids.
  - Add `- **Planned:** B7b, B7c` and `- **Traceability:** per part (B7a, B7b, B7c), each with its own ids` under Status.
- [ ] **Step 5: Run.** Run `uv run --project engine pytest tools/test_trace.py -v` (PASS). Then run `python tools/trace.py`. Expected: it exits 1 listing only the `B7a-R0x: no test` lines, which later tasks cover. Do not regenerate the matrix until Task 7.
- [ ] **Step 6: Commit.** Commit with `chore(trace): planned requirement prefixes; B7 ids per part`.

### Task 2: Phase filter and phase counts on the work list API (B7a-R01, B7a-R02)

**Files:**
- Modify: `engine/src/nautical_deliverance/domain/inquiry.py`. Add `PHASES: dict[str, frozenset[Status]]` with the four phases from Global Constraints.
- Modify: `engine/src/nautical_deliverance/persistence/inquiry_repo.py:97-138`. `list_rows` gains `phase: str | None`. Add `phase_counts(session, *, q: str | None, buyer: uuid.UUID | None) -> dict[str, int]`.
- Modify: `engine/src/nautical_deliverance/api/inquiries.py:294-320` (`list_inquiries`) and `api/inquiry_models.py`.
- Test: `engine/tests/db/test_inquiry_api.py`.

**Interfaces:**
- Produces: `GET /api/v1/inquiries?phase=list|market|stemmed|cancelled` returns the existing list. When `phase` is given, it filters by the phase's statuses and takes precedence over `status`. An unknown phase gives 422 on `phase`.
- Produces: `GET /api/v1/inquiries/phase-counts?q=&mine=` returns `{"list": int, "market": int, "stemmed": int, "cancelled": int}`, for every role, honouring `q` and `mine`. This is a separate endpoint so the list response stays a JSON array: the web and older tests rely on it, and it amends spec §3, which put the counts on the list response.

- [ ] **Step 1: Write the failing tests.** Tag every test `@pytest.mark.req("B7a-R01")`, and add `"B7a-R02"` on the search ones.
  - `test_phase_returns_exactly_its_statuses`: parametrized over the four phases. Seed one inquiry per status with the existing helpers, and assert the returned statuses equal `PHASES[phase]`.
  - `test_phase_counts_follow_search`: two vessels, `q` = one vessel's name, so the counts include only matches. Review Focus 2: a `q` matching only a cancelled inquiry gives `{"list": 0, "market": 0, "stemmed": 0, "cancelled": 1}`.
  - `test_unknown_phase_is_422`: the field is `phase`.
  - `test_phase_counts_every_role_and_org_isolation`: Operator gets 200, and another org's inquiries are not counted.
- [ ] **Step 2: Run.** Run `uv run pytest tests/db/test_inquiry_api.py -k phase -v`. Expected: FAIL (404 or 422).
- [ ] **Step 3: Implement.**
  - `list_rows(..., phase=...)` adds `Inquiry.status.in_([s.value for s in PHASES[phase]])`.
  - `phase_counts` is one `select(Inquiry.status, func.count())` with the same joins and `q`/`buyer` filter, grouped by status and folded into phases. Factor the shared `q` filter out of `list_rows` into `_search(stmt, q)` so both functions use it.
  - Register the route `/phase-counts` **before** `/{inquiry_id}`.
- [ ] **Step 4: Run.** Run the same command. Expected: PASS. Then run the full `uv run pytest tests/db/test_inquiry_api.py`. Expected: PASS.
- [ ] **Step 5: Commit.** Commit with `feat(engine): work-list phases and phase counts`.

### Task 3: Operator as name and migration 0007 (B7a-R04)

**Files:**
- Create: `engine/src/nautical_deliverance/persistence/migrations/versions/0007_operator_name.py`
- Modify: `persistence/models.py`:
  - Inquiry: `operator_id` is replaced by `operator_name: Mapped[str | None]`.
  - Vessel: `default_operator` is replaced by `default_operator_name: Mapped[str | None]`.
- Modify: `api/inquiry_models.py`:
  - `InquiryIn.operator_id` is replaced by `operator_name: OperatorName | None = None`.
  - `OperatorName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]`, with a validator that turns `""` into `None`.
  - Remove `operator_id` from `never_null`.
  - `InquiryOut`: `operator_id` and `operator_name: str` are replaced by `operator_name: str | None`.
- Modify: `api/inquiries.py`:
  - Delete `OPERATOR_ROLES` uses for the operator, the `"operator_id"` entry of `USER_ROLES` and `_check_refs`'s loop, `_default_operator` and `"operator_id"` in `DUPLICATED` (Task 5 deletes `DUPLICATED`).
  - Create sets `values["operator_name"] = body.operator_name if "operator_name" in body.model_fields_set else vessel.default_operator_name`.
- Modify: `api/master.py:124`. `VesselIn.default_operator` is replaced by `default_operator_name: OperatorName | None = None`. Import `OperatorName` from `inquiry_models`, or move it to `api/common.py` if that avoids a cycle.
- Modify: `domain/inquiry.py:45`. In `LOCKED_AFTER_DRAFT`, `"operator_id"` becomes `"operator_name"`.
- Modify: `persistence/inquiry_repo.py:198-226`. Drop the `operator` alias and join, and read `Inquiry.operator_name`.
- Modify: `persistence/seed.py:520-545` and the master seed, so vessels get invented `default_operator_name` values (R6: invented names such as `Olga Operator`, `Per Ops`).
- Test: `engine/tests/db/test_inquiry_schema.py`, `test_inquiry_api.py`, `test_master_api.py` and a new `engine/tests/db/test_migration_0007.py`.

**Interfaces:**
- Consumes: Task 2's `list_rows` (unchanged signature).
- Produces:
  - The JSON fields `operator_name: string | null` on inquiry in, patch and out, and `default_operator_name: string | null` on vessel in and out.
  - No `operator_id` or `default_operator` anywhere.

- [ ] **Step 1: Write the failing tests.** Tag them `@pytest.mark.req("B7a-R04")`.
  - `test_0007_copies_operator_names`. Use the repo's migration test pattern; find it with `grep -rln "alembic" engine/tests`, and if none exists, use `alembic.command.upgrade` and `downgrade` against the test database.
    - At `0006`, insert an inquiry whose operator user has name `Olga Operator`, one whose user has no name and e-mail `ops@x.example` (Review Focus 1), and a vessel whose `default_operator` is a known user.
    - Upgrade to `0007` and assert the names `Olga Operator` and `ops@x.example` and the vessel default name.
    - Downgrade to `0006` and assert that `operator_id` exists and is nullable.
  - `test_create_prefills_operator_from_vessel`: no `operator_name` in the body gives the vessel's name. An explicit `null` gives null.
  - `test_operator_name_validation`: 121 characters give 422 on `operator_name`. `"  Per Ops  "` is stored as `Per Ops`. `"   "` is stored as null (Review Focus 4).
  - `test_operator_name_locked_after_draft`: PATCH after RFQ sent gives 422 `Locked after Draft` (Review Focus 3).
  - `test_operator_id_is_gone`: POST with `operator_id` gives 422 (Strict forbids extra fields). `operator_id` is absent from `GET /inquiries/{id}`. In the engine code, `grep -rn "operator_id\|default_operator\b" engine/src` returns nothing.
  - `test_vessel_default_operator_name_roundtrip` in `test_master_api.py`.
- [ ] **Step 2: Run.** Run `uv run pytest tests/db -k "operator or 0007" -v`. Expected: FAIL.
- [ ] **Step 3: Write `0007_operator_name.py`** (`revision = "0007"`, `down_revision = "0006"`).
  - **Upgrade:**
    - `ALTER TABLE inquiry ADD COLUMN operator_name text CHECK (char_length(operator_name) <= 120)`.
    - `UPDATE inquiry i SET operator_name = coalesce(nullif(u.name, ''), u.email) FROM app_user u WHERE u.id = i.operator_id`.
    - `ALTER TABLE inquiry DROP COLUMN operator_id`.
    - The same for `vessel`: `default_operator_name`, filled from `app_user` where `id = default_operator`, then drop `default_operator`.
    - Run the UPDATEs with RLS in mind. Migrations run as the owner, so check how 0002–0006 handle FORCE RLS and follow that.
  - **Downgrade:** add `operator_id uuid REFERENCES app_user (id)` (nullable) and `default_operator uuid`, then drop the name columns.
  - Grants: follow 0003's grant lines for the new columns, if column grants are used.
- [ ] **Step 4: Change the models, API, repo and seed** per Files.
- [ ] **Step 5: Run.** Run `uv run pytest tests -q`. Expected: all PASS, including the existing D-072 and E4 Operator tests (`test_operator_never_sees_prices.py`). Fix any test that built inquiries with `operator_id` by passing `operator_name`.
- [ ] **Step 6: Commit.** Commit with `feat(engine): operator as a name (B7-D10), migration 0007`.

### Task 4: Web work list tabs, search first, dashboard links (B7a-R01, B7a-R02, B7a-R06)

**Files:**
- Modify: `web/src/inquiryApi.ts`:
  - `ListParams` gains `phase?: Phase`.
  - Add `type Phase = "list" | "market" | "stemmed" | "cancelled"` and `phaseCounts(params: {q?: string; mine?: boolean}): Promise<Record<Phase, number>>`, which calls `GET inquiries/phase-counts`.
- Modify: `web/src/inquiries/WorkList.tsx`:
  - Remove `Filter`, `STATUS_OPTIONS` and the status Select.
  - Add tabs as a `role="tablist"` with three `role="tab"` buttons and `aria-selected`. Use the existing design-system tabs component if `web/src/ui` has one (check with `ls web/src/ui`). Otherwise use plain buttons in `WorkList.module.css`.
  - Add the `Show cancelled` Checkbox. When checked, it loads `phase=cancelled` and the tabs show `aria-selected=false`.
  - Order the filter row as: search TextField first (label `Search`, hint `Reference, vessel or port`), then Sort, then Mine.
  - The phase comes from the hash query `#/inquiries?phase=stemmed`, defaulting to `market`, so dashboard links work. Changing tabs updates the hash with `history.replaceState`.
- Modify: `web/src/dashboard/Dashboard.tsx:~104`. Each status-count `<dd>` value becomes `<a href="#/inquiries?phase=…">` per B7-D21 (draft → list; rfq_sent, offers_received, winner_selected → market; nominated → stemmed). Statuses without a phase, such as cancelled, stay plain text.
- Modify: `web/src/App.tsx`, if its router strips the query, so `#/inquiries?phase=x` still renders WorkList.
- Modify: `web/src/inquiries/WorkList.stories.tsx` (stories `AsBuyer` and `AsViewer` keep their ids; add `phaseCounts` to the mock api), `web/src/dashboard/*.stories.tsx` if the mock needs it, and the visual baselines (CI regenerates them; follow how B5 updated baselines, see `web/tests/visual/README*` or `package.json` scripts).
- Test: `web/src/inquiries/WorkList.test.tsx`, `web/src/dashboard/Dashboard.test.tsx`, `web/src/inquiryApi.test.ts`.

**Interfaces:**
- Consumes: Task 2's endpoints.
- Produces: the hash format `#/inquiries?phase=<Phase>`.

- [ ] **Step 1: Write the failing tests.** Put `[B7a-R01]` or `[B7a-R02]` in each name.
  - `[B7a-R01] shows three tabs with counts and opens In the market`: tabs named `On the list (1)`, `In the market (2)`, `Stemmed (3)`. The first `listInquiries` call has `phase: "market"`.
  - `[B7a-R01] clicking a tab loads that phase and updates the hash`: clicking Stemmed calls with `phase: "stemmed"`, and `location.hash` becomes `#/inquiries?phase=stemmed`.
  - `[B7a-R01] the hash selects the tab`: `#/inquiries?phase=list` gives On the list selected.
  - `[B7a-R01] Show cancelled lists only cancelled`: the call has `phase: "cancelled"`, and no tab is selected.
  - `[B7a-R02] search is the first filter and filters within the tab`: the first field in the filter row is `Search` with the hint text. Typing calls both `listInquiries` and `phaseCounts` with `q` and the current phase.
  - `[B7a-R02] a search with no hits in the tab says so`: with counts all 0, the text is `Nothing matches this search in this tab.` (Review Focus 2).
  - `[B7a-R01] dashboard status tiles link to their tab`: in `Dashboard.test.tsx`, `Winner selected` links to `#/inquiries?phase=market`, and `Nominated` links to `#/inquiries?phase=stemmed`.
  - Remove or adapt the old status-filter tests, keeping their requirement ids where the behaviour still exists.
- [ ] **Step 2: Run.** Run `pnpm exec vitest run src/inquiries/WorkList.test.tsx src/dashboard`. Expected: FAIL.
- [ ] **Step 3: Implement** per Files.
- [ ] **Step 4: Run.** Run `pnpm exec vitest run`, `pnpm exec tsc --noEmit -p .` and `pnpm exec eslint .`. Expected: all PASS.
- [ ] **Step 5: Commit.** Commit with `feat(web): work-list phase tabs, search first, dashboard links (B7-D4, D18, D20, D21)`.

### Task 5: Remove Duplicate, operator name in the forms (B7a-R03, B7a-R04)

**Files:**
- Engine:
  - `api/inquiries.py`: delete `duplicate_inquiry`, `DUPLICATED`, and the `"duplicate"` literal and `extra` in `_create` if nothing else uses them. Keep `VersionIn` for take, and fix its docstring to "Body of take".
  - `persistence/audit.py:20`: keep the `"duplicate"` action, because history rows from before must still render. Add the comment `# historic: Duplicate was removed in B7 (B7-D5)`.
  - `persistence/seed.py:~592`: remove the Duplicate-specific comment and logic if it only served Duplicate. The seed must stay idempotent; `test_seed_inquiries.py` proves it.
- Web:
  - `inquiryApi.ts`: delete `duplicateInquiry`.
  - `inquiries/InquiryPage.tsx:~240-252`: delete the Duplicate button.
  - `inquiries/InquiryForm.tsx:~185-195`: the operator Select becomes a TextField `operator_name` (label `Operator`, maxLength 120).
  - `inquiries/formModel.ts`:
    - `operator_id` becomes `operator_name`.
    - The vessel refill uses `default_operator_name`.
    - Empty is sent as `null` explicitly when the user cleared it. When the field is untouched on create, it is omitted, so the engine prefills.
  - `inquiries/InquiryPage.tsx:49-59`: drop `operators`.
  - `inquiries/pageSupport.ts`: use the fixture field names.
  - `admin/configs.tsx`, vessel fields: add `{ key: "default_operator_name", label: "Default operator", kind: "text", required: false }`.
- Docs:
  - In `docs/superpowers/specs/2026-11-05-b2-inquiries-design.md`, mark the B2-D10 row `**Withdrawn by B7-D5 (2026-11-26).**`.
  - In the same spec, B2-D5's "cancel and duplicate" becomes "cancel and create a new inquiry".
- Test: `engine/tests/db/test_inquiry_actions.py` (delete the duplicate tests and add the gone test), `web/src/inquiries/InquiryPage.test.tsx`, `web/src/admin/MasterDataPage.test.tsx`.

**Interfaces:**
- Consumes: Task 3's JSON field names.

- [ ] **Step 1: Write the failing tests.**
  - `@pytest.mark.req("B7a-R03") test_duplicate_endpoint_is_gone`: `POST /inquiries/{id}/duplicate` gives 404 or 405.
  - `[B7a-R03] the inquiry page has no Duplicate action`: no button named `Duplicate` for any role or status.
  - `[B7a-R04] the operator is a text field prefilled from the vessel`: choosing vessel 1 fills `Operator` with its `default_operator_name`. Editing it sends `operator_name`.
  - `[B7a-R04] vessel admin edits Default operator`.
  - Move the existing `[B2-R..]` Duplicate tests out (delete them). Leave a requirement id uncovered only if trace still finds other tests for it; check this in Step 4.
- [ ] **Step 2: Run** the engine tests with `uv run pytest tests/db/test_inquiry_actions.py -v` and the web tests with `pnpm exec vitest run src/inquiries src/admin`. Expected: FAIL.
- [ ] **Step 3: Implement** per Files.
- [ ] **Step 4: Run everything.** Run `uv run pytest tests -q`, `pnpm exec vitest run`, `pnpm exec tsc --noEmit -p .` and `pnpm exec eslint .`, then run `python tools/trace.py`. No `B2-Rxx: no test` may appear. If the B2-D10 requirement row has lost all its tests, mark that row in the B2 spec as `Withdrawn (B7-D5)`, keeping the id with its test reference via the new `test_duplicate_endpoint_is_gone` tagged with both ids. Do not delete the row.
- [ ] **Step 5: Commit.** Commit with `feat: remove Duplicate (B7-D5); operator name in forms`.

### Task 6: pilot_user.py with several roles and `--add-role` (B7a-R05)

**Files:**
- Modify: `tools/pilot_user.py`:
  - `--role` becomes `action="append"`, with at least one required. Every role must be in `ROLES`.
  - Add `--add-role`, a flag that changes the mode and needs only `--email`, `--role` and `--admin-user`. It finds the user by exact e-mail and posts the listed realm roles.
  - Exit codes:
    - 0 = done
    - 2 = no user, or several users, for that e-mail (message `no user with e-mail <email>`)
    - The existing ones otherwise
  - The create flow posts all roles in one role-mapping call.
- Modify: `docs/deploy/oracle-runbook.md` §12. Add a two-role example and the add-role command:
  ```
  python3 tools/pilot_user.py --admin-user admin --email <her e-mail> --add-role --role admin
  ```
  Use the same heredoc form as the existing §12 example.
- Test: `tools/test_pilot_user.py`, run in CI by the `pilot-user` job against a real Keycloak.

**Interfaces:**
- Produces: `create_user(args, admin_password) -> str` (unchanged, where `args.role` is now `list[str]`) and `add_roles(args: argparse.Namespace, admin_password: str) -> None`.

- [ ] **Step 1: Write the failing tests.** Tag them `@pytest.mark.req("B7a-R05")`.
  - `test_create_with_two_roles`: the user has both `bunker_buyer` and `admin` realm roles.
  - `test_add_role_to_existing_user`: create with `bunker_buyer`, then `--add-role --role admin`. The user has both roles, and the password is not reset: `requiredActions` is unchanged and no new credential was set, per Keycloak's `credentials` list length.
  - `test_add_role_unknown_email_exits_2` (Review Focus 5): exit 2 with the message, and the user count is unchanged.
  - `test_unknown_role_in_list_is_refused`: `--role admin --role nope` exits non-zero and creates nothing.
- [ ] **Step 2: Run.** Run `uv run --project engine pytest tools/test_pilot_user.py -v`. These tests need the dev Keycloak on 127.0.0.1:8081, per the file's docstring. Locally they may skip, and CI runs them. Expected locally: FAIL or skip.
- [ ] **Step 3: Implement** per Files.
- [ ] **Step 4: Run.** Run the same command against the local dev stack (`docker compose -f infra/docker-compose.yml up -d --wait`). Expected: PASS.
- [ ] **Step 5: Commit.** Commit with `feat(tools): pilot users with several roles, --add-role (B7-D8)`.

### Task 7: Stories, visual baselines, trace matrix and gates (B7a-R06, B7a-R07)

**Files:**
- `web/src/inquiries/WorkList.stories.tsx`: add a story `Stemmed tab` with `phase=stemmed` in the hash, and keep `AsBuyer` and `AsViewer`.
- `web/tests/visual/stories.spec.ts`: the existing worklist clock pin (`2026-11-11T12:00:00Z`) must cover new worklist story ids too. It already matches `inquiries-worklist` by prefix.
- Visual baselines: regenerate in the Linux Playwright container the way the repo does it. Find the script with `grep -n "visual" web/package.json`.
- `.github/workflows/ci.yml`: add `B7a-R07` to the two `# req:` gate lines, next to `B6-R11` and `B5-R13`.
- `docs/traceability.md`: regenerate it with `python tools/trace.py`.
- `docs/versions.md`: no change, because no new dependency is added.

- [ ] **Step 1: Write the failing check.** Run `python tools/trace.py`. Expected: exit 1 if any `B7a-R0x` is unreferenced; R06 and R07 are still missing at this point.
- [ ] **Step 2: Tag the coverage.**
  - Add the `[B7a-R06]` id to the stories spec tests that screenshot the new and changed stories. Follow how `[B1-R13]` is used there: either add a second id in the title of the worklist and dashboard story tests, or add one assertion test `[B7a-R06] work list tabs are keyboard reachable and labelled` in `WorkList.test.tsx`. That test tabs onto the tablist and checks that each tab's accessible name includes its count.
  - Add `B7a-R07` to ci.yml.
- [ ] **Step 3: Regenerate the visual baselines** for the changed stories (worklist, dashboard, inquiry page and the vessel admin page) in light and dark.
- [ ] **Step 4: Run the full gates.**
  - In `engine`, run `uv run ruff check . && uv run mypy . && uv run pytest --cov`. Expected: ≥ 90 % line and branch.
  - In `web`, run `pnpm exec eslint . && pnpm exec tsc --noEmit -p . && pnpm exec vitest run --coverage`. Expected: ≥ 90 %.
  - Run `python tools/trace.py`, then `python tools/trace.py --check`. Expected: exit 0, with B7b and B7c rows shown as `planned`.
- [ ] **Step 5: Commit.** Commit with `test: B7a stories, baselines and traceability`.

## After the plan (owner steps, not tasks)

1. When the owner approves, push the branch `feat/b7a-worklist` and open the PR. Merge it only after CI is green and the owner says so.
2. Deploy on the server with the 40-character merge SHA (runbook §10). Migration `0007` runs as part of the engine start (check how 0001–0006 ran in production).
3. Run the runbook §12 `--add-role --role admin` for her account on the server.
