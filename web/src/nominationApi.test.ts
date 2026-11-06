import { afterEach, describe, expect, it, vi } from "vitest";
import { createNominationApi } from "./nominationApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

const api = createNominationApi({
  token: () => Promise.resolve("tok"),
  renew: () => Promise.resolve(null),
});
const B = "http://api.test/api/v1";

describe("nomination API client", () => {
  it.each([
    ["list", () => api.listNominations("i1"), "GET", `${B}/inquiries/i1/nominations`, undefined],
    ["create", () => api.createNomination("i1"), "POST", `${B}/inquiries/i1/nominations`, {}],
    [
      "create for a contact",
      () => api.createNomination("i1", "k2"),
      "POST",
      `${B}/inquiries/i1/nominations`,
      { contact_id: "k2" },
    ],
    [
      "preview",
      () => api.getNominationPreview("n1"),
      "GET",
      `${B}/nominations/n1/preview`,
      undefined,
    ],
    [
      "patch",
      () => api.patchNomination("n1", 2, "k2"),
      "PATCH",
      `${B}/nominations/n1`,
      { version: 2, contact_id: "k2" },
    ],
    [
      "mark sent",
      () => api.markNominationSent("n1", 1),
      "POST",
      `${B}/nominations/n1/mark-sent`,
      { version: 1 },
    ],
    [
      "withdraw",
      () => api.withdrawNomination("n1", 1),
      "POST",
      `${B}/nominations/n1/withdraw`,
      { version: 1 },
    ],
  ])("[B5-R11] %s", async (_, run, method, url, body) => {
    const f = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await run();
    const [calledUrl, init] = f.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe(url);
    expect(init.method).toBe(method);
    expect(init.body === undefined ? undefined : JSON.parse(init.body as string)).toEqual(body);
  });

  it("[B5-R11] a 409 keeps the engine's text as ApiError.detail", async () => {
    const body = JSON.stringify({ detail: "Nomination total differs from the decision" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 409 })));
    const e = await api.markNominationSent("n1", 1).catch((x: unknown) => x);
    expect(e).toMatchObject({
      status: 409,
      detail: "Nomination total differs from the decision",
      issues: [],
    });
  });
});
