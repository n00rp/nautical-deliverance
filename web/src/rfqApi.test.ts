import { afterEach, describe, expect, it, vi } from "vitest";
import { createRfqApi } from "./rfqApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

const api = createRfqApi({
  token: () => Promise.resolve("tok"),
  renew: () => Promise.resolve(null),
});
const B = "http://api.test/api/v1";
const recipients = [{ counterparty_id: "c1", contact_id: "k1" }];

describe("RFQ API client", () => {
  it.each([
    [
      "suggestions",
      () => api.getSuggestions("i1"),
      "GET",
      `${B}/inquiries/i1/suggestions`,
      undefined,
    ],
    ["log", () => api.listRfqs("i1"), "GET", `${B}/inquiries/i1/rfqs`, undefined],
    [
      "create",
      () => api.createRfqs("i1", { deadline: "2026-11-10T08:00:00.000Z", recipients }),
      "POST",
      `${B}/inquiries/i1/rfqs`,
      { deadline: "2026-11-10T08:00:00.000Z", recipients },
    ],
    ["preview", () => api.getPreview("r1"), "GET", `${B}/rfqs/r1/preview`, undefined],
    [
      "patch",
      () => api.patchRfq("r1", 2, { contact_id: "k2" }),
      "PATCH",
      `${B}/rfqs/r1`,
      { contact_id: "k2", version: 2 },
    ],
    ["mark sent", () => api.markSent("r1", 1), "POST", `${B}/rfqs/r1/mark-sent`, { version: 1 }],
    ["withdraw", () => api.withdrawRfq("r1", 1), "POST", `${B}/rfqs/r1/withdraw`, { version: 1 }],
    ["decline", () => api.declineRfq("r1", 3), "POST", `${B}/rfqs/r1/decline`, { version: 3 }],
    ["history", () => api.rfqHistory("r1"), "GET", `${B}/rfqs/r1/history`, undefined],
  ])("[B3-R13] %s", async (_, run, method, url, body) => {
    const f = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await run();
    const [calledUrl, init] = f.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe(url);
    expect(init.method).toBe(method);
    expect(init.body === undefined ? undefined : JSON.parse(init.body as string)).toEqual(body);
  });
});
