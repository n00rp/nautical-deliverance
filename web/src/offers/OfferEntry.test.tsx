import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { OfferApi } from "../offerApi";
import { declinedRfq } from "../rfqs/testSupport";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { OfferEntry, type OfferEntryProps } from "./OfferEntry";
import { entryApi, m3Lines, mtLines, savedOffer } from "./testSupport";

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
  vi.restoreAllMocks();
});

function setup(api: OfferEntryProps["api"], roles: Role[] = ["bunker_buyer"], rfqId = "r1") {
  render(
    <ToastProvider>
      <OfferEntry inquiryId="i1" rfqId={rfqId} api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
}

const create = () => vi.fn<OfferApi["createOffer"]>().mockResolvedValue(savedOffer);
const patch = () => vi.fn<OfferApi["patchOffer"]>().mockResolvedValue(savedOffer);
const field = (name: string | RegExp) => screen.findByLabelText(name);
const VLSFO = "VLSFO 0.5% — 500 mt";
const MGO = "MGO 0.1% — 100 mt";

describe("OfferEntry", () => {
  it("[B4-R12] live line costs and total update, with a Partial note until every line is priced", async () => {
    setup(entryApi(mtLines));
    expect(await screen.findByText("USD 0.00")).toBeTruthy();
    expect(screen.getByText("Partial")).toBeTruthy();

    await userEvent.type(await field(VLSFO), "612.345");
    expect(screen.getByText("500.000 mt = USD 306,172.50")).toBeTruthy();
    expect(screen.getByText("USD 306,172.50")).toBeTruthy();
    expect(screen.getByText("Partial")).toBeTruthy();

    await userEvent.type(await field(MGO), "845.5");
    await userEvent.type(await field("Barging"), "1200");
    expect(screen.getByText("USD 391,922.50")).toBeTruthy();
    expect(screen.queryByText("Partial")).toBeNull();
  });

  it("[B4-R12] a density field appears only on an m3 line whose inquiry gave none (B4-D6)", async () => {
    setup(entryApi(m3Lines));
    await field("Density for LNG");
    expect(screen.queryByLabelText("Density for VLSFO 0.5%")).toBeNull();
    expect(screen.queryByLabelText("Density for Bio LNG")).toBeNull();
    expect(screen.getByText("Needs a density")).toBeTruthy();

    // 120 m3 x 850.0 kg/m3 / 1000 = 102.000 mt, then the density makes the line count.
    await userEvent.type(screen.getByLabelText("LNG — 120 m3"), "845.5");
    await userEvent.type(screen.getByLabelText("Density for LNG"), "850");
    expect(screen.getByText("102.000 mt = USD 86,241.00")).toBeTruthy();
  });

  it("[B4-R12] a total over the limit says so instead of showing a number", async () => {
    const huge = [{ ...mtLines[0]!, quantity: "999999999.999" }];
    setup(entryApi(huge));
    await userEvent.type(await field("VLSFO 0.5% — 999999999.999 mt"), "99999.999");
    expect((await screen.findByRole("alert")).textContent).toBe("total too large");
  });

  it("[B4-R12] 422 errors from the engine land on their fields", async () => {
    const api = {
      ...entryApi(mtLines),
      createOffer: vi.fn<OfferApi["createOffer"]>().mockRejectedValue(
        new ApiError(422, [
          { field: "lines[1].price_per_mt", message: "Must be a positive price" },
          { field: "valid_until", message: "Must be in the future" },
          { field: "barging_cost", message: "Too many decimals" },
        ]),
      ),
    };
    setup(api);
    await userEvent.type(await field(VLSFO), "612.345");
    await userEvent.type(await field(MGO), "0");
    await userEvent.type(await field("Barging"), "1");
    fireEvent.change(await field(/^Valid until/), { target: { value: "2020-01-01T00:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));

    await waitFor(() => {
      expect(screen.getByLabelText(MGO).getAttribute("aria-invalid")).toBe("true");
    });
    expect(screen.getByLabelText(VLSFO).getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByLabelText(/^Valid until/).getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Barging").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Must be a positive price", { selector: "p" })).toBeTruthy();
    expect(screen.getByText("3 problems to fix")).toBeTruthy();

    // Editing a field drops its own error only.
    await userEvent.type(screen.getByLabelText(MGO), "5");
    expect(screen.getByLabelText(MGO).getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByLabelText("Barging").getAttribute("aria-invalid")).toBe("true");
  });

  it("[B4-R12] a 403 on save shows a locked note", async () => {
    const api = {
      ...entryApi(mtLines),
      createOffer: vi.fn<OfferApi["createOffer"]>().mockRejectedValue(new ApiError(403)),
    };
    setup(api);
    fireEvent.change(await field(/^Valid until/), { target: { value: "2026-11-10T08:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));
    expect(await screen.findByText("Hidden for your role: saving offers")).toBeTruthy();
  });

  it("[B4-R12] an Operator has no access and nothing is requested", () => {
    const api = entryApi(mtLines);
    const spy = vi.spyOn(api, "getInquiry");
    const offer = vi.spyOn(api, "getOffer");
    setup(api, ["operator"]);
    expect(screen.getByText("Hidden for your role: offer entry")).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
    expect(offer).not.toHaveBeenCalled();
  });

  it("[B4-R12] a viewer cannot enter offers either", () => {
    setup(entryApi(mtLines), ["viewer"]);
    expect(screen.getByText("Hidden for your role: offer entry")).toBeTruthy();
  });

  it("[B4-R12] an RFQ that is not sent takes no new offer, and an unknown RFQ none at all", async () => {
    const api = { ...entryApi(mtLines), listRfqs: () => Promise.resolve([declinedRfq]) };
    setup(api, ["admin"], "r2");
    expect(await screen.findByText("No offer can be entered")).toBeTruthy();
    cleanup();
    setup(api, ["admin"], "nope");
    expect(await screen.findByText("No offer can be entered")).toBeTruthy();
  });

  it("[B4-R12] a failed load shows an error state", async () => {
    const api = { ...entryApi(mtLines), listRfqs: () => Promise.reject(new ApiError(500)) };
    setup(api);
    expect(await screen.findByText("Could not load the offer")).toBeTruthy();
  });

  it("[B4-R12] editing prefills the saved offer and patches it with its version", async () => {
    const api = {
      ...entryApi(mtLines, savedOffer),
      patchOffer: patch(),
      getOffer: vi.fn<OfferApi["getOffer"]>().mockResolvedValue(savedOffer),
    };
    setup(api);
    expect(await screen.findByText(/Edit offer from Beta Marine/)).toBeTruthy();
    expect(api.getOffer).toHaveBeenCalledWith("o1"); // by the offer id on the RFQ log item
    expect(screen.getByLabelText<HTMLInputElement>(VLSFO).value).toBe("612.345");
    expect(screen.getByLabelText<HTMLInputElement>("Barging").value).toBe("1200.00");
    expect(screen.getByText("USD 391,922.50")).toBeTruthy();

    await userEvent.clear(screen.getByLabelText(MGO));
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));

    await waitFor(() => {
      expect(api.patchOffer).toHaveBeenCalledTimes(1);
    });
    const [id, version, body] = api.patchOffer.mock.calls[0]!;
    expect([id, version]).toEqual(["o1", 3]);
    // Blank price means no offer for that line; `lines` replaces the whole set.
    expect(body.lines).toEqual([{ inquiry_line_id: "l1", price_per_mt: "612.345" }]);
    expect(body.payment_terms).toBe("30 days");
    expect(body.delivery_method).toBe("barge");
    expect(window.location.hash).toBe("#/inquiries/i1/rfqs");
  });

  it("[B4-R12] a second Save click while saving sends one request", async () => {
    let release = () => {};
    const api = {
      ...entryApi(mtLines),
      createOffer: vi.fn<OfferApi["createOffer"]>().mockImplementation(
        () =>
          new Promise((resolve) => {
            release = () => {
              resolve(savedOffer);
            };
          }),
      ),
    };
    setup(api);
    fireEvent.change(await field(/^Valid until/), { target: { value: "2026-11-10T08:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));
    fireEvent.submit(screen.getByRole("form", { name: "Offer" }));
    expect(api.createOffer).toHaveBeenCalledTimes(1);
    release();
    await waitFor(() => {
      expect(window.location.hash).toBe("#/inquiries/i1/rfqs");
    });
  });

  it("[B4-R12] a negative or invalid input is a field error and the total stays visible", async () => {
    setup(entryApi(mtLines));
    const vlsfo = await field(VLSFO);
    await userEvent.type(vlsfo, "600");
    await userEvent.type(screen.getByLabelText(MGO), "-5");
    expect(screen.getByLabelText(MGO).getAttribute("aria-invalid")).toBe("true");
    expect(screen.getAllByText("Must not be negative").length).toBeGreaterThan(0);
    expect(screen.getByText("USD 300,000.00")).toBeTruthy();
    await userEvent.type(screen.getByLabelText("Barging"), "abc");
    expect(screen.getByLabelText("Barging").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("USD 300,000.00")).toBeTruthy();
  });

  it("[B4-R12] a price field says to use a dot as decimal point", async () => {
    setup(entryApi(mtLines));
    await field(VLSFO);
    expect(screen.getAllByText(/Use '\.' as decimal point/).length).toBe(2);
  });

  it("[B4-R12] the delivery method can be cleared", async () => {
    const api = { ...entryApi(mtLines, savedOffer), patchOffer: patch() };
    setup(api);
    await userEvent.click(await screen.findByRole("combobox", { name: "Delivery method" }));
    await userEvent.click(await screen.findByRole("option", { name: "None" }));
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));
    await waitFor(() => {
      expect(api.patchOffer).toHaveBeenCalledTimes(1);
    });
    expect(api.patchOffer.mock.calls[0]![2].delivery_method).toBeNull();
  });

  it("[B4-R12] a density is sent only for the m3 line that asks for one", async () => {
    const api = { ...entryApi(m3Lines), createOffer: create() };
    setup(api);
    await userEvent.type(await field("VLSFO 0.5% — 500 mt"), "600");
    await userEvent.type(screen.getByLabelText("LNG — 120 m3"), "845.5");
    await userEvent.type(screen.getByLabelText("Density for LNG"), "850");
    await userEvent.type(screen.getByLabelText("Bio LNG — 10 m3"), "700");
    fireEvent.change(screen.getByLabelText(/^Valid until/), {
      target: { value: "2026-11-10T08:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));
    await waitFor(() => {
      expect(api.createOffer).toHaveBeenCalledTimes(1);
    });
    expect(api.createOffer.mock.calls[0]![1].lines).toEqual([
      { inquiry_line_id: "l1", price_per_mt: "600" },
      { inquiry_line_id: "l2", price_per_mt: "845.5", density: "850" },
      { inquiry_line_id: "l3", price_per_mt: "700" },
    ]);
  });
});
