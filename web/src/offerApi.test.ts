import { afterEach, describe, expect, it, vi } from "vitest";
import { createOfferApi } from "./offerApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

const api = createOfferApi({
  token: () => Promise.resolve("tok"),
  renew: () => Promise.resolve(null),
});
const B = "http://api.test/api/v1";
const body = {
  valid_until: "2026-11-10T08:00:00.000Z",
  lines: [{ inquiry_line_id: "l1", price_per_mt: "612.345" }],
};

describe("offer API client", () => {
  it.each([
    ["create", () => api.createOffer("r1", body), "POST", `${B}/rfqs/r1/offer`, body],
    ["get", () => api.getOffer("o1"), "GET", `${B}/offers/o1`, undefined],
    [
      "patch",
      () => api.patchOffer("o1", 2, { payment_terms: null }),
      "PATCH",
      `${B}/offers/o1`,
      { payment_terms: null, version: 2 },
    ],
    ["history", () => api.offerHistory("o1"), "GET", `${B}/offers/o1/history`, undefined],
    ["comparison", () => api.getComparison("i1"), "GET", `${B}/inquiries/i1/comparison`, undefined],
    [
      "select winner",
      () => api.selectWinner("i1", 3, { offer_id: "o1", reason: "timing" }),
      "POST",
      `${B}/inquiries/i1/select-winner`,
      { offer_id: "o1", reason: "timing", version: 3 },
    ],
  ])("[B4-R12] %s", async (_, run, method, url, expected) => {
    const f = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await run();
    const [calledUrl, init] = f.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe(url);
    expect(init.method).toBe(method);
    expect(init.body === undefined ? undefined : JSON.parse(init.body as string)).toEqual(expected);
  });
});
