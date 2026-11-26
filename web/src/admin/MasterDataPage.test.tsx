import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { MasterType } from "../masterApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import type { Role } from "../ui/RoleGate/RoleGate";
import { configFor, MASTER_CONFIGS } from "./configs";
import { MasterDataPage } from "./MasterDataPage";
import { fakeApi, rec } from "./testSupport";

const SEED_NAME: Record<MasterType, string> = {
  "legal-entities": "Seed Entity",
  vessels: "Seed Vessel",
  ports: "Seed Port",
  counterparties: "Seed Counterparty",
  products: "Seed Product",
  "iso-spec-versions": "Seed Iso",
  "bunkering-reasons": "Seed Reason",
};

const seed = () => ({
  "legal-entities": [rec("le1", { name: "Seed Entity", code: "SE" })],
  vessels: [
    rec("v1", {
      name: "Seed Vessel",
      imo: "9074729",
      vessel_type: "Tanker",
      dwt: 50000,
      flag: "Malta",
      default_operator_name: "Seed Operator",
      legal_entity_id: "le1",
    }),
  ],
  ports: [
    rec("p1", { locode: "NLRTM", name: "Seed Port", country: "NL", time_zone: "Europe/Amsterdam" }),
    rec("p2", { locode: "SGSIN", name: "Other Port", country: "SG", time_zone: "Asia/Singapore" }),
  ],
  counterparties: [rec("cp1", { name: "Seed Counterparty", type: "trader", notes: null })],
  products: [
    rec("pr1", { name: "Seed Product", default_unit: "mt" }),
    rec("pr2", { name: "Other Product", default_unit: "m3" }),
  ],
  "iso-spec-versions": [rec("i1", { name: "Seed Iso" })],
  "bunkering-reasons": [rec("r1", { name: "Seed Reason" })],
});

function setup(path: MasterType, roles: Role[] = ["admin"], api = fakeApi(seed())) {
  window.location.hash = `#/admin/${path}`;
  render(
    <ToastProvider>
      <MasterDataPage config={configFor(path)} api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
  return api;
}

const details = () => within(screen.getByRole("form", { name: "Details" }));
const label = (text: string) => new RegExp(`^${text}\\b`);

async function fillAll(path: MasterType) {
  for (const f of configFor(path).fields) {
    if (f.kind === "select" && !f.default) {
      await userEvent.click(details().getByRole("combobox", { name: label(f.label) }));
      await userEvent.click((await screen.findAllByRole("option"))[0] as HTMLElement);
    } else if (f.kind === "text" || f.kind === "int") {
      const text = f.key === "name" ? "Created thing" : f.kind === "int" ? "1000" : `x${f.key}`;
      await userEvent.type(details().getByLabelText(label(f.label)), text);
    }
  }
}

beforeAll(() => {
  // jsdom lacks the pointer/scroll APIs Radix Select uses.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  window.location.hash = "";
});

describe.each(MASTER_CONFIGS)("$title page", ({ path, singular }) => {
  it("[B1-R11] lists, creates, edits, deactivates, reactivates and shows history", async () => {
    setup(path);
    expect(await screen.findByRole("cell", { name: SEED_NAME[path] })).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: `New ${singular}` }));
    await fillAll(path);
    await userEvent.click(details().getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("cell", { name: "Created thing" })).toBeTruthy();

    const name = await waitFor(() => {
      const el = details().getByLabelText<HTMLInputElement>(label("Name"));
      expect(el.value).toBe("Created thing");
      return el;
    });
    await userEvent.clear(name);
    await userEvent.type(name, "Renamed");
    await userEvent.click(details().getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("cell", { name: "Renamed" })).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => {
      expect(screen.queryByRole("cell", { name: "Renamed" })).toBeNull();
    });
    await userEvent.click(await screen.findByRole("button", { name: "Reactivate" }));
    expect(await screen.findByRole("cell", { name: "Renamed" })).toBeTruthy();

    const history = within(await screen.findByRole("region", { name: "History" }));
    for (const verb of [/\bcreated\b/, /\bupdated\b/, /\bdeactivated\b/, /\breactivated\b/]) {
      await waitFor(() => {
        expect(history.getAllByText(verb).length).toBeGreaterThan(0);
      });
    }
  });

  it("[B1-R11] non-admin roles see the record read-only without edit controls", async () => {
    setup(path, ["viewer"]);
    await userEvent.click(await screen.findByRole("cell", { name: SEED_NAME[path] }));
    await screen.findByRole("form", { name: "Details" });

    expect(screen.queryByRole("button", { name: `New ${singular}` })).toBeNull();
    for (const b of [
      "Save",
      "Create",
      "Deactivate",
      "Reactivate",
      "Save coverage",
      "Add contact",
    ]) {
      expect(screen.queryByRole("button", { name: b })).toBeNull();
    }
    for (const input of details().getAllByRole("textbox")) {
      expect((input as HTMLInputElement).disabled).toBe(true);
    }
    expect(screen.getAllByText(/Hidden for your role/).length).toBeGreaterThan(0);
  });
});

describe("master-data pages", () => {
  it("[B1-R11] an empty list shows an EmptyState", async () => {
    setup("products", ["admin"], fakeApi());
    expect(await screen.findByText("No products yet")).toBeTruthy();
  });

  it("[B1-R11] filter shows inactive records and search narrows the list", async () => {
    const api = fakeApi(seed());
    await api.setActive("products", "pr2", 1, false);
    setup("products", ["admin"], api);
    await screen.findByRole("cell", { name: "Seed Product" });
    expect(screen.queryByRole("cell", { name: "Other Product" })).toBeNull();

    await userEvent.click(screen.getByRole("combobox", { name: "Show" }));
    await userEvent.click(await screen.findByRole("option", { name: "All" }));
    expect(await screen.findByRole("cell", { name: "Other Product" })).toBeTruthy();

    await userEvent.type(screen.getByLabelText("Search"), "Other");
    await waitFor(() => {
      expect(screen.queryByRole("cell", { name: "Seed Product" })).toBeNull();
    });
  });

  it("[B1-R11] the counterparty page edits contacts and the coverage matrix", async () => {
    const api = setup("counterparties");
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Counterparty" }));

    const contactForm = within(await screen.findByRole("form", { name: "Contact" }));
    await userEvent.type(contactForm.getByLabelText(label("Name")), "Ann");
    await userEvent.type(contactForm.getByLabelText(label("E-mail")), "ann@alpha.example");
    await userEvent.click(contactForm.getByRole("button", { name: "Add contact" }));
    const contacts = within(await screen.findByRole("region", { name: "Contacts" }));
    expect(await contacts.findByRole("cell", { name: "ann@alpha.example" })).toBeTruthy();

    await userEvent.click(contacts.getByRole("button", { name: "Edit" }));
    const edit = within(screen.getByRole("form", { name: "Contact" }));
    await userEvent.type(edit.getByLabelText(label("Name")), "e");
    await userEvent.click(edit.getByRole("button", { name: "Save contact" }));
    expect(await contacts.findByRole("cell", { name: "Anne" })).toBeTruthy();

    await userEvent.click(contacts.getByRole("button", { name: "Deactivate" }));
    await userEvent.click(contacts.getByRole("button", { name: "Confirm deactivate" }));
    expect(await contacts.findByText("Inactive")).toBeTruthy();
    await userEvent.click(contacts.getByRole("button", { name: "Reactivate" }));
    await waitFor(() => {
      expect(contacts.queryByText("Inactive")).toBeNull();
    });

    const coverage = within(await screen.findByRole("region", { name: "Coverage" }));
    await userEvent.click(
      await coverage.findByRole("checkbox", { name: "Seed Port – Seed Product" }),
    );
    await userEvent.click(coverage.getByRole("checkbox", { name: "Other Port – Other Product" }));
    await userEvent.click(coverage.getByRole("button", { name: "Save coverage" }));
    await waitFor(() => {
      expect(api.sets.get("counterparties/cp1/coverage")?.items).toEqual([
        { port_id: "p1", product_id: "pr1" },
        { port_id: "p2", product_id: "pr2" },
      ]);
    });
    // Saving the set bumped the counterparty version; a following save must not conflict.
    const name = details().getByLabelText<HTMLInputElement>(label("Name"));
    await userEvent.type(name, "!");
    await userEvent.click(details().getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("cell", { name: "Seed Counterparty!" })).toBeTruthy();
  });

  it("[B1-R11] the vessel page edits approved fuels", async () => {
    const api = setup("vessels");
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Vessel" }));
    const fuels = within(await screen.findByRole("region", { name: "Approved fuels" }));
    await userEvent.click(await fuels.findByRole("checkbox", { name: "Seed Product" }));
    await userEvent.click(fuels.getByRole("button", { name: "Save approved fuels" }));
    await waitFor(() => {
      expect(api.sets.get("vessels/v1/approved-fuels")?.items).toEqual([{ product_id: "pr1" }]);
    });
  });

  it("[B1-R11] a 409 conflict explains itself and reloads the latest record", async () => {
    const api = setup("counterparties");
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Counterparty" }));
    const name = await waitFor(() => {
      const el = details().getByLabelText<HTMLInputElement>(label("Name"));
      expect(el.value).toBe("Seed Counterparty");
      return el;
    });
    vi.spyOn(api, "update").mockImplementationOnce(() => {
      Object.assign(api.rows("counterparties")[0] as object, {
        name: "Changed elsewhere",
        version: 2,
      });
      return Promise.reject(new ApiError(409));
    });
    await userEvent.type(name, "!");
    await userEvent.click(details().getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Record was changed by someone else — reloaded the latest version"),
    ).toBeTruthy();
    await waitFor(() => {
      expect(details().getByLabelText<HTMLInputElement>(label("Name")).value).toBe(
        "Changed elsewhere",
      );
    });
    expect(await screen.findByRole("cell", { name: "Changed elsewhere" })).toBeTruthy();
  });

  it("[B1-R11] after a contact 409 the form carries the fresh version, so the next save works", async () => {
    const api = fakeApi(seed(), {}, [
      rec("k1", { name: "Ann", email: "ann@alpha.example", phone: null, is_primary: false }),
    ]);
    setup("counterparties", ["admin"], api);
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Counterparty" }));
    const contacts = within(await screen.findByRole("region", { name: "Contacts" }));
    await userEvent.click(await contacts.findByRole("button", { name: "Edit" }));
    const form = () => within(screen.getByRole("form", { name: "Contact" }));
    const spy = vi.spyOn(api, "updateContact");
    spy.mockImplementationOnce(() => {
      Object.assign(api.contactsNow[0] as object, { name: "Changed elsewhere", version: 2 });
      return Promise.reject(new ApiError(409));
    });
    await userEvent.type(form().getByLabelText(label("Name")), "!");
    await userEvent.click(form().getByRole("button", { name: "Save contact" }));

    await waitFor(() => {
      expect(form().getByLabelText<HTMLInputElement>(label("Name")).value).toBe(
        "Changed elsewhere",
      );
    });
    await userEvent.type(form().getByLabelText(label("Name")), "!");
    await userEvent.click(form().getByRole("button", { name: "Save contact" }));
    expect(await contacts.findByRole("cell", { name: "Changed elsewhere!" })).toBeTruthy();
    expect(spy).toHaveBeenLastCalledWith("cp1", "k1", 2, expect.anything());
  });

  it("[B7a-R04] vessel admin edits Default operator", async () => {
    const api = setup("vessels");
    const update = vi.spyOn(api, "update");
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Vessel" }));
    const field = await waitFor(() =>
      details().getByLabelText<HTMLInputElement>(label("Default operator")),
    );
    expect(field.value).toBe("Seed Operator");
    await userEvent.clear(field);
    await userEvent.type(field, "New Ops Ltd");
    await userEvent.click(details().getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(
        "vessels",
        "v1",
        1,
        expect.objectContaining({ default_operator_name: "New Ops Ltd" }),
      );
    });
  });

  it("[B1-R11] a 422 on a set save shows the server's message", async () => {
    const api = setup("vessels");
    vi.spyOn(api, "putSet").mockRejectedValueOnce(
      new ApiError(422, [{ field: "items", message: "Unknown product" }]),
    );
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Vessel" }));
    const fuels = within(await screen.findByRole("region", { name: "Approved fuels" }));
    await userEvent.click(await fuels.findByRole("checkbox", { name: "Seed Product" }));
    await userEvent.click(fuels.getByRole("button", { name: "Save approved fuels" }));
    expect(await screen.findByText("Unknown product")).toBeTruthy();
  });

  it("[B1-R11] a 422 shows field errors on the field and in the summary", async () => {
    const api = setup("ports");
    vi.spyOn(api, "create").mockRejectedValueOnce(
      new ApiError(422, [{ field: "locode", message: "LOCODE already exists" }]),
    );
    await userEvent.click(await screen.findByRole("button", { name: "New port" }));
    await fillAll("ports");
    await userEvent.click(details().getByRole("button", { name: "Create" }));

    expect((await screen.findAllByText("LOCODE already exists")).length).toBe(2);
    expect(details().getByLabelText(label("UN/LOCODE")).getAttribute("aria-invalid")).toBe("true");
  });

  it("[B1-R11] a 403 on save shows the locked note", async () => {
    const api = setup("products");
    vi.spyOn(api, "create").mockRejectedValueOnce(new ApiError(403));
    await userEvent.click(await screen.findByRole("button", { name: "New product" }));
    await fillAll("products");
    await userEvent.click(details().getByRole("button", { name: "Create" }));
    expect(await screen.findByText(/Hidden for your role: saving changes/)).toBeTruthy();
  });

  it("[B1-R11] other failures show an error toast", async () => {
    const api = setup("products");
    vi.spyOn(api, "create").mockRejectedValueOnce(new Error("boom"));
    await userEvent.click(await screen.findByRole("button", { name: "New product" }));
    await fillAll("products");
    await userEvent.click(details().getByRole("button", { name: "Create" }));
    expect(await screen.findByText("boom")).toBeTruthy();
  });

  it("[B1-R11] a failing lifecycle call is explained and the panel can be closed", async () => {
    const api = setup("products");
    vi.spyOn(api, "setActive").mockRejectedValueOnce(new ApiError(403));
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Product" }));
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText(/not allowed to change/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("form", { name: "Details" })).toBeNull();
    expect(window.location.hash).toBe("#/admin/products");
  });

  it("[B1-R08] the port page shows the current local time of each port", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-05T12:00:00Z"));
    setup("ports");
    expect(await screen.findByText("05 Nov 12:00 UTC · 20:00 local")).toBeTruthy();
    expect(screen.getByText("05 Nov 12:00 UTC · 13:00 local")).toBeTruthy();

    await userEvent.click(screen.getByRole("cell", { name: "Other Port" }));
    const zone = await waitFor(() => {
      const el = details().getByLabelText<HTMLInputElement>(label("Time zone"));
      expect(el.value).toBe("Asia/Singapore");
      return el;
    });
    expect(screen.getAllByText("05 Nov 12:00 UTC · 20:00 local").length).toBe(2);

    await userEvent.clear(zone);
    await userEvent.type(zone, "Not/AZone");
    expect(screen.getAllByText(/ local$/).length).toBe(2); // only the two table rows
  });

  it("[B1-R11] vessels list the legal entity by name", async () => {
    setup("vessels");
    expect(await screen.findByRole("cell", { name: "Seed Entity" })).toBeTruthy();
  });
});
