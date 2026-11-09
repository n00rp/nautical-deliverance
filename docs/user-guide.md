# Nautical Deliverance: pilot user guide

For people using the bunker procurement pilot. Button and field names below are written exactly as
they appear on screen.

## Demo data notice

The pilot runs on **demo data only**. Vessels, ports, suppliers, prices and inquiries belong to the
fictional organisation "Pilot Demo Shipping". Do not enter real commercial information, real prices
or personal data. Nothing you do here sends an e-mail by itself: the e-mail link only opens a draft
in your own mail program. This is a planning tool, not for navigation.

## Sign in

1. Open the pilot address you were given (it starts with `https://`).
2. The sign-in page opens by itself and asks for **Username or email** and **Password**; then click
   **Sign In**.
3. The first time, you use the temporary password you received and are asked to choose a new one.
   Keep it private: it is yours alone.
4. After sign-in you see the **Dashboard** and the **Inquiries** list in the top navigation.

If sign-in was cancelled or failed, the pilot shows the reason; click **Sign in** to try again.
If you cannot sign in, contact the pilot owner who created your account.

## Roles

Your role decides what you can do. You have exactly one.

| Role | What you can do |
|---|---|
| Admin | Everything a Bunker Buyer can do, plus maintaining the master data (vessels, ports, suppliers, products). |
| Bunker Buyer | Runs the purchase flow below: creates inquiries, sends RFQs, enters offers, selects the winner, creates the nomination. |
| Operator | Sees the inquiry and, once a supplier is nominated, that supplier's name. Never sees prices, offers, comparisons or the reason for the choice. |
| Viewer | Reads inquiries, offers, the comparison and the decision. Cannot change anything. |

## The purchase flow

The steps for a Bunker Buyer. Every inquiry moves from Draft to Nominated.

1. **Create the inquiry.** Under **Inquiries**, click **New inquiry**. Choose the Vessel, enter the
   Voyage, choose an Operator and a Port, and fill in the ETA and ETD. Choose the Bunkering reason.
   Click **Add line** for each fuel you want (for example VLSFO 0.5% and DMA 0.1%): choose the
   Product, enter the Quantity and choose the ISO spec version. Click **Create inquiry**. The
   inquiry starts as Draft.
2. **Select suppliers.** On the inquiry, click **Select suppliers**. The pre-selection suggests
   suppliers that can serve the port and products. Adjust it if you wish, then click **Create n RFQ
   drafts**. You get one RFQ per supplier.
3. **Send the RFQs.** Open an RFQ. Use **Open in e-mail** to write the request in your mail program,
   send it from there, then click **Mark sent** and **Confirm sent**. The status changes from Draft to
   Sent. Repeat for each RFQ.
4. **Enter the offers.** When a supplier answers, open that RFQ and click **Enter offer**. Type the
   price for each line and the **Valid until** date, then click **Save offer**.
5. **Compare.** On the inquiry, click **Compare offers**. The table lists the suppliers; the cheapest
   one is marked Lowest.
6. **Select the winner.** In the row of your choice click **Select winner**. If it is not the
   lowest offer, choose a Reason (for example Operational fit), add a Note, and click
   **Confirm selection**. The reason is stored with the decision.
7. **Nominate.** Back on the inquiry, click **Create nomination**. Read the nomination text, send it
   to the supplier with **Open in e-mail**, then click **Mark sent** and **Confirm sent**. The
   inquiry is now Nominated.

The Dashboard shows **Inquiries by status**, so you can see how many are Draft, Sent and Nominated,
and what needs attention (for example an offer that is about to expire or an ETA without a
nomination).

## Confidentiality

The platform protects each supplier's commercial information.

- **RFQs are individual.** Every supplier gets its own RFQ. One supplier never sees another
  supplier's name, price or offer, and the e-mail drafts never contain them.
- **The Operator sees no prices.** An Operator sees the nominated supplier's name only. Prices,
  totals, the comparison and the reason for the choice are hidden from the Operator everywhere,
  including the Dashboard.
- **Your organisation only.** You see only the data of your own organisation.
- Keep your password private and sign out on shared computers.

## Questions and problems

Ask the pilot owner who gave you access. Please include what you clicked, the inquiry reference
(for example INQ-...) and the time, but never your password.
