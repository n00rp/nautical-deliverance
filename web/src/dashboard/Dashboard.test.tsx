import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Dashboard as Data } from "../dashboardApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Dashboard } from "./Dashboard";
import { empty, full, operator } from "./testSupport";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

function setup(data: Data | Error) {
  const getDashboard = vi.fn(() =>
    data instanceof Error ? Promise.reject(data) : Promise.resolve(data),
  );
  render(
    <ToastProvider>
      <Dashboard api={{ getDashboard }} />
      <ToastHost />
    </ToastProvider>,
  );
}

describe("Dashboard", () => {
  it("[B5-R11] shows each attention kind with its tone, due time and link", async () => {
    setup(full);
    const row = async (ref: string) =>
      within(await screen.findByRole("row", { name: new RegExp(ref) }));
    const deadline = await row("INQ-2611-001");
    expect(deadline.getByText("RFQ deadline").getAttribute("data-tone")).toBe("crit");
    expect(deadline.getByText("12 Nov 06:00 UTC · 07:00 local")).toBeTruthy();
    expect(deadline.getByText("2 RFQ(s) without offer")).toBeTruthy();
    expect((await row("INQ-2611-002")).getByText("Offer validity").getAttribute("data-tone")).toBe(
      "warn",
    );
    expect(
      (await row("INQ-2611-003")).getByText("ETA, not nominated").getAttribute("data-tone"),
    ).toBe("crit");
    const drafts = await row("INQ-2611-004");
    expect(drafts.getByText("RFQ drafts unsent").getAttribute("data-tone")).toBe("warn");
    expect(drafts.getByText("—")).toBeTruthy();
  });

  it("[B5-R11] the reference links to the inquiry and the link navigates", async () => {
    setup(full);
    const link = await screen.findByRole("link", { name: "INQ-2611-001" });
    expect(link.getAttribute("href")).toBe("#/inquiries/i1");
    await userEvent.click(link);
    expect(window.location.hash).toBe("#/inquiries/i1");
  });

  it("[B5-R11] shows the status counts", async () => {
    setup(full);
    const tiles = within(await screen.findByRole("region", { name: "Inquiries by status" }));
    expect(tiles.getAllByRole("term").map((t) => t.textContent)).toEqual([
      "Draft",
      "RFQ sent",
      "Offers received",
      "Winner selected",
      "Nominated",
      "Cancelled",
    ]);
    expect(tiles.getAllByRole("definition").map((d) => d.textContent)).toEqual([
      "2",
      "1",
      "3",
      "0",
      "4",
      "1",
    ]);
  });

  it("[B5-R11] shows the month figures as exact strings", async () => {
    setup(full);
    const month = within(await screen.findByRole("region", { name: "Month 2026-11" }));
    expect(month.getByText("USD 987,654.30")).toBeTruthy();
    expect(month.getByText("1234.5 mt")).toBeTruthy();
    expect(month.getByText("excl. 2 lines without density")).toBeTruthy();
    expect(month.getByText("2.50")).toBeTruthy();
  });

  it("[B5-R11] an empty month: no exclusion note, no average, and nothing needs attention", async () => {
    setup(empty);
    expect(await screen.findByText("Nothing needs attention")).toBeTruthy();
    const month = within(screen.getByRole("region", { name: "Month 2026-11" }));
    expect(month.getByText("USD 0.00")).toBeTruthy();
    expect(month.getByText("0.000 mt")).toBeTruthy();
    expect(month.getByText("—")).toBeTruthy();
    expect(month.queryByText(/excl\./)).toBeNull();
  });

  it("[B5-R11] the Operator view has counts and ETA items, and no month figures", async () => {
    setup(operator);
    expect(await screen.findByText("ETA, not nominated")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Inquiries by status" })).toBeTruthy();
    expect(screen.queryByText(/^Month /)).toBeNull();
    expect(screen.queryByText(/USD/)).toBeNull();
  });

  it("[B5-R11] a failed load says so", async () => {
    setup(new Error("boom"));
    expect(await screen.findByText("Could not load the dashboard")).toBeTruthy();
    expect(await screen.findByText("boom")).toBeTruthy();
  });
});
