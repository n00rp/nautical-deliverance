# B7 Pilot 1 Feedback Round — Specification

- **Status:** Approved by owner 2026-11-26 (including proposed decisions B7-D10–B7-D22); D-082 confirmed by the owner 2026-11-26
- **Date:** 2026-11-26
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md); D-069 and D-076 as amended by D-082 (§1); D-070 (RFQ by `mailto:`, unchanged), D-072, D-074, D-078; builds on [B2](2026-11-05-b2-inquiries-design.md), [B3](2026-11-05-b3-supplier-selection-rfq-design.md), [B4](2026-11-06-b4-offers-decision-design.md) and [B5](2026-11-06-b5-nomination-dashboard-design.md).
- **Goal:** Make pilot 1 fit how the bunker desk actually works, based on the brief author's first week in the live pilot. Fewer clicks between sending RFQs and comparing prices, a work list split into the desk's own three phases, and a first simple report.

## 0. Why

The brief author used the live pilot for a week (feedback received 2026-11-26). The main points:

1. Operators will not log in. They e-mail what each vessel needs, so the buyer creates every inquiry.
2. Bunker buyer and admin are the same people, so one login per person is enough.
3. Duplicate is not needed. She prefers a new inquiry every time.
4. Sending an RFQ should not need a separate "mark sent" click, and prices should be enterable straight away.
5. She could not find where to enter prices or how to compare total cost. Both exist (RFQ log → Enter offer → Compare offers), but she did not find the way there.
6. Orders need extra costs such as barging and port costs. These already exist as five fixed costs on each offer (barging, port call, agent, surveyor, other). The owner keeps those five for now (§1, B7-D6).
7. The list should be split into "on the list", "active in the market" and "stemmed".
8. Search by vessel or port. This already exists (reference, vessel, port), but it is not prominent.
9. Reports such as stems per month and per entity.

**Success:** she can go from a new inquiry to a priced comparison without hunting for screens. She sees her work in the three phases she thinks in. She can answer "how many stems did we have per month and per entity" herself.

**Anti-goals:**
- Nothing that weakens D-070 confidentiality, meaning one recipient per RFQ and only allow-listed fields.
- Nothing that sends e-mail from the system.
- No new role model. The roles stay and simply get used differently.

## 1. Decisions

Owner decisions:

| ID | Decision |
|---|---|
| B7-D1 | **RFQ handoff stays `mailto:` (D-070 unchanged).** The owner chose this on 2026-11-26. A browser opens only one `mailto:` per click, and one mail with several recipients would break D-070. So each RFQ row gets one **Send** action that opens the mail in the user's mail client **and** marks the RFQ sent in the same click. |
| B7-D2 | **An offer can be entered on a draft RFQ.** Entering prices on a draft first marks it sent (text frozen, B3-D3; same checks as Mark sent), then stores the offer in the same transaction. |
| B7-D3 | **Compare offers becomes an editable price table** (owner choice 2026-11-26). It has one column per active RFQ (draft or sent, with or without an offer) and rows for each product line's price per mt, the five fixed costs, valid until, and the live total. The full offer form (S5) stays for the remaining fields. |
| B7-D4 | **The work list is split into three tabs:** *On the list* (Draft), *In the market* (RFQ sent, Offers received, Winner selected) and *Stemmed* (Nominated). Cancelled inquiries sit behind a "Show cancelled" toggle. Search stays and works within the selected tab. |
| B7-D5 | **Duplicate is removed** (B2-D10 withdrawn): the API endpoint, the UI action and its tests. B2-D5's "cancel and duplicate" becomes "cancel and create a new inquiry". |
| B7-D6 | **The five fixed costs stay.** There is no free list of cost lines. The owner will ask her after B7 whether "other" is enough. |
| B7-D7 | **No operator logins.** The Operator role, its permissions and its confidentiality tests stay in code (D-072 unchanged). No operator accounts are issued. |
| B7-D8 | **One login per buyer with both roles.** Pilot accounts for buyers get the realm roles `bunker_buyer` **and** `admin`. |
| B7-D9 | **A simple report** (D-082) shows stems and spend per month and per legal entity, plus a CSV export of all inquiries. |

Program decision (confirmed by the owner 2026-11-26):

| ID | Decision |
|---|---|
| D-082 | **B7 is a pilot-1 feedback round**, built after B6 and before pilot 2. Pilot 2 (delivery, invoice matching, claims, full reporting, Accounting/AP) moves to **B8+**. A **simple reporting slice** (stems and spend per month and legal entity, CSV export of inquiries) moves from pilot 2 into B7. This amends D-069 (pilot 2 still owns full reporting) and D-076 (build order). |

Proposed B7 decisions, confirmed by the owner's approval of this spec:

| ID | Decision | Rationale |
|---|---|---|
| B7-D10 | **The operator becomes a name, not a user.** `inquiry.operator_id` (FK to `app_user`) is replaced by `operator_name` (text ≤ 120, optional). `vessel.default_operator` (Keycloak id) is replaced by `default_operator_name` (text ≤ 120, optional) and prefills the inquiry. The migration copies the current user's display name. The requester stays a user and defaults to the creator. | With no operator logins, operators never appear in the user directory, so a user picker could not name them. |
| B7-D11 | **Nominations get the same one-click Send** (B7-D1 pattern) in place of Open in e-mail followed by Mark sent. | One consistent way to send any e-mail draft. She will meet the nomination right after the RFQs. |
| B7-D12 | **Send cannot be undone in B7.** A wrongly sent RFQ is withdrawn or declined as today. Send asks for no confirmation; the click itself is the intent. | Keeps the RFQ state model (B3-D6) unchanged. Reverting a frozen text is a new rule we do not need yet. |
| B7-D13 | **In the price table, "valid until" is prefilled** when a column has no offer. The prefill is 23:59 in the port's local time on the current day; if that moment has passed, it is now + 24 h. It is editable in its row. | B4 requires valid until, and typing a date per supplier is the slowest step. Same-day validity is the common case. |
| B7-D14 | **Saving the price table:** one **Save prices** button saves every changed column. Each column is its own request (create offer, or PATCH with `version`). A failing column keeps its edits and shows its error, while the others are saved. A column whose offer is the selected winner is read-only (B4-D12). Leaving the page with unsaved edits asks first. | Per-offer versions already exist (B4-D3). One button matches a spreadsheet workflow. Partial success is honest about what was stored. |
| B7-D15 | **Report basis = the dashboard's basis (B5-D5).** A stem is an inquiry whose first nomination has been sent. Its month is the calendar month (UTC) of that send. Volume and spend are computed as on the dashboard (`decided_total` for spend). Grouping is by month and by legal entity, for the last 12 months, with totals. | One definition of "stem" across dashboard and report. |
| B7-D16 | **CSV export** of every inquiry the caller can see, in the selected tab or all tabs. Format: UTF-8 with BOM, comma separator, RFC 4180 quoting, ISO 8601 UTC timestamps, and amounts as plain decimals with a dot (`394413.50`). Columns: reference, status, vessel, IMO, legal entity, port, ETA, ETD, buyer, operator name, winner counterparty, decided total, currency, first nomination sent at. | Opens in Excel and in any tool. With Swedish locale, Excel may need "Data → From Text/CSV"; the report page says so. |
| B7-D17 | **Report permissions:** Admin, Bunker Buyer and Viewer. **Operator: 403** on the report and the export, because they contain spend and winners. | D-072. |
| B7-D19 | **Density in the price table:** when an m³ line has no density on the inquiry, the table shows a *Density* cell for that line in every column (B4-D6). It sits directly under the line's price, labelled "<product> density kg/m³". Without a density the line stays out of the total, and the column is tagged Partial, as in B4. | Keeps such lines priceable in the table. Usually no row appears, because most inquiries carry a density. |
| B7-D20 | **Show cancelled** switches the list to the cancelled inquiries only (`phase=cancelled`, single-valued). The tabs stay visible but deselected. **Export CSV** exports the current view: the selected tab, or the cancelled list, with the current search. | One phase per request keeps the API, counts and tests simple. |
| B7-D21 | **Dashboard links:** the status-count tiles become links to the matching tab. Draft opens *On the list*. RFQ sent, Offers received and Winner selected open *In the market*. Nominated opens *Stemmed*. There is no per-status filter. Attention items keep linking to their inquiry. | B7-D4 replaces the status filter, and a tile that opens its phase is enough. |
| B7-D22 | **After a winner is selected, draft columns are read-only** in the price table, with the note "RFQs cannot be sent after a winner is selected" (B3 rule, `CREATABLE` unchanged). Sent RFQs without an offer stay editable while the inquiry is Winner selected, as B4 allows. | Keeps B3's send rule unchanged. A late quote from an already-contacted supplier can still be entered. |
| B7-D18 | **Tab labels:** the UI is English (program rule), so the tabs read *On the list*, *In the market* and *Stemmed*. Each tab shows its count. The default tab is *In the market*. The dashboard's links open the matching tab. | Her own words, translated. "In the market" is where daily work happens. |

## 2. Data model changes

| Entity | Change |
|---|---|
| Inquiry | `operator_id` is dropped and `operator_name` (text ≤ 120, optional) is added, filled by migration from `app_user.name` (B7-D10). |
| Vessel | `default_operator` is dropped and `default_operator_name` (text ≤ 120, optional) is added, filled by migration from the directory where the id resolves, otherwise null. |
| Rfq, Offer, Nomination | No schema change. |

The migration is reversible (down: names cannot map back to users, so `operator_id` is restored as nullable and left empty). Seed and demo data use invented operator names (R6 from B2 still applies). Audit history keeps the old values as recorded.

## 3. API changes (under `/api/v1/`)

- `GET /inquiries` gains `phase=list|market|stemmed|cancelled`. This replaces the UI's use of `status`, which stays accepted. The response carries `phase_counts:{list, market, stemmed, cancelled}` for the current `q`.
- `POST /inquiries/{id}/duplicate` is **removed**.
- `POST /rfqs/{id}/offer` also accepts a **draft** RFQ (B7-D2). In that case it runs Mark sent's checks and freezing first, in the same transaction. All B3 and B4 errors are unchanged (for example, 422 when ETA/ETD are missing or the deadline has passed).
- `GET /reports/stems?months=12` → `{currency, rows:[{month, legal_entity_id, legal_entity_name, stems, nominated_mt, mt_excluded_lines, nominated_spend}], totals_by_month, totals_by_entity, total}`.
- `GET /inquiries/export.csv?phase=…&q=…` → `text/csv` per B7-D16.
- Inquiry and vessel bodies: `operator_id` is replaced by `operator_name`, and `default_operator` by `default_operator_name`.

Send (B7-D1, B7-D11) needs **no new endpoint**. The web calls the existing `mark-sent` and opens the `mailto:` in the same click handler. If mark-sent fails, the mail is **not** opened and the error is shown, so a failed save never leaves an open mail behind.

## 4. UI changes

- **Work list (`#/inquiries`):** three tabs with counts, a "Show cancelled" toggle, and the search field first in the filter row with the hint "Reference, vessel or port". The status filter is removed because the tabs replace it. Sort stays.
- **Inquiry page:** the Duplicate action is removed. The Operator field is a text field, prefilled from the vessel.
- **RFQ log (S4):** each draft row has **Send**, and the detail panel shows Send in place of Open in e-mail + Mark sent. Copy text stays. Withdraw and Mark declined are unchanged. After Send the row shows *Sent* with its time.
- **Price table (S6, Compare offers):**
  ```
                    Alpha Marine   Beta Bunkers   Gamma Fuel (draft)
  VLSFO  $/mt       [ 612.50 ]     [ 608.000 ]    [          ]
  MGO    $/mt       [ 845.50 ]     [ 850.00 ]     [          ]
  Barging           [ 1200.00 ]    [ 900.00 ]     [          ]
  Port call         [ 0 ]          [ 350.00 ]     [          ]
  Agent             [ 350.00 ]     [ 0 ]          [          ]
  Surveyor          [ 450.00 ]     [ 450.00 ]     [          ]
  Other             [ 0 ]          [ 0 ]          [          ]
  Valid until       [27 Nov 23:59] [27 Nov 23:59] [26 Nov 23:59]
  Total (USD)       394,413.50     391,120.00 ✓   —
  Delta to lowest   +3,293.50      lowest
                    Details · Select   Details · Select
                                                      [ Save prices ]
  ```
  Totals are live, with the shared BigInt algorithm and vectors (B4-D9). The lowest, partial, expired and selected markers follow B4. **Details** opens S5 for the other fields, and **Select** is the existing winner selection with its rationale rules. Typing into a draft column shows a note: "Saving marks this RFQ sent".
- **Nomination (S7):** Send replaces Open in e-mail + Mark sent (B7-D11).
- **Reports (`#/reports`, in the navigation for Admin, Bunker Buyer and Viewer):** a month × legal entity table of stems and spend with totals, plus an **Export CSV** button. The work list also has **Export CSV** for the current tab and search.

## 5. Operations

- `tools/pilot_user.py` accepts `--role` more than once (for example `--role bunker_buyer --role admin`).
- A new `--add-role` mode adds a role to an existing user found by e-mail, without changing the password.
- Runbook §12 shows the two-role command and the add-role command for her existing account.

## 6. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B7-R01 | Phase tabs (B7-D4, B7-D18, B7-D20, B7-D21) | `phase` returns exactly the statuses of §1, and `phase_counts` match per `q`. The UI shows three tabs with counts, *In the market* as default, and Show cancelled. Dashboard links open the right tab. Each phase is tested with every status. |
| B7-R02 | Search prominent | The search field is first in the filter row with its hint. Search combined with each phase filters within the phase, and counts follow the search (tested). |
| B7-R03 | Duplicate removed (B7-D5) | The endpoint returns 404/405, no UI shows Duplicate, B2-D10 is marked withdrawn in the B2 spec, and the seed still works. |
| B7-R04 | Operator as name (B7-D10) | Migration up/down is tested on a seeded database. The inquiry and vessel APIs accept and return names (≤ 120, trimmed, optional). The vessel prefill works. No endpoint references `operator_id` any more. The Operator role's B2–B5 permission and confidentiality tests (E4) still pass. |
| B7-R05 | One-click Send (B7-D1, B7-D11) | One click on Send calls mark-sent, then opens the `mailto:` only on success; on failure there is no mail and an error is shown. This holds for RFQs and nominations. B3-R05/R06/R12 and the B5 nomination confidentiality tests pass unchanged. |
| B7-R06 | Offer on a draft RFQ (B7-D2) | Creating an offer on a draft RFQ freezes its text exactly as Mark sent would, sets `sent_at`, moves the inquiry Draft → RFQ sent → Offers received through `can_transition`, and writes the audit entries in one transaction. Missing ETA/ETD or a passed deadline gives 422 and stores nothing. Withdrawn and declined RFQs give 409. |
| B7-R07 | Price table (B7-D3, B7-D13, B7-D14, B7-D19, B7-D22) | Columns are every draft and sent RFQ. The selected-winner column is read-only, and so are draft columns once a winner is selected. The density cells appear exactly for m³ lines without inquiry density. Live totals equal the engine's for the shared vectors. The valid-until prefill follows B7-D13 (tested across time zones and the "already passed" case). Save sends one request per changed column. A version conflict or 422 in one column keeps that column's edits and shows the error while the others are saved. The unsaved-changes prompt works. |
| B7-R08 | Step budgets (E10) | Send five RFQs in ≤ 5 interactions from the RFQ log. Enter prices for 3 suppliers × 2 lines + 1 barging cost each, and save, in ≤ 13 interactions. Asserted by scripted tests, alongside the B4 budgets. |
| B7-R09 | Stems report (B7-D15, B7-D17) | Exact figures for a seeded set covering several entities and months, an inquiry nominated twice (counted once, by first send), an m³ line without density (excluded and counted in `mt_excluded_lines`), and month boundaries in UTC. Figures equal the dashboard's for the current month. Operator gets 403. RLS isolates organizations. |
| B7-R10 | CSV export (B7-D16, B7-D17) | Columns, BOM, quoting (commas, quotes, line breaks, non-ASCII), decimals and timestamps exactly as specified. Phase and search filters apply. Operator gets 403. No field outside the listed columns appears, so internal comments and rationale never do (marker test). |
| B7-R11 | Pilot users with two roles (§5) | `pilot_user.py` creates a user with two roles and adds a role to an existing user. Tested in the existing `pilot-user` CI job. The runbook is updated. |
| B7-R12 | Screens and accessibility | New and changed screens have Storybook stories with visual baselines and axe checks, light and dark, as B1-R13. The price table is keyboard-navigable, and every cell has a label naming its supplier and row. |
| B7-R13 | Gates inherited | All S0–B6 gates are green, coverage ≥ 90 % line and branch, and `tools/trace.py --check` is green with every B7 requirement covered. |

## 7. Delivery (owner choice A, 2026-11-26)

Three PRs, each deployable and live on its own:

| Part | Content | Requirements |
|---|---|---|
| B7a | Phase tabs, prominent search, Duplicate removed, operator as name, two-role pilot users | R01–R04, R11, R12–R13 for its screens |
| B7b | One-click Send (RFQ, nomination), offer on a draft RFQ, editable price table | R05–R08, R12–R13 for its screens |
| B7c | Stems report and CSV export | R09–R10, R12–R13 for its screens |

After B7a is deployed, her account gets the admin role (§5).

## 8. Out of scope

- E-mail sent by the system (§9 of the program spec still applies).
- Free cost lines (B7-D6).
- Currencies other than USD.
- Pilot-2 reporting beyond §1 D-082 (supplier performance, price history, claims).
- Undoing a sent RFQ (B7-D12).
- Importing offers from e-mail.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Send marks an RFQ sent although the user then closes the mail without sending | Accepted for the pilot (B7-D12). Withdraw or decline as today. The help text under the RFQ log says so. |
| A wide price table on a laptop (many suppliers) | Horizontal scroll inside the table with a sticky row label column. Usually 3–6 suppliers. |
| Operator-name migration loses information | Names are copied from the directory before the column is dropped, and audit history keeps the old ids. |
| A CSV in Swedish Excel shows decimals wrongly | A note on the report page and in the guide. XLSX later if she asks. |
