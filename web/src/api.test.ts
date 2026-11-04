import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchMe } from "./api";

const me = { user_id: "u-1", organization: { id: "o-1", name: "Acme" }, roles: ["admin"] };

afterEach(() => {
  vi.unstubAllGlobals();
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
});
