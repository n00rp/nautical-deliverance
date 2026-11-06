// Exact offer arithmetic on BigInt scaled integers, held to contracts/offer-cost-vectors.json
// (B4-R04). Mirrors engine domain/offer.py. Inputs are non-negative decimal strings.
// No floats anywhere (D-074).

const pow10 = (n: number) => 10n ** BigInt(n);
const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
/** 999999999999.99 as cents. */
const MAX_CENTS = 99_999_999_999_999n;

/**
 * "612.345" with scale 3 -> 612345n. Throws on bad text or more than `scale` decimals.
 * A leading "-" is accepted only with `signed` (display of deltas); prices stay non-negative.
 */
export function parseDecimal(s: string, scale: number, signed = false): bigint {
  const m = DECIMAL.exec(s);
  const frac = m?.[3] ?? "";
  if (!m?.[2] || frac.length > scale || (m[1] && !signed))
    throw new Error(`Invalid decimal "${s}" (scale ${scale})`);
  return BigInt(m[1] + m[2] + frac.padEnd(scale, "0"));
}

/** 612345n with scale 3 -> "612.345". */
export function formatDecimal(v: bigint, scale: number): string {
  const digits = v.toString().padStart(scale + 1, "0");
  return scale === 0 ? digits : `${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
}

/** An exact value: v / 10^scale. */
type Qty = { v: bigint; scale: number };

const exact = (s: string): Qty => ({
  v: parseDecimal(s, s.split(".")[1]?.length ?? 0),
  scale: s.split(".")[1]?.length ?? 0,
});

type OfferLineInput = {
  line_id: string;
  unit: "mt" | "m3";
  quantity: string;
  inquiry_density: string | null;
  price_per_mt: string | null;
  offer_density: string | null;
};

export type OfferInput = { lines: OfferLineInput[]; fixed: string[] };

export type OfferResult = {
  lines: { line_id: string; qty_mt: string | null; line_cost: string | null; in_total: boolean }[];
  total: string;
  complete: boolean;
};

/** Exact quantity in mt; null for an m3 line without any density (the inquiry's wins). */
export function quantityMt(line: OfferLineInput): Qty | null {
  const q = exact(line.quantity);
  if (line.unit === "mt") return q;
  const density = line.inquiry_density ?? line.offer_density;
  if (density === null) return null;
  const d = exact(density);
  return { v: q.v * d.v, scale: q.scale + d.scale + 3 }; // m3 * kg/m3 / 1000
}

/** Shortest exact decimal with at least 3 decimals; never rounds. */
export function formatQty(q: Qty): string {
  let { v, scale } = q;
  while (scale > 3 && v % 10n === 0n) {
    v /= 10n;
    scale -= 1;
  }
  for (; scale < 3; scale += 1) v *= 10n;
  return formatDecimal(v, scale);
}

/** Cost in cents, half-up (B4-D1); `price` is a scale-3 integer. */
export function lineCost(qty: Qty, price: bigint): bigint {
  const drop = pow10(qty.scale + 1); // qty scale + 3 price decimals - 2 cent decimals
  return (qty.v * price + drop / 2n) / drop;
}

/** Line costs and total; throws Error("total too large") above 999999999999.99. */
export function evaluateOffer(o: OfferInput): OfferResult {
  let total = o.fixed.reduce((sum, f) => sum + parseDecimal(f, 2), 0n);
  const lines = o.lines.map((l) => {
    const qty = quantityMt(l);
    const qty_mt = qty && formatQty(qty);
    if (!qty || l.price_per_mt === null)
      return { line_id: l.line_id, qty_mt, line_cost: null, in_total: false };
    const cost = lineCost(qty, parseDecimal(l.price_per_mt, 3));
    total += cost;
    return { line_id: l.line_id, qty_mt, line_cost: formatDecimal(cost, 2), in_total: true };
  });
  if (total > MAX_CENTS) throw new Error("total too large");
  return {
    lines,
    total: formatDecimal(total, 2),
    complete: lines.length > 0 && lines.every((l) => l.in_total),
  };
}

/** Groups the integer part of an exact decimal string: "12345.678" -> "12,345.678". */
export const formatMt = (s: string): string =>
  s.replace(/^-?\d+/, (i) => i.replace(/\B(?=(\d{3})+$)/g, ","));

/** "1234567.89" -> "USD 1,234,567.89"; "-25000" -> "USD -25,000.00". */
export function formatUsd(s: string): string {
  const cents = parseDecimal(s, 2, true);
  const [int = "", frac = ""] = formatDecimal(cents < 0n ? -cents : cents, 2).split(".");
  return `USD ${cents < 0n ? "-" : ""}${int.replace(/\B(?=(\d{3})+$)/g, ",")}.${frac}`;
}
