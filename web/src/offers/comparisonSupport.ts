// Sample comparisons and a stand-in client for the Comparison tests and stories.
import { inquiry } from "../inquiries/pageSupport";
import type { Decision, Inquiry } from "../inquiryApi";
import { evaluateOffer, formatDecimal, parseDecimal } from "../money";
import type { Comparison, ComparisonRow } from "../offerApi";
import { mtLines, savedOffer } from "./testSupport";
import type { ComparisonProps } from "./Comparison";

type Spec = {
  id: string;
  name: string;
  /** Prices of the two lines (500 mt VLSFO, 100 mt MGO); null leaves the line out. */
  prices: [string | null, string | null];
  fields?: Partial<ComparisonRow>;
};

const QTY = ["500", "100"];

/** One offer row without ranking flags; line costs and total come from the shared arithmetic. */
function offer({ id, name, prices, fields = {} }: Spec): ComparisonRow {
  const calc = evaluateOffer({
    lines: mtLines.map((l, i) => ({
      line_id: l.id,
      unit: "mt",
      quantity: QTY[i] ?? "0",
      inquiry_density: null,
      price_per_mt: prices[i] ?? null,
      offer_density: null,
    })),
    fixed: ["0.00"],
  });
  return {
    ...savedOffer,
    id,
    offer_id: id,
    rfq_id: `r-${id}`,
    counterparty_name: name,
    barging_cost: "0.00",
    delivery_method: null,
    payment_terms: null,
    lines: mtLines.map((l, i) => {
      const r = calc.lines[i];
      return {
        inquiry_line_id: l.id,
        product: l.product_name,
        price_per_mt: prices[i] ?? null,
        density: null,
        qty_mt: r?.qty_mt ?? null,
        line_cost: r?.line_cost ?? null,
        in_total: r?.in_total ?? false,
      };
    }),
    total: calc.total,
    complete: calc.complete,
    lowest: false,
    delta_to_lowest: null,
    ...fields,
  };
}

/** Ranks like the engine: complete offers that can be selected now compete for "lowest" (R5). */
function comparison(specs: Spec[], decision: Decision | null = null): Comparison {
  const rows = specs.map(offer);
  const live = rows.filter((r) => r.complete && !r.expired && r.rfq_status === "sent");
  const cents = (r: ComparisonRow) => parseDecimal(r.total, 2);
  const low = live.length
    ? live.reduce((a, r) => (cents(r) < a ? cents(r) : a), cents(live[0]!))
    : 0n;
  return {
    rows: rows.map((r) => {
      const isLive = live.includes(r);
      return {
        ...r,
        lowest: isLive && cents(r) === low,
        delta_to_lowest: isLive ? formatDecimal(cents(r) - low, 2) : null,
        selected: decision?.winner_offer_id === r.id,
      };
    }),
    decision,
  };
}

const alpha: Spec = { id: "oa", name: "Alpha Marine", prices: ["600.000", "800.000"] };
const beta: Spec = { id: "ob", name: "Beta Marine", prices: ["612.345", "845.500"] };
const gamma: Spec = {
  id: "og",
  name: "Gamma Bunkers",
  prices: ["620.000", "860.000"],
  fields: { physical_supplier: "Gulf Fuel Terminal", valid_until: "2026-11-12T08:00:00Z" },
};

/** Three complete offers; the first is the lowest. */
export const completeOnly = comparison([alpha, beta, gamma]);

/** Two complete offers at the same total: both are the lowest. */
export const tie = comparison([alpha, { ...beta, prices: ["600.000", "800.000"] }, gamma]);

/** A partial offer, an expired offer that is cheaper than all and a declined one. */
export const partialAndExpired = comparison([
  alpha,
  { id: "od", name: "Delta Oil", prices: [null, "700.000"], fields: { expiring_soon: true } },
  {
    id: "oe",
    name: "Echo Fuels",
    prices: ["500.000", "700.000"],
    fields: { expired: true, valid_until: "2026-11-05T08:00:00Z" },
  },
  {
    id: "of",
    name: "Foxtrot Supply",
    prices: ["590.000", "790.000"],
    fields: { rfq_status: "declined" },
  },
  beta,
]);

const decision: Decision = {
  winner_offer_id: "ob",
  reason: "reliability",
  note: "Known barge operator at this port",
  decided_at: "2026-11-06T10:30:00Z",
  decided_by_name: "Bea Buyer",
  decided_total: "390722.50",
  currency: "USD",
};

/** Beta was picked although Alpha is cheaper. */
export const decided = comparison([alpha, beta, gamma], decision);

export const offersInquiry = (fields: Partial<Inquiry> = {}) =>
  inquiry({ status: "offers_received", lines: mtLines, version: 4, ...fields });

/** Serves the inquiry and the comparison; selecting answers with the inquiry. */
export function compareApi(
  data: Comparison,
  rec: Inquiry = offersInquiry(),
): ComparisonProps["api"] {
  return {
    getInquiry: () => Promise.resolve(rec),
    getComparison: () => Promise.resolve(data),
    selectWinner: () => Promise.resolve(rec),
  };
}
