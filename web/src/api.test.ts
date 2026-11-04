import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchMe } from "./api";

const me = { user_id: "u-1", organization: { id: "o-1", name: "Acme" }, roles: ["admin"] };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("fetchMe", () => {
  it("[S0-R03] fetchMe sends bearer token and parses response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(me), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchMe("tok")).resolves.toEqual(me);

    expect(fetchMock).toHaveBeenCalledWith("http://api.test/api/v1/me", {
      headers: { Authorization: "Bearer tok" },
    });
  });

  it("[S0-R03] fetchMe throws ApiError with status on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));

    await expect(fetchMe("bad")).rejects.toMatchObject({ name: "ApiError", status: 401 });
    await expect(fetchMe("bad")).rejects.toBeInstanceOf(ApiError);
  });

  it("[S0-R03] fetchMe does not double the slash for a trailing-slash base URL", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://api.test/");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(me), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchMe("tok");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://api.test/api/v1/me");
  });

  it.each([
    ["null", null],
    ["no org", { user_id: "u", roles: [] }],
    ["bad org name", { user_id: "u", organization: { id: "o", name: 1 }, roles: [] }],
    ["bad roles", { user_id: "u", organization: { id: "o", name: "n" }, roles: [1] }],
    ["roles not array", { user_id: "u", organization: { id: "o", name: "n" }, roles: "admin" }],
  ])("[S0-R03] fetchMe rejects a malformed body (%s)", async (_label, body) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })),
    );

    await expect(fetchMe("tok")).rejects.toThrow("Unexpected response");
  });
});
