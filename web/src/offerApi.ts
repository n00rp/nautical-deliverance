import { createRequest, toHistory, type RawHistory, type TokenSource } from "./http";
import type { Decision, DecisionReason, Inquiry } from "./inquiryApi";

export type DeliveryMethod = "barge" | "truck" | "pipeline" | "ex_wharf";
/** Amounts, prices, densities and quantities are decimal strings, never numbers (D-074). */
type OfferLine = {
  inquiry_line_id: string;
  product: string;
  price_per_mt: string | null;
  density: string | null;
  qty_mt: string | null;
  line_cost: string | null;
  in_total: boolean;
};

export const COST_KEYS = [
  "barging_cost",
  "port_call_cost",
  "agent_cost",
  "surveyor_cost",
  "other_cost",
] as const;
type CostKey = (typeof COST_KEYS)[number];

export const COST_LABEL: Record<CostKey, string> = {
  barging_cost: "Barging",
  port_call_cost: "Port call",
  agent_cost: "Agent",
  surveyor_cost: "Surveyor",
  other_cost: "Other",
};

/** Why a non-lowest offer was chosen, as the select shows it. */
export const REASON_LABEL: Record<DecisionReason, string> = {
  flexibility: "Flexibility",
  operational_fit: "Operational fit",
  availability: "Availability",
  reliability: "Reliability",
  timing: "Timing",
  payment_terms: "Payment terms",
  commercial_judgement: "Commercial judgement",
  other: "Other",
};

export type Offer = Record<CostKey, string> & {
  id: string;
  rfq_id: string;
  inquiry_id: string;
  rfq_status: string;
  counterparty_name: string;
  selected: boolean;
  currency: string;
  valid_until: string;
  payment_terms: string | null;
  delivery_from: string | null;
  delivery_to: string | null;
  delivery_method: DeliveryMethod | null;
  physical_supplier: string | null;
  supplier_comment: string | null;
  lines: OfferLine[];
  total: string;
  complete: boolean;
  received_at: string;
  version: number;
};

export type ComparisonRow = Offer & {
  offer_id: string;
  lowest: boolean;
  delta_to_lowest: string | null;
  expired: boolean;
  expiring_soon: boolean;
};

export type Comparison = { rows: ComparisonRow[]; decision: Decision | null };

/** Body of POST /rfqs/{id}/offer; a PATCH adds `version`, and `lines` replaces the set. */
export type OfferBody = Partial<Record<CostKey, string>> & {
  valid_until: string;
  payment_terms?: string | null;
  delivery_from?: string | null;
  delivery_to?: string | null;
  delivery_method?: DeliveryMethod | null;
  physical_supplier?: string | null;
  supplier_comment?: string | null;
  lines: { inquiry_line_id: string; price_per_mt: string; density?: string }[];
};

export type SelectBody = {
  offer_id: string;
  reason?: DecisionReason;
  note?: string;
};

/** Typed client for the offer, comparison and decision routes under /api/v1. */
export function createOfferApi(auth: TokenSource) {
  const call = createRequest(auth);
  const offer = (id: string, tail = "") => `offers/${encodeURIComponent(id)}${tail}`;
  const inquiry = (id: string, tail: string) => `inquiries/${encodeURIComponent(id)}/${tail}`;

  return {
    createOffer: (rfqId: string, body: OfferBody) =>
      call<Offer>("POST", `rfqs/${encodeURIComponent(rfqId)}/offer`, body),
    getOffer: (id: string) => call<Offer>("GET", offer(id)),
    patchOffer: (id: string, version: number, body: Partial<OfferBody>) =>
      call<Offer>("PATCH", offer(id), { ...body, version }),
    offerHistory: async (id: string) =>
      toHistory(await call<RawHistory[]>("GET", offer(id, "/history"))),
    getComparison: (inquiryId: string) => call<Comparison>("GET", inquiry(inquiryId, "comparison")),
    selectWinner: (inquiryId: string, version: number, body: SelectBody) =>
      call<Inquiry>("POST", inquiry(inquiryId, "select-winner"), { ...body, version }),
  };
}

export type OfferApi = ReturnType<typeof createOfferApi>;
