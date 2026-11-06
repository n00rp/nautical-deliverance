# B3 Supplier Selection and RFQ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suggestions per port, individual RFQ drafts, mail handoff, mark sent/withdraw/decline with frozen text, the RFQ log, and proven confidentiality.

**Architecture:**
- **Pure rules** live in `domain/rfq.py`: `RfqContext`, `render_rfq`, `build_mailto` and the RFQ transitions. The API builds the context from the database. The render function never sees an ORM row.
- **Migration** `0004_rfq` adds the `rfq` table and `inquiry.rfq_deadline`. It also adds a trigger that keeps sent text immutable.
- **Router** is `api/rfqs.py`, with its models in `api/rfq_models.py`. Queries live in `persistence/rfq_repo.py` and reuse `master_repo.counterparties_covering`.
- **Inquiry status changes** go through the existing `_transition` and `can_transition` in `api/inquiries.py`. Move `_transition` to `inquiry_repo` if both routers need it.
- **Web:** adds `web/src/rfqs/`.

**Tech Stack:** as B2. Hypothesis for the property tests.

**Spec:** [docs/superpowers/specs/2026-11-05-b3-supplier-selection-rfq-design.md](../specs/2026-11-05-b3-supplier-selection-rfq-design.md) covers all of B3-D1–D12 and B3-R01–R15. The patterns to follow are in the [B2 plan](2026-11-05-b2-inquiries.md).

## Global Constraints

- **Repo path:** exactly `C:\Programing\nautical deliverence` ("deliverence" with an e, and the path contains a space). Never use the sibling folder `nautical deliverance`.
- **Gates:** all S0, B1 and B2 gates stay green:
  - engine with the DB and `ND_REQUIRE_DB=1`;
  - coverage ≥ 90 % line and branch;
  - web gates including jscpd;
  - visual tests in the pinned container;
  - cold smoke;
  - licence check.
- **Requirement tags:** `@pytest.mark.req("B3-Rnn")` or `[B3-Rnn]`. At the end, `python tools/trace.py --check` exits 0 and `docs/traceability.md` is regenerated.
- **Layers:** `domain` imports no FastAPI or SQLAlchemy, and `persistence` imports no `api`.
- **The `rfq` table:**
  - `organization_id` with FORCE RLS (USING + WITH CHECK);
  - composite `(organization_id, id)` FKs;
  - `nd_app` gets `SELECT, INSERT, UPDATE`, never DELETE.
- **RFQ statuses:** `draft`, `sent`, `declined`, `withdrawn`. The only allowed transitions are draft→sent, draft→withdrawn and sent→declined.
- **Errors:** as B1/B2:
  - 422 returns `{"detail":[{"field","message"}]}`;
  - a stale version returns 409 `{"detail":"Record was changed by someone else"}`;
  - a role that may not write gets 403;
  - another organization's id gets 404.
- **Permissions (B3-D11):**
  - write: Admin, Bunker Buyer;
  - read: Admin, Bunker Buyer, Viewer;
  - Operator: 403 on every RFQ endpoint.
- **Subject:** `RFQ <reference> – <vessel> – <port>`, using an en dash with spaces.
- **mailto:**
  - exactly one address in the path;
  - only `subject`, plus `body` when the whole link is ≤ 1800 characters;
  - never `cc`, `bcc` or `to`.
- **Instants:** shown as `DD Mon HH:MM UTC · HH:MM local`, matching the engine's formatting of B1-R08. Put the helper in `domain/` if no engine helper exists yet.
- **Demo data:** demo only, with `.example` e-mails (D-066).
- **Branch and commits:**
  - work on `feat/b3-rfq`, which already holds the spec;
  - use Conventional Commits ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  - do not push without the controller.

## Review Focus

1. **A contact or counterparty is deactivated after its RFQ was sent.** The log still shows the RFQ with the frozen address, and that address never changes. The contact cannot be chosen for a new draft. This belongs to Tasks 3 and 4.
2. **The inquiry buyer changes after an RFQ was sent.** The frozen signature stays as it was, and the log shows "changed since sent". This belongs to Task 4.
3. **A marker string with mail-meaningful characters** (`&`, `?`, `#`, `%`, newline, `"`, non-ASCII) appears in an allowed field such as spec notes. The text stays intact after percent-encoding, and it cannot inject a `cc=`/`bcc=` parameter. This belongs to Task 1.
4. **Two buyers click Mark sent at the same moment on the first two RFQs of a Draft inquiry.** The inquiry transitions exactly once, with exactly one inquiry audit entry, and both RFQs end up sent. If one of them has a stale version, it gets a 409. This belongs to Task 4.
5. **The deadline has passed while the RFQ is still a draft.** Mark sent returns 422 on `response_deadline`, and the UI prompts for a new deadline. This belongs to Tasks 4 and 7.

## File Structure

```
engine/src/nautical_deliverance/domain/rfq.py            RfqStatus, RFQ_TRANSITIONS, can_rfq_transition, RfqContext, RfqLine, render_rfq, build_mailto, MAILTO_MAX
engine/src/nautical_deliverance/persistence/migrations/versions/0004_rfq.py
engine/src/nautical_deliverance/persistence/models.py    + Rfq, Inquiry.rfq_deadline
engine/src/nautical_deliverance/persistence/rfq_repo.py  suggestions, context builder, log query
engine/src/nautical_deliverance/api/rfq_models.py, api/rfqs.py
engine/src/nautical_deliverance/persistence/seed.py      + demo RFQs
engine/tests/unit/test_rfq_domain.py, engine/tests/db/test_rfq_*.py
web/src/rfqApi.ts, web/src/rfqs/{SupplierSelection,RfqLog,RfqPreview}.tsx (+ tests, stories)
```

---

### Task 1: RFQ domain: render, mailto and transitions (B3-R05 mailto, R06, R07, R09 RFQ part, R12 encoding)

**Files:** Create `domain/rfq.py` and `tests/unit/test_rfq_domain.py`.

**Interfaces — Produces:**
- `class RfqStatus(StrEnum)` with the four values. `RFQ_TRANSITIONS` and `can_rfq_transition(a, b) -> bool`.
- `@dataclass(frozen=True) class RfqLine` with these fields:
  - `product: str`
  - `quantity: Decimal`
  - `unit: str`
  - `density: Decimal | None`
  - `spec_notes: str | None`
  - `iso_version: str`
- `@dataclass(frozen=True) class RfqContext`. These are exactly the allowed fields, and no others:
  - `reference`, `vessel_name`, `vessel_imo`
  - `port_name`, `port_locode`, `port_time_zone`
  - `eta: datetime | None`, `etd: datetime | None`
  - `agent_name: str | None`
  - `lines: tuple[RfqLine, ...]`
  - `response_deadline: datetime`
  - `recipient_name`, `recipient_email`, `buyer_name`
- `render_rfq(ctx: RfqContext) -> tuple[str, str]` returns subject and body.
  - The body follows the B0 prototype template (`docs/prototypes/b0-purchase-flow.html`, the RFQ text builder around line 284), adapted to the allowed fields.
  - Quantities are printed exactly as the Decimal holds them, with no float formatting.
  - Density is printed only when it is given.
  - A missing ETA or ETD prints as "to be advised".
- `MAILTO_MAX = 1800`.
- `build_mailto(to: str, subject: str, body: str) -> tuple[str, bool]` returns the URL and whether the body was included.
  - It uses `urllib.parse.quote` with `safe=""` for the subject and body, and quotes the address so that it is a single address.
  - It rejects a `to` that contains `,`, `;`, `?` or whitespace, and raises `ValueError`.

- [ ] **Step 1: Write the failing tests.**
  - `req("B3-R07")`, golden test: one fixed context renders exactly the expected subject and body. Write the literal expected text in the test. It must include a DST-sensitive local time, an m³ line with density and an mt line without density.
  - `req("B3-R06")`, Hypothesis property test.
    - Generate an inquiry-like dict with random unique marker strings in every forbidden field:
      - internal comments and cancel reason;
      - operator, requester and legal entity names;
      - other counterparties' names and e-mails;
      - the count of recipients, as the marker `"COUNT-<n>"`;
      - price and rationale placeholders.
    - Build `RfqContext` through a test-local `to_context(d, recipient)` that copies only the allowed keys. This mirrors the production builder, and Task 3 asserts that the two agree.
    - Assert that no marker occurs in the subject, the body or the mailto URL, either raw or after unquoting.
  - `req("B3-R05")`:
    - every mailto has exactly one `@` before the `?` and no `cc=`, `bcc=` or `to=`;
    - `build_mailto` rejects `"a@x.example,b@y.example"`.
  - `req("B3-R12")`:
    - round-trip `unquote` on the subject and body reproduces them exactly for the strings `&`, `?`, `#`, `%`, `\n`, `"` and `"Ünïcode – ok"`. This also covers Review Focus #3;
    - the body is dropped exactly when the link would exceed 1800 characters, with boundary tests at 1800 and 1801.
  - `req("B3-R09")`: the RFQ transition table is exact, with a property test over all 16 status pairs.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_rfq_domain.py`. Expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same tests, then the gates (ruff, format, mypy, lint-imports, vulture). Expect PASS.
- [ ] **Step 5: Commit** with `feat(engine): add RFQ rendering and mail handoff rules`.

### Task 2: Schema (B3-R01 DB, B3-R02)

**Files:** Create `migrations/versions/0004_rfq.py` and `tests/db/test_rfq_schema.py`. Modify `persistence/models.py`.

**Interfaces — Produces:**
- `inquiry.rfq_deadline timestamptz null`.
- `rfq`, with these columns:
  - `id`, `organization_id`
  - `inquiry_id`, `counterparty_id`, `contact_id`, as composite FKs
  - `status text`, with a check against the four values
  - `response_deadline timestamptz not null`
  - `generated_at timestamptz not null`
  - `sent_at`, `sent_to_email`, `sent_subject`, `sent_body`, all null
  - `inquiry_version_at_send int null`
  - `version`, `created_at`, `created_by`, `updated_at`
- These constraints and triggers:
  - Check: `status in ('sent','declined')` ⇔ all four `sent_*` fields are not null.
  - Partial unique index `rfq_one_active_idx` on `(inquiry_id, counterparty_id)` where `status <> 'withdrawn'`.
  - Composite FK `(organization_id, counterparty_id, contact_id)` → contact, which guarantees the contact belongs to the counterparty. Add `UNIQUE(organization_id, counterparty_id, id)` on contact if it is missing.
  - Trigger `rfq_sent_immutable`: a BEFORE UPDATE trigger that raises when `OLD.sent_body` is not null and any `sent_*` field or `inquiry_version_at_send` changes.
- Grants: `SELECT, INSERT, UPDATE` to `nd_app`.
- If `audit_entry.action` needs new verbs (`send`, `withdraw`, `decline`), widen the check in this migration.

- [ ] **Step 1: Write the failing tests.**
  - `req("B3-R01")`: accept and reject cases for each check, for the partial unique index (including that a withdrawn RFQ frees the pair), for the contact-belongs-to-counterparty FK, and for the immutability trigger.
  - `req("B3-R02")`: RLS on `rfq` makes rows invisible and immutable across orgs.
  - `nd_app` cannot DELETE.
- [ ] **Step 2: Run** the tests. Expect FAIL.
- [ ] **Step 3: Implement** the migration and the model, following `0003_inquiries.py`. Run `alembic upgrade head` and confirm the downgrade round-trip works.
- [ ] **Step 4: Run** the full suite. Expect PASS.
- [ ] **Step 5: Commit** with `feat(engine): add RFQ schema with RLS`.

### Task 3: Suggestions, create, log, preview, edit (B3-R01 API, R02, R03, R04, R05, R10, R11)

**Files:**
- Create `persistence/rfq_repo.py`, `api/rfq_models.py` and `api/rfqs.py`.
- Modify `main.py`.
- Create `tests/db/test_rfq_api.py`.

**Interfaces:**
- **Consumes:**
  - Task 1 and Task 2 code;
  - `master_repo.counterparties_covering(session, port_id, product_ids, mode=...)`;
  - `api/common.py` helpers and `api/users.current_user`;
  - `record_change`;
  - inquiry loading as in `api/inquiries.py`.
- **Produces:**
  - `rfq_repo.build_context(session, rfq) -> RfqContext` is the only place that maps DB rows to the allow-listed context.
  - `rfq_repo.suggestions(session, inquiry) -> {covers_all, covers_some, not_listed}`.
    - Each entry is `{counterparty_id, name, type, contacts:[{id,name,email,is_primary}], primary_contact_id | None, covered_product_ids, active_rfq_id | None}`.
    - Only active counterparties and contacts are included, and only contacts that have an e-mail.
  - Routes, as in spec §4:
    - `GET /inquiries/{id}/suggestions`
    - `GET /inquiries/{id}/rfqs`, the log
    - `POST /inquiries/{id}/rfqs` with `{deadline, recipients:[{counterparty_id, contact_id}]}`, which returns 201 with the created RFQs and is atomic
    - `GET /rfqs/{id}/preview` → `{to, subject, body, mailto, body_in_link}`
    - `PATCH /rfqs/{id}` with `{version, contact_id?, response_deadline?}`, allowed only while the RFQ is a draft
  - Creating RFQs also sets `inquiry.rfq_deadline` to the given deadline, with an audited update on the inquiry.
- **Log item shape:**
  - `{id, counterparty_name, contact_name, email, generated_at, sent_at, status, response_deadline, offer_received: false, changed_since_sent: bool, version}`.
  - `email` is the frozen `sent_to_email` once the RFQ is sent, and the current contact e-mail before that.
  - `changed_since_sent` is true when `render_rfq(build_context(...))` no longer equals the frozen subject and body.
  - `offer_received` stays false until B4.

**Rules:**
- **Who can create:**
  - creation requires an inquiry buyer (B3-D12): 422 on `buyer_id`, "Assign a buyer before creating RFQs";
  - the inquiry status must be draft, rfq_sent or offers_received, otherwise 409.
- **Recipient validation:** every recipient must be an active counterparty of the org, and its contact must be active, belong to that counterparty and have an e-mail. Otherwise return 422 on `recipients[i].contact_id` or `recipients[i].counterparty_id`.
- **Duplicates:** a counterparty that already has an active RFQ gets 422 on `recipients[i].counterparty_id`, "Already has an RFQ".
- **Deadline:** must be in the future, else 422 on `deadline`.

- [ ] **Step 1: Write the failing tests.**
  - `req("B3-R03")`: a parametrized test over every route in this task, for all four roles (Task 4 extends the same matrix with its routes). Operator gets 403 everywhere. Viewer can read but not write.
  - `req("B3-R04")`: the three suggestion groups on a world where counterparty A covers all products, B covers some and C has no coverage at the port. Inactive counterparties, contacts, products and the port are each excluded. Compare against `counterparties_covering` directly.
  - `req("B3-R05")`: creating with 3 recipients gives 3 RFQs, and each preview `to` is its own contact. This is a property test over generated recipient subsets of the world.
  - `req("B3-R06")`, API level: `build_context` contains no attribute outside `RfqContext`'s fields. Assert that `dataclasses.fields` equals the expected list. Also assert that the preview of an inquiry with marker strings in internal comments, cancel reason and the names of other recipients contains none of them.
  - `req("B3-R01")`: each 422 above, using the exact field paths.
  - `req("B3-R02")`: another org's counterparty or contact id gives 422, and another org's inquiry or RFQ id gives 404.
  - `req("B3-R10")`:
    - create works in draft, rfq_sent and offers_received;
    - it returns 409 in winner_selected, nominated and cancelled (set the status in the DB);
    - a second active RFQ for the same counterparty gets 422 (the after-withdraw case is tested in Task 4);
    - Review Focus #1, the create half: an inactive contact is not offered and is rejected.
  - `req("B3-R11")`: create writes one audit entry per RFQ and one for the inquiry deadline update. A patch writes one entry. A no-op patch writes none.
- [ ] **Step 2: Run** the tests. Expect FAIL.
- [ ] **Step 3: Implement.** Keep the router at about 400 lines or fewer.
- [ ] **Step 4: Run** the full suite and gates. Expect PASS.
- [ ] **Step 5: Commit** with `feat(engine): add RFQ suggestions and drafts`.

### Task 4: Mark sent, withdraw, decline, inquiry transition (B3-R08, R09, R10, R11)

**Files:** Modify `api/rfqs.py` and `persistence/rfq_repo.py`, and `api/inquiries.py` if `_transition` moves to `inquiry_repo`. Create `tests/db/test_rfq_actions.py`.

**Interfaces — Produces:**
- `POST /rfqs/{id}/mark-sent` with `{version}`:
  - Requires `can_rfq_transition(draft, sent)`, a deadline in the future (422 on `response_deadline`, "Deadline has passed") and `ready_to_leave_draft(eta, etd)` (422 on `eta`, "Set ETA and ETD before sending").
  - Freezes `sent_to_email`, `sent_subject` and `sent_body` from the live render, and sets `sent_at = now` and `inquiry_version_at_send`.
  - If the inquiry status is draft, it transitions the inquiry to `rfq_sent` through `can_transition`, with an inquiry audit entry, in the same transaction. Lock the inquiry row first so that two first sends transition exactly once (Review Focus #4).
- `POST /rfqs/{id}/withdraw` with `{version}` works from draft only. `POST /rfqs/{id}/decline` with `{version}` works from sent only. A disallowed transition gives 409 "Cannot move from X to Y".
- `GET /rfqs/{id}/history` returns entries newest first.

- [ ] **Step 1: Write the failing tests.**
  - `req("B3-R08")`, after mark sent:
    - changing the inquiry's ETA, agent and internal comments leaves the RFQ's subject and body unchanged;
    - `changed_since_sent` becomes true after an ETA or agent change, and stays false after an internal-comments change, because comments are not in the context;
    - updating `sent_body` directly in SQL raises the trigger error;
    - Review Focus #2: a buyer change sets the flag.
  - `req("B3-R09")`:
    - the first mark sent moves the inquiry draft→rfq_sent, and a second one leaves it unchanged;
    - mark sent without ETA gives 422;
    - mark sent with a past deadline gives 422 (Review Focus #5);
    - withdraw on a sent RFQ gives 409, and decline on a draft gives 409.
  - Review Focus #4: concurrent first sends give exactly one inquiry transition and one inquiry audit entry.
  - Review Focus #1: after mark sent, deactivating the contact leaves the log e-mail unchanged.
  - `req("B3-R10")`: after withdraw, a new RFQ for the same counterparty is allowed.
  - `req("B3-R11")`: each action writes one RFQ audit entry, and history comes back newest first.
  - `req("B3-R03")`: extend the Task 3 role matrix with mark-sent, withdraw, decline and history.
- [ ] **Step 2: Run** the tests. Expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite and gates. Expect PASS.
- [ ] **Step 5: Commit** with `feat(engine): add RFQ send, withdraw and decline`.

### Task 5: Demo RFQs (B3-R14)

**Files:** Modify `persistence/seed.py`, the seed tests and `tools/smoke.sh`.

- [ ] **Step 1: Write the failing tests**, tagged `req("B3-R14")`.
  - Per org, the seed adds RFQs to the demo inquiries:
    - the rfq_sent and offers_received inquiries get sent RFQs;
    - one Draft inquiry gets 2 draft RFQs;
    - at least 1 RFQ is declined.
  - The frozen texts equal `render_rfq(build_context(...))` at seed time.
  - Each inquiry has at most 1 active RFQ per counterparty.
  - Every address ends in `.example`.
  - A second seed run writes nothing (idempotent).
  - The existing denylist test still passes.
- [ ] **Step 2: Run** the tests and confirm they FAIL. Then **Step 3: Implement**, reusing `build_context` and `render_rfq`.
- [ ] **Step 4:** extend smoke so that `GET /inquiries/{id}/rfqs` as the buyer returns at least 1 item, and as the operator returns 403. Run smoke from a cold stack and confirm it PASSES.
- [ ] **Step 5: Commit** with `feat(engine): seed demo RFQs`.

### Task 6: Web: client and supplier selection, S3 (B3-R13 part)

**Files:**
- Create `web/src/rfqApi.ts` with a test.
- Create `web/src/rfqs/SupplierSelection.tsx` with a test and a story.
- Modify the routes (`#/inquiries/<id>/suppliers`), the inquiry page action "Select suppliers", and the work-list next step.

**Interfaces:**
- **Consumes:**
  - the Task 3 and Task 4 shapes;
  - `web/src/http.ts`;
  - the Part A components;
  - `formatInstant`, `DateTimeField` (with the port-zone hint) and `errors.ts`.
- **Produces:** `getSuggestions`, `listRfqs`, `createRfqs`, `getPreview`, `patchRfq`, `markSent`, `withdrawRfq`, `declineRfq` and `rfqHistory`.

**Screen:**
- **Deadline field.** Pre-fill it with `rfq_deadline`. If that is missing, use ETA − 48 h when ETA is at least 72 h ahead. Otherwise leave it empty.
- **Three groups.** `covers_all` is checked, `covers_some` is unchecked with a "Covers: <products>" note, and `not_listed` is unchecked in a collapsible section.
- **Rows.** Each row has a contact select, defaulting to the primary contact. A row with `active_rfq_id` shows "RFQ <status>" and is disabled.
- **Create button.** Labelled "Create N RFQ drafts". It is disabled while N = 0 or the deadline is empty, and navigates to the RFQ log on success.
- **Operator.** The inquiry page does not show the action at all.
- **Work-list next step:**
  - a Draft with a buyer and no RFQs: "Create RFQs";
  - a Draft without a buyer: "Assign buyer";
  - while drafts remain: "x of y RFQs sent". The list API may need `rfq_counts`; add `rfq_total` and `rfq_sent` to `InquiryListItem` in the engine (a small engine change with a test).

- [ ] **Step 1: Write the failing tests.**
  - `[B3-R13]`:
    - groups and pre-selection;
    - contact default and change;
    - the disabled already-RFQ'd row;
    - deadline pre-fill rules;
    - 422 mapping (`recipients[1].contact_id` shown on its row);
    - Operator has no access.
  - Budget: from the inquiry page, the run "Select suppliers" → accept the pre-selection → "Create" is ≤ 5 interactions. Assert the exact count.
  - The story covers light and dark mode, with axe.
- [ ] **Step 2: Run** the tests. Expect FAIL. **Step 3: Implement**, using Part A components and tokens only.
- [ ] **Step 4: Run** the web gates. Expect PASS.
- [ ] **Step 5: Commit** with `feat(web): add supplier selection`.

### Task 7: Web: RFQ log, preview, mail handoff, final verification (B3-R12 UI, R13, R15)

**Files:**
- Create `web/src/rfqs/RfqLog.tsx` and `RfqPreview.tsx`, with tests and stories.
- Add the route `#/inquiries/<id>/rfqs`.
- Add baselines.
- Regenerate `docs/traceability.md`.
- Add `# req: … B3-R15` to the engine and web jobs in ci.yml.

**Screen:**
- **Table.** Columns are Recipient, Contact, Address, Generated, Sent, Status (StatusPill variants), Deadline, Offer received ("—") and Changed. A "Changed since sent" warn pill is shown when it applies.
- **Detail panel.**
  - It shows the exact preview: To, Subject and Body in a monospace, read-only block.
  - **Open in e-mail** is an `<a href={mailto}>`. When `body_in_link` is false it shows the note "Body too long for a mail link — use Copy text".
  - **Copy text** uses `navigator.clipboard.writeText(body)` and shows a toast. If clipboard access fails, it selects the text instead.
  - The **Mark sent**, **Withdraw** and **Mark declined** buttons use InlineConfirm and are protected by an in-flight guard.
  - A 422 "Deadline has passed" shows an inline deadline editor (PATCH) (Review Focus #5).
- **Viewer.** Read-only: preview and copy only.
- **Operator.** No route access, shown as a LockedNote.

- [ ] **Step 1: Write the failing tests.**
  - `[B3-R12]`:
    - the mailto href equals the API value;
    - "Copy text" writes exactly the body;
    - the too-long note is shown.
  - `[B3-R13]`:
    - log columns;
    - action visibility per status and role;
    - the in-flight guard (a double-click on Mark sent sends one request);
    - the inquiry status updates to "RFQ sent" after the first send.
  - Stories for the log with draft, sent, declined and changed rows, in light and dark mode, with axe.
- [ ] **Step 2: Run** the tests. Expect FAIL. **Step 3: Implement.**
- [ ] **Step 4: Final verification.**
  - Engine gates with the DB, and coverage ≥ 90.
  - All web gates, coverage ≥ 90/90, build and build-storybook.
  - Visual tests in the container, regenerating only new or intended baselines. The second run must be clean.
  - Cold smoke and the licence check.
  - `python tools/trace.py`, then `--check`, which must exit 0 with B3-R01–R15 covered.
- [ ] **Step 5: Commit** with `feat(web): add RFQ log and mail handoff`, including traceability.md.

## Spec coverage

| Requirement | Task(s) |
|---|---|
| B3-R01 | 2, 3 |
| B3-R02 | 2, 3 |
| B3-R03 | 3 (incl. Task 4 routes) |
| B3-R04 | 3 |
| B3-R05 | 1, 3 |
| B3-R06 | 1, 3 |
| B3-R07 | 1 |
| B3-R08 | 4 |
| B3-R09 | 1, 4 |
| B3-R10 | 3, 4 |
| B3-R11 | 3, 4 |
| B3-R12 | 1, 7 |
| B3-R13 | 6, 7 |
| B3-R14 | 5 |
| B3-R15 | 7 |
