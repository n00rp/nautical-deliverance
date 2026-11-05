import { describe, expect, it } from "vitest";
import { ADMIN_NAV, MASTER_CONFIGS } from "./configs";
import { parseAdmin, parseInquiries } from "./routes";

describe("admin routes", () => {
  it("[B1-R11] parses list, record and new hashes", () => {
    expect(parseAdmin("#/admin/vessels")).toEqual({ path: "vessels", id: undefined });
    expect(parseAdmin("#/admin/vessels/abc")).toEqual({ path: "vessels", id: "abc" });
    expect(parseAdmin("#/admin/ports/new")).toEqual({ path: "ports", id: "new" });
    expect(parseAdmin("#/admin/unknown")).toBeNull();
    expect(parseAdmin("")).toBeNull();
    expect(parseAdmin("#/other")).toBeNull();
  });

  it("[B1-R11] the nav lists all seven pages under Master data", () => {
    expect(ADMIN_NAV).toHaveLength(7);
    expect(ADMIN_NAV.every((n) => n.section === "Master data")).toBe(true);
    expect(ADMIN_NAV.map((n) => n.href)).toEqual(MASTER_CONFIGS.map((c) => `#/admin/${c.path}`));
  });

  it("[B2-R12] parses the inquiry hashes, with the empty hash as the start page", () => {
    expect(parseInquiries("")).toEqual({ id: undefined });
    expect(parseInquiries("#")).toEqual({ id: undefined });
    expect(parseInquiries("#/")).toEqual({ id: undefined });
    expect(parseInquiries("#/inquiries")).toEqual({ id: undefined });
    expect(parseInquiries("#/inquiries/")).toEqual({ id: undefined });
    expect(parseInquiries("#/inquiries/new")).toEqual({ id: "new" });
    expect(parseInquiries("#/inquiries/abc")).toEqual({ id: "abc" });
    expect(parseInquiries("#/admin/ports")).toBeNull();
    expect(parseInquiries("#/inquiries/a/b")).toBeNull();
  });
});
