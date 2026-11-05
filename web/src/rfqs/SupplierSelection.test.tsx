import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { Suggestions } from "../rfqApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { SupplierSelection } from "./SupplierSelection";
import { rfqApi, sentRfq, supplier, suggestions, twoProducts } from "./testSupport";

beforeAll(() => {
  // jsdom lacks the pointer/scroll APIs Radix Select uses.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});
afterEach(() => {
  cleanup();
  window.location.hash = "";
});

const DAY_MS = 86_400_000;
const inDays = (n: number) => new Date(Date.now() + n * DAY_MS).toISOString();

type Api = Parameters<typeof SupplierSelection>[0]["api"];

function setup(
  over: {
    rec?: ReturnType<typeof twoProducts>;
    groups?: Suggestions;
    roles?: Role[];
    create?: Api["createRfqs"];
  } = {},
) {
  const create = over.create ?? vi.fn<Api["createRfqs"]>().mockResolvedValue([]);
  const api = {
    ...rfqApi(over.rec ?? { ...twoProducts(), rfq_deadline: "2026-11-10T08:00:00Z" }, over.groups, [
      sentRfq,
    ]),
    createRfqs: create,
  };
  const getSuggestions = vi.spyOn(api, "getSuggestions");
  render(
    <ToastProvider>
      <SupplierSelection inquiryId="i1" api={api} roles={over.roles ?? ["bunker_buyer"]} />
      <ToastHost />
    </ToastProvider>,
  );
  return { create, getSuggestions };
}

const row = (name: string) => within(screen.getByRole("row", { name: new RegExp(name) }));
const box = (name: string) => row(name).getByRole<HTMLInputElement>("checkbox");

describe("SupplierSelection", () => {
  it("[B3-R13] pre-selects the suppliers that cover everything and labels the rest", async () => {
    setup();
    await screen.findByRole("button", { name: "Create 2 RFQ drafts" });
    expect(box("Alpha Marine").checked).toBe(true);
    expect(box("Beta Marine").checked).toBe(true);
    expect(box("Gamma Marine").checked).toBe(false);
    expect(row("Gamma Marine").getByText("Covers: MGO 0.1%")).toBeTruthy();
    expect(box("Delta Marine").checked).toBe(false);
    expect(screen.getByText("Not listed for this port (1)").closest("details")).toBeTruthy();
    expect(screen.getByText("Covers all products (2)")).toBeTruthy();
    expect(screen.getByText("Covers some products (1)")).toBeTruthy();
  });

  it("[B3-R13] the create button counts the selection and is disabled at zero", async () => {
    setup();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select Gamma Marine" }));
    expect(screen.getByRole("button", { name: "Create 3 RFQ drafts" })).toBeTruthy();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Alpha Marine" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Beta Marine" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Gamma Marine" }));
    const button = screen.getByRole<HTMLButtonElement>("button", { name: "Create 0 RFQ drafts" });
    expect(button.disabled).toBe(true);
  });

  it("[B3-R13] sends the primary contact by default and the chosen one after a change", async () => {
    const { create } = setup();
    const alpha = await screen.findByRole("combobox", { name: "Contact for Alpha Marine" });
    expect(alpha.textContent).toContain("Alpha Primary");
    await userEvent.click(alpha);
    await userEvent.click(await screen.findByRole("option", { name: /Alpha Second/ }));
    await userEvent.click(screen.getByRole("button", { name: "Create 2 RFQ drafts" }));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith("i1", {
        deadline: "2026-11-10T08:00:00.000Z",
        recipients: [
          { counterparty_id: "Alpha", contact_id: "Alpha-2" },
          { counterparty_id: "Beta", contact_id: "Beta-1" },
        ],
      });
    });
    expect(window.location.hash).toBe("#/inquiries/i1/rfqs");
  });

  it("[B3-R13] a supplier with an active RFQ shows its status and cannot be selected", async () => {
    setup({
      groups: {
        ...suggestions,
        covers_all: [
          suggestions.covers_all[0] ?? supplier("Alpha"),
          supplier("Beta", { active_rfq_id: "r1" }),
        ],
      },
    });
    await screen.findByRole("button", { name: "Create 1 RFQ drafts" });
    expect(row("Beta Marine").getByText("RFQ sent")).toBeTruthy();
    expect(box("Beta Marine").checked).toBe(false);
    expect(box("Beta Marine").disabled).toBe(true);
    expect(row("Beta Marine").getByRole("combobox").hasAttribute("disabled")).toBe(true);
  });

  it("[B3-R13] a supplier without a usable contact cannot be selected", async () => {
    setup({
      groups: {
        ...suggestions,
        covers_all: [supplier("Alpha", { contacts: [], primary_contact_id: null })],
      },
    });
    await screen.findByRole("button", { name: "Create 0 RFQ drafts" });
    expect(box("Alpha Marine").disabled).toBe(true);
    expect(row("Alpha Marine").getByText("No contact with an e-mail address")).toBeTruthy();
  });

  it.each([
    ["the inquiry's own deadline", { rfq_deadline: "2026-11-10T08:00:00Z" }, "2026-11-10T08:00"],
    [
      "ETA - 48 h when the ETA is 72 h or more away",
      { eta: "2099-01-10T06:00:00Z" },
      "2099-01-08T06:00",
    ],
    ["empty when the ETA is under 72 h away", { eta: inDays(2) }, ""],
    ["empty without an ETA", { eta: null }, ""],
  ])("[B3-R13] deadline pre-fill: %s", async (_, fields, expected) => {
    setup({ rec: { ...twoProducts(), rfq_deadline: null, ...fields } });
    const field = await screen.findByLabelText<HTMLInputElement>(/^Offer deadline/);
    expect(field.value).toBe(expected);
    const button = screen.getByRole<HTMLButtonElement>("button", { name: /^Create 2 RFQ drafts/ });
    expect(button.disabled).toBe(expected === "");
  });

  it("[B3-R13] shows the deadline in port time", async () => {
    setup();
    expect(await screen.findByText("10 Nov 08:00 UTC · 09:00 local")).toBeTruthy();
  });

  it("[B3-R13] a 422 on recipients[1].contact_id appears on that row and clears on change", async () => {
    const create = vi
      .fn<Api["createRfqs"]>()
      .mockRejectedValue(
        new ApiError(422, [{ field: "recipients[1].contact_id", message: "Inactive contact" }]),
      );
    setup({ create });
    await userEvent.click(await screen.findByRole("button", { name: "Create 2 RFQ drafts" }));
    await waitFor(() => {
      expect(row("Beta Marine").getByText("Inactive contact")).toBeTruthy();
    });
    expect(
      within(screen.getByRole("row", { name: /Alpha Marine/ })).queryByText("Inactive contact"),
    ).toBeNull();
    await userEvent.click(row("Beta Marine").getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: /Beta Second/ }));
    expect(screen.queryByText("Inactive contact")).toBeNull();
  });

  it("[B3-R13] a 422 on the deadline appears on the deadline field", async () => {
    setup({
      create: vi
        .fn<Api["createRfqs"]>()
        .mockRejectedValue(
          new ApiError(422, [{ field: "deadline", message: "Must be in the future" }]),
        ),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Create 2 RFQ drafts" }));
    const field = await screen.findByLabelText(/^Offer deadline/);
    await waitFor(() => {
      expect(field.getAttribute("aria-invalid")).toBe("true");
    });
    expect(screen.getAllByText("Must be in the future").length).toBeGreaterThan(0);
  });

  it("[B3-R13] a missing buyer is reported in the summary", async () => {
    setup({
      create: vi
        .fn<Api["createRfqs"]>()
        .mockRejectedValue(
          new ApiError(422, [
            { field: "buyer_id", message: "Assign a buyer before creating RFQs" },
          ]),
        ),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Create 2 RFQ drafts" }));
    expect(
      await screen.findByRole("link", { name: "Assign a buyer before creating RFQs" }),
    ).toBeTruthy();
  });

  it("[B3-R13] a second click while the request is in flight sends nothing more", async () => {
    let finish: () => void = () => undefined;
    const create = vi.fn<Api["createRfqs"]>(() => new Promise((r) => (finish = () => r([]))));
    setup({ create });
    await screen.findByRole("button", { name: "Create 2 RFQ drafts" });
    fireEvent.submit(screen.getByRole("form", { name: "Supplier selection" }));
    fireEvent.submit(screen.getByRole("form", { name: "Supplier selection" }));
    expect(create).toHaveBeenCalledTimes(1);
    finish();
  });

  it.each<Role[]>([["operator"], ["viewer"]])(
    "[B3-R13] %s has no access and loads nothing",
    (...roles) => {
      const { getSuggestions } = setup({ roles: roles.flat() });
      expect(screen.getByText(/^Hidden for your role/)).toBeTruthy();
      expect(screen.queryByRole("button", { name: /RFQ drafts/ })).toBeNull();
      expect(getSuggestions).not.toHaveBeenCalled();
    },
  );

  it("[B3-R13] says so when nothing could be loaded", async () => {
    const api = rfqApi();
    api.getSuggestions = () => Promise.reject(new ApiError(403));
    render(
      <ToastProvider>
        <SupplierSelection inquiryId="i1" api={api} roles={["admin"]} />
        <ToastHost />
      </ToastProvider>,
    );
    expect(await screen.findByText("Could not load suppliers")).toBeTruthy();
  });

  it("[B3-R13] says so when no supplier covers every product", async () => {
    setup({ groups: { covers_all: [], covers_some: suggestions.covers_some, not_listed: [] } });
    expect(await screen.findByText("No supplier covers every product")).toBeTruthy();
  });
});
