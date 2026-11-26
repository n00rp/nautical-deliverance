import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { createInquiryApi, STATUS_LABEL } from "./inquiryApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const stub = (response: Response) => {
  const f = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", f);
  return f;
};

const renew = vi.fn().mockResolvedValue("fresh");
const api = createInquiryApi({ token: () => Promise.resolve("tok"), renew });
const B = "http://api.test/api/v1";

describe("inquiry API client", () => {
  it.each([
    ["list", () => api.listInquiries({}), "GET", `${B}/inquiries`, undefined],
    [
      "list with every filter",
      () => api.listInquiries({ status: "all", q: "a b", mine: true, sort: "reference" }),
      "GET",
      `${B}/inquiries?status=all&q=a+b&mine=true&sort=reference`,
      undefined,
    ],
    [
      "[B7a-R01] list by phase",
      () => api.listInquiries({ phase: "stemmed", q: "a" }),
      "GET",
      `${B}/inquiries?phase=stemmed&q=a`,
      undefined,
    ],
    [
      "[B7a-R02] phase counts",
      () => api.phaseCounts({ q: "a", mine: true }),
      "GET",
      `${B}/inquiries/phase-counts?q=a&mine=true`,
      undefined,
    ],
    ["get", () => api.getInquiry("i1"), "GET", `${B}/inquiries/i1`, undefined],
    [
      "create",
      () => api.createInquiry({ vessel_id: "v" }),
      "POST",
      `${B}/inquiries`,
      { vessel_id: "v" },
    ],
    [
      "patch",
      () => api.patchInquiry("i1", 3, { voyage: "V1" }),
      "PATCH",
      `${B}/inquiries/i1`,
      { voyage: "V1", version: 3 },
    ],
    ["take", () => api.takeInquiry("i1", 2), "POST", `${B}/inquiries/i1/take`, { version: 2 }],
    [
      "cancel",
      () => api.cancelInquiry("i1", 2, "Changed plan"),
      "POST",
      `${B}/inquiries/i1/cancel`,
      { version: 2, reason: "Changed plan" },
    ],
    [
      "duplicate",
      () => api.duplicateInquiry("i1", 2),
      "POST",
      `${B}/inquiries/i1/duplicate`,
      { version: 2 },
    ],
    ["users", () => api.listUsers(), "GET", `${B}/users`, undefined],
    [
      "users by role",
      () => api.listUsers("bunker_buyer"),
      "GET",
      `${B}/users?role=bunker_buyer`,
      undefined,
    ],
  ])("[B2-R12] %s", async (_, run, method, url, body) => {
    const f = stub(json([]));
    await run();
    const [calledUrl, init] = f.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe(url);
    expect(init.method).toBe(method);
    expect(init.body === undefined ? undefined : JSON.parse(init.body as string)).toEqual(body);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("[B2-R11] history reshapes the changes for HistoryList", async () => {
    stub(
      json([
        {
          id: "h",
          actor: "u",
          at: "t",
          action: "take",
          changes: { buyer_id: { before: null, after: "u" } },
        },
      ]),
    );
    const [entry] = await api.inquiryHistory("i1");
    expect(entry?.changes).toEqual([{ field: "buyer_id", before: null, after: "u" }]);
  });

  it("[B2-R12] keeps decimals as strings", async () => {
    stub(json({ lines: [{ quantity: "1000.500" }] }));
    const inquiry = await api.getInquiry("i1");
    expect(inquiry.lines[0]?.quantity).toBe("1000.500");
  });

  it("[B2-R12] retries once with a renewed token after a 401", async () => {
    const f = vi.fn().mockResolvedValueOnce(json({}, 401)).mockResolvedValueOnce(json([]));
    vi.stubGlobal("fetch", f);
    await api.listInquiries({});
    expect((f.mock.calls[1] as [string, RequestInit])[1].headers).toMatchObject({
      Authorization: "Bearer fresh",
    });
  });

  it("[B2-R12] throws ApiError with the 422 field list", async () => {
    stub(json({ detail: [{ field: "lines[0].quantity", message: "Bad" }] }, 422));
    const err = await api.createInquiry({}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).issues).toEqual([{ field: "lines[0].quantity", message: "Bad" }]);
  });

  it("[B2-R12] has a label for each engine status", () => {
    expect(Object.keys(STATUS_LABEL)).toEqual([
      "draft",
      "rfq_sent",
      "offers_received",
      "winner_selected",
      "nominated",
      "cancelled",
    ]);
  });
});
