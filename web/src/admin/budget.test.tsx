import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { configFor } from "./configs";
import { MasterDataPage } from "./MasterDataPage";
import { fakeApi, rec } from "./testSupport";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("step budget", () => {
  it("[B1-R11] creating a counterparty with one contact and three coverage rows takes at most 15 interactions", async () => {
    const api = fakeApi({
      ports: [
        rec("p1", {
          locode: "NLRTM",
          name: "Rotterdam",
          country: "NL",
          time_zone: "Europe/Amsterdam",
        }),
        rec("p2", {
          locode: "SGSIN",
          name: "Singapore",
          country: "SG",
          time_zone: "Asia/Singapore",
        }),
      ],
      products: [
        rec("pr1", { name: "VLSFO 0.5%", default_unit: "mt" }),
        rec("pr2", { name: "DMA 0.1%", default_unit: "mt" }),
      ],
    });
    window.location.hash = "#/admin/counterparties";
    render(
      <ToastProvider>
        <MasterDataPage config={configFor("counterparties")} api={api} roles={["admin"]} />
        <ToastHost />
      </ToastProvider>,
    );

    // Every click and every field entry (one `type` call fills a whole field) is one step.
    let steps = 0;
    const click = async (el: HTMLElement) => {
      steps += 1;
      await userEvent.click(el);
    };
    const enter = async (el: HTMLElement, text: string) => {
      steps += 1;
      await userEvent.type(el, text);
    };

    await click(await screen.findByRole("button", { name: "New counterparty" }));
    const details = within(screen.getByRole("form", { name: "Details" }));
    await enter(details.getByLabelText(/^Name\b/), "Alpha Fuels");
    await click(details.getByRole("button", { name: "Create" }));

    const contact = within(await screen.findByRole("form", { name: "Contact" }));
    await enter(contact.getByLabelText(/^Name\b/), "Ann");
    await enter(contact.getByLabelText(/^E-mail\b/), "ann@alpha.example");
    await click(contact.getByRole("button", { name: "Add contact" }));

    const coverage = within(await screen.findByRole("region", { name: "Coverage" }));
    for (const name of ["Rotterdam – VLSFO 0.5%", "Rotterdam – DMA 0.1%", "Singapore – VLSFO 0.5%"]) {
      await click(await coverage.findByRole("checkbox", { name }));
    }
    await click(coverage.getByRole("button", { name: "Save coverage" }));

    await screen.findByText("Coverage saved");
    expect([...api.sets.values()][0]?.items).toHaveLength(3);
    expect(api.contactsNow).toHaveLength(1);
    // Documented count: New, name, Create, contact name, e-mail, Add contact, 3 boxes, Save coverage.
    expect(steps).toBe(10);
    expect(steps).toBeLessThanOrEqual(15);
  });
});
