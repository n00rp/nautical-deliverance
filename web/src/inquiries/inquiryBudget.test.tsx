import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { parseInquiries, useHash } from "../admin/routes";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { InquiryPage } from "./InquiryPage";
import { inquiryApi, master } from "./pageSupport";
import { WorkList } from "./WorkList";

beforeAll(() => {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});
afterEach(() => {
  cleanup();
  window.location.hash = "";
});

const base = inquiryApi();
const api = { ...base, createInquiry: vi.fn(base.createInquiry) };

function Routes() {
  const route = parseInquiries(useHash());
  return route?.id ? (
    <InquiryPage key={route.id} id={route.id} api={api} master={master} roles={["bunker_buyer"]} />
  ) : (
    <WorkList api={api} roles={["bunker_buyer"]} />
  );
}

describe("step budget", () => {
  it("[B2-R13] creating an inquiry with two product lines from the work list takes at most 25 interactions", async () => {
    render(
      <ToastProvider>
        <Routes />
        <ToastHost />
      </ToastProvider>,
    );

    // Every click and every field entry (one entry fills a whole field) is one step.
    let steps = 0;
    const click = async (el: HTMLElement) => {
      steps += 1;
      await userEvent.click(el);
    };
    const choose = async (el: HTMLElement, option: string) => {
      await click(el);
      await click(await screen.findByRole("option", { name: option }));
    };
    const enter = (el: HTMLElement, value: string) => {
      steps += 1;
      fireEvent.change(el, { target: { value } });
    };
    const type = async (el: HTMLElement, text: string) => {
      steps += 1;
      await userEvent.type(el, text);
    };
    const line = (n: number) => within(screen.getByRole("group", { name: `Line ${String(n)}` }));
    const fillLine = async (n: number, product: string, quantity: string) => {
      await choose(line(n).getByRole("combobox", { name: "Product" }), product);
      await type(line(n).getByLabelText(/^Quantity/), quantity);
      await choose(line(n).getByRole("combobox", { name: "ISO spec version" }), "ISO 8217:2024");
    };

    await click(await screen.findByRole("button", { name: "New inquiry" }));
    await screen.findByRole("form", { name: "Inquiry" });
    await choose(screen.getByRole("combobox", { name: "Vessel" }), "Northern Star");
    await choose(screen.getByRole("combobox", { name: "Port" }), "Rotterdam");
    enter(screen.getByLabelText(/^ETA/), "2026-11-12T06:00");
    enter(screen.getByLabelText(/^ETD/), "2026-11-13T06:00");
    await choose(screen.getByRole("combobox", { name: "Bunkering reason" }), "Regular bunkering");
    await fillLine(1, "VLSFO 0.5%", "500");
    await click(screen.getByRole("button", { name: "Add line" }));
    await fillLine(2, "MGO 0.1%", "120");
    await click(screen.getByRole("button", { name: "Create inquiry" }));

    await waitFor(() => {
      expect(api.createInquiry).toHaveBeenCalledTimes(1);
    });
    const body = api.createInquiry.mock.calls[0]?.[0] as { lines: unknown[] };
    expect(body.lines).toHaveLength(2);
    // Documented count: New inquiry (1), vessel (2), port (2), ETA, ETD (2), reason (2),
    // line 1: product (2), quantity, ISO version (2), Add line, line 2 (5), Create inquiry.
    expect(steps).toBe(21);
    expect(steps).toBeLessThanOrEqual(25);
  });
});
