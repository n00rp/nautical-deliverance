import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { createMasterApi } from "./masterApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stub(response: Response) {
  const f = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", f);
  return f;
}

const api = createMasterApi("tok");
const B = "http://api.test/api/v1/master";
const C = `${B}/counterparties/c1/contacts`;

describe("master API client", () => {
  it.each([
    [
      "list",
      () => api.list("ports", "all", "a b"),
      "GET",
      `${B}/ports?active=all&q=a+b`,
      [],
      undefined,
    ],
    [
      "list without q",
      () => api.list("ports", "true"),
      "GET",
      `${B}/ports?active=true`,
      [],
      undefined,
    ],
    ["get", () => api.get("ports", "i1"), "GET", `${B}/ports/i1`, {}, undefined],
    ["create", () => api.create("ports", { name: "n" }), "POST", `${B}/ports`, {}, { name: "n" }],
    [
      "update",
      () => api.update("ports", "i1", 3, { name: "n" }),
      "PATCH",
      `${B}/ports/i1`,
      {},
      { name: "n", version: 3 },
    ],
    [
      "deactivate",
      () => api.setActive("ports", "i1", 3, false),
      "POST",
      `${B}/ports/i1/deactivate`,
      {},
      { version: 3 },
    ],
    [
      "reactivate",
      () => api.setActive("ports", "i1", 3, true),
      "POST",
      `${B}/ports/i1/reactivate`,
      {},
      { version: 3 },
    ],
    ["contacts", () => api.contacts("c1"), "GET", `${C}?active=all`, [], undefined],
    ["add contact", () => api.addContact("c1", { name: "n" }), "POST", C, {}, { name: "n" }],
    [
      "update contact",
      () => api.updateContact("c1", "k1", 2, { name: "n" }),
      "PATCH",
      `${C}/k1`,
      {},
      { name: "n", version: 2 },
    ],
    [
      "deactivate contact",
      () => api.setContactActive("c1", "k1", 2, false),
      "POST",
      `${C}/k1/deactivate`,
      {},
      { version: 2 },
    ],
    [
      "reactivate contact",
      () => api.setContactActive("c1", "k1", 2, true),
      "POST",
      `${C}/k1/reactivate`,
      {},
      { version: 2 },
    ],
    [
      "get set",
      () => api.getSet("counterparties/c1/coverage"),
      "GET",
      `${B}/counterparties/c1/coverage`,
      { version: 1, items: [] },
      undefined,
    ],
    [
      "put set",
      () => api.putSet("vessels/v1/approved-fuels", 4, [{ product_id: "p" }]),
      "PUT",
      `${B}/vessels/v1/approved-fuels`,
      { version: 5, items: [] },
      { version: 4, items: [{ product_id: "p" }] },
    ],
  ])(
    "[B1-R11] %s sends the right request with the bearer token",
    async (_n, call, method, url, reply, body) => {
      const f = stub(json(reply));
      await call();
      const [sentUrl, init] = f.mock.calls[0] as [string, RequestInit];
      expect(sentUrl).toBe(url);
      expect(init.method).toBe(method);
      expect(init.body === undefined ? undefined : JSON.parse(init.body as string)).toEqual(body);
      expect(init.headers).toMatchObject({ Authorization: "Bearer tok" });
    },
  );

  it("[B1-R11] history turns the changes map into a list", async () => {
    stub(
      json([
        {
          id: "h1",
          actor: "u1",
          at: "2026-11-05T10:00:00Z",
          action: "update",
          changes: { name: { before: "a", after: "b" } },
        },
      ]),
    );
    await expect(api.history("ports", "i1")).resolves.toEqual([
      {
        id: "h1",
        actor: "u1",
        at: "2026-11-05T10:00:00Z",
        action: "update",
        changes: [{ field: "name", before: "a", after: "b" }],
      },
    ]);
  });

  it("[B1-R11] a 422 carries the field issues, a 409 the status", async () => {
    stub(json({ detail: [{ field: "imo", message: "Invalid IMO number" }] }, 422));
    const err = await api.create("vessels", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 422,
      issues: [{ field: "imo", message: "Invalid IMO number" }],
    });

    stub(json({ detail: "Record was changed by someone else" }, 409));
    await expect(api.update("vessels", "x", 1, {})).rejects.toMatchObject({
      status: 409,
      issues: [],
    });
  });

  it("[B1-R11] ids from the URL are encoded in request paths", async () => {
    const f = stub(json({}));
    await api.get("ports", "../x/y");
    expect((f.mock.calls[0] as [string])[0]).toBe(`${B}/ports/..%2Fx%2Fy`);
  });

  it("[B1-R11] an unreadable error body still gives an ApiError", async () => {
    stub(new Response("<html>", { status: 502 }));
    await expect(api.get("ports", "x")).rejects.toMatchObject({ status: 502, issues: [] });
  });
});
