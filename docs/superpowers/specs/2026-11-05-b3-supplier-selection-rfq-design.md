# B3 Supplier Selection and RFQ — Specification

- **Status:** Draft for owner review
- **Date:** 2026-11-05
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B3 (D-076); D-070 (RFQ confidentiality, `mailto:`), B0-D8 (pre-selection), B0 screens S3/S4; builds on [B1](2026-11-05-b1-domain-and-design-system-design.md) coverage (B1-R09) and [B2](2026-11-05-b2-inquiries-design.md) inquiries.
- **Goal:** From an inquiry, the buyer selects suppliers/traders with suggestions per port, generates one individual RFQ draft per recipient, opens it in their own e-mail client, marks it sent, and follows every recipient in the RFQ log — with the brief's confidentiality rules guaranteed and proven.

## 1. Decisions

Confirmed by the owner in the B3 interview:

| ID | Decision |
|---|---|
| B3-D1 | Each RFQ goes to **one contact** of the counterparty: the primary contact is pre-selected; any other active contact with an e-mail address may be chosen per RFQ. |
| B3-D2 | The **response deadline** is set once per inquiry (`rfq_deadline`) and copied into each new draft; it can be adjusted per RFQ until that RFQ is sent. |
| B3-D3 | Draft text is **regenerated from the inquiry until marked sent**; at "Mark sent" subject and body are **frozen** and stored exactly as sent. If the inquiry changes afterwards, the RFQ log shows "Inquiry changed since sent". |
| B3-D4 | Recipients may be **added later** (new drafts) while the inquiry is Draft, RFQ sent or Offers received. |
| B3-D5 | The inquiry moves **Draft → RFQ sent automatically when its first RFQ is marked sent**, through `can_transition`; this requires ETA and ETD (`ready_to_leave_draft`, B2 R5). The B2-D5 lock then applies. |
| B3-D6 | RFQ statuses: **Draft, Sent, Declined, Withdrawn**. A draft can be withdrawn; a sent RFQ can be marked declined. "Offer received" is set by B4 when an offer is entered. |
| B3-D7 | **"Open in e-mail"** builds a `mailto:` with the single recipient, subject and — when the encoded link stays ≤ 1800 characters — the body; **"Copy text"** always copies the full body. |
| B3-D8 | One fixed **English template**, signed with the inquiry buyer's name and "Bunker desk". No editable templates in pilot 1. |

Proposed — confirmed by the owner's approval of this spec:

| ID | Decision | Rationale |
|---|---|---|
| B3-D9 | RFQ text is produced by **one pure render function** that receives a typed `RfqContext` holding **only allow-listed fields** (§3). Forbidden data never reaches the function. | Confidentiality by construction, not by filtering; new inquiry fields cannot leak unless explicitly added to the context. |
| B3-D10 | At most **one active RFQ (Draft or Sent or Declined) per counterparty per inquiry**; a Withdrawn RFQ frees the counterparty for a new draft. | Prevents duplicate RFQs to the same supplier. |
| B3-D11 | Permissions: create, edit, mark sent, withdraw, decline — Admin, Bunker Buyer; read suggestions, RFQs and preview — Admin, Bunker Buyer, Viewer; **Operator: 403 on every RFQ endpoint** (who was contacted is commercially sensitive, D-072). | Program spec §4. |
| B3-D12 | An inquiry must have a buyer before RFQs can be created (the signature names the buyer). | Avoids unsigned RFQs; B2-D7 Take is one click. |

## 2. Data model (organization-scoped, FORCE RLS, composite org FKs, audit; as B1/B2)

| Entity | Fields |
|---|---|
| Inquiry (added) | `rfq_deadline` timestamptz, optional |
| Rfq | inquiry, counterparty, contact (must belong to the counterparty; active; has e-mail), status (`draft`, `sent`, `declined`, `withdrawn`), response deadline (timestamptz, required, must be in the future when marked sent), generated_at, sent_at (set by Mark sent), sent_to_email, sent_subject, sent_body (all three set only at Mark sent, then immutable), inquiry_version_at_send, version, created_at, created_by, updated_at. Partial unique index: (inquiry, counterparty) where status ≠ `withdrawn`. Grants: SELECT, INSERT, UPDATE (no DELETE). |

## 3. RFQ content

**Allowed** (the complete `RfqContext`): inquiry reference; vessel name and IMO; port name and UN/LOCODE; ETA and ETD as `DD Mon HH:MM UTC · HH:MM local` (or "to be advised" when absent — never possible once sent, B3-D5); agent name; product lines (product, quantity, unit, density if given, spec notes, ISO 8217 version); response deadline in the same format; recipient contact name; buyer name.

**Never** (D-070, brief §RFQ Confidentiality): other counterparties or contacts; the number of suppliers contacted; internal comments; cancel reason; price expectations, offers, comparison or decision rationale (B4+); operator, requester and legal entity; any e-mail address other than the recipient's.

Subject: `RFQ <reference> – <vessel> – <port>`. Body: the prototype's template (B0 S4) with the allowed fields.

`mailto:` contains exactly one address in the path and only `subject` and optionally `body` parameters — never `cc`, `bcc` or `to`.

## 4. API (under `/api/v1/`)

`GET /inquiries/{id}/suggestions` → three groups: `covers_all`, `covers_some` (with the covered products), `not_listed` (active counterparties with no coverage for the port), each with active contacts and the primary contact id · `GET /inquiries/{id}/rfqs` (the log) · `POST /inquiries/{id}/rfqs` `{deadline, recipients:[{counterparty_id, contact_id}]}` → one draft each, atomic · `GET /rfqs/{id}/preview` → `{to, subject, body, mailto, body_in_link}` (live for drafts, frozen for sent) · `PATCH /rfqs/{id}` (contact, deadline; draft only; `version`) · `POST /rfqs/{id}/mark-sent|withdraw|decline` (`version`). Errors as B1/B2.

## 5. UI

- **S3 Supplier selection** (from the inquiry page, "Select suppliers"): deadline field (pre-filled with `rfq_deadline` or ETA − 48 h when ETA is ≥ 72 h ahead, else empty), the three groups per B0-D8 (`covers_all` checked, others unchecked; partial coverage shows which products), contact select per row, "Create N RFQ drafts". Counterparties that already have an active RFQ show it and cannot be selected again.
- **S4 RFQ log**: table with recipient, contact, address, generated, sent, status, deadline, offer received (— until B4), "changed since sent" flag; selecting a row opens a detail panel with the exact preview, "Open in e-mail", "Copy text", "Mark sent", "Withdraw" (draft), "Mark declined" (sent). Inquiry work list next step: "Create RFQs" for a Draft with a buyer, "x of y RFQs sent" while drafts remain.

## 6. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B3-R01 | Entities and constraints | Every field and constraint in §2 is enforced in DB and API (422 with a field error), incl. contact-belongs-to-counterparty, active contact with e-mail, partial unique index, immutability of sent text; accept and reject test each. |
| B3-R02 | Organization isolation | `rfq` is RLS-protected; another organization's RFQs are invisible and immutable; foreign counterparty/contact ids in a create give 422. |
| B3-R03 | Permissions (B3-D11) | One parametrized test covers every RFQ endpoint × four roles; Operator gets 403 on all of them, including suggestions and preview. |
| B3-R04 | Suggestions (B0-D8) | On demo data, the three groups match the B1 coverage query exactly; inactive counterparties, contacts, ports and products are excluded; tested with an inquiry whose products are covered fully by some, partly by others. |
| B3-R05 | One recipient per draft (D-070) | Every create produces one RFQ per recipient; each preview and `mailto:` holds exactly one address, the chosen contact's; no `cc`/`bcc`/`to` parameter ever appears; property-tested over generated recipient sets. |
| B3-R06 | Confidentiality (E4, D-070) | Property test over generated inquiries, counterparties and contacts, with unique marker strings in every forbidden field of §3: no marker ever appears in subject, body or `mailto:` of any RFQ; the number of recipients does not appear; holds for live and frozen text. |
| B3-R07 | Render correctness | Golden test: a fixed inquiry renders exactly the expected subject and body (times in UTC · local, quantities exact as entered, density only when given). |
| B3-R08 | Frozen text (B3-D3) | After Mark sent, changing the inquiry (ETA, agent, comments) leaves the RFQ's subject and body unchanged and sets "changed since sent"; the frozen fields cannot be updated (DB and API). |
| B3-R09 | Status flow (B3-D5, B3-D6) | First Mark sent moves the inquiry Draft → RFQ sent through `can_transition`; Mark sent is rejected (422) while ETA/ETD are missing or the deadline is past; RFQ transitions accept exactly Draft→Sent, Draft→Withdrawn, Sent→Declined; others give 409. |
| B3-R10 | Late additions and uniqueness (B3-D4, B3-D10) | Drafts can be added in Draft, RFQ sent and Offers received, not in later statuses or Cancelled (409); a second active RFQ for the same counterparty is rejected (422); after Withdraw it is allowed. |
| B3-R11 | Audit | Create, edit, mark sent, withdraw, decline write exactly one AuditEntry each on the RFQ; the inquiry transition writes one on the inquiry; RFQ history newest first. |
| B3-R12 | Mail handoff (B3-D7) | `mailto:` is correctly percent-encoded (tested with `&`, `?`, `#`, line breaks, non-ASCII); the body is included only when the link stays ≤ 1800 characters; "Copy text" copies exactly the preview body. |
| B3-R13 | Screens and step budget (B0-R02, E10) | S3 and S4 per §5 with Part A components; select suppliers and create drafts ≤ 5 interactions from the inquiry page (pre-selection accepted), asserted by a scripted test; Storybook/visual and axe as B1-R13. |
| B3-R14 | Demo data (D-066) | The seed adds RFQs to the demo inquiries (drafts, sent, declined) with frozen text rendered by the same function; all addresses `.example`; idempotent. |
| B3-R15 | Gates inherited | All S0/B1/B2 gates green; coverage ≥ 90 % line and branch; `tools/trace.py --check` green with all B3 requirements covered. |

## 7. Out of scope

Sending e-mail from the system; reading replies; attachments; editable templates; offers and "offer received" (B4); reminders.

## 8. Risks

| Risk | Mitigation |
|---|---|
| A future field leaks into RFQs | Allow-listed `RfqContext` (B3-D9); confidentiality property test uses markers in every non-allowed field, so a new field must be added to the test's forbidden list or the allow-list deliberately. |
| Buyer forgets to mark sent | Work list next step shows "x of y RFQs sent"; drafts stay visible in the log. |
| Mail client truncates long `mailto:` | Body only within 1800 characters; "Copy text" always available (B3-D7). |
