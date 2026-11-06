// Sample nominations and a stateful stand-in for the nomination screen's client, shared by the
// Nomination tests and stories.
import { inquiry } from "../inquiries/pageSupport";
import type { Inquiry, InquiryStatus } from "../inquiryApi";
import type { NominationItem } from "../nominationApi";
import type { RfqPreview, Suggestions } from "../rfqApi";
import { supplier } from "../rfqs/testSupport";

export const draftNom: NominationItem = {
  id: "n3",
  status: "draft",
  sequence: null,
  contact_id: "Beta-1",
  contact_name: "Beta Primary",
  email: "beta.primary@example.test",
  sent_at: null,
  changed_since_sent: false,
  version: 1,
};
export const sentNom: NominationItem = {
  ...draftNom,
  id: "n1",
  status: "sent",
  sequence: 1,
  sent_at: "2026-11-06T09:00:00Z",
  version: 2,
};
export const amendedNom: NominationItem = {
  ...sentNom,
  id: "n2",
  sequence: 2,
  sent_at: "2026-11-07T09:00:00Z",
};
export const changedNom: NominationItem = { ...sentNom, changed_since_sent: true };

const mail = (subject: string, body: string): RfqPreview => ({
  to: "beta.primary@example.test",
  subject,
  body,
  mailto: `mailto:beta.primary@example.test?subject=${encodeURIComponent(subject)}&body=x`,
  body_in_link: true,
});

const SUBJECT = "Nomination INQ-2611-001 – Northern Star – Rotterdam";
const AMENDED = "Amended nomination (2) INQ-2611-001 – Northern Star – Rotterdam";
export const firstText = mail(
  SUBJECT,
  "We confirm the following nomination.\n500.000 mt VLSFO 0.5%\nTotal USD 421,000.00\nBunker desk",
);
const amendedText = mail(AMENDED, "We confirm the amended nomination.\nTotal USD 421,000.00");
/** The frozen text of version 1 is old: the ETA moved since. */
const frozenOld = mail(SUBJECT, "We confirm the following nomination.\nETA 11 Nov 06:00 UTC");

/** Beta Marine won; the suggestions list its two contacts for the contact select. */
export const betaSuggestions: Suggestions = {
  covers_all: [supplier("Beta", { name: "Beta Marine" })],
  covers_some: [],
  not_listed: [],
};

/**
 * A stateful stand-in: Mark sent freezes the draft as the next version and, for the first send,
 * moves the inquiry to Nominated, as the engine does. `previews` maps nomination ids to texts.
 */
export function nominationApi(
  list: NominationItem[] = [draftNom],
  start: InquiryStatus = "winner_selected",
) {
  let noms = list.map((n) => ({ ...n }));
  let status: InquiryStatus = start;
  const texts: Record<string, RfqPreview> = {
    n1: frozenOld,
    n2: amendedText,
    n3: start === "nominated" ? amendedText : firstText,
  };
  const change = (id: string, fields: Partial<NominationItem>, version: number) => {
    noms = noms.map((n) => (n.id === id ? { ...n, ...fields, version: version + 1 } : n));
    return Promise.resolve(noms.find((n) => n.id === id) ?? draftNom);
  };
  const inq = (): Inquiry =>
    inquiry({
      status,
      winner_counterparty_name: "Beta Marine",
      winner_counterparty_id: "Beta",
      buyer_id: "b1",
    });
  return {
    getInquiry: () => Promise.resolve(inq()),
    getSuggestions: () => Promise.resolve(betaSuggestions),
    listNominations: () => Promise.resolve(noms.map((n) => ({ ...n }))),
    createNomination: () => {
      noms = [{ ...draftNom, id: "n9" }, ...noms];
      texts.n9 = status === "nominated" ? amendedText : firstText;
      return Promise.resolve(noms[0] ?? draftNom);
    },
    getNominationPreview: (id: string) => Promise.resolve(texts[id] ?? firstText),
    patchNomination: (id: string, version: number, contactId: string) => {
      const second = contactId === "Beta-2";
      const fields = second
        ? { contact_id: contactId, contact_name: "Beta Second", email: "beta.second@example.test" }
        : { contact_id: contactId, contact_name: draftNom.contact_name, email: draftNom.email };
      return change(id, fields, version);
    },
    markNominationSent: (id: string, version: number) => {
      const sequence = Math.max(0, ...noms.map((n) => n.sequence ?? 0)) + 1;
      status = "nominated";
      return change(id, { status: "sent", sequence, sent_at: "2026-11-08T09:00:00Z" }, version);
    },
    withdrawNomination: (id: string, version: number) =>
      change(id, { status: "withdrawn" }, version),
  };
}
