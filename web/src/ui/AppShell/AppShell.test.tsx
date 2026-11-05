import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

const nav = [
  { href: "#worklist", label: "Work list", section: "Purchase" },
  { href: "#inquiry", label: "Inquiry", section: "Purchase" },
  { href: "#reports", label: "Reports", disabled: true, section: "Later" },
];

const shell = (props: Partial<Parameters<typeof AppShell>[0]> = {}) =>
  render(
    <AppShell
      productName="Bunker Desk"
      user={{ name: "Ada", roles: ["admin", "viewer"] }}
      nav={nav}
      {...props}
    >
      <p>content</p>
    </AppShell>,
  );

describe("AppShell", () => {
  afterEach(cleanup);

  it("[B1-R13] app shell: product name, user, roles, banner and content", () => {
    shell({ banner: "Demo data only" });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Bunker Desk");
    expect(screen.getByText("Ada")).toBeTruthy();
    expect(screen.getByText("admin, viewer")).toBeTruthy();
    expect(screen.getByRole("note").textContent).toBe("Demo data only");
    expect(within(screen.getByRole("main")).getByText("content")).toBeTruthy();
  });

  it("[B1-R13] app shell: nav links, disabled entries are not links, sections shown once", () => {
    shell();
    const main = screen.getByRole("navigation", { name: "Main" });
    expect(
      within(main)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Work list", "Inquiry"]);
    expect(within(main).getByText("Reports").closest("a")).toBeNull();
    expect(within(main).getAllByText("Purchase")).toHaveLength(1);
  });

  it("[B1-R13] app shell: narrow menu button toggles the nav", async () => {
    shell();
    const button = screen.getByRole("button", { name: "Menu" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    await userEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("navigation", { name: "Main" }).id).toBe(
      button.getAttribute("aria-controls"),
    );
    await userEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("[B1-R13] app shell: signed out and without nav renders no user, menu or nav", () => {
    shell({ user: null, nav: [] });
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("button", { name: "Menu" })).toBeNull();
    expect(screen.queryByText("Ada")).toBeNull();
  });
});
