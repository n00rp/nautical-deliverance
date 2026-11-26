import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { InquiryListItem } from "../inquiryApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { item } from "./testSupport";
import { WorkList } from "./WorkList";

beforeAll(() => {
  // jsdom lacks the pointer/scroll APIs Radix Select uses.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});
afterEach(() => {
  cleanup();
  phaseCounts.mockClear();
  window.location.hash = "";
  vi.useRealTimers();
});

const phaseCounts = vi.fn().mockResolvedValue({ list: 1, market: 2, stemmed: 3, cancelled: 4 });

function setup(rows: InquiryListItem[] = [item("1")], roles: Role[] = ["admin"]) {
  const listInquiries = vi.fn().mockResolvedValue(rows);
  render(
    <ToastProvider>
      <WorkList api={{ listInquiries, phaseCounts }} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
  return listInquiries;
}

const lastParams = (f: ReturnType<typeof setup>) => f.mock.lastCall?.[0] as unknown;

describe("WorkList", () => {
  it("[B2-R12] renders the columns and a row", async () => {
    setup([item("1", { status: "rfq_sent" })]);
    const headers = (await screen.findAllByRole("columnheader")).map((h) => h.textContent);
    expect(headers).toEqual(["Reference", "Vessel", "Port", "ETA", "Status", "Next step", "Buyer"]);
    const row = within(await screen.findByRole("row", { name: /INQ-2611-001/ }));
    expect(row.getByText("Test Vessel")).toBeTruthy();
    expect(row.getByText("Rotterdam")).toBeTruthy();
    expect(row.getByText("12 Nov 06:00 UTC · 07:00 local")).toBeTruthy();
    expect(row.getAllByText("RFQ sent")).toHaveLength(2); // status pill and next step
    expect(row.getByText("Bea Buyer")).toBeTruthy();
  });

  it("[B3-R13] next step of a draft: assign a buyer or create RFQs", async () => {
    setup([item("1", { buyer_name: null }), item("2")]);
    const next = async (n: string) =>
      within(await screen.findByRole("row", { name: new RegExp(`INQ-2611-00${n}`) }));
    expect((await next("1")).getByText("Assign buyer")).toBeTruthy();
    expect((await next("2")).getByText("Create RFQs")).toBeTruthy();
  });

  it("[B3-R13] after the first send the next step counts the drafts that remain", async () => {
    setup([
      item("1", { status: "rfq_sent", rfq_total: 3, rfq_sent: 1 }),
      item("2", { status: "offers_received", rfq_total: 2, rfq_sent: 1 }),
      item("3", { status: "rfq_sent", rfq_total: 2, rfq_sent: 2 }),
    ]);
    const next = async (n: string) =>
      within(await screen.findByRole("row", { name: new RegExp(`INQ-2611-00${n}`) }));
    expect((await next("1")).getByText("1 of 3 RFQs sent")).toBeTruthy();
    expect((await next("2")).getByText("1 of 2 RFQs sent")).toBeTruthy();
    expect((await next("3")).queryByText(/RFQs sent/)).toBeNull(); // all sent: the status label
    expect((await next("3")).getAllByText("RFQ sent")).toHaveLength(2);
  });

  it("[B3-R13] the RFQ progress links straight to the RFQ log", async () => {
    setup([item("1", { status: "rfq_sent", rfq_total: 3, rfq_sent: 1 })]);
    const link = await screen.findByRole("link", { name: "1 of 3 RFQs sent" });
    expect(link.getAttribute("href")).toBe("#/inquiries/1/rfqs");
    await userEvent.click(link);
    expect(window.location.hash).toBe("#/inquiries/1/rfqs");
  });

  it("[B4-R12] offers received link to the comparison, a selected winner asks for a nomination", async () => {
    setup([
      item("1", { status: "offers_received", rfq_total: 3, rfq_sent: 3, offer_total: 2 }),
      item("2", { status: "offers_received", rfq_total: 3, rfq_sent: 1, offer_total: 1 }),
      item("3", { status: "winner_selected", rfq_total: 3, rfq_sent: 3, offer_total: 2 }),
    ]);
    const two = await screen.findByRole("link", { name: "Compare 2 offers" });
    expect(two.getAttribute("href")).toBe("#/inquiries/1/offers");
    expect(screen.getByRole("link", { name: "Compare 1 offer" })).toBeTruthy();
    const third = within(await screen.findByRole("row", { name: /INQ-2611-003/ }));
    expect(third.getByText("Create nomination")).toBeTruthy();
  });

  it("[B5-R11] a winner links to the nomination screen; a nominated inquiry shows its version", async () => {
    setup([
      item("1", { status: "winner_selected", rfq_total: 3, rfq_sent: 3, offer_total: 2 }),
      item("2", { status: "nominated", rfq_total: 3, rfq_sent: 3, nomination_sent: 2 }),
    ]);
    const create = await screen.findByRole("link", { name: "Create nomination" });
    expect(create.getAttribute("href")).toBe("#/inquiries/1/nomination");
    const done = screen.getByRole("link", { name: "Nominated (v2)" });
    expect(done.getAttribute("href")).toBe("#/inquiries/2/nomination");
  });

  it("[B5-R11] the first nomination version shows no version number", async () => {
    setup([item("1", { status: "nominated", rfq_total: 3, rfq_sent: 3, nomination_sent: 1 })]);
    expect(await screen.findByRole("link", { name: "Nominated" })).toBeTruthy();
  });

  it("[B5-R11] a winner with a waiting draft says Send nomination", async () => {
    setup([
      item("1", { status: "winner_selected", rfq_total: 3, rfq_sent: 3, nomination_draft: true }),
    ]);
    const link = await screen.findByRole("link", { name: "Send nomination" });
    expect(link.getAttribute("href")).toBe("#/inquiries/1/nomination");
  });

  it("[B5-R11] the Operator sees Nominated with the supplier and no link", async () => {
    setup(
      [
        item("1", {
          status: "nominated",
          rfq_total: null,
          rfq_sent: null,
          offer_total: null,
          nomination_sent: null,
          winner_counterparty_name: "Beta Marine",
        }),
      ],
      ["operator"],
    );
    expect(await screen.findByText("Nominated: Beta Marine")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("[B4-R12] the Operator sees the selected supplier and no comparison", async () => {
    setup(
      [
        item("1", {
          status: "winner_selected",
          rfq_total: null,
          rfq_sent: null,
          offer_total: null,
          winner_counterparty_name: "Beta Marine",
        }),
        item("2", {
          status: "offers_received",
          rfq_total: null,
          rfq_sent: null,
          offer_total: null,
        }),
      ],
      ["operator"],
    );
    expect(await screen.findByText("Selected supplier: Beta Marine")).toBeTruthy();
    expect(screen.queryByText(/Compare/)).toBeNull();
    expect(screen.queryByText("Create nomination")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("[B3-R03] the Operator sees no RFQ counts, only the status", async () => {
    setup(
      [
        item("1", { status: "rfq_sent", rfq_total: null, rfq_sent: null }),
        item("2", { rfq_total: null, rfq_sent: null }),
      ],
      ["operator"],
    );
    expect(await screen.findByRole("row", { name: /INQ-2611-001/ })).toBeTruthy();
    expect(screen.queryByText(/RFQs sent/)).toBeNull();
    expect(screen.queryByText("Create RFQs")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("[B2-R12] next step: cancelled shows a dash", async () => {
    setup([item("1"), item("2", { status: "cancelled" })]);
    const cancelled = within(await screen.findByRole("row", { name: /INQ-2611-002/ }));
    expect(cancelled.getByText("—")).toBeTruthy();
  });

  it("[B2-R12] a null ETA says ETA missing and never warns", async () => {
    setup([item("1", { eta: null })]);
    expect(await screen.findByText("ETA missing")).toBeTruthy();
    expect(screen.queryByText(/not nominated/)).toBeNull();
  });

  it("[B2-R12] the warning shows only when eta_warning is set", async () => {
    // Before the fixture's ETA (2026-11-12), so the text is the 48 h one, not "ETA passed".
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-11T12:00:00Z"));
    setup([item("1", { eta_warning: true }), item("2")]);
    const warned = within(await screen.findByRole("row", { name: /INQ-2611-001/ }));
    expect(warned.getByText("ETA in < 48 h, not nominated")).toBeTruthy();
    expect(screen.getAllByText(/not nominated/)).toHaveLength(1);
  });

  it("[B2-R12] a passed ETA says ETA passed instead of the 48 h text", async () => {
    setup([item("1", { eta: "2020-01-01T00:00:00Z", eta_warning: true })]);
    expect(await screen.findByText("ETA passed, not nominated")).toBeTruthy();
    expect(screen.queryByText(/< 48 h/)).toBeNull();
  });

  it("[B2-R12] shows Unassigned without a buyer", async () => {
    setup([item("1", { buyer_name: null })]);
    expect(await screen.findByText("Unassigned")).toBeTruthy();
  });

  it("[B2-R12] Review Focus 5: shows the buyer name from the API, whatever their roles", async () => {
    setup([item("1", { buyer_name: "Former Buyer" })], ["viewer"]);
    expect(await screen.findByText("Former Buyer")).toBeTruthy();
  });

  it("[B7a-R01] shows three tabs with counts and opens In the market", async () => {
    const f = setup();
    expect(await screen.findByRole("tab", { name: "On the list (1)" })).toBeTruthy();
    expect(
      screen.getByRole("tab", { name: "In the market (2)" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.getByRole("tab", { name: "Stemmed (3)" })).toBeTruthy();
    expect(f.mock.calls[0]?.[0]).toEqual({ phase: "market", sort: "eta" });
  });

  it("[B7a-R01] clicking a tab loads that phase and updates the hash", async () => {
    const f = setup();
    await userEvent.click(await screen.findByRole("tab", { name: "Stemmed (3)" }));
    await waitFor(() => {
      expect(lastParams(f)).toEqual({ phase: "stemmed", sort: "eta" });
    });
    expect(window.location.hash).toBe("#/inquiries?phase=stemmed");
  });

  it("[B7a-R01] the hash selects the tab", async () => {
    window.location.hash = "#/inquiries?phase=list";
    setup();
    const tab = await screen.findByRole("tab", { name: "On the list (1)" });
    expect(tab.getAttribute("aria-selected")).toBe("true");
  });

  it("[B7a-R01] Show cancelled lists only cancelled", async () => {
    const f = setup();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Show cancelled" }));
    await waitFor(() => {
      expect(lastParams(f)).toEqual({ phase: "cancelled", sort: "eta" });
    });
    for (const t of screen.getAllByRole("tab"))
      expect(t.getAttribute("aria-selected")).toBe("false");
  });

  it("[B7a-R02] search is the first filter and filters within the tab", async () => {
    const f = setup();
    const search = await screen.findByRole("textbox", { name: "Search" });
    expect(search.closest("div")?.parentElement?.firstElementChild?.contains(search)).toBe(true);
    expect(screen.getByText("Reference, vessel or port")).toBeTruthy();
    await userEvent.type(search, "rott");
    await waitFor(() => {
      expect(lastParams(f)).toEqual({ phase: "market", q: "rott", sort: "eta" });
      expect(phaseCounts).toHaveBeenLastCalledWith({ q: "rott" });
    });
  });

  it("[B7a-R02] a search with no hits in the tab says so", async () => {
    // A search that matches only cancelled inquiries: every tab reads (0).
    phaseCounts
      .mockResolvedValueOnce({ list: 1, market: 2, stemmed: 3, cancelled: 4 })
      .mockResolvedValueOnce({ list: 0, market: 0, stemmed: 0, cancelled: 1 });
    setup([]);
    await userEvent.type(await screen.findByRole("textbox", { name: "Search" }), "zzz");
    expect(await screen.findByText("Nothing matches this search in this tab.")).toBeTruthy();
    for (const name of ["On the list (0)", "In the market (0)", "Stemmed (0)"])
      expect(await screen.findByRole("tab", { name })).toBeTruthy();
  });

  it("[B2-R12] search is debounced by 250 ms", async () => {
    const f = setup();
    await screen.findByText("INQ-2611-001");
    await userEvent.type(screen.getByRole("textbox", { name: "Search" }), "rott");
    expect(f).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(lastParams(f)).toEqual({ phase: "market", q: "rott", sort: "eta" });
    });
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("[B2-R12] sort sends sort=reference", async () => {
    const f = setup();
    await userEvent.click(await screen.findByRole("combobox", { name: "Sort" }));
    await userEvent.click(await screen.findByRole("option", { name: "Reference" }));
    await waitFor(() => {
      expect(lastParams(f)).toEqual({ phase: "market", sort: "reference" });
    });
  });

  it("[B2-R12] Mine sends mine for buyers and admins, and is hidden from operators", async () => {
    const f = setup();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Mine" }));
    await waitFor(() => {
      expect(lastParams(f)).toEqual({ phase: "market", mine: true, sort: "eta" });
    });
    cleanup();
    setup([item("1")], ["operator"]);
    await screen.findByText("INQ-2611-001");
    expect(screen.queryByRole("checkbox", { name: "Mine" })).toBeNull();
  });

  it("[B2-R12] New inquiry is for admin, buyer and operator but not viewer", async () => {
    setup([item("1")], ["operator"]);
    await userEvent.click(await screen.findByRole("button", { name: "New inquiry" }));
    expect(window.location.hash).toBe("#/inquiries/new");
    cleanup();
    setup([item("1")], ["viewer"]);
    await screen.findByText("INQ-2611-001");
    expect(screen.queryByRole("button", { name: "New inquiry" })).toBeNull();
  });

  it("[B2-R12] selecting a row opens the inquiry", async () => {
    setup([item("abc")]);
    await userEvent.click(await screen.findByText("INQ-2611-abc"));
    expect(window.location.hash).toBe("#/inquiries/abc");
  });

  it("[B2-R12] shows the empty state", async () => {
    setup([]);
    expect(await screen.findByText("No inquiries")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "New inquiry" })).toHaveLength(1);
  });

  it("[B2-R12] a failed load shows a toast", async () => {
    const listInquiries = vi.fn().mockRejectedValue(new Error("boom"));
    render(
      <ToastProvider>
        <WorkList api={{ listInquiries, phaseCounts }} roles={["admin"]} />
        <ToastHost />
      </ToastProvider>,
    );
    expect(await screen.findByText("boom")).toBeTruthy();
    // A failure is not an empty result.
    expect(await screen.findByText("Could not load inquiries")).toBeTruthy();
    expect(screen.queryByText("No inquiries")).toBeNull();
  });
});
