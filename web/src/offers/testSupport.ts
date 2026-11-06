// Sample inquiries and a stand-in client for the OfferEntry tests and stories.
import { inquiry } from "../inquiries/pageSupport";
import type { Inquiry } from "../inquiryApi";
import type { ComparisonRow } from "../offerApi";
import { sentRfq } from "../rfqs/testSupport";
import type { OfferEntryProps } from "./OfferEntry";

type Line = Inquiry["lines"][number];

const base = inquiry().lines[0] as Line;

/** An inquiry line; override any field (the id is also the product id). */
const line = (id: string, product: string, quantity: string, fields: Partial<Line> = {}) => ({
  ...base,
  id,
  position: parseInt(id.slice(1), 10),
  product_id: id,
  product_name: product,
  quantity,
  ...fields,
});

/** Two mt lines. */
export const mtLines = [line("l1", "VLSFO 0.5%", "500"), line("l2", "MGO 0.1%", "100")];

/** An mt line, an m3 line without density (asks for one) and an m3 line with one (does not). */
export const m3Lines = [
  line("l1", "VLSFO 0.5%", "500"),
  line("l2", "LNG", "120", { unit: "m3" }),
  line("l3", "Bio LNG", "10", { unit: "m3", density: "850.0" }),
];

const offerInquiry = (lines: Line[]) => inquiry({ status: "rfq_sent", lines });

/** Beta Marine's saved offer for the two mt lines: 500 mt at 612.345 and 100 mt at 845.5. */
export const savedOffer: ComparisonRow = {
  id: "o1",
  offer_id: "o1",
  rfq_id: sentRfq.id,
  inquiry_id: "i1",
  rfq_status: "sent",
  counterparty_name: "Beta Marine",
  selected: false,
  currency: "USD",
  valid_until: "2026-11-10T08:00:00Z",
  payment_terms: "30 days",
  delivery_from: null,
  delivery_to: null,
  delivery_method: "barge",
  physical_supplier: null,
  supplier_comment: null,
  barging_cost: "1200.00",
  port_call_cost: "0.00",
  agent_cost: "0.00",
  surveyor_cost: "0.00",
  other_cost: "0.00",
  lines: [
    {
      inquiry_line_id: "l1",
      product: "VLSFO 0.5%",
      price_per_mt: "612.345",
      density: null,
      qty_mt: "500.000",
      line_cost: "306172.50",
      in_total: true,
    },
    {
      inquiry_line_id: "l2",
      product: "MGO 0.1%",
      price_per_mt: "845.500",
      density: null,
      qty_mt: "100.000",
      line_cost: "84550.00",
      in_total: true,
    },
  ],
  total: "391922.50",
  complete: true,
  received_at: "2026-11-06T09:00:00Z",
  version: 3,
  lowest: true,
  delta_to_lowest: null,
  expired: false,
  expiring_soon: false,
};

/** Serves the inquiry, the sent RFQ and (optionally) a saved offer; saves answer with that offer. */
export function entryApi(lines: Line[], saved?: ComparisonRow): OfferEntryProps["api"] {
  const row = saved ?? savedOffer;
  return {
    getInquiry: () => Promise.resolve(offerInquiry(lines)),
    listRfqs: () =>
      Promise.resolve([saved ? { ...sentRfq, offer_received: true, offer_id: saved.id } : sentRfq]),
    getOffer: () => Promise.resolve(row),
    createOffer: () => Promise.resolve(row),
    patchOffer: () => Promise.resolve(row),
  };
}
