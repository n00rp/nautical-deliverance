import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { Inquiry, InquiryApi } from "../inquiryApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { InquiryPage } from "./InquiryPage";
import { inquiry, inquiryApi, master } from "./pageSupport";

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

type Over = Partial<InquiryApi>;

function setup(
  rec: Inquiry | "new" = inquiry(),
  roles: Role[] = ["bunker_buyer"],
  over: Over = {},
) {
  const base = inquiryApi(rec === "new" ? inquiry() : rec);
  const api = {
    ...base,
    getInquiry: vi.fn(base.getInquiry),
    createInquiry: vi.fn(base.createInquiry),
    patchInquiry: vi.fn(base.patchInquiry),
    takeInquiry: vi.fn(base.takeInquiry),
    cancelInquiry: vi.fn(base.cancelInquiry),
    duplicateInquiry: vi.fn(base.duplicateInquiry),
    ...over,
  };
  render(
    <ToastProvider>
      <InquiryPage id={rec === "new" ? "new" : rec.id} api={api} master={master} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
  return api;
}

const form = () => screen.findByRole("form", { name: "Inquiry" });
const combo = (name: string, scope: Pick<typeof screen, "getByRole"> = screen) =>
  scope.getByRole<HTMLButtonElement>("combobox", { name });
async function pick(
  name: string,
  option: string,
  scope: Pick<typeof screen, "getByRole"> = screen,
) {
  await userEvent.click(combo(name, scope));
  await userEvent.click(await screen.findByRole("option", { name: option }));
}
const line = (n: number) => within(screen.getByRole("group", { name: `Line ${String(n)}` }));
const twoLines = () => {
  const [first] = inquiry().lines;
  if (!first) throw new Error("fixture has no line");
  return inquiry({
    lines: [
      first,
      { ...first, id: "l2", position: 2, product_id: "pr2", product_name: "MGO 0.1%" },
    ],
  });
};

describe("InquiryPage vessel selection", () => {
  it("[B2-R13] choosing a vessel shows IMO, type and DWT and fills legal entity and operator", async () => {
    setup("new", ["operator"]);
    await form();
    await pick("Vessel", "Northern Star");
    expect(screen.getByText("IMO 9000001 · Product tanker · 50000 DWT")).toBeTruthy();
    expect(combo("Legal entity").textContent).toContain("Alpha Marine");
    expect(combo("Operator").textContent).toContain("Olga Operator");
  });

  it("[B2-R13] Review Focus 4: a changed vessel refills only values that still hold the old defaults", async () => {
    setup("new", ["bunker_buyer"]);
    await form();
    await pick("Vessel", "Northern Star");
    await pick("Operator", "Oskar Operator"); // the user's own choice, not the vessel default
    await pick("Vessel", "Harbour Light");
    expect(combo("Legal entity").textContent).toContain("Beta Shipping"); // still the default: refilled
    expect(combo("Operator").textContent).toContain("Oskar Operator"); // user's choice: kept
  });
});

describe("InquiryPage roles and locking", () => {
  it("[B2-R13] after Draft the scope fields are disabled with a locked note, the rest stays editable", async () => {
    setup(inquiry({ status: "rfq_sent" }));
    await form();
    expect(screen.getByText("Locked after Draft — duplicate to change scope")).toBeTruthy();
    expect(combo("Vessel").disabled).toBe(true);
    expect(combo("Port").disabled).toBe(true);
    expect(line(1).getByRole("combobox", { name: "Product" })).toHaveProperty("disabled", true);
    expect(screen.queryByRole("button", { name: "Add line" })).toBeNull();
    expect(screen.getByLabelText<HTMLInputElement>(/^ETA/).disabled).toBe(false);
    expect(screen.getByLabelText<HTMLInputElement>("Agent name").disabled).toBe(false);
  });

  it("[B2-R13] a Draft is fully editable for a buyer", async () => {
    setup();
    await form();
    expect(combo("Vessel").disabled).toBe(false);
    expect(screen.queryByText(/Locked after Draft/)).toBeNull();
  });

  it.each<[string, Role]>([
    ["an operator after creating", "operator"],
    ["a viewer", "viewer"],
  ])("[B2-R13] %s sees the page read-only", async (_, role) => {
    setup(inquiry(), [role]);
    await form();
    expect(combo("Vessel").disabled).toBe(true);
    expect(screen.getByLabelText<HTMLInputElement>(/^ETA/).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Duplicate" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel inquiry" })).toBeNull();
    expect(screen.getByText(/Hidden for your role/)).toBeTruthy();
  });

  it("[B2-R13] an operator may create, a viewer may not", async () => {
    setup("new", ["operator"]);
    await form();
    expect(screen.getByRole("button", { name: "Create inquiry" })).toBeTruthy();
    cleanup();
    setup("new", ["viewer"]);
    await form();
    expect(screen.queryByRole("button", { name: "Create inquiry" })).toBeNull();
  });

  it("[B2-R13] a cancelled inquiry is read-only and shows its reason", async () => {
    setup(inquiry({ status: "cancelled", cancel_reason: "Vessel sold" }));
    await form();
    expect(screen.getByText("Cancelled: Vessel sold")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});

describe("InquiryPage errors", () => {
  it("[B2-R13] a 422 maps to fields, including a later line", async () => {
    const api = setup(twoLines(), ["bunker_buyer"], {
      patchInquiry: vi.fn().mockRejectedValue(
        new ApiError(422, [
          { field: "lines[1].quantity", message: "Must be a positive number" },
          { field: "eta", message: "ETA must be in the future" },
        ]),
      ),
    });
    await form();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await line(2).findByText("Must be a positive number")).toBeTruthy();
    expect(line(1).queryByText("Must be a positive number")).toBeNull();
    expect(screen.getAllByText("ETA must be in the future").length).toBeGreaterThan(0);
    expect(screen.getByText("2 problems to fix")).toBeTruthy();
    expect(api.patchInquiry).toHaveBeenCalledTimes(1);
  });

  it("[B2-R13] a 409 shows a toast and reloads the latest version", async () => {
    const api = setup(inquiry(), ["bunker_buyer"], {
      patchInquiry: vi.fn().mockRejectedValue(new ApiError(409)),
    });
    await form();
    await userEvent.type(screen.getByLabelText("Agent name"), "Ahoy Agency");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/changed by someone else/)).toBeTruthy();
    await waitFor(() => {
      expect(api.getInquiry).toHaveBeenCalledTimes(2);
    });
    // The draft is reset to the server state.
    await waitFor(() => {
      expect(screen.getByLabelText<HTMLInputElement>("Agent name").value).toBe("");
    });
  });

  it("[B2-R13] a 403 on save says the role may not change the record", async () => {
    setup(inquiry(), ["bunker_buyer"], {
      patchInquiry: vi.fn().mockRejectedValue(new ApiError(403)),
    });
    await form();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Hidden for your role: saving changes")).toBeTruthy();
  });

  it("[B2-R13] any other failure shows a toast and keeps the draft", async () => {
    setup(inquiry(), ["bunker_buyer"], {
      patchInquiry: vi.fn().mockRejectedValue(new Error("Network down")),
    });
    await form();
    await userEvent.type(screen.getByLabelText("Agent name"), "Ahoy");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Network down")).toBeTruthy();
    expect(screen.getByLabelText<HTMLInputElement>("Agent name").value).toBe("Ahoy");
  });

  it("[B2-R13] a failed load shows an error instead of an empty form", async () => {
    setup(inquiry(), ["bunker_buyer"], {
      getInquiry: vi.fn().mockRejectedValue(new ApiError(404)),
    });
    expect(await screen.findByText("Could not load this inquiry")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Inquiry" })).toBeNull();
  });
});

describe("InquiryPage actions", () => {
  it("[B2-R13] Save sends only what changed, with the current version", async () => {
    const api = setup(inquiry({ version: 3 }));
    await form();
    await userEvent.type(screen.getByLabelText("Agent name"), "Ahoy Agency");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(api.patchInquiry).toHaveBeenCalledWith("i1", 3, { agent_name: "Ahoy Agency" });
    });
    expect(await screen.findByText("Saved")).toBeTruthy();
  });

  it("[B2-R13] Cancel needs a reason", async () => {
    const api = setup(inquiry({ version: 2 }));
    await form();
    await userEvent.click(screen.getByRole("button", { name: "Cancel inquiry" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm cancel inquiry" }));
    expect(screen.getByText("Enter a reason to cancel")).toBeTruthy();
    expect(api.cancelInquiry).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Cancel reason"), "Vessel sold");
    await userEvent.click(screen.getByRole("button", { name: "Cancel inquiry" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm cancel inquiry" }));
    await waitFor(() => {
      expect(api.cancelInquiry).toHaveBeenCalledWith("i1", 2, "Vessel sold");
    });
  });

  it("[B2-R13] Duplicate opens the new Draft", async () => {
    const api = setup(inquiry({ version: 4 }), ["bunker_buyer"], {
      duplicateInquiry: vi.fn().mockResolvedValue(inquiry({ id: "i2" })),
    });
    await form();
    await userEvent.click(screen.getByRole("button", { name: "Duplicate" }));
    await waitFor(() => {
      expect(window.location.hash).toBe("#/inquiries/i2");
    });
    expect(api.duplicateInquiry).toHaveBeenCalledWith("i1", 4);
  });

  it("[B2-R13] a double click on Duplicate sends one request and disables the actions", async () => {
    let finish: (i: Inquiry) => void = () => undefined;
    const api = setup(inquiry({ buyer_id: null, buyer_name: null }), ["bunker_buyer"], {
      duplicateInquiry: vi.fn(
        () =>
          new Promise<Inquiry>((resolve) => {
            finish = resolve;
          }),
      ),
    });
    await form();
    const dup = screen.getByRole("button", { name: "Duplicate" });
    await userEvent.dblClick(dup);
    expect(api.duplicateInquiry).toHaveBeenCalledTimes(1);
    for (const name of ["Take", "Duplicate", "Cancel inquiry"]) {
      expect(screen.getByRole("button", { name }).hasAttribute("disabled")).toBe(true);
    }
    finish(inquiry({ id: "i2" }));
    await waitFor(() => {
      expect(window.location.hash).toBe("#/inquiries/i2");
    });
  });

  it("[B2-R11] an admin's history entry shows the admin's name, and pickers include admins", async () => {
    setup(inquiry(), ["admin"], {
      inquiryHistory: () =>
        Promise.resolve([
          { id: "h2", actor: "ad1", at: "2026-11-05T10:00:00Z", action: "take", changes: [] },
        ]),
    });
    await form();
    const history = within(screen.getByRole("region", { name: "History" }));
    expect(await history.findByText("Ada Admin")).toBeTruthy();
    for (const name of ["Operator", "Buyer"]) {
      await userEvent.click(combo(name));
      expect(await screen.findByRole("option", { name: "Ada Admin" })).toBeTruthy();
      await userEvent.keyboard("{Escape}");
    }
  });

  it("[B2-R13] Take is shown without a buyer, for admins and buyers only", async () => {
    const unassigned = inquiry({ buyer_id: null, buyer_name: null, version: 5 });
    const api = setup(unassigned, ["admin"]);
    await form();
    await userEvent.click(screen.getByRole("button", { name: "Take" }));
    await waitFor(() => {
      expect(api.takeInquiry).toHaveBeenCalledWith("i1", 5);
    });
    cleanup();
    setup(unassigned, ["operator"]);
    await form();
    expect(screen.queryByRole("button", { name: "Take" })).toBeNull();
    cleanup();
    setup(inquiry(), ["admin"]);
    await form();
    expect(screen.queryByRole("button", { name: "Take" })).toBeNull();
  });

  it("[B3-R13] Select suppliers opens the supplier screen, in the states that accept RFQs only", async () => {
    setup(inquiry(), ["bunker_buyer"]);
    await form();
    await userEvent.click(screen.getByRole("button", { name: "Select suppliers" }));
    expect(window.location.hash).toBe("#/inquiries/i1/suppliers");
    cleanup();
    setup(inquiry({ status: "nominated" }), ["bunker_buyer"]);
    await form();
    expect(screen.queryByRole("button", { name: "Select suppliers" })).toBeNull();
    cleanup();
    setup(inquiry(), ["operator"]);
    await form();
    expect(screen.queryByRole("button", { name: "Select suppliers" })).toBeNull();
  });

  it("[B3-R13] the RFQs link opens the log for readers, and for writers even before any RFQ", async () => {
    const link = () => screen.queryByRole("link", { name: "RFQs" });
    setup(inquiry({ rfq_total: 2, rfq_sent: 1 }), ["viewer"]);
    await form();
    expect(link()?.getAttribute("href")).toBe("#/inquiries/i1/rfqs");
    cleanup();
    setup(inquiry({ rfq_total: 0 }), ["viewer"]);
    await form();
    expect(link()).toBeNull(); // nothing to read yet
    cleanup();
    setup(inquiry({ rfq_total: 0 }), ["bunker_buyer"]);
    await form();
    expect(link()?.getAttribute("href")).toBe("#/inquiries/i1/rfqs");
    cleanup();
    setup(inquiry({ rfq_total: 0 }), ["admin"]);
    await form();
    expect(link()).toBeTruthy();
    cleanup();
    setup(inquiry({ rfq_total: null, rfq_sent: null }), ["operator"]);
    await form();
    expect(link()).toBeNull();
  });

  it("[B3-R13] the fields that go into the RFQ text say so; internal comments stay internal", async () => {
    setup(twoLines());
    await form();
    // Spec notes of 2 lines and the agent name; the agent e-mail is not in the RFQ text.
    expect(screen.getAllByText("Sent to suppliers in the RFQ")).toHaveLength(3);
    expect(screen.getByText("Internal — never sent to suppliers")).toBeTruthy();
  });

  it("[B2-R11] shows the history, with actors named when known", async () => {
    setup();
    await form();
    const history = within(screen.getByRole("region", { name: "History" }));
    expect(await history.findByText("Olga Operator")).toBeTruthy();
  });

  it("[B2-R13] Create sends the full body and opens the new inquiry", async () => {
    const api = setup("new", ["bunker_buyer"], {
      createInquiry: vi.fn().mockResolvedValue(inquiry({ id: "i9" })),
    });
    await form();
    await pick("Vessel", "Northern Star");
    await pick("Port", "Rotterdam");
    fireEvent.change(screen.getByLabelText(/^ETA/), { target: { value: "2026-11-12T06:00" } });
    fireEvent.change(screen.getByLabelText(/^ETD/), { target: { value: "2026-11-13T06:00" } });
    await pick("Bunkering reason", "Regular bunkering");
    await pick("Product", "LNG", line(1));
    await userEvent.type(line(1).getByLabelText(/^Quantity/), "120.5");
    await pick("ISO spec version", "ISO 8217:2024", line(1));
    await userEvent.click(screen.getByRole("button", { name: "Create inquiry" }));
    await waitFor(() => {
      expect(window.location.hash).toBe("#/inquiries/i9");
    });
    expect(api.createInquiry).toHaveBeenCalledWith({
      vessel_id: "v1",
      legal_entity_id: "le1",
      operator_id: "op1",
      port_id: "p1",
      eta: "2026-11-12T06:00:00.000Z",
      etd: "2026-11-13T06:00:00.000Z",
      bunkering_reason_id: "br1",
      voyage: null,
      agent_name: null,
      agent_email: null,
      internal_comments: null,
      lines: [
        {
          product_id: "pr3",
          quantity: "120.5",
          unit: "m3", // taken from the product's default unit
          density: null,
          spec_notes: null,
          iso_spec_version_id: "iso1",
        },
      ],
    });
  });
});

describe("InquiryPage lines", () => {
  it("[B2-R09] density shows only for m3, switching to mt clears it (Review Focus 3)", async () => {
    const [first] = inquiry().lines;
    if (!first) throw new Error("fixture has no line");
    const api = setup(
      inquiry({ lines: [{ ...first, unit: "m3", density: "850.5", not_in_total: false }] }),
    );
    await form();
    expect(line(1).getByLabelText<HTMLInputElement>(/^Density/).value).toBe("850.5");
    await pick("Unit", "mt", line(1));
    expect(line(1).queryByLabelText(/^Density/)).toBeNull();
    // Back to m3: the field returns empty, not with the old value.
    await pick("Unit", "m³", line(1));
    expect(line(1).getByLabelText<HTMLInputElement>(/^Density/).value).toBe("");
    await pick("Unit", "mt", line(1));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(api.patchInquiry).toHaveBeenCalled();
    });
    const sent = vi.mocked(api.patchInquiry).mock.calls[0]?.[2] as {
      lines: { unit: string; density: unknown }[];
    };
    expect(sent.lines[0]).toMatchObject({ unit: "mt", density: null });
  });

  it("[B2-R09] an m3 line without density is marked not in total", async () => {
    const [first] = inquiry().lines;
    if (!first) throw new Error("fixture has no line");
    setup(inquiry({ lines: [{ ...first, unit: "m3", density: null, not_in_total: true }] }));
    await form();
    expect(line(1).getByText("Not in total until density is given")).toBeTruthy();
    await userEvent.type(line(1).getByLabelText(/^Density/), "850");
    expect(line(1).queryByText("Not in total until density is given")).toBeNull();
  });

  it("[B2-R13] lines can be added and removed, up to 10", async () => {
    setup();
    await form();
    expect(line(1).queryByRole("button", { name: /^Remove line/ })).toBeNull(); // the last line stays
    for (let n = 2; n <= 10; n++) {
      await userEvent.click(screen.getByRole("button", { name: "Add line" }));
    }
    expect(screen.getAllByRole("group", { name: /^Line \d+$/ })).toHaveLength(10);
    expect(screen.getByRole("button", { name: "Add line" })).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("button", { name: "Remove line 10" }));
    expect(screen.getAllByRole("group", { name: /^Line \d+$/ })).toHaveLength(9);
  });

  it("[B2-R10] a not-approved-fuel warning shows on the line it belongs to", async () => {
    setup(
      inquiry({
        ...twoLines(),
        warnings: [
          {
            field: "lines[1].product_id",
            code: "not_approved_fuel",
            message: "Not an approved fuel for this vessel",
          },
        ],
      }),
    );
    await form();
    expect(line(2).getByText("Not an approved fuel for this vessel")).toBeTruthy();
    expect(line(1).queryByText("Not an approved fuel for this vessel")).toBeNull();
  });

  it("[B2-R10] warnings of the saved vessel disappear once the vessel changes", async () => {
    setup(
      inquiry({
        warnings: [
          { field: "lines[0].product_id", code: "not_approved_fuel", message: "Not approved" },
        ],
      }),
    );
    await form();
    expect(screen.getByText("Not approved")).toBeTruthy();
    await pick("Vessel", "Harbour Light");
    expect(screen.queryByText("Not approved")).toBeNull();
  });

  it("[B2-R13] the internal comments section is marked internal", async () => {
    setup();
    await form();
    expect(screen.getByRole("region", { name: "Internal — never sent to suppliers" })).toBeTruthy();
  });
});
