import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseInquiries, useHash } from "../admin/routes";
import { inquiryApi, master } from "../inquiries/pageSupport";
import { InquiryPage } from "../inquiries/InquiryPage";
import type { RfqApi } from "../rfqApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { rfqApi, twoProducts } from "./testSupport";
import { SupplierSelection } from "./SupplierSelection";

afterEach(() => {
  cleanup();
  window.location.hash = "";
  served = rec;
  created.mockClear();
});

// The ETA is 10 days away, so the deadline pre-fills as ETA - 48 h and needs no entry.
const rec = { ...twoProducts(), eta: new Date(Date.now() + 10 * 86_400_000).toISOString() };
const created = vi.fn<RfqApi["createRfqs"]>().mockResolvedValue([]);
const soon = { ...twoProducts(), eta: new Date(Date.now() + 86_400_000).toISOString() };
// Which inquiry the fake API serves; the second test switches to the one without a pre-fill.
let served = rec;
const inquiries = { ...inquiryApi(rec), getInquiry: () => Promise.resolve(served) };
const suppliers = {
  ...rfqApi(rec),
  getInquiry: () => Promise.resolve(served),
  createRfqs: created,
};

function Routes() {
  const route = parseInquiries(useHash());
  return route?.view === "suppliers" ? (
    <SupplierSelection inquiryId="i1" api={suppliers} roles={["bunker_buyer"]} />
  ) : (
    <InquiryPage id="i1" api={inquiries} master={master} roles={["bunker_buyer"]} />
  );
}

describe("step budget", () => {
  it("[B3-R13] creating RFQs for the pre-selected suppliers from the inquiry page takes at most 5 interactions", async () => {
    window.location.hash = "#/inquiries/i1";
    render(
      <ToastProvider>
        <Routes />
        <ToastHost />
      </ToastProvider>,
    );

    let steps = 0;
    const click = async (el: HTMLElement) => {
      steps += 1;
      await userEvent.click(el);
    };

    await click(await screen.findByRole("button", { name: "Select suppliers" }));
    await click(await screen.findByRole("button", { name: "Create 2 RFQ drafts" }));

    await waitFor(() => {
      expect(created).toHaveBeenCalledTimes(1);
    });
    // Documented count: Select suppliers (1), Create 2 RFQ drafts (2).
    expect(steps).toBe(2);
    expect(steps).toBeLessThanOrEqual(5);
  });

  it("[B3-R13] with no pre-filled deadline, entering one still takes at most 5 interactions", async () => {
    // ETA is under 72 h away, so nothing is pre-filled and the deadline must be entered.
    served = soon;
    window.location.hash = "#/inquiries/i1";
    render(
      <ToastProvider>
        <Routes />
        <ToastHost />
      </ToastProvider>,
    );

    let steps = 0;
    const click = async (el: HTMLElement) => {
      steps += 1;
      await userEvent.click(el);
    };

    await click(await screen.findByRole("button", { name: "Select suppliers" }));
    const field = await screen.findByLabelText(/^Offer deadline/);
    steps += 1;
    fireEvent.change(field, { target: { value: "2026-11-10T08:00" } });
    await click(await screen.findByRole("button", { name: "Create 2 RFQ drafts" }));

    await waitFor(() => {
      expect(created).toHaveBeenCalledTimes(1);
    });
    // Documented count: Select suppliers (1), enter the deadline (2), Create 2 RFQ drafts (3).
    expect(steps).toBe(3);
    expect(steps).toBeLessThanOrEqual(5);
  });
});
