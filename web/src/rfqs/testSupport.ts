// Sample suppliers and a stand-in RFQ client, shared by the SupplierSelection tests and story.
import type { InquiryApi } from "../inquiryApi";
import type { RfqApi, RfqItem, Suggestion, Suggestions } from "../rfqApi";
import { inquiry } from "../inquiries/pageSupport";

const contact = (id: string, name: string, primary = false) => ({
  id,
  name,
  email: `${name.toLowerCase().replace(/ /g, ".")}@example.test`,
  is_primary: primary,
});

/** A supplier with a primary and a second contact; override any field. */
export const supplier = (id: string, fields: Partial<Suggestion> = {}): Suggestion => ({
  counterparty_id: id,
  name: `${id} Marine`,
  type: "physical_supplier",
  contacts: [contact(`${id}-1`, `${id} Primary`, true), contact(`${id}-2`, `${id} Second`)],
  primary_contact_id: `${id}-1`,
  covered_product_ids: ["pr1"],
  active_rfq_id: null,
  ...fields,
});

/** Two suppliers cover VLSFO; one covers only MGO; one is not listed; one already has an RFQ. */
export const suggestions: Suggestions = {
  covers_all: [supplier("Alpha"), supplier("Beta", { type: "trader" })],
  covers_some: [supplier("Gamma", { covered_product_ids: ["pr2"] })],
  not_listed: [supplier("Delta", { covered_product_ids: [] })],
};

export const sentRfq: RfqItem = {
  id: "r1",
  counterparty_name: "Beta Marine",
  contact_name: "Beta Primary",
  email: "beta.primary@example.test",
  generated_at: "2026-11-05T09:00:00Z",
  sent_at: "2026-11-05T10:00:00Z",
  status: "sent",
  response_deadline: "2026-11-10T08:00:00Z",
  offer_received: false,
  changed_since_sent: false,
  version: 2,
};

/** Both groups' products: the inquiry has VLSFO (pr1); MGO (pr2) is added here. */
export const twoProducts = () => {
  const base = inquiry();
  const [first] = base.lines;
  if (!first) throw new Error("fixture has no line");
  return {
    ...base,
    lines: [
      first,
      { ...first, id: "l2", position: 2, product_id: "pr2", product_name: "MGO 0.1%" },
    ],
  };
};

type Api = Pick<InquiryApi, "getInquiry"> &
  Pick<RfqApi, "getSuggestions" | "listRfqs" | "createRfqs">;

/** Serves one inquiry, its suggestions and RFQ log; `createRfqs` answers with an empty log. */
export function rfqApi(
  current = twoProducts(),
  groups: Suggestions = suggestions,
  log: RfqItem[] = [],
): Api {
  return {
    getInquiry: () => Promise.resolve(current),
    getSuggestions: () => Promise.resolve(groups),
    listRfqs: () => Promise.resolve(log),
    createRfqs: () => Promise.resolve([]),
  };
}
