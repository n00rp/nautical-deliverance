import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  evaluateOffer,
  formatDecimal,
  formatQty,
  formatUsd,
  lineCost,
  parseDecimal,
  quantityMt,
  type OfferInput,
} from "./money";

type Vector = {
  name: string;
  offer: OfferInput;
  expected: { error: string } | ReturnType<typeof evaluateOffer>;
};

const { cases } = JSON.parse(
  readFileSync(resolve(process.cwd(), "../contracts/offer-cost-vectors.json"), "utf8"),
) as { cases: Vector[] };

describe("exact money", () => {
  it("[B4-R04] the shared vectors are loaded", () => {
    expect(cases.length).toBeGreaterThanOrEqual(15);
  });

  it.each(cases.map((c) => [c.name, c] as const))("[B4-R04] vector: %s", (_, c) => {
    if ("error" in c.expected) {
      expect(() => evaluateOffer(c.offer)).toThrow(c.expected.error);
    } else {
      expect(evaluateOffer(c.offer)).toEqual(c.expected);
    }
  });

  it("[B4-R04] parseDecimal and formatDecimal round-trip and reject bad input", () => {
    expect(parseDecimal("612.345", 3)).toBe(612345n);
    expect(parseDecimal("5", 2)).toBe(500n);
    expect(formatDecimal(612345n, 3)).toBe("612.345");
    expect(formatDecimal(5n, 3)).toBe("0.005");
    expect(formatDecimal(7n, 0)).toBe("7");
    expect(() => parseDecimal("1.2345", 3)).toThrow();
    for (const bad of ["", "abc", "-1", "1.", ".5", "1,5", "1e3"]) {
      expect(() => parseDecimal(bad, 3)).toThrow();
    }
  });

  it("[B4-R04] quantityMt is exact and lineCost rounds half-up to cents", () => {
    const line = (unit: "mt" | "m3", quantity: string, inq: string | null, off: string | null) => ({
      line_id: "A",
      unit,
      quantity,
      inquiry_density: inq,
      price_per_mt: null,
      offer_density: off,
    });
    const qty = quantityMt(line("m3", "1000.001", "850.5", null));
    expect(qty && formatQty(qty)).toBe("850.5008505");
    expect(quantityMt(line("m3", "1.000", null, null))).toBeNull();
    expect(quantityMt(line("m3", "1.000", "900.0", "700.0"))).toEqual(
      quantityMt(line("m3", "1.000", "900.0", null)),
    );
    expect(lineCost({ v: 1000n, scale: 3 }, 5n)).toBe(1n); // 1.000 mt x 0.005 = 0.005 -> 0.01
    expect(lineCost({ v: 999n, scale: 3 }, 5n)).toBe(0n); // 0.999 x 0.005 = 0.004995 -> 0.00
  });

  it("[B4-R04] formatUsd groups thousands and keeps two decimals", () => {
    expect(formatUsd("1234567.89")).toBe("USD 1,234,567.89");
    expect(formatUsd("0.01")).toBe("USD 0.01");
    expect(formatUsd("999")).toBe("USD 999.00");
  });

  it("[B4-R12] formatUsd shows a negative value with a sign, for display only", () => {
    expect(formatUsd("-25000.00")).toBe("USD -25,000.00");
    expect(formatUsd("-0.05")).toBe("USD -0.05");
    expect(parseDecimal("-1.00", 2, true)).toBe(-100n);
    expect(() => parseDecimal("-1.00", 2)).toThrow(); // prices stay non-negative
  });

  it("[B4-R04][B4-R12] money.ts and OfferEntry.tsx never use float conversions", () => {
    for (const file of ["money.ts", "offers/OfferEntry.tsx"]) {
      const text = readFileSync(resolve(process.cwd(), "src", file), "utf8");
      for (const banned of ["parseFloat(", "Number(", "toFixed("]) {
        expect(text, `${file} contains ${banned}`).not.toContain(banned);
      }
    }
  });
});
