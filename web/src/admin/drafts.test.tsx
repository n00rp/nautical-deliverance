import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { MasterType } from "../masterApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { configFor } from "./configs";
import { MasterDataPage } from "./MasterDataPage";
import { fakeApi, rec } from "./testSupport";

const seed = () => ({
  vessels: [
    rec("v1", {
      name: "Seed Vessel",
      imo: "9074729",
      vessel_type: "Tanker",
      dwt: 50000,
      flag: "Malta",
      legal_entity_id: "le1",
    }),
  ],
  "legal-entities": [rec("le1", { name: "Seed Entity", code: "SE" })],
  ports: [
    rec("p1", { locode: "NLRTM", name: "Seed Port", country: "NL", time_zone: "Europe/Amsterdam" }),
    rec("p2", { locode: "SGSIN", name: "Other Port", country: "SG", time_zone: "Asia/Singapore" }),
  ],
  counterparties: [rec("cp1", { name: "Seed Counterparty", type: "trader", notes: null })],
  products: [
    rec("pr1", { name: "Seed Product", default_unit: "mt" }),
    rec("pr2", { name: "Other Product", default_unit: "m3" }),
  ],
});

const NAMES: Partial<Record<MasterType, string>> = {
  counterparties: "Seed Counterparty",
  vessels: "Seed Vessel",
  products: "Seed Product",
};

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
const nameField = () => details().getByLabelText<HTMLInputElement>(/^Name\b/);
const CELL = "Seed Port – Seed Product";

async function openCounterparty(api = fakeApi(seed(), { "counterparties/cp1/coverage": [] })) {
  setup("counterparties", ["admin"], api);
  await userEvent.click(await screen.findByRole("cell", { name: "Seed Counterparty" }));
  const coverage = within(await screen.findByRole("region", { name: "Coverage" }));
  await coverage.findByRole("checkbox", { name: CELL });
  const updated = () =>
    waitFor(() => {
      const history = within(screen.getByRole("region", { name: "History" }));
      expect(history.getAllByText(/\bupdated\b/).length).toBeGreaterThan(0);
    });
  return { api, coverage, updated };
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
  window.location.hash = "";
});

describe("drafts, sets and focus", () => {
  it("[B1-R11] saving coverage keeps an unsaved Details draft", async () => {
    const { coverage, updated } = await openCounterparty();
    const name = nameField();
    await userEvent.type(name, "!");
    await userEvent.click(coverage.getByRole("checkbox", { name: CELL }));
    await userEvent.click(coverage.getByRole("button", { name: "Save coverage" }));
    await screen.findByText("Coverage saved");
    await updated();
    expect(nameField()).toBe(name);
    expect(name.value).toBe("Seed Counterparty!");
    // The draft still saves with the latest version: no conflict.
    await userEvent.click(details().getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("cell", { name: "Seed Counterparty!" })).toBeTruthy();
  });

  it("[B1-R11] saving Details keeps unsaved coverage ticks", async () => {
    const { api, coverage, updated } = await openCounterparty();
    const getSet = vi.spyOn(api, "getSet");
    await userEvent.click(coverage.getByRole("checkbox", { name: CELL }));
    await userEvent.type(nameField(), "!");
    await userEvent.click(details().getByRole("button", { name: "Save" }));
    await screen.findByText("Saved");
    await updated();
    expect(coverage.getByRole<HTMLInputElement>("checkbox", { name: CELL }).checked).toBe(true);
    expect(getSet).not.toHaveBeenCalled();
    await userEvent.click(coverage.getByRole("button", { name: "Save coverage" }));
    await screen.findByText("Coverage saved");
  });

  it("[B1-R11] set Save is disabled until the set has loaded", async () => {
    const api = fakeApi(seed(), { "counterparties/cp1/coverage": [] });
    vi.spyOn(api, "getSet").mockReturnValueOnce(new Promise(() => undefined));
    setup("counterparties", ["admin"], api);
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Counterparty" }));
    const coverage = within(await screen.findByRole("region", { name: "Coverage" }));
    await userEvent.click(await coverage.findByRole("checkbox", { name: CELL }));
    const save = coverage.getByRole<HTMLButtonElement>("button", { name: "Save coverage" });
    expect(save.disabled).toBe(true);
    const put = vi.spyOn(api, "putSet");
    await userEvent.click(save);
    expect(put).not.toHaveBeenCalled();
  });

  it("[B1-R11] set Save needs a change and is disabled again after saving", async () => {
    const { coverage } = await openCounterparty();
    const save = () => coverage.getByRole<HTMLButtonElement>("button", { name: "Save coverage" });
    expect(save().disabled).toBe(true);
    await userEvent.click(coverage.getByRole("checkbox", { name: CELL }));
    expect(save().disabled).toBe(false);
    await userEvent.click(save());
    await screen.findByText("Coverage saved");
    await waitFor(() => {
      expect(save().disabled).toBe(true);
    });
  });

  it("[B1-R11] saving coverage carries through entries on inactive ports and products", async () => {
    const data = seed();
    Object.assign(data.products[1] as object, { active: false });
    Object.assign(data.ports[1] as object, { active: false });
    const api = fakeApi(data, {
      "counterparties/cp1/coverage": [
        { port_id: "p1", product_id: "pr2" },
        { port_id: "p2", product_id: "pr1" },
      ],
    });
    const { coverage } = await openCounterparty(api);
    await userEvent.click(coverage.getByRole("checkbox", { name: CELL }));
    await userEvent.click(coverage.getByRole("button", { name: "Save coverage" }));
    await screen.findByText("Coverage saved");
    const items = api.sets.get("counterparties/cp1/coverage")?.items ?? [];
    expect(items).toHaveLength(3);
    expect(items).toEqual(
      expect.arrayContaining([
        { port_id: "p1", product_id: "pr1" },
        { port_id: "p1", product_id: "pr2" },
        { port_id: "p2", product_id: "pr1" },
      ]),
    );
  });

  it("[B1-R11] after creating a record focus moves into its form", async () => {
    setup("products");
    await userEvent.click(await screen.findByRole("button", { name: "New product" }));
    await userEvent.type(nameField(), "Fresh");
    await userEvent.click(details().getByRole("button", { name: "Create" }));
    await waitFor(() => {
      const form = screen.getByRole("form", { name: "Details" });
      expect(nameField().value).toBe("Fresh");
      expect(form.contains(document.activeElement)).toBe(true);
    });
  });

  it("[B1-R11] saving Details keeps the form mounted", async () => {
    setup("products");
    await userEvent.click(await screen.findByRole("cell", { name: "Seed Product" }));
    const name = await waitFor(() => {
      expect(nameField().value).toBe("Seed Product");
      return nameField();
    });
    await userEvent.type(name, "!");
    await userEvent.click(details().getByRole("button", { name: "Save" }));
    await screen.findByRole("cell", { name: "Seed Product!" });
    expect(nameField()).toBe(name);
  });

  it("[B1-R11] the locked note clears when the roles change", async () => {
    const api = fakeApi(seed());
    vi.spyOn(api, "create").mockRejectedValueOnce(new ApiError(403));
    window.location.hash = "#/admin/products";
    const page = (roles: Role[]) => (
      <ToastProvider>
        <MasterDataPage config={configFor("products")} api={api} roles={roles} />
      </ToastProvider>
    );
    const { rerender } = render(page(["admin"]));
    await userEvent.click(await screen.findByRole("button", { name: "New product" }));
    await userEvent.type(nameField(), "Fresh");
    await userEvent.click(details().getByRole("button", { name: "Create" }));
    await screen.findByText(/Hidden for your role: saving changes/);
    rerender(page(["admin", "operator"]));
    expect(await screen.findByRole("button", { name: "Create" })).toBeTruthy();
  });

  it.each([
    ["counterparties", "Coverage"],
    ["vessels", "Approved fuels"],
  ] as const)(
    "[B1-R11] non-admins get disabled %s checkboxes and no Save",
    async (path, region) => {
      setup(path, ["viewer"]);
      await userEvent.click(await screen.findByRole("cell", { name: NAMES[path] ?? "" }));
      const set = within(await screen.findByRole("region", { name: region }));
      const boxes = await set.findAllByRole<HTMLInputElement>("checkbox");
      expect(boxes.every((b) => b.disabled)).toBe(true);
      expect(set.queryByRole("button", { name: /^Save/ })).toBeNull();
    },
  );
});
